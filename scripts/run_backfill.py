"""Backfill Deribit option trades, instrument metadata, funding and bars.

Typical first run (hours, resumable — safe to kill and restart):
    python scripts/run_backfill.py --all
Trades only, one currency:
    python scripts/run_backfill.py --trades --currency BTC
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dbop import (backfill, bars, config, forwards, funding,  # noqa: E402
                  instruments, oi)


def _date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", choices=list(config.CURRENCIES), default=None,
                    help="default: both")
    ap.add_argument("--start", type=_date, default=None)
    ap.add_argument("--end", type=_date, default=None)
    ap.add_argument("--workers", type=int, default=config.BACKFILL_WORKERS)
    ap.add_argument("--instruments", action="store_true")
    ap.add_argument("--trades", action="store_true")
    ap.add_argument("--funding", action="store_true")
    ap.add_argument("--bars", action="store_true")
    ap.add_argument("--dvol", action="store_true")
    ap.add_argument("--oi", action="store_true",
                    help="snapshot live open interest for the reconciliation test")
    ap.add_argument("--forwards", action="store_true",
                    help="build the forward curve from dated futures")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="refetch cached days")
    ap.add_argument("--log", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("run_backfill")

    currencies = [args.currency] if args.currency else list(config.CURRENCIES)
    do = {k: (args.all or getattr(args, k)) for k in
          ("instruments", "trades", "funding", "bars", "dvol", "oi", "forwards")}
    if not any(do.values()):
        ap.error("nothing to do: pass --all or one of --instruments/--trades/"
                 "--funding/--bars/--dvol/--oi/--forwards")

    t0 = time.time()
    for cur in currencies:
        if do["instruments"]:
            log.info("=== %s instrument metadata ===", cur)
            instruments.build(cur)
        if do["funding"]:
            log.info("=== %s funding history ===", cur)
            funding.build(cur, start=args.start, end=args.end)
        if do["bars"]:
            log.info("=== %s %dmin perp bars ===", cur, config.BAR_MINUTES)
            bars.build(cur, start=args.start, end=args.end)
            log.info("=== %s daily perp bars ===", cur)
            bars.build_daily(cur, start=args.start, end=args.end)
        if do["dvol"]:
            log.info("=== %s DVOL ===", cur)
            bars.build_dvol(cur, start=args.start, end=args.end)
        if do["oi"]:
            log.info("=== %s open-interest snapshot ===", cur)
            oi.snapshot(cur)
        if do["forwards"]:
            log.info("=== %s forward curve from dated futures ===", cur)
            forwards.build(cur)
        if do["trades"]:
            log.info("=== %s option trades ===", cur)
            backfill.backfill(cur, start=args.start, end=args.end,
                              workers=args.workers, force=args.force)

    log.info("all done in %.1f min", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
