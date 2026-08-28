"""Perpetual funding-rate history.

Funding is the carry cost of the perpetual hedge: an option dealer who is delta
hedged in the perp pays (or receives) it continuously. It is the price side of
the hedging-cost instrument in the 2SLS design, so it needs the same span as
the option tape.

Only www serves this endpoint; the history host rejects it.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from . import api, config, util

log = logging.getLogger(__name__)

# The endpoint caps the window it will answer; a month per request is well
# inside the limit and keeps the request count small.
CHUNK_DAYS = 30


def _to_ms(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day,
                           tzinfo=dt.timezone.utc).timestamp() * 1000)


def fetch(currency: str, start: dt.date | None = None,
          end: dt.date | None = None) -> pd.DataFrame:
    inst = config.PERPETUAL[currency]
    start = start or config.SAMPLE_START[currency]
    end = end or dt.datetime.now(dt.timezone.utc).date()

    rows = []
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=CHUNK_DAYS), end + dt.timedelta(days=1))
        chunk = api.get_funding_rate_history(inst, _to_ms(cur), _to_ms(stop))
        rows.extend(chunk)
        log.debug("%s funding %s..%s: %d rows", currency, cur, stop, len(chunk))
        cur = stop

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).drop_duplicates("timestamp")
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["date"] = df["ts"].dt.date
    df["currency"] = currency
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "date", "currency", "timestamp", "interest_8h",
               "interest_1h", "index_price", "prev_index_price"]]


def build(currency: str, **kw) -> pd.DataFrame:
    df = fetch(currency, **kw)
    path = config.FUNDING / f"{currency}.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("wrote %s (%d rows, %s..%s)", path, len(df),
             df["date"].min() if len(df) else None,
             df["date"].max() if len(df) else None)
    return df


def load(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.FUNDING / f"{currency}.parquet")


def daily(currency: str) -> pd.DataFrame:
    """Collapse to one row per UTC day.

    ``funding_day`` is the total carry a hedger pays over the day (the sum of
    the hourly accruals), which is the quantity that multiplies inventory in
    the hedging-cost measure. The mean 8h print is kept as the conventional
    headline rate.
    """
    df = load(currency)
    g = df.groupby("date")
    out = pd.DataFrame({
        "funding_day": g["interest_1h"].sum(),
        "funding_8h_mean": g["interest_8h"].mean(),
        "funding_1h_mean": g["interest_1h"].mean(),
        "funding_1h_std": g["interest_1h"].std(),
        "n_prints": g["interest_1h"].size(),
    }).reset_index()
    out["currency"] = currency
    return util.normalize_date_col(out)
