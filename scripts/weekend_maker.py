"""The weekend spread costed correctly, for a taker and for a maker.

Every trading result in this project ran through a spread built as
``net_weekend_heavy - net_weekday_only``. Both stored legs are the P&L of a
SHORT contract, and the engine always *subtracts* costs, so negating the second
leg turned its costs into a credit. An implementable position that is short one
contract and long another pays both legs' costs. The gap is exactly twice the
long leg's cost, which at five-minute rehedging is larger than the entire
reported edge.

This script recomputes the spread the implementable way and, in the same pass,
prices the version a market maker would run. Separating the two cost components
is what makes that possible:

* **fees** -- Deribit's option fee on entry and delivery, plus the perpetual
  taker fee on every rebalance of the delta hedge. A maker pays these exactly
  as a taker does.
* **spread** -- the effective half-spread recovered from the tape by
  differencing buyer-paid against seller-received implied volatility. A taker
  pays it on both legs; a passive fill *earns* it on both.

The swing between those two is 4x the half-spread per unit vega, and it is the
whole of the maker's advantage on this trade. Whether that is enough is the
question the script exists to answer.

Outputs:

  w60_spread_costed.csv    per asset and rehedge interval: gross, fees, spread,
                           taker net, maker net, full sample and trailing year
  w61_fee_split.csv        the fee column split into exchange fees and the cost
                           of hedging in the perpetual, which decides whether a
                           fee tier could close the gap
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

from dbop import bars, config, costs, greeks          # noqa: E402

log = logging.getLogger("weekend_maker")

REHEDGE = (5, 60, 480, 1440)


def paired_legs(cur: str) -> tuple[pd.DataFrame, pd.Series, float]:
    """Section 6's entries, bucketed its way, plus the price path and spread."""
    d = wc.build_entries(cur)
    half = costs.summarize_spread(
        costs.effective_spread_iv(d)).get("median_half_spread_volpts", 0.0) / 100.0

    b = bars.load(cur)
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()

    d = d.sort_values("timestamp")
    q = d.groupby("date")["wknd_frac"]
    lo = q.transform(lambda s: s.quantile(0.25))
    hi = q.transform(lambda s: s.quantile(0.75))
    ok = (hi - lo) >= 0.15
    d["side"] = np.where(ok & (d["wknd_frac"] >= hi), "weekend_heavy",
                  np.where(ok & (d["wknd_frac"] <= lo), "weekday_only", "mixed"))
    d = d[d["side"] != "mixed"]
    first = d.groupby(["date", "side"], observed=True).head(1).copy()
    first["vega_usd"] = greeks.greeks(
        first["F"].to_numpy(), first["strike"].to_numpy(dtype="float64"),
        first["T"].to_numpy(), first["sigma"].to_numpy(),
        first["cp_sign"].to_numpy())["vega_usd"]
    return first, px, half


def _stats(s: pd.Series, label: str = "") -> dict:
    s = pd.Series(s).dropna()
    n = len(s)
    if n < 2:
        return {f"{label}n": n, f"{label}mean": np.nan, f"{label}t": np.nan,
                f"{label}sharpe": np.nan}
    mu, sd = s.mean(), s.std()
    return {f"{label}n": n, f"{label}mean": mu,
            f"{label}t": mu / (sd / np.sqrt(n)),
            f"{label}sharpe": mu / sd * np.sqrt(252) if sd > 0 else np.nan}


def costed(cur: str, first: pd.DataFrame, px: pd.Series,
           half: float) -> pd.DataFrame:
    """The spread at each rehedge interval, as coded, as implementable, as a maker."""
    v = first["vega_usd"].replace(0, np.nan)
    rows = []
    for step in REHEDGE:
        c = wc.leg_costs(first, px, step, half)
        x = first.assign(gross=c["gross"] / v, fee=c["fee"] / v,
                         spread=c["spread"] / v)
        piv = {k: x.pivot_table(index="date", columns="side", values=k)
               for k in ("gross", "fee", "spread")}
        idx = piv["gross"].dropna().index
        for k in piv:
            piv[k] = piv[k].loc[idx]
        if "weekend_heavy" not in piv["gross"] or "weekday_only" not in piv["gross"]:
            continue

        g_s, g_l = piv["gross"]["weekend_heavy"], piv["gross"]["weekday_only"]
        f_s, f_l = piv["fee"]["weekend_heavy"], piv["fee"]["weekday_only"]
        p_s, p_l = piv["spread"]["weekend_heavy"], piv["spread"]["weekday_only"]

        gross = g_s - g_l
        as_coded = (g_s - f_s - p_s) - (g_l - f_l - p_l)
        taker = wc.spread_pnl(g_s, g_l, f_s + p_s, f_l + p_l)
        maker = wc.spread_pnl(g_s, g_l, f_s, f_l) + (p_s + p_l)

        taker = pd.Series(taker, index=idx)
        maker = pd.Series(maker, index=idx)
        recent = pd.to_datetime(idx) >= pd.to_datetime(idx).max() - pd.Timedelta(days=365)

        rows.append({
            "asset": cur, "rehedge_minutes": step, "n": len(idx),
            "half_spread_volpts": 100 * half,
            "gross": gross.mean(),
            "fees_both_legs": (f_s + f_l).mean(),
            "spread_both_legs": (p_s + p_l).mean(),
            "as_coded_mean": as_coded.mean(),
            **_stats(taker, "taker_"), **_stats(maker, "maker_"),
            "taker_recent": taker[recent].mean(),
            "maker_recent": maker[recent].mean(),
            "maker_recent_t": _stats(maker[recent])["t"],
        })
        log.info("  %s %5dm: gross %+.4f fees %.4f spread %.4f -> taker %+.4f "
                 "maker %+.4f (as coded %+.4f)", cur, step, rows[-1]["gross"],
                 rows[-1]["fees_both_legs"], rows[-1]["spread_both_legs"],
                 rows[-1]["taker_mean"], rows[-1]["maker_mean"],
                 rows[-1]["as_coded_mean"])
    return pd.DataFrame(rows)


def fee_split(cur: str, first: pd.DataFrame, px: pd.Series) -> pd.DataFrame:
    """Exchange option fees against the cost of hedging in the perpetual.

    A fee tier or maker rebate can only touch the exchange component, so the
    split decides whether better terms could ever make this trade pay.
    Isolated by zeroing each fee function in turn rather than by re-deriving
    the arithmetic, so the numbers come from the same engine as everything else.
    """
    v = first["vega_usd"].replace(0, np.nan)
    real_opt, real_perp = costs.option_fee_usd, costs.perp_fee_usd
    zero = lambda *a, **k: np.zeros(len(first))                      # noqa: E731

    rows = []
    for step in REHEDGE:
        base = wc.leg_costs(first, px, step, 0.0)["fee"] / v
        try:
            costs.option_fee_usd = lambda u, p, **k: np.zeros_like(
                np.asarray(u, dtype="float64"))
            no_opt = wc.leg_costs(first, px, step, 0.0)["fee"] / v
        finally:
            costs.option_fee_usd = real_opt
        try:
            costs.perp_fee_usd = lambda n, **k: np.zeros_like(
                np.asarray(n, dtype="float64"))
            no_perp = wc.leg_costs(first, px, step, 0.0)["fee"] / v
        finally:
            costs.perp_fee_usd = real_perp

        x = first.assign(total=base, opt=base - no_opt, perp=base - no_perp)
        piv = x.pivot_table(index="date", columns="side",
                            values=["total", "opt", "perp"]).dropna()
        rows.append({
            "asset": cur, "rehedge_minutes": step,
            "fees_total": piv["total"].sum(axis=1).mean(),
            "option_fees": piv["opt"].sum(axis=1).mean(),
            "perp_fees": piv["perp"].sum(axis=1).mean(),
        })
        log.info("  %s %5dm: fees %.4f = option %.4f + perp %.4f", cur, step,
                 rows[-1]["fees_total"], rows[-1]["option_fees"],
                 rows[-1]["perp_fees"])
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=list(config.CURRENCIES))
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    costed_all, split_all = [], []
    for cur in a.currencies:
        log.info("%s: building paired legs", cur)
        first, px, half = paired_legs(cur)
        log.info("%s: %d entries, half-spread %.2f vol pts",
                 cur, len(first), 100 * half)
        costed_all.append(costed(cur, first, px, half))
        split_all.append(fee_split(cur, first, px))
        del first, px

    for frames, name in ((costed_all, "w60_spread_costed"),
                         (split_all, "w61_fee_split")):
        frames = [f for f in frames if not f.empty]
        if not frames:
            continue
        out = pd.concat(frames, ignore_index=True)
        p = config.TABLES / f"{name}.csv"
        out.to_csv(p, index=False)
        log.info("-> %s", p)
        print(f"\n=== {name} ===")
        print(out.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
