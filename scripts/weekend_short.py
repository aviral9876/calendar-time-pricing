"""Is the weekend discount still shortable? Date-wise P&L and weekend behaviour.

Section 6 established that the trade isolating the weekend mispricing -- sell
the weekend-heavy contract, buy the weekday-heavy one, vega-matched and
delta-hedged -- was profitable over the full sample and that the edge has been
decaying. This script answers the operational question that summary leaves
open: what does the trade earn *date by date*, what has it earned recently,
and what does the underlying actually do over each weekend?

Three outputs per currency:

  w32_short_daily_{cur}.csv      per-entry-date P&L of the short-weekend spread
                                 (net and gross, per unit vega), plus each leg
  w33_short_by_year.csv          the same aggregated by calendar year and over
                                 trailing windows, all currencies in one table
  w34_weekend_behaviour_{cur}.csv one row per calendar weekend: how the price
                                 moved Sat 00:00 -> Mon 00:00 UTC, the realized
                                 weekend vol, the prior Mon-Fri weekday vol,
                                 and the implied vol at which Friday's
                                 weekend-heavy contracts actually traded

The daily P&L reuses the engine in weekend_commercial.py unchanged, so every
number here is net of the same measured costs (exchange fees on both option
legs and every perpetual rebalance, plus the 0.42-vol-point effective
half-spread crossed twice).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import weekend_commercial as wc                       # noqa: E402

from dbop import bars, config, costs, greeks, jumps   # noqa: E402

log = logging.getLogger("weekend_short")

MS_YEAR = config.YEAR * 86_400_000


def daily_spread(cur: str, d: pd.DataFrame) -> pd.DataFrame:
    """Per-date P&L of the section-6 trade, one row per paired entry date."""
    d = d.copy()
    sp = costs.summarize_spread(costs.effective_spread_iv(d))
    half_sp = sp.get("median_half_spread_volpts", 0.0) / 100.0

    b = bars.load(cur)
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()

    d = d.sort_values("timestamp")
    q = d.groupby("date")["wknd_frac"]
    lo = q.transform(lambda s: s.quantile(0.25))
    hi = q.transform(lambda s: s.quantile(0.75))
    spread_ok = (hi - lo) >= 0.15
    d["wk_bucket"] = np.where(spread_ok & (d["wknd_frac"] >= hi), "weekend_heavy",
                       np.where(spread_ok & (d["wknd_frac"] <= lo), "weekday_only",
                                "mixed"))
    d = d[d["wk_bucket"] != "mixed"]
    first = d.groupby(["date", "wk_bucket"], observed=True).head(1).copy()

    first["pnl_gross"] = wc.hedged_pnl_to_expiry(first, px, charge_costs=False)
    first["pnl_net"] = wc.hedged_pnl_to_expiry(first, px, charge_costs=True,
                                               half_spread_vol=half_sp)
    first["vega_usd"] = greeks.greeks(
        first["F"].to_numpy(), first["strike"].to_numpy(dtype="float64"),
        first["T"].to_numpy(), first["sigma"].to_numpy(),
        first["cp_sign"].to_numpy())["vega_usd"]
    v = first["vega_usd"].replace(0, np.nan)
    first["net_per_vega"] = first["pnl_net"] / v
    first["gross_per_vega"] = first["pnl_gross"] / v

    piv_n = first.pivot_table(index="date", columns="wk_bucket",
                              values="net_per_vega")
    piv_g = first.pivot_table(index="date", columns="wk_bucket",
                              values="gross_per_vega")
    out = pd.DataFrame({
        "short_weekend_leg_net": piv_n.get("weekend_heavy"),
        "short_weekday_leg_net": piv_n.get("weekday_only"),
    })
    # The spread is SHORT the weekend-heavy contract and LONG the weekday-only
    # one, so its P&L is the short-weekend leg minus the short-weekday leg.
    out["spread_net"] = out["short_weekend_leg_net"] - out["short_weekday_leg_net"]
    out["spread_gross"] = (piv_g.get("weekend_heavy")
                           - piv_g.get("weekday_only"))
    out = out.dropna(subset=["spread_net"])
    out.index.name = "date"
    return out


def _stats(s: pd.Series) -> dict:
    s = s.dropna()
    n = len(s)
    if n < 2:
        return {"n": n, "mean": np.nan, "t": np.nan, "sharpe": np.nan,
                "hit_rate": np.nan, "total": np.nan}
    mu, sd = s.mean(), s.std()
    return {"n": n, "mean": mu, "t": mu / (sd / np.sqrt(n)),
            "sharpe": mu / sd * np.sqrt(252) if sd > 0 else np.nan,
            "hit_rate": (s > 0).mean(), "total": s.sum()}


def by_year(dailies: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cur, df in dailies.items():
        idx = pd.to_datetime(df.index)
        for yr, grp in df.groupby(idx.year):
            rows.append({"asset": cur, "period": str(yr),
                         **_stats(grp["spread_net"])})
        end = idx.max()
        for label, days in (("last_6m", 182), ("last_12m", 365),
                            ("last_24m", 730)):
            rows.append({"asset": cur, "period": label,
                         **_stats(df.loc[idx >= end - pd.Timedelta(days=days),
                                         "spread_net"])})
        rows.append({"asset": cur, "period": "full", **_stats(df["spread_net"])})
    return pd.DataFrame(rows)


def weekly_iv(entries: pd.DataFrame) -> pd.DataFrame:
    """Vega-weighted IV quoted ahead of each weekend, and its weekday control.

    The weekend quote is Friday's, on contracts that are at least half weekend
    by calendar coverage. The weekday control cannot also come from Friday --
    every short-dated contract listed on a Friday spans the weekend, so a
    low-coverage bucket is empty there. It is taken from the Tuesday and
    Wednesday of the same week instead, where the same maturities carry no
    weekend at all.
    """
    if entries.empty or "date" not in entries.columns:
        return pd.DataFrame(columns=["sat", "iv_weekend", "iv_weekday"])
    d = entries.copy()
    dow = pd.to_datetime(d["date"]).dt.dayofweek
    d = d[dow.isin([1, 2, 4])]                    # Tue, Wed, Fri
    if d.empty:
        return pd.DataFrame(columns=["sat", "iv_weekend", "iv_weekday"])
    d["dow"] = pd.to_datetime(d["date"]).dt.dayofweek
    d["vega_usd"] = greeks.greeks(
        d["F"].to_numpy(), d["strike"].to_numpy(dtype="float64"),
        d["T"].to_numpy(), d["sigma"].to_numpy(),
        d["cp_sign"].to_numpy())["vega_usd"]
    d["wv"] = d["sigma"] * d["vega_usd"]
    # Key every day to the Saturday that ends its week.
    day = pd.to_datetime(d["date"], utc=True)
    d["sat"] = day + pd.to_timedelta(5 - d["dow"], unit="D")

    def _wavg(g: pd.DataFrame) -> float:
        tot = g["vega_usd"].sum()
        return float(g["wv"].sum() / tot) if tot > 0 else np.nan

    we = d[(d["dow"] == 4) & (d["wknd_frac"] >= 0.5)].groupby("sat").apply(
        _wavg, include_groups=False).rename("iv_weekend")
    wd = d[(d["dow"] != 4) & (d["wknd_frac"] <= 0.05)].groupby("sat").apply(
        _wavg, include_groups=False).rename("iv_weekday")
    return pd.concat([we, wd], axis=1).reset_index()


REHEDGE_LADDER = (5, 60, 480, 1440)


def outright_ladder(cur: str, entries: pd.DataFrame) -> pd.DataFrame:
    """The weekend leg on its own, against the spread, by rehedge interval.

    Dropping the weekday leg turns a relative trade into an outright short of
    variance, and that changes which cost dominates. The two legs of the spread
    carry similar vega and therefore similar perpetual rebalancing fees, so most
    of the hedging cost differences out; standing alone, the weekend leg pays all
    of it. At five-minute rehedging that is roughly 0.13 per unit vega over a
    seven-day contract -- larger than any weekend effect in this paper -- so the
    outright version cannot be judged at one frequency. The ladder is the answer,
    not a robustness check.

    The outright short also earns the variance risk premium, which the spread
    differences away. Its level is therefore not evidence about weekends; only
    its comparison against the spread is.
    """
    d = entries.sort_values("timestamp").copy()
    q = d.groupby("date")["wknd_frac"]
    lo = q.transform(lambda s: s.quantile(0.25))
    hi = q.transform(lambda s: s.quantile(0.75))
    spread_ok = (hi - lo) >= 0.15
    d["wk_bucket"] = np.where(spread_ok & (d["wknd_frac"] >= hi), "weekend_heavy",
                       np.where(spread_ok & (d["wknd_frac"] <= lo), "weekday_only",
                                "mixed"))
    d = d[d["wk_bucket"] != "mixed"]
    first = d.groupby(["date", "wk_bucket"], observed=True).head(1).copy()

    half_sp = costs.summarize_spread(
        costs.effective_spread_iv(entries)).get("median_half_spread_volpts", 0.0) / 100.0

    b = bars.load(cur)
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()

    vega = greeks.greeks(
        first["F"].to_numpy(), first["strike"].to_numpy(dtype="float64"),
        first["T"].to_numpy(), first["sigma"].to_numpy(),
        first["cp_sign"].to_numpy())["vega_usd"]
    first["vega_usd"] = vega

    rows = []
    for step in REHEDGE_LADDER:
        g = wc.hedged_pnl_to_expiry(first, px, rehedge_minutes=step,
                                    charge_costs=False)
        n = wc.hedged_pnl_to_expiry(first, px, rehedge_minutes=step,
                                    charge_costs=True, half_spread_vol=half_sp)
        v = first["vega_usd"].replace(0, np.nan)
        f = first.assign(gross=g / v, net=n / v)
        piv_n = f.pivot_table(index="date", columns="wk_bucket", values="net")
        piv_g = f.pivot_table(index="date", columns="wk_bucket", values="gross")
        if "weekend_heavy" not in piv_n or "weekday_only" not in piv_n:
            continue
        paired = piv_n.dropna()
        outright = paired["weekend_heavy"]
        spread = paired["weekend_heavy"] - paired["weekday_only"]
        gross_out = piv_g.dropna()["weekend_heavy"]

        idx = pd.to_datetime(paired.index)
        recent = idx >= idx.max() - pd.Timedelta(days=365)
        # Keep the coarsest rung's series: it is the only one at which an
        # outright short is a real proposition, so drawdown and the year-by-year
        # path have to be readable from it.
        if step == REHEDGE_LADDER[-1]:
            pd.DataFrame({"outright_net": outright, "spread_net": spread,
                          "outright_gross": gross_out}).to_csv(
                config.TABLES / f"w37_outright_daily_{cur}.csv")
        rows.append({
            "asset": cur, "rehedge_minutes": step, "n": len(paired),
            "outright_gross": gross_out.mean(),
            "fee_drag": gross_out.mean() - outright.mean(),
            **{f"outright_{k}": v for k, v in _stats(outright).items()
               if k in ("mean", "t", "sharpe", "hit_rate")},
            **{f"spread_{k}": v for k, v in _stats(spread).items()
               if k in ("mean", "t", "sharpe", "hit_rate")},
            "outright_mean_12m": outright[recent].mean(),
            "outright_t_12m": _stats(outright[recent])["t"],
            "spread_mean_12m": spread[recent].mean(),
            "spread_t_12m": _stats(spread[recent])["t"],
        })
        log.info("  %s %4dm: outright net %+.4f (t %+.2f), spread %+.4f (t %+.2f)",
                 cur, step, rows[-1]["outright_mean"], rows[-1]["outright_t"],
                 rows[-1]["spread_mean"], rows[-1]["spread_t"])
    return pd.DataFrame(rows)


def behaviour_by_year(behs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per asset-year: what weekends did, and what they were paid."""
    rows = []
    for cur, b in behs.items():
        b = b.copy()
        b["year"] = pd.to_datetime(b.index).year
        for yr, g in b.groupby("year"):
            iv, rv = g.get("iv_weekend"), g["rv_vol_ann"]
            rows.append({
                "asset": cur, "year": int(yr), "n_weekends": len(g),
                "mean_abs_move_pct": g["ret_pct"].abs().mean(),
                "median_range_pct": g["range_pct"].median(),
                "share_down": (g["ret_pct"] < 0).mean(),
                "share_move_over_3pct": (g["ret_pct"].abs() > 3).mean(),
                "median_rv_vol": rv.median(),
                "median_vol_ratio": g["vol_ratio"].median(),
                "median_iv_weekend": iv.median() if iv is not None else np.nan,
                # The mean is the estimand a variance seller is paid on; the
                # median is what a screen shows. Section 5.6 is the reason to
                # report both.
                "mean_iv_minus_rv": g["iv_minus_rv"].mean()
                if "iv_minus_rv" in g else np.nan,
                "median_iv_minus_rv": g["iv_minus_rv"].median()
                if "iv_minus_rv" in g else np.nan,
            })
    return pd.DataFrame(rows)


def weekend_behaviour(cur: str, entries: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar weekend: price path, realized vol, Friday IV."""
    b = jumps.resample(bars.load(cur), config.BAR_MINUTES)
    b = b.set_index(pd.to_datetime(b["ts"], utc=True)).sort_index()
    close = b["close"].astype("float64")
    ret2 = np.log(close).diff() ** 2
    dow = close.index.dayofweek
    day = close.index.floor("D")

    # A weekend is Sat 00:00 -> Mon 00:00 UTC; key it by its Saturday.
    sat = day.where(dow == 5, (day - pd.Timedelta(days=1)).where(dow == 6))
    is_we = dow >= 5

    per_year = 365.25 * 24 * 60 / config.BAR_MINUTES

    we = pd.DataFrame({"close": close[is_we], "ret2": ret2[is_we],
                       "sat": pd.Series(sat, index=close.index)[is_we]})
    grp = we.groupby("sat")
    beh = pd.DataFrame({
        "px_open": grp["close"].first(),
        "px_close": grp["close"].last(),
        "px_high": grp["close"].max(),
        "px_low": grp["close"].min(),
        "n_bars": grp["close"].size(),
        "rv": grp["ret2"].sum(),
    })
    beh = beh[beh["n_bars"] >= 0.6 * 2 * 24 * 60 / config.BAR_MINUTES]
    beh["ret_pct"] = 100 * (beh["px_close"] / beh["px_open"] - 1)
    beh["range_pct"] = 100 * (beh["px_high"] / beh["px_low"] - 1)
    beh["rv_vol_ann"] = np.sqrt(beh["rv"] / beh["n_bars"] * per_year)

    # Preceding Mon-Fri realized vol on the same grid.
    wd = pd.DataFrame({"ret2": ret2[~is_we]}, index=close.index[~is_we])
    wd["week_sat"] = (wd.index.floor("D")
                      + pd.to_timedelta(5 - wd.index.dayofweek, unit="D"))
    wg = wd.groupby("week_sat")["ret2"]
    wk = pd.DataFrame({"wd_rv": wg.sum(), "wd_n": wg.size()})
    wk = wk[wk["wd_n"] >= 0.6 * 5 * 24 * 60 / config.BAR_MINUTES]
    wk["wd_vol_ann"] = np.sqrt(wk["wd_rv"] / wk["wd_n"] * per_year)
    beh = beh.join(wk[["wd_vol_ann"]], how="left")
    beh["vol_ratio"] = beh["rv_vol_ann"] / beh["wd_vol_ann"]

    wiv = weekly_iv(entries)
    if not wiv.empty:
        wiv = wiv.set_index(pd.to_datetime(wiv["sat"], utc=True))
        beh = beh.join(wiv[["iv_weekend", "iv_weekday"]], how="left")
        # What a seller of weekend variance was paid, against what the weekend
        # then delivered. Positive means the sale was, ex post, at a good price.
        beh["iv_minus_rv"] = beh["iv_weekend"] - beh["rv_vol_ann"]
        beh["iv_wknd_ratio"] = beh["iv_weekend"] / beh["iv_weekday"]

    beh.index.name = "weekend_sat"
    return beh.drop(columns=["rv", "n_bars"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=list(config.CURRENCIES))
    ap.add_argument("--reuse", action="store_true",
                    help="skip currencies whose tables are already on disk")
    ap.add_argument("--no-ladder", action="store_true",
                    help="skip the outright-vs-spread rehedge ladder")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    dailies, behs, ladders = {}, {}, []
    for cur in a.currencies:
        p_daily = config.TABLES / f"w32_short_daily_{cur}.csv"
        p_beh = config.TABLES / f"w34_weekend_behaviour_{cur}.csv"
        # Loading the tape and walking the hedge path costs minutes per
        # currency, so a rerun that only needs the cross-asset summary reads
        # back what is already on disk.
        if a.reuse and p_daily.exists() and p_beh.exists():
            dailies[cur] = pd.read_csv(p_daily, index_col=0)
            behs[cur] = pd.read_csv(p_beh, index_col=0)
            log.info("%s: reusing %s", cur, p_daily.name)
            continue

        log.info("%s: daily spread P&L", cur)
        entries = wc.build_entries(cur)
        df = daily_spread(cur, entries)
        dailies[cur] = df
        df.to_csv(p_daily)
        log.info("-> %s (%d paired days)", p_daily, len(df))

        log.info("%s: weekend behaviour", cur)
        beh = weekend_behaviour(cur, entries)
        behs[cur] = beh
        beh.to_csv(p_beh, float_format="%.6g")
        log.info("-> %s (%d weekends)", p_beh, len(beh))

        if not a.no_ladder:
            log.info("%s: outright vs spread, by rehedge interval", cur)
            ladders.append(outright_ladder(cur, entries))

    yr = by_year(dailies)
    p_yr = config.TABLES / "w33_short_by_year.csv"
    yr.to_csv(p_yr, index=False)
    log.info("-> %s", p_yr)

    beh_yr = behaviour_by_year(behs)
    p_beh_yr = config.TABLES / "w35_weekend_behaviour_by_year.csv"
    beh_yr.to_csv(p_beh_yr, index=False)
    log.info("-> %s", p_beh_yr)
    print(beh_yr.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
    print()
    print(yr.to_string(index=False,
                       float_format=lambda x: f"{x:,.4f}"))

    if ladders:
        lad = pd.concat(ladders, ignore_index=True)
        p_lad = config.TABLES / "w36_outright_vs_spread.csv"
        lad.to_csv(p_lad, index=False)
        log.info("-> %s", p_lad)
        print()
        print(lad.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
