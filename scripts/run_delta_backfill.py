"""Backfill Delta Exchange India candles and print first-look statistics.

Phase 1 scope: the perpetual (5m traded candles, monthly files, resumable).

    python scripts/run_delta_backfill.py --currency BTC --perp --stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dbop import delta_backfill, weekend
from dbop.venues import delta_india as dx


def stats(currency: str) -> None:
    df = delta_backfill.load_perp(currency, check=False)
    df = delta_backfill.usable_days(df)
    # realized_by_daytype expects ts as datetimes, not epoch ms
    df = df.assign(ts=pd.to_datetime(df["ts"], unit="ms", utc=True))
    rv = weekend.realized_by_daytype(df)
    r = weekend.weekend_variance_ratio(rv)
    print(f"\n{currency} on Delta India ({dx.PERPETUAL[currency]}), "
          f"{df['ts'].min():%Y-%m-%d} to {df['ts'].max():%Y-%m-%d}, "
          f"{r['n_weekday']} weekday / {r['n_weekend']} weekend days used")
    print(f"  annualized vol   weekday {100 * (r['var_weekday'] * 365) ** 0.5:6.2f}%   "
          f"weekend {100 * (r['var_weekend'] * 365) ** 0.5:6.2f}%")
    print(f"  variance ratio   {r['variance_ratio']:.3f}   "
          f"(vol ratio {r['vol_ratio']:.3f}, "
          f"diff t = {r['diff'] / r['se_diff']:.2f})")
    print(f"  [Deribit full-sample BTC vol ratio for reference: 0.737]")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--currency", default="BTC", choices=sorted(dx.PERPETUAL))
    p.add_argument("--perp", action="store_true", help="backfill perp candles")
    p.add_argument("--stats", action="store_true",
                   help="print weekend/weekday realized vol from stored candles")
    p.add_argument("--discover", action="store_true",
                   help="probe expired option symbols (Fri-Tue expiries)")
    p.add_argument("--options", action="store_true",
                   help="fetch 1h traded+mark candles for discovered contracts")
    p.add_argument("--opt-start", type=dt.date.fromisoformat,
                   default=dt.date(2024, 2, 1))
    p.add_argument("--opt-end", type=dt.date.fromisoformat, default=None)
    p.add_argument("--width", type=float, default=0.10,
                   help="discovery ladder half-width around spot")
    p.add_argument("--start", type=dt.date.fromisoformat, default=None)
    p.add_argument("--end", type=dt.date.fromisoformat, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--log", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=args.log.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not (args.perp or args.stats or args.discover or args.options):
        p.error("nothing to do: pass --perp, --discover, --options or --stats")

    if args.perp:
        n = delta_backfill.backfill_perp(
            args.currency, start=args.start, end=args.end, force=args.force)
        print(f"backfilled {n} candles for {args.currency}")

    if args.discover:
        end = args.opt_end or dt.datetime.now(dt.timezone.utc).date()
        n = delta_backfill.discover_range(
            args.currency, args.opt_start, end, width=args.width,
            force=args.force)
        print(f"probed {n} expiries for {args.currency}")

    if args.options:
        n = delta_backfill.backfill_option_candles(
            args.currency, force=args.force)
        print(f"fetched {n} option candle files for {args.currency}")

    if args.stats:
        stats(args.currency)
    return 0


if __name__ == "__main__":
    sys.exit(main())
