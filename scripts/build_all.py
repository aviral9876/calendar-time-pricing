"""Build every constructed dataset from the cached tape.

    python scripts/build_all.py --currency BTC
    python scripts/build_all.py            # both currencies

Runs entirely offline once the backfill has completed, so it is safe to
iterate on repeatedly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from dbop import (config, expensiveness, forwards, instruments,  # noqa: E402
                  inventory, oi, panels, rv, surfaces, tape, validate)

log = logging.getLogger("build_all")


def _date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def build_currency(currency: str, start=None, end=None,
                   exclude_blocks=True, exclude_combos=True,
                   exclude_liquidations=False) -> dict:
    t0 = time.time()
    meta = instruments.load(currency)

    try:
        curves = forwards.curves_by_date(currency)
        log.info("[%s] forward curve loaded for %d days", currency, len(curves))
    except FileNotFoundError:
        log.warning("[%s] NO FORWARD CURVE: greeks will use the index as the "
                    "forward, which biases implied vol in contango. Run "
                    "scripts/run_backfill.py --forwards", currency)
        curves = None

    log.info("[%s] loading tape", currency)
    trades = tape.load(currency, start, end, curves=curves)
    if trades.empty:
        log.warning("[%s] no trades cached", currency)
        return {}
    log.info("[%s] %d trades, %s..%s", currency, len(trades),
             trades["date"].min().date(), trades["date"].max().date())

    base = tape.baseline_filter(trades, exclude_blocks, exclude_combos,
                                exclude_liquidations)
    log.info("[%s] %d trades after baseline filter (%.1f%% kept)", currency,
             len(base), 100 * len(base) / len(trades))

    # Marks and surfaces come from ALL trades, including blocks: a block print
    # is still a price observation even though it is not dealer-absorbed flow.
    log.info("[%s] daily marks and surfaces", currency)
    marks = tape.daily_marks(trades)
    slices, grid = surfaces.build(currency, marks)

    log.info("[%s] realized vol and HAR", currency)
    rv.build(currency)

    log.info("[%s] flow and positions", currency)
    flow = inventory.daily_flow(base)
    pos = inventory.positions(flow, meta)
    log.info("[%s] %d instrument-days of open position", currency, len(pos))

    log.info("[%s] revaluing inventory on the daily surface", currency)
    day_surf = {d: surfaces.DaySurface(g)
                for d, g in slices.groupby("date", observed=True)}
    index_by_date = marks.groupby("date")["index_price"].median()
    revalued = inventory.revalue(pos, meta, day_surf, index_by_date)

    bucket = inventory.bucket_panel(revalued)
    market = inventory.market_panel(revalued)

    log.info("[%s] delta-hedged returns", currency)
    from dbop import funding as funding_mod
    fnd = funding_mod.daily(currency)
    dh = expensiveness.delta_hedged_returns(marks, meta, fnd)
    dh_agg = expensiveness.aggregate_dh_returns(dh)

    log.info("[%s] model-free implied variance", currency)
    mfiv = expensiveness.bkm_implied_variance(slices, 30)
    if len(mfiv):
        mfiv = expensiveness.variance_risk_premium(
            mfiv, rv.load(currency), 30)

    log.info("[%s] assembling panels", currency)
    mkt = panels.build_market(currency, market, grid, dh_agg, mfiv)
    bkt = panels.build_buckets(currency, bucket)
    panels.save(currency, mkt, bkt)

    # Measurement diagnostics that belong in the paper, not just the log.
    checks = inventory.validate_positions(pos, revalued, meta)
    signing = inventory.validate_signing(flow)
    signing.to_parquet(config.PANELS / f"{currency}_signing_test.parquet",
                       index=False)

    # The direct test of the passive-side-is-the-dealer assumption: reconstructed
    # net taker positions against reported open interest.
    try:
        recon = oi.reconciliation_report(currency, flow)
        recon.to_parquet(config.PANELS / f"{currency}_oi_reconciliation.parquet",
                         index=False)
        log.info("[%s] open-interest reconciliation:\n%s", currency,
                 recon.to_string(index=False))
    except FileNotFoundError:
        log.warning("[%s] no open-interest snapshot; run "
                    "scripts/run_backfill.py --oi", currency)
    tape.volume_summary(currency, trades).to_parquet(
        config.PANELS / f"{currency}_volume_summary.parquet", index=False)

    log.info("[%s] position checks: %s", currency, checks)
    log.info("[%s] signing test:\n%s", currency, signing.to_string(index=False))
    log.info("[%s] built in %.1f min", currency, (time.time() - t0) / 60)

    return {"market": mkt, "buckets": bkt, "grid": grid, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", choices=list(config.CURRENCIES), default=None)
    ap.add_argument("--start", type=_date, default=None)
    ap.add_argument("--end", type=_date, default=None)
    ap.add_argument("--keep-blocks", action="store_true")
    ap.add_argument("--drop-liquidations", action="store_true")
    ap.add_argument("--log", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")

    currencies = [args.currency] if args.currency else list(config.CURRENCIES)
    for cur in currencies:
        out = build_currency(
            cur, args.start, args.end,
            exclude_blocks=not args.keep_blocks,
            exclude_combos=not args.keep_blocks,
            exclude_liquidations=args.drop_liquidations)
        if out:
            report = validate.run_all(cur, out["grid"])
            print(f"\n===== {cur} validation =====")
            print(report.to_string(index=False))
            report.to_parquet(config.PANELS / f"{cur}_validation.parquet",
                              index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
