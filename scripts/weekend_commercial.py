"""Commercial path: is the weekend mispricing tradeable after costs?

The academic result is relative -- weekend variance is priced too high *relative
to* weekday variance -- so the trade that isolates it is a vega-matched calendar
spread: sell the weekend-heavy contract, buy the weekday-heavy one, delta-hedge
both. That pays spread on two legs instead of one, which is exactly why it has
to be tested against measured costs rather than assumed ones.

The absolute version (sell weekend-heavy straddles outright) is reported
alongside, but it earns the whole variance risk premium and so is not evidence
about weekends specifically.
"""
from __future__ import annotations

import argparse
import logging
import numpy as np
import pandas as pd

from dbop import config, tape, weekend, bars, greeks, costs, util

log = logging.getLogger("weekend_commercial")

MAX_T_DAYS = 7.0
MIN_T_DAYS = 0.5
DELTA_BAND = (0.35, 0.65)
# Discrete-hedging error scales with the square root of the rehedge interval,
# and on 0.5-7 day options it dominates everything else. At 8-hourly rehedging
# the P&L noise is ~150x the edge the pricing test implies, so the backtest
# cannot see the effect at any sample size we will ever have. Five-minute
# rehedging is what the bar data supports and cuts that noise by roughly 10x.
REHEDGE_MINUTES = 5


def hedged_pnl_to_expiry(entry: pd.DataFrame, px: pd.Series,
                         rehedge_minutes: int = REHEDGE_MINUTES,
                         charge_costs: bool = True,
                         half_spread_vol: float = 0.0) -> np.ndarray:
    """Delta-hedged P&L per contract of a SHORT option held to settlement, USD.

    Positive means the short position made money. The option is sold at its
    traded price, hedged in the perpetual at ``rehedge_hours`` intervals using
    the Black-76 delta at the prevailing price and the *entry* implied vol, and
    settled against the index at expiry. Hedging at the entry vol rather than a
    refitted one is deliberate: it is what a desk running this rule could
    actually do without a live surface.
    """
    n = len(entry)
    pnl = entry["premium_usd"].to_numpy(dtype="float64").copy()   # received
    K = entry["strike"].to_numpy(dtype="float64")
    cp = entry["cp_sign"].to_numpy(dtype="float64")
    sig = entry["sigma"].to_numpy(dtype="float64")
    t0 = entry["timestamp"].to_numpy(dtype="int64")
    te = entry["expiration_timestamp"].to_numpy(dtype="int64")

    idx = px.index.to_numpy(dtype="int64")          # ms
    vals = px.to_numpy(dtype="float64")

    def price_at(ms):
        pos = np.searchsorted(idx, ms, side="right") - 1
        pos = np.clip(pos, 0, len(vals) - 1)
        return vals[pos]

    step = rehedge_minutes * 60_000
    hedge = np.zeros(n)                              # perp units held
    hedge_cash = np.zeros(n)
    fees = np.zeros(n)

    S0 = price_at(t0)
    T0 = np.clip((te - t0) / (config.YEAR * 86_400_000), 1e-9, None)
    d0 = greeks.greeks(S0, K, T0, sig, cp)["delta"]
    # A short option carries delta -Delta, so the neutralizing hedge is LONG
    # Delta units of the perpetual.
    hedge = d0
    hedge_cash = -hedge * S0
    fees += costs.perp_fee_usd(hedge * S0)

    cur = t0 + step
    for _ in range(int(np.ceil((te - t0).max() / step)) + 1):
        live = cur < te
        if not live.any():
            break
        S = price_at(np.where(live, cur, t0))
        Tr = np.clip((te - cur) / (config.YEAR * 86_400_000), 1e-9, None)
        want = np.where(live, greeks.greeks(S, K, Tr, sig, cp)["delta"], hedge)
        trade = want - hedge
        hedge_cash -= trade * S
        fees += costs.perp_fee_usd(trade * S)
        hedge = want
        cur = cur + step

    ST = price_at(te)
    payoff = np.maximum(cp * (ST - K), 0.0)          # owed by the short
    pnl += hedge_cash + hedge * ST - payoff
    fees += costs.option_fee_usd(S0, entry["premium_usd"].to_numpy())
    fees += costs.option_fee_usd(ST, payoff)         # delivery fee when ITM

    # Crossing the spread costs vega * half-spread on entry, whichever way the
    # position is going. Measured from the tape rather than assumed.
    if half_spread_vol:
        vega = greeks.greeks(S0, K, T0, sig, cp)["vega_usd"]
        fees += np.abs(vega) * half_spread_vol

    return pnl - fees if charge_costs else pnl



def leg_costs(entry: pd.DataFrame, px: pd.Series, rehedge_minutes: int,
              half_spread_vol: float) -> pd.DataFrame:
    """Gross P&L and its two cost components, per contract, per unit of one leg.

    Three passes over the same hedge path: no costs, fees only, fees plus the
    measured spread. Separating them is what makes a maker's economics
    computable -- a passive fill earns the half-spread instead of paying it,
    while exchange and perpetual fees fall on maker and taker alike.
    """
    gross = hedged_pnl_to_expiry(entry, px, rehedge_minutes, charge_costs=False)
    fees = hedged_pnl_to_expiry(entry, px, rehedge_minutes, charge_costs=True,
                                half_spread_vol=0.0)
    both = hedged_pnl_to_expiry(entry, px, rehedge_minutes, charge_costs=True,
                                half_spread_vol=half_spread_vol)
    return pd.DataFrame({"gross": gross, "fee": gross - fees,
                         "spread": fees - both}, index=entry.index)


def spread_pnl(gross_short, gross_long, cost_short, cost_long,
               earns_spread=None):
    """P&L of a position SHORT one contract and LONG another.

    The engine prices a short and always subtracts costs, so ``net_short`` and
    ``net_long`` cannot simply be differenced: negating the long leg's stored
    net would turn its costs into a credit. An implementable spread pays the
    costs of *both* legs:

        P&L = (gross_short - gross_long) - (cost_short + cost_long)

    ``earns_spread``, when given, is the half-spread each leg would instead
    *earn* on a passive fill; it is added back rather than subtracted.
    """
    core = (np.asarray(gross_short, dtype="float64")
            - np.asarray(gross_long, dtype="float64"))
    core = core - (np.asarray(cost_short, dtype="float64")
                   + np.asarray(cost_long, dtype="float64"))
    if earns_spread is not None:
        core = core + 2.0 * np.asarray(earns_spread, dtype="float64")
    return core


def build_entries(currency: str) -> pd.DataFrame:
    df = tape.load(currency, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    keep = (d["iv_ok"] & d["delta"].notna()
            & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
            & d["delta"].abs().between(*DELTA_BAND)
            & (d["premium_usd"] > 0))
    d = d.loc[keep].copy()
    d = weekend.attach(d)
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
    d["T_days"] = d["T"] * config.YEAR
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", default="BTC")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cur = a.currency

    print("=" * 78)
    print(f"{cur}: WEEKEND MISPRICING, NET OF MEASURED COSTS")
    print("=" * 78)

    d = build_entries(cur)
    print(f"\nCandidate entries: {len(d):,} trades, {d.date.nunique():,} days")

    sp = costs.effective_spread_iv(d)
    s = costs.summarize_spread(sp)
    print("\nEffective half-spread, measured from aggressor sides:")
    for k, v in s.items():
        print(f"  {k:34s} {v:,.4f}")

    b = bars.load(cur)
    # Use the raw millisecond column. Deriving it from `ts` is a trap: that
    # column is datetime64[ms], not [ns], so the usual //10**6 rescaling
    # silently turns milliseconds into kiloseconds and every price lookup
    # resolves to 1970.
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()
    log.info("price series %s .. %s",
             pd.Timestamp(px.index.min(), unit="ms", tz="UTC"),
             pd.Timestamp(px.index.max(), unit="ms", tz="UTC"))

    # Buckets must be assigned WITHIN each day. Absolute thresholds make the
    # two legs nearly mutually exclusive -- a Friday offers weekend-heavy
    # contracts and a Tuesday offers weekday-only ones -- so a fixed cutoff
    # yields a spread that could almost never be put on. Splitting each day's
    # own cross-section guarantees both legs exist simultaneously, which is the
    # only version of this trade a desk could actually run.
    d = d.sort_values("timestamp")
    q = d.groupby("date")["wknd_frac"]
    lo, hi = q.transform(lambda s: s.quantile(0.25)), q.transform(lambda s: s.quantile(0.75))
    spread_ok = (hi - lo) >= 0.15          # need real within-day dispersion
    d["wk_bucket"] = np.where(spread_ok & (d["wknd_frac"] >= hi), "weekend_heavy",
                       np.where(spread_ok & (d["wknd_frac"] <= lo), "weekday_only",
                                "mixed"))
    d = d[d["wk_bucket"] != "mixed"]
    first = (d.groupby(["date", "wk_bucket"], observed=True).head(1).copy())
    print(f"\nEntries after one-per-day-per-bucket: {len(first):,}")
    print(first.groupby("wk_bucket").size().to_string())

    half_sp = s.get("median_half_spread_volpts", 0.0) / 100.0
    first["pnl_gross"] = hedged_pnl_to_expiry(first, px, charge_costs=False)
    first["pnl_usd"] = hedged_pnl_to_expiry(first, px, charge_costs=True,
                                            half_spread_vol=half_sp)
    first["vega_usd"] = greeks.greeks(
        first["F"].to_numpy(), first["strike"].to_numpy(dtype="float64"),
        first["T"].to_numpy(), first["sigma"].to_numpy(),
        first["cp_sign"].to_numpy())["vega_usd"]
    first["pnl_per_vega"] = first["pnl_usd"] / first["vega_usd"].replace(0, np.nan)

    # Sanity check: a correctly signed, correctly hedged SHORT option book must
    # earn the variance risk premium GROSS of costs. It is checked gross on
    # purpose -- rehedging every five minutes pays perpetual taker fees roughly
    # two thousand times over a seven-day contract, which is enough to turn a
    # genuine premium negative. An earlier version of this check compared the
    # net figure against a gross expectation and looked like an engine bug.
    okg = first["pnl_gross"].div(first["vega_usd"].replace(0, np.nan))
    okg = okg.replace([np.inf, -np.inf], np.nan).dropna()
    okn = first["pnl_per_vega"].replace([np.inf, -np.inf], np.nan).dropna()
    print(f"\n  [check] short delta-hedged P&L per vega, GROSS: "
          f"mean {okg.mean():+.4f} (must be POSITIVE -- the VRP)")
    print(f"          net of fees and spread:            "
          f"mean {okn.mean():+.4f}  (fees {okg.mean() - okn.mean():+.4f})")
    if okg.mean() <= 0:
        print("          WARNING: gross premium is not positive; suspect the "
              "P&L engine before the market.")

    print("\n" + "-" * 78)
    print("SHORT delta-hedged option P&L per unit vega, by weekend coverage")
    print("-" * 78)
    g = first.groupby("wk_bucket")["pnl_per_vega"]
    tab = pd.DataFrame({"n": g.size(), "mean": g.mean(), "sd": g.std(),
                        "median": g.median()})
    tab["t"] = tab["mean"] / (tab["sd"] / np.sqrt(tab["n"]))
    print(tab.to_string(float_format=lambda x: f"{x:,.4f}"))

    if {"weekend_heavy", "weekday_only"} <= set(tab.index):
        print("\n" + "-" * 78)
        print("RELATIVE TRADE: short weekend-heavy / long weekday-only, vega-matched")
        print("-" * 78)
        first["gross_per_vega"] = (first["pnl_gross"]
                                   / first["vega_usd"].replace(0, np.nan))
        for label, col in (("GROSS (no fees, no spread)", "gross_per_vega"),
                           ("NET   (fees + measured spread)", "pnl_per_vega")):
            piv = first.pivot_table(index="date", columns="wk_bucket",
                                    values=col).dropna()
            sp_pnl = piv["weekend_heavy"] - piv["weekday_only"]
            n = len(sp_pnl)
            mu, sd = sp_pnl.mean(), sp_pnl.std()
            sharpe = mu / sd * np.sqrt(252) if sd > 0 else np.nan
            cum = sp_pnl.cumsum()
            dd = float((cum - cum.cummax()).min())
            print(f"\n  {label}   n={n:,}")
            print(f"    mean per vega {mu:+.4f}   t {mu/(sd/np.sqrt(n)):+.2f}"
                  f"   Sharpe {sharpe:+.2f}   maxDD {dd:,.1f}")
            half = n // 2
            a1, a2 = sp_pnl.iloc[:half], sp_pnl.iloc[half:]
            print(f"    first half {a1.mean():+.4f} (t {a1.mean()/(a1.std()/np.sqrt(len(a1))):+.2f})"
                  f"   second half {a2.mean():+.4f} "
                  f"(t {a2.mean()/(a2.std()/np.sqrt(len(a2))):+.2f})")

        med_half = s.get("median_half_spread_volpts", np.nan)
        print(f"\n  measured half-spread {med_half:.2f} vol pts per leg; the "
              f"relative trade crosses it twice.")

    config.TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(config.TABLES / f"w2_weekend_trade_{cur}.csv")
    print(f"\n-> {config.TABLES / f'w2_weekend_trade_{cur}.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
