"""Open-interest snapshots, and the reconciliation that tests the sign inference.

The paper reconstructs end-user positions as the running sum of aggressor-signed
volume. Nothing in the trade tape verifies that reconstruction, and the
literature that builds dealer inventory this way -- in equities and in crypto --
validates it only indirectly, by showing the resulting measure predicts what
theory says it should. Deribit makes a direct test possible.

Every trade has two sides, so the market can be split into the cohort that
accumulated by crossing the spread and the cohort that accumulated passively.
Open interest counts all contracts outstanding. That gives a hard inequality:

    |cumulative signed taker flow|  <=  open interest

for every instrument, at every point in time. A violation is proof that either
trades are missing from the tape or the sign convention is inverted -- it cannot
be explained by any story about who the counterparties are.

The ratio itself is informative beyond the pass/fail. Close to one, the taker
cohort is almost entirely one-directional, which is what the "end users take,
dealers make" reading requires. Close to zero, takers are balanced against each
other and the passive side cannot be a single risk-absorbing intermediary.

Deribit serves open interest only as a live snapshot, so this reconciles
currently-listed instruments against positions reconstructed up to the same
moment. That is a cross-sectional test on hundreds of instruments, not a time
series, but it is a real out-of-sample check on the central measurement.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import api, config

log = logging.getLogger(__name__)

SNAPSHOT_DIR = config.DATA / "oi_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def snapshot(currency: str) -> pd.DataFrame:
    """Fetch and store the current open interest for every listed option."""
    res = api.get("get_book_summary_by_currency",
                  {"currency": currency, "kind": "option"},
                  base=config.LIVE_BASE)
    df = pd.DataFrame(res)
    keep = ["instrument_name", "open_interest", "volume", "mark_iv",
            "mark_price", "underlying_price", "bid_price", "ask_price",
            "creation_timestamp"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["currency"] = currency
    df["snapshot_ts"] = dt.datetime.now(dt.timezone.utc)

    stamp = df["snapshot_ts"].iloc[0].strftime("%Y-%m-%dT%H%M")
    path = SNAPSHOT_DIR / f"{currency}_{stamp}.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("wrote %s (%d instruments, %d with open interest)", path, len(df),
             int((df["open_interest"] > 0).sum()))
    return df


def latest_snapshot(currency: str) -> pd.DataFrame:
    files = sorted(SNAPSHOT_DIR.glob(f"{currency}_*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"no open-interest snapshot for {currency}; "
            f"run scripts/run_backfill.py --oi")
    return pd.read_parquet(files[-1])


def reconcile(currency: str, flow: pd.DataFrame,
              snap: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compare reconstructed net taker positions against reported open interest.

    ``flow`` is the instrument-day signed-demand frame from
    ``inventory.daily_flow``; positions are its cumulative sum per instrument.
    """
    snap = snap if snap is not None else latest_snapshot(currency)
    snap = snap[snap["open_interest"] > 0]

    cum = (flow.sort_values("date")
              .groupby("instrument_name", observed=True)
              .agg(net_position=("net_amount", "sum"),
                   gross_volume=("gross_amount", "sum"),
                   n_trades=("n_trades", "sum"),
                   last_date=("date", "max"))
              .reset_index())

    m = snap.merge(cum, on="instrument_name", how="inner")
    if m.empty:
        return m

    m["abs_net"] = m["net_position"].abs()
    m["oi_ratio"] = m["abs_net"] / m["open_interest"]
    # The inequality can only be violated by missing trades or an inverted
    # sign; a small tolerance absorbs the gap between the snapshot time and the
    # last cached trading day.
    m["violates"] = m["oi_ratio"] > 1.05
    return m


def reconciliation_report(currency: str, flow: pd.DataFrame,
                          snap: pd.DataFrame | None = None) -> pd.DataFrame:
    """Summary statistics for the paper's measurement-validation subsection."""
    m = reconcile(currency, flow, snap)
    if m.empty:
        return pd.DataFrame([{"currency": currency, "n_instruments": 0,
                              "note": "no overlap between snapshot and tape"}])

    return pd.DataFrame([{
        "currency": currency,
        "n_instruments": len(m),
        "share_violating_OI_bound": float(m["violates"].mean()),
        "median_|net|/OI": float(m["oi_ratio"].median()),
        "mean_|net|/OI": float(m["oi_ratio"].mean()),
        "p90_|net|/OI": float(m["oi_ratio"].quantile(0.90)),
        "share_net_long_endusers": float((m["net_position"] > 0).mean()),
        "corr_|net|_vs_OI": float(np.corrcoef(
            m["abs_net"], m["open_interest"])[0, 1]),
        "total_OI": float(m["open_interest"].sum()),
        "total_|net|": float(m["abs_net"].sum()),
    }])
