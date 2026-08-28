"""S1: short weekend straddles on Delta Exchange India, from candle history.

Runs the full pre-registered grid and writes:

    output/tables/di40_weekend_blotter.csv    per-Friday blotter, base config
    output/tables/di41_rehedge_ladder.csv     net/vega by rehedge frequency
    output/tables/di42_exit_grid.csv          entry hour x exit
    output/tables/di43_spread_scenarios.csv   measured vs 2x spread
    output/tables/di45_filter_oos.csv         pre-specified filter, IS/OOS halves

Graduation gates (pre-registered in docs/delta_india_plan.md): net edge > 2x
round-trip cost, sign stable across the rehedge ladder at >= 60 min, positive
OOS under the pre-specified filter.
"""
from __future__ import annotations

import argparse
import functools
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dbop import config, delta_backfill as db, straddle
from dbop.venues import delta_symbols as ds

log = logging.getLogger(__name__)

REHEDGE_LADDER = (5, 60, 240, 1440)
ENTRY_HOURS = (8, 12, 16)
EXIT_KEYS = ("sat_00", "sun_00", "mon_00", "expiry")

# Measured on the live chain 2026-08-26 (output/tables/di01_quoted_spread.csv):
# ATM 0-2d median half-spread 0.15 vol pts. The 2x scenario is the stress.
HALF_SPREAD_MEASURED = 0.0015


def build_chain(currency: str) -> pd.DataFrame:
    disc = db.discovered_symbols(currency)
    if disc.empty:
        raise RuntimeError("no discovered contracts; run the backfill first")
    disc["expiry_ms"] = disc["expiry"].map(ds.expiry_ts_ms)
    return disc[["symbol", "strike", "expiry_ms"]]


def make_loader(currency: str):
    @functools.lru_cache(maxsize=4096)
    def load(symbol: str, mark: bool) -> pd.DataFrame:
        try:
            return db.load_option_candles(currency, symbol, mark=mark)
        except FileNotFoundError:
            return pd.DataFrame()
    return load


def perp_series(currency: str) -> pd.Series:
    px = db.load_perp(currency)
    return pd.Series(px["close"].to_numpy(), index=px["ts"].to_numpy())


def run_grid(currency: str, entry_hour: int, exit_key: str,
             rehedge_minutes: int, half_spread_vol: float,
             stop_mult: float | None, px, chain, load) -> pd.DataFrame:
    rows = []
    for fri in straddle.fridays(int(px.index.min()), int(px.index.max())):
        r = straddle.run_one(int(fri), px, chain, load, currency=currency,
                             entry_hour=entry_hour, exit_key=exit_key,
                             rehedge_minutes=rehedge_minutes,
                             half_spread_vol=half_spread_vol,
                             stop_mult=stop_mult)
        if r is not None:
            r.update({"entry_hour": entry_hour, "exit": exit_key,
                      "rehedge": rehedge_minutes,
                      "half_spread": half_spread_vol})
            rows.append(r)
    return pd.DataFrame(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--currency", default="BTC")
    p.add_argument("--entry-hour", type=int, default=12)
    p.add_argument("--exit", default="sun_00", choices=EXIT_KEYS)
    p.add_argument("--rehedge", type=int, default=60)
    p.add_argument("--stop-mult", type=float, default=None)
    p.add_argument("--full-grid", action="store_true",
                   help="run every table, not just the base blotter")
    p.add_argument("--log", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log.upper())

    px = perp_series(args.currency)
    chain = build_chain(args.currency)
    load = make_loader(args.currency)
    T = config.TABLES

    # base blotter
    bl = run_grid(args.currency, args.entry_hour, args.exit, args.rehedge,
                  HALF_SPREAD_MEASURED, args.stop_mult, px, chain, load)
    bl.to_csv(T / "di40_weekend_blotter.csv", index=False)
    s = straddle.summarize(bl)
    print(f"\nbase config (entry {args.entry_hour:02d}:00 UTC Fri, exit "
          f"{args.exit}, rehedge {args.rehedge}m, half-spread "
          f"{100 * HALF_SPREAD_MEASURED:.2f} vol pts):")
    for k, v in s.items():
        print(f"  {k:>16}: {v:8.4f}" if isinstance(v, float)
              else f"  {k:>16}: {v}")

    if not args.full_grid:
        return 0

    # rehedge ladder
    rows = []
    for rh in REHEDGE_LADDER:
        b = run_grid(args.currency, args.entry_hour, args.exit, rh,
                     HALF_SPREAD_MEASURED, args.stop_mult, px, chain, load)
        rows.append({"rehedge": rh, **straddle.summarize(b)})
    lad = pd.DataFrame(rows)
    lad.to_csv(T / "di41_rehedge_ladder.csv", index=False)
    print("\nrehedge ladder:\n" + lad.to_string(index=False))

    # entry x exit grid at the base rehedge
    rows = []
    for eh in ENTRY_HOURS:
        for ex in EXIT_KEYS:
            b = run_grid(args.currency, eh, ex, args.rehedge,
                         HALF_SPREAD_MEASURED, args.stop_mult, px, chain,
                         load)
            rows.append({"entry_hour": eh, "exit": ex,
                         **straddle.summarize(b)})
    grid = pd.DataFrame(rows)
    grid.to_csv(T / "di42_exit_grid.csv", index=False)
    print("\nentry x exit grid:\n" + grid.to_string(index=False))

    # spread scenarios
    rows = []
    for label, hs in (("gross", 0.0), ("measured", HALF_SPREAD_MEASURED),
                      ("stress_2x", 2 * HALF_SPREAD_MEASURED)):
        b = run_grid(args.currency, args.entry_hour, args.exit, args.rehedge,
                     hs, args.stop_mult, px, chain, load)
        rows.append({"scenario": label, "half_spread": hs,
                     **straddle.summarize(b)})
    sc = pd.DataFrame(rows)
    sc.to_csv(T / "di43_spread_scenarios.csv", index=False)
    print("\nspread scenarios:\n" + sc.to_string(index=False))

    # pre-specified filter, IS/OOS halves. The filter is fixed a priori:
    # trade only when entry IV exceeds the week-so-far realized vol
    # (f_iv_premium > 1) — the sign GPP-style carry logic predicts, and the
    # winner of the Deribit OOS run. No threshold search.
    b = run_grid(args.currency, args.entry_hour, args.exit, args.rehedge,
                 HALF_SPREAD_MEASURED, args.stop_mult, px, chain, load)
    b = b.sort_values("friday").reset_index(drop=True)
    half = len(b) // 2
    rows = []
    for name, part in (("IS", b.iloc[:half]), ("OOS", b.iloc[half:])):
        filt = part[part["f_iv_premium"] > 1.0]
        rows.append({"half": name, "rule": "all",
                     **straddle.summarize(part)})
        rows.append({"half": name, "rule": "iv_premium>1",
                     **straddle.summarize(filt)})
    fo = pd.DataFrame(rows)
    fo.to_csv(T / "di45_filter_oos.csv", index=False)
    print("\npre-specified filter, sample halves:\n" + fo.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
