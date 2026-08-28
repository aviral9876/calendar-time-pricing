"""5-minute OHLCV bars for the perpetual, and DVOL history.

Realized volatility and delta-hedged returns need a high-frequency underlying
series, but they do not need the raw perp trade tape (billions of rows). Bars
from the chart endpoint carry the same information at a thousandth of the cost.

The perpetual is the correct underlying here rather than the spot index: it is
what a dealer actually hedges in, so its returns are the ones that enter the
hedge P&L.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import api, config, util

log = logging.getLogger(__name__)

# The chart endpoint returns at most ~5,000 bars per call and gives no error
# when it truncates: it simply returns fewer rows than the window covers. A
# naive 30-day chunk at 5-minute resolution asks for 8,640 and silently loses
# the last twelve days, which is how 40% of the return series went missing
# before this was caught. Chunks are therefore sized from the resolution.
MAX_BARS_PER_REQUEST = 5000
SAFETY = 0.9
CHUNK_DAYS = 30                      # ceiling for coarse resolutions

# Minutes per bar for each resolution the endpoint accepts.
_RES_MINUTES = {"1": 1, "3": 3, "5": 5, "10": 10, "15": 15, "30": 30,
                "60": 60, "120": 120, "180": 180, "360": 360, "720": 720,
                "1D": 1440}


def chunk_days_for(resolution: str) -> int:
    """Largest window that stays inside the endpoint's bar cap."""
    minutes = _RES_MINUTES.get(str(resolution))
    if not minutes:
        return CHUNK_DAYS
    per_day = 1440 / minutes
    return max(1, min(CHUNK_DAYS,
                      int(MAX_BARS_PER_REQUEST * SAFETY / per_day)))


def _to_ms(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day,
                           tzinfo=dt.timezone.utc).timestamp() * 1000)


def fetch_bars(instrument: str, start: dt.date, end: dt.date,
               resolution: str = str(config.BAR_MINUTES)) -> pd.DataFrame:
    chunk = chunk_days_for(resolution)
    frames = []
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=chunk), end + dt.timedelta(days=1))
        res = api.get_tradingview_chart_data(instrument, _to_ms(cur),
                                             _to_ms(stop), resolution)
        if res.get("status") == "ok" and res.get("ticks"):
            n = len(res["ticks"])
            if n >= MAX_BARS_PER_REQUEST:
                log.warning("%s %s..%s returned %d bars: still hitting the "
                            "cap, data may be truncated", instrument, cur,
                            stop, n)
            frames.append(pd.DataFrame({
                "timestamp": res["ticks"],
                "open": res["open"], "high": res["high"],
                "low": res["low"], "close": res["close"],
                "volume": res["volume"], "cost": res["cost"],
            }))
        cur = stop

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp")
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["date"] = df["ts"].dt.date
    return df.sort_values("ts").reset_index(drop=True)


def build(currency: str, start: dt.date | None = None,
          end: dt.date | None = None) -> pd.DataFrame:
    start = start or config.SAMPLE_START[currency]
    end = end or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    df = fetch_bars(config.PERPETUAL[currency], start, end)
    path = config.BARS / f"{currency}-perp-{config.BAR_MINUTES}min.parquet"
    df.to_parquet(path, compression="zstd", index=False)

    # Silent truncation is the failure mode here, so report completeness rather
    # than a row count that looks fine either way.
    if len(df):
        per_day = df.groupby("date").size()
        expect = 1440 // config.BAR_MINUTES
        log.info("wrote %s (%d bars, %s..%s; %d days, %.1f%% complete, "
                 "%d days below 70%% coverage)", path, len(df),
                 df["date"].min(), df["date"].max(), len(per_day),
                 100 * (per_day >= expect).mean(),
                 int((per_day < 0.7 * expect).sum()))
    else:
        log.warning("%s: no bars returned", currency)
    return df


def build_daily(currency: str, start: dt.date | None = None,
                end: dt.date | None = None) -> pd.DataFrame:
    """One clean close per day for the perpetual.

    Used as the forward-curve anchor. Aggregating the 5-minute cache would work
    too, but only where that cache is complete; a dedicated daily series is one
    value per day by construction and cannot be silently thinned.
    """
    start = start or config.SAMPLE_START[currency]
    end = end or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    df = fetch_bars(config.PERPETUAL[currency], start, end, resolution="1D")
    path = config.BARS / f"{currency}-perp-daily.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("wrote %s (%d daily bars, %s..%s)", path, len(df),
             df["date"].min() if len(df) else None,
             df["date"].max() if len(df) else None)
    return df


def load_daily(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.BARS / f"{currency}-perp-daily.parquet")


MIN_COVERAGE = 0.90


def load(currency: str, check: bool = True) -> pd.DataFrame:
    """Load the 5-minute bar cache, refusing a series with holes in it.

    A truncated bar series is silently poisonous: `log(close).diff()` spans any
    gap and records it as one 5-minute return, so realized variance is inflated
    (by up to 222x on affected days, when this last happened) and any P&L path
    steps through a price jump that never occurred. It is checked on load
    because the file can be clobbered by a stale process holding an older
    version of this module -- which is exactly how ETH ended up 58% complete
    while its log line claimed a successful write.
    """
    df = pd.read_parquet(
        config.BARS / f"{currency}-perp-{config.BAR_MINUTES}min.parquet")
    if check and len(df):
        ts = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        span_days = (ts.max() - ts.min()).total_seconds() / 86400 + 1
        expected = span_days * (1440 / config.BAR_MINUTES)
        coverage = len(df) / expected if expected else 0.0
        gaps = int((ts.sort_values().diff().dt.total_seconds()
                    > 60 * config.BAR_MINUTES).sum())
        if coverage < MIN_COVERAGE:
            raise ValueError(
                f"{currency} bar series is {coverage:.1%} complete with {gaps} "
                f"gaps; rebuild with bars.build({currency!r}) before using it. "
                f"Gap-spanning returns corrupt realized variance and P&L paths."
            )
        if gaps:
            log.warning("%s: %d gaps in the bar series (%.1f%% coverage)",
                        currency, gaps, coverage * 100)
    return df


def build_dvol(currency: str, start: dt.date | None = None,
               end: dt.date | None = None) -> pd.DataFrame:
    """Deribit's own 30-day model-free implied vol index.

    Used as a control (market-wide vol level) and as an external check on our
    independently constructed surface.
    """
    start = start or config.SAMPLE_START[currency]
    end = end or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))

    frames = []
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=90), end + dt.timedelta(days=1))
        res = api.get_volatility_index_data(currency, _to_ms(cur), _to_ms(stop),
                                            resolution="3600")
        data = res.get("data", []) if isinstance(res, dict) else []
        if data:
            frames.append(pd.DataFrame(
                data, columns=["timestamp", "open", "high", "low", "close"]))
        cur = stop

    if not frames:
        log.warning("%s: no DVOL data returned", currency)
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp")
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["date"] = df["ts"].dt.date
    df = df.sort_values("ts").reset_index(drop=True)
    path = config.DVOL / f"{currency}_dvol.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("wrote %s (%d rows, %s..%s)", path, len(df),
             df["date"].min(), df["date"].max())
    return df


def load_dvol(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.DVOL / f"{currency}_dvol.parquet")


def dvol_daily(currency: str) -> pd.DataFrame:
    df = load_dvol(currency)
    out = df.groupby("date")["close"].last().rename("dvol").reset_index()
    out["currency"] = currency
    return util.normalize_date_col(out)
