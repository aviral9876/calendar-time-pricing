"""Resumable backfill of the Deribit option trade tape.

Unit of work is one (currency, UTC day). Each completed day is written as a
zstd parquet and recorded in a manifest, so a run killed at any point resumes
by skipping days already marked complete.

Pagination subtlety: the endpoint returns at most 1000 trades and a has_more
flag. The next page must start at the LAST timestamp seen, not that timestamp
plus one millisecond, because many trades share a millisecond and advancing
past it silently drops them. That re-requests the boundary millisecond, so
pages overlap by a few trades and we deduplicate on trade_id.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import api, config

log = logging.getLogger(__name__)

DAY_MS = 86_400_000

# Fields Deribit always returns for an option trade. Note that `contracts` is
# NOT reliable historically: it is absent (NaN) for the whole early sample and
# only appears in recent years. `amount`, quoted in units of the underlying
# coin, is the authoritative quantity everywhere and is what inventory uses.
CORE_FIELDS = ["trade_id", "trade_seq", "timestamp", "instrument_name", "price",
               "amount", "contracts", "direction", "iv", "index_price",
               "mark_price", "tick_direction"]
# Fields present only when applicable (block trades ~1.3% of trades,
# combos ~0.7%, liquidations ~0.03%), so they must be filled, not assumed.
OPTIONAL_FIELDS = ["liquidation", "block_trade_id", "block_trade_leg_count",
                   "block_rfq_id", "combo_id", "combo_trade_id"]

_manifest_lock = threading.Lock()


# ------------------------------------------------------------------- paths


def day_path(currency: str, day: dt.date, kind: str = "option"):
    d = config.OPTION_TRADES / currency if kind == "option" else \
        config.TRADES / kind / currency
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{currency}-{day:%Y-%m-%d}.parquet"


def manifest_path(currency: str, kind: str = "option"):
    return config.MANIFEST / f"{kind}_{currency}.parquet"


def load_manifest(currency: str, kind: str = "option") -> pd.DataFrame:
    p = manifest_path(currency, kind)
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=["date", "n_trades", "n_requests", "first_ts",
                                 "last_ts", "complete", "fetched_at"])


def _record(currency: str, kind: str, row: dict) -> None:
    with _manifest_lock:
        man = load_manifest(currency, kind)
        man = man[man["date"] != row["date"]]
        man = pd.concat([man, pd.DataFrame([row])], ignore_index=True)
        man = man.sort_values("date").reset_index(drop=True)
        man.to_parquet(manifest_path(currency, kind), compression="zstd",
                       index=False)


def completed_days(currency: str, kind: str = "option") -> set:
    man = load_manifest(currency, kind)
    if man.empty:
        return set()
    return set(man.loc[man["complete"].astype(bool), "date"])


# ------------------------------------------------------------------ fetching


def _to_ms(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day,
                           tzinfo=dt.timezone.utc).timestamp() * 1000)


def fetch_day_trades(currency: str, day: dt.date, kind: str = "option"
                     ) -> tuple[list[dict], int]:
    """All trades in one UTC day. Returns (deduplicated trades, n_requests)."""
    start, end = _to_ms(day), _to_ms(day) + DAY_MS - 1
    cursor, seen, out, n_req = start, set(), [], 0
    # SOL trades arrive inside the shared USDC feed, so pagination must run on
    # the full feed and the filter applied per page -- filtering the request
    # is not possible, and filtering after pagination would break the cursor.
    api_cur = config.API_CURRENCY.get(currency, currency)
    prefix = config.INSTRUMENT_PREFIX.get(currency, f"{currency}-")

    while True:
        page, has_more = api.get_last_trades_by_currency_and_time(
            api_cur, cursor, end, kind=kind,
            count=config.TRADES_PAGE_SIZE, sorting="asc")
        n_req += 1
        if not page:
            break

        fresh = [t for t in page
                 if t["trade_id"] not in seen
                 and str(t.get("instrument_name", "")).startswith(prefix)]
        seen.update(t["trade_id"] for t in page)
        out.extend(fresh)

        if not has_more:
            break

        nxt = max(t["timestamp"] for t in page)
        if nxt <= cursor and not fresh:
            # Every trade in the window shares one millisecond and we have
            # already taken them all; advancing is the only way to progress.
            nxt = cursor + 1
            if nxt > end:
                break
        cursor = nxt
        if n_req > 5000:
            raise RuntimeError(f"runaway pagination on {currency} {day}")

    return out, n_req


def normalize(trades: list[dict], currency: str) -> pd.DataFrame:
    """Raw JSON -> typed frame. Direction becomes the aggressor sign: +1 when
    the taker bought (so the passive counterparty, presumed intermediary, is
    short), -1 when the taker sold."""
    df = pd.DataFrame(trades)
    if df.empty:
        return pd.DataFrame(columns=CORE_FIELDS + OPTIONAL_FIELDS)

    for col in OPTIONAL_FIELDS:
        if col not in df.columns:
            df[col] = None
    for col in CORE_FIELDS:
        if col not in df.columns:
            df[col] = pd.NA

    df["direction"] = df["direction"].map({"buy": 1, "sell": -1}).astype("int8")
    df["timestamp"] = df["timestamp"].astype("int64")
    df["trade_seq"] = pd.to_numeric(df["trade_seq"], errors="coerce").astype("int64")
    for c in ("price", "amount", "contracts", "index_price", "mark_price"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["iv"] = pd.to_numeric(df["iv"], errors="coerce").astype("float32")
    df["tick_direction"] = pd.to_numeric(
        df["tick_direction"], errors="coerce").fillna(-1).astype("int8")
    df["liquidation"] = df["liquidation"].fillna("").astype(str)
    df["block_trade_leg_count"] = pd.to_numeric(
        df["block_trade_leg_count"], errors="coerce").fillna(0).astype("int16")
    for c in ("trade_id", "instrument_name", "block_trade_id", "block_rfq_id",
              "combo_id", "combo_trade_id"):
        df[c] = df[c].astype("string")

    df["is_block"] = df["block_trade_id"].notna()
    df["is_combo"] = df["combo_id"].notna() | df["combo_trade_id"].notna()
    df["is_liq"] = df["liquidation"].ne("")
    df["currency"] = currency

    df = df.sort_values(["timestamp", "trade_id"]).reset_index(drop=True)
    return df[CORE_FIELDS + OPTIONAL_FIELDS
              + ["is_block", "is_combo", "is_liq", "currency"]]


def check_sequences(df: pd.DataFrame, currency: str, day: dt.date) -> int:
    """Per-instrument trade_seq should advance without gaps within a day.

    Gaps are logged rather than raised: a genuine gap at a day boundary is
    expected, and Deribit reuses trade_seq per instrument, so this is a
    completeness signal, not an invariant.
    """
    if df.empty:
        return 0
    gaps = 0
    for name, g in df.groupby("instrument_name", observed=True):
        s = g["trade_seq"].to_numpy()
        d = s[1:] - s[:-1]
        gaps += int((d > 1).sum())
    if gaps:
        log.debug("%s %s: %d trade_seq gaps (expected at day boundaries)",
                  currency, day, gaps)
    return gaps


def backfill_day(currency: str, day: dt.date, kind: str = "option",
                 force: bool = False) -> int:
    """Fetch, normalize and cache one currency-day. Returns trade count."""
    path = day_path(currency, day, kind)
    if path.exists() and not force:
        return int(pd.read_parquet(path, columns=["timestamp"]).shape[0])

    trades, n_req = fetch_day_trades(currency, day, kind)
    df = normalize(trades, currency)
    gaps = check_sequences(df, currency, day)

    if len(df):
        df.to_parquet(path, compression="zstd", index=False)
    elif path.exists():
        path.unlink()

    _record(currency, kind, {
        "date": day.isoformat(),
        "n_trades": len(df),
        "n_requests": n_req,
        "first_ts": int(df["timestamp"].iloc[0]) if len(df) else 0,
        "last_ts": int(df["timestamp"].iloc[-1]) if len(df) else 0,
        "seq_gaps": gaps,
        "complete": True,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    return len(df)


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def backfill(currency: str, start: dt.date | None = None,
             end: dt.date | None = None, kind: str = "option",
             workers: int = config.BACKFILL_WORKERS,
             force: bool = False) -> int:
    """Backfill a date span, skipping days already marked complete."""
    start = start or config.SAMPLE_START[currency]
    end = end or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))

    days = date_range(start, end)
    if not force:
        done = completed_days(currency, kind)
        days = [d for d in days if d.isoformat() not in done]
    if not days:
        log.info("%s %s: nothing to do", currency, kind)
        return 0

    log.info("%s %s: %d days to fetch (%s..%s) with %d workers",
             currency, kind, len(days), days[0], days[-1], workers)

    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(backfill_day, currency, d, kind, force): d
                   for d in days}
        for i, fut in enumerate(as_completed(futures), 1):
            day = futures[fut]
            try:
                total += fut.result()
            except Exception as exc:  # one bad day must not kill an overnight run
                log.warning("failed %s %s: %s", currency, day, exc)
            if i % 100 == 0:
                log.info("  %d/%d days, %d trades so far", i, len(days), total)
    log.info("%s %s: done, %d trades", currency, kind, total)
    return total


# ------------------------------------------------------------------- loading


def load_days(currency: str, start: dt.date | None = None,
              end: dt.date | None = None, columns: list[str] | None = None,
              kind: str = "option") -> pd.DataFrame:
    """Concatenate cached day files in a span."""
    start = start or config.SAMPLE_START[currency]
    end = end or dt.date.today()
    frames = []
    for d in date_range(start, end):
        p = day_path(currency, d, kind)
        if p.exists():
            frames.append(pd.read_parquet(p, columns=columns))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
