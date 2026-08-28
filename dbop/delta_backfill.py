"""Candle backfill for Delta Exchange India.

Delta has no historical trade tape, so unlike the Deribit pipeline everything
here is candle-shaped: traded OHLCV per symbol plus ``MARK:`` model candles for
options. The unit of work is one (symbol, resolution, month); completed months
are skipped on rerun, the current month is always refreshed.

Layout:
    data/delta_india/perp/{CUR}/{SYMBOL}-{res}-YYYY-MM.parquet
    data/delta_india/options/{CUR}/{SYMBOL}-{res}.parquet        (one file per contract)
    data/delta_india/options/{CUR}/MARK-{SYMBOL}-{res}.parquet
    data/delta_india/manifest/...
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import config
from .venues import delta_india as dx

log = logging.getLogger(__name__)

DELTA = config.DATA / "delta_india"
PERP_DIR = DELTA / "perp"
OPT_DIR = DELTA / "options"
MANIFEST_DIR = DELTA / "manifest"
for _d in (DELTA, PERP_DIR, OPT_DIR, MANIFEST_DIR):
    _d.mkdir(parents=True, exist_ok=True)

PERP_RESOLUTION = "5m"

# A perp day with fewer traded bars than this is unusable for realized vol —
# same threshold as rv.MIN_BARS_PER_DAY on the Deribit side. Early 2024 months
# on the young venue are genuinely sparse.
MIN_BARS_PER_DAY = 200


def _to_frame(candles: list[dict]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(
            columns=["time", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(candles)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).drop_duplicates("time")
    df = df.sort_values("time").reset_index(drop=True)
    df["ts"] = df["time"].astype("int64") * 1000            # epoch ms, repo convention
    return df


def fetch_candles(symbol: str, resolution: str,
                  start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    """All candles for [start, end), chunked under the 4,000-candle page cap."""
    start_s = int(start.replace(tzinfo=dt.timezone.utc).timestamp())
    end_s = int(end.replace(tzinfo=dt.timezone.utc).timestamp())
    step = dx.chunk_seconds(resolution)
    rows: list[dict] = []
    t = start_s
    while t < end_s:
        rows.extend(dx.get_candles(symbol, resolution, t, min(t + step, end_s)))
        t += step
    return _to_frame(rows)


# ------------------------------------------------------------------ perpetual


def _month_range(start: dt.date, end: dt.date):
    m = dt.date(start.year, start.month, 1)
    while m <= end:
        nxt = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        yield m, nxt
        m = nxt


def perp_path(currency: str, month: dt.date, resolution: str = PERP_RESOLUTION):
    d = PERP_DIR / currency
    d.mkdir(parents=True, exist_ok=True)
    sym = dx.PERPETUAL[currency]
    return d / f"{sym}-{resolution}-{month:%Y-%m}.parquet"


def backfill_perp(currency: str, start: dt.date | None = None,
                  end: dt.date | None = None,
                  resolution: str = PERP_RESOLUTION, force: bool = False) -> int:
    """Month-file backfill; completed past months are skipped, the month
    containing ``end`` (or today) is always refetched."""
    sym = dx.PERPETUAL[currency]
    start = start or dt.date.fromisoformat(dx.SAMPLE_START[currency])
    end = end or dt.datetime.now(dt.timezone.utc).date()
    n_new = 0
    for m, nxt in _month_range(start, end):
        path = perp_path(currency, m, resolution)
        current = nxt > end
        if path.exists() and not current and not force:
            continue
        df = fetch_candles(sym, resolution,
                           dt.datetime(m.year, m.month, 1),
                           dt.datetime(nxt.year, nxt.month, 1))
        df.to_parquet(path, compression="zstd", index=False)
        n_new += len(df)
        log.info("%s %s %s: %d candles", sym, resolution, m.strftime("%Y-%m"),
                 len(df))
    return n_new


def load_perp(currency: str, resolution: str = PERP_RESOLUTION,
              check: bool = True) -> pd.DataFrame:
    d = PERP_DIR / currency
    files = sorted(d.glob(f"{dx.PERPETUAL[currency]}-{resolution}-*.parquet"))
    if not files:
        raise FileNotFoundError(f"no perp candles for {currency}; run backfill")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if check:
        # Coverage on the *mature* part of the sample. The venue's first months
        # are thin (traded candles only print when trades occur), which is a
        # fact about the venue, not a data fault; but a gap in the recent series
        # would poison realized vol exactly the way the Deribit 5,001-bar
        # truncation once did, so the last year must be near-complete.
        per_day = df.groupby(df["ts"] // 86_400_000).size()
        recent = per_day.tail(365)
        bars_per_day = 86_400 // dx.RESOLUTION_SECONDS[resolution]
        coverage = float(recent.mean()) / bars_per_day
        if coverage < 0.90:
            raise RuntimeError(
                f"{currency} perp {resolution} coverage over the last year is "
                f"{coverage:.1%}; refusing a gappy series (re-run backfill)")
    return df


def perp_daily_close(currency: str) -> pd.DataFrame:
    """Daily last close, for strike-ladder generation during discovery."""
    df = load_perp(currency, check=False)
    day = (df["ts"] // 86_400_000) * 86_400_000
    out = df.groupby(day)["close"].last().rename("close").reset_index()
    out["date"] = pd.to_datetime(out["ts"], unit="ms", utc=True).dt.date
    return out[["date", "close"]]


def usable_days(df: pd.DataFrame,
                min_bars: int = MIN_BARS_PER_DAY) -> pd.DataFrame:
    """Filter a candle frame to days with enough bars for realized vol."""
    day = df["ts"] // 86_400_000
    counts = day.map(day.value_counts())
    return df[counts >= min_bars]


# ------------------------------------------------------------ option discovery
#
# No endpoint lists expired instruments, so historical symbols are
# reconstructed and probed: for each expiry date, walk the strike ladder
# outward from spot and ask the candle endpoint for daily candles. An empty
# result is a miss; a streak of misses on both wings ends the walk. Calls and
# puts are listed as pairs on this venue, so only calls are probed and puts are
# picked up at fetch time.

from .venues import delta_symbols as ds  # noqa: E402

PROBE_MISS_STREAK = 6
PROBE_LOOKBACK_DAYS = 10      # daily expiries list ~4 days out; margin for weeklies


def _daily_dir(currency: str):
    d = OPT_DIR / currency / "daily"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _h1_dir(currency: str):
    d = OPT_DIR / currency / "h1"
    d.mkdir(parents=True, exist_ok=True)
    return d


def discovery_manifest_path(currency: str):
    return MANIFEST_DIR / f"discovery_{currency}.parquet"


def load_discovery_manifest(currency: str) -> pd.DataFrame:
    p = discovery_manifest_path(currency)
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=["expiry", "anchor_spot", "width", "step",
                                 "n_hits", "probed_at"])


def _probe_one(symbol: str, expiry: dt.date) -> pd.DataFrame:
    """Daily traded candles over the contract's plausible life; empty = miss."""
    e_ms = ds.expiry_ts_ms(expiry)
    start = dt.datetime.fromtimestamp(e_ms / 1000, dt.timezone.utc) \
        - dt.timedelta(days=PROBE_LOOKBACK_DAYS)
    end = dt.datetime.fromtimestamp(e_ms / 1000, dt.timezone.utc) \
        + dt.timedelta(days=1)
    candles = dx.get_candles(symbol, "1d",
                             int(start.timestamp()), int(end.timestamp()))
    return _to_frame(candles)


def discover_expiry(currency: str, expiry: dt.date, width: float = 0.10,
                    step: float | None = None,
                    miss_streak: int = PROBE_MISS_STREAK) -> pd.DataFrame:
    """Probe the call ladder around spot for one expiry date.

    Returns the daily candles of every hit, with a ``symbol`` column, and
    persists them; records the expiry in the discovery manifest either way.
    """
    step = step or ds.PROBE_STEP[currency]
    spot_tbl = perp_daily_close(currency)
    anchor_rows = spot_tbl[spot_tbl["date"] <= expiry]
    if anchor_rows.empty:
        raise RuntimeError(f"no perp close on or before {expiry}")
    spot = float(anchor_rows["close"].iloc[-1])

    center = round(spot / step) * step
    frames: list[pd.DataFrame] = []
    for direction in (+1, -1):
        misses = 0
        i = 0 if direction > 0 else 1
        while misses < miss_streak:
            k = center + direction * i * step
            i += 1
            if k <= 0 or abs(k - spot) > spot * width:
                break
            sym = ds.format_symbol("C", currency, k, expiry)
            df = _probe_one(sym, expiry)
            if df.empty:
                misses += 1
                continue
            misses = 0
            df["symbol"] = sym
            frames.append(df)

    hits = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["time", "open", "high", "low", "close", "volume", "ts",
                 "symbol"])
    hits.to_parquet(_daily_dir(currency) / f"{expiry:%Y-%m-%d}.parquet",
                    compression="zstd", index=False)

    man = load_discovery_manifest(currency)
    man = man[man["expiry"] != pd.Timestamp(expiry)]
    row = pd.DataFrame([{
        "expiry": pd.Timestamp(expiry), "anchor_spot": spot, "width": width,
        "step": step, "n_hits": hits["symbol"].nunique(),
        "probed_at": pd.Timestamp.utcnow(),
    }])
    man = pd.concat([man, row], ignore_index=True).sort_values("expiry")
    man.to_parquet(discovery_manifest_path(currency), index=False)
    log.info("%s %s: %d strikes found (spot %.0f)", currency, expiry,
             hits["symbol"].nunique(), spot)
    return hits


def discover_range(currency: str, start: dt.date, end: dt.date,
                   dows: tuple[int, ...] = (4, 5, 6, 0, 1),
                   width: float = 0.10, force: bool = False) -> int:
    """Probe every expiry date in [start, end] whose weekday is in ``dows``
    (Monday=0). Default covers Fri through Tue: the weekend contracts plus the
    Tuesday weekday control."""
    man = load_discovery_manifest(currency)
    done = set()
    if not man.empty:
        done = set(pd.to_datetime(
            man.loc[man["width"] >= width, "expiry"]).dt.date)
    n = 0
    d = start
    while d <= end:
        if d.weekday() in dows and (force or d not in done):
            # One lost expiry must not kill an hours-long unattended run;
            # unrecorded expiries are re-probed on the next invocation.
            try:
                discover_expiry(currency, d, width=width)
                n += 1
            except Exception:
                log.exception("discovery failed for %s %s; continuing",
                              currency, d)
        d += dt.timedelta(days=1)
    return n


def discovered_symbols(currency: str) -> pd.DataFrame:
    """All discovered contracts: symbol, expiry, strike, plus traded volume."""
    rows = []
    for f in sorted(_daily_dir(currency).glob("*.parquet")):
        df = pd.read_parquet(f, columns=["symbol", "volume"])
        if df.empty:
            continue
        g = df.groupby("symbol")["volume"].sum().reset_index()
        rows.append(g)
    if not rows:
        return pd.DataFrame(columns=["symbol", "volume", "expiry", "strike"])
    out = pd.concat(rows, ignore_index=True)
    parsed = out["symbol"].map(ds.parse_symbol)
    out["expiry"] = [p["expiry_date"] for p in parsed]
    out["strike"] = [p["strike"] for p in parsed]
    return out


# ------------------------------------------------------- option hourly candles


def option_candle_path(currency: str, symbol: str, mark: bool):
    name = f"MARK-{symbol}.parquet" if mark else f"{symbol}.parquet"
    return _h1_dir(currency) / name


def backfill_option_candles(currency: str, force: bool = False,
                            max_moneyness: float = 0.06) -> int:
    """1h traded + mark candles for discovered calls and their put twins.

    Restricted to strikes within ``max_moneyness`` of the discovery anchor
    spot: the backtest trades near-ATM straddles, and the wings would triple
    the download for contracts nothing here prices.
    """
    disc = discovered_symbols(currency)
    man = load_discovery_manifest(currency)
    man = man.assign(expiry=pd.to_datetime(man["expiry"]).dt.date)
    disc = disc.merge(man[["expiry", "anchor_spot"]], on="expiry", how="left")
    keep = (disc["strike"] - disc["anchor_spot"]).abs()         <= disc["anchor_spot"] * max_moneyness
    disc = disc[keep]
    n = 0
    for _, row in disc.iterrows():
        e_ms = ds.expiry_ts_ms(row["expiry"])
        start = dt.datetime.fromtimestamp(e_ms / 1000, dt.timezone.utc) \
            - dt.timedelta(days=PROBE_LOOKBACK_DAYS + 1)
        end = dt.datetime.fromtimestamp(e_ms / 1000, dt.timezone.utc) \
            + dt.timedelta(hours=1)
        for side_sym in (row["symbol"], "P" + row["symbol"][1:]):
            for mark in (False, True):
                path = option_candle_path(currency, side_sym, mark)
                if path.exists() and not force:
                    continue
                query = ds.mark_symbol(side_sym) if mark else side_sym
                try:
                    df = fetch_candles(query, "1h",
                                       start.replace(tzinfo=None),
                                       end.replace(tzinfo=None))
                except Exception:
                    log.exception("candles failed for %s; continuing", query)
                    continue
                df.to_parquet(path, compression="zstd", index=False)
                n += 1
    return n


def load_option_candles(currency: str, symbol: str,
                        mark: bool = False) -> pd.DataFrame:
    p = option_candle_path(currency, symbol, mark)
    if not p.exists():
        raise FileNotFoundError(p)
    return pd.read_parquet(p)
