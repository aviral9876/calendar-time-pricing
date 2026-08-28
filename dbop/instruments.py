"""Option instrument metadata: strike, expiry, type, contract size.

Most of the sample is delisted, so the expired=true listing is the primary
source (~120k BTC instruments as of Aug 2026). Instrument names also encode
strike/expiry/type, and we cross-validate the two: a mismatch means either the
name convention changed or we are parsing the wrong currency, and both are
silent-corruption risks for every downstream greek.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from . import api, config

log = logging.getLogger(__name__)

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def parse_instrument_name(name: str) -> tuple[dt.datetime, float, str]:
    """'BTC-27DEC24-60000-C' -> (expiry_utc, strike, 'C').

    Deribit option expiries settle at 08:00 UTC on the named day.

    Sub-dollar underlyings encode the decimal point as a letter d, because the
    hyphen-delimited name has no room for a period: 'XRP_USDC-9MAR24-0d54-C' is
    a 0.54 strike. Every book whose strikes cross 1.0 mixes the two forms in the
    same expiry ('XRP_USDC-22MAR24-1-C'), so this cannot be switched on the
    currency; it has to be read off the field itself.
    """
    parts = name.split("-")
    if len(parts) != 4:
        raise ValueError(f"not an option instrument name: {name!r}")
    _, exp_s, strike_s, cp = parts
    # Day is 1 or 2 digits ('1JUN18', '27DEC24'); month is always 3 letters and
    # year 2 digits, so slice from the right.
    day = int(exp_s[:-5])
    mon = _MONTHS[exp_s[-5:-2].upper()]
    yr = 2000 + int(exp_s[-2:])
    expiry = dt.datetime(yr, mon, day, config.EXPIRY_HOUR_UTC,
                         tzinfo=dt.timezone.utc)
    strike = float(strike_s.replace("d", ".", 1))
    return expiry, strike, ("C" if cp.upper().startswith("C") else "P")


def fetch_instruments(currency: str) -> pd.DataFrame:
    """Union of expired and active option instruments for one currency.

    ``currency`` is ours, not the exchange's: SOL books live under the USDC
    umbrella, so the request goes out as USDC and the response is filtered back
    down by instrument prefix.
    """
    api_cur = config.API_CURRENCY.get(currency, currency)
    prefix = config.INSTRUMENT_PREFIX.get(currency, f"{currency}-")
    rows = []
    for expired in (True, False):
        chunk = api.get_instruments(api_cur, kind="option", expired=expired)
        kept = [r for r in chunk
                if str(r.get("instrument_name", "")).startswith(prefix)]
        log.info("%s: %d %s instruments (%d returned for %s)", currency,
                 len(kept), "expired" if expired else "active", len(chunk),
                 api_cur)
        rows.extend(kept)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"{currency}: no instruments matched {prefix!r}")
    keep = ["instrument_name", "strike", "expiration_timestamp",
            "creation_timestamp", "option_type", "contract_size",
            "settlement_period", "price_index", "is_active", "tick_size",
            "min_trade_amount", "instrument_id"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.drop_duplicates("instrument_name").reset_index(drop=True)

    df["currency"] = currency
    df["cp"] = df["option_type"].str[0].str.upper()
    df["expiry"] = pd.to_datetime(df["expiration_timestamp"], unit="ms", utc=True)
    df["listed"] = pd.to_datetime(df["creation_timestamp"], unit="ms", utc=True)
    df["expiry_date"] = df["expiry"].dt.date
    return df


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cross-check parsed instrument names against exchange metadata.

    A silently wrong strike or expiry would corrupt every greek, moneyness
    bucket and inventory weight downstream, so disagreements are never merged
    away. Strike and type mismatches raise outright. Expiry mismatches are
    quarantined instead, because the exchange has occasionally listed an
    instrument in error and killed it minutes later: as of Aug 2026 the only
    four such BTC cases were listed at 08:10 and expired 08:20 the same
    morning, with ETH-scale strikes, and never traded. Quarantined instruments
    are written out separately and excluded; any trade that later references
    one will fail the join in tape.attach_instruments rather than pass
    silently.

    Returns (clean, quarantined).
    """
    parsed = df["instrument_name"].map(parse_instrument_name)
    p_expiry = pd.Series(pd.to_datetime([p[0] for p in parsed], utc=True),
                         index=df.index)
    p_strike = pd.Series([p[1] for p in parsed], index=df.index)
    p_cp = pd.Series([p[2] for p in parsed], index=df.index)

    bad_strike = df.index[(p_strike - df["strike"]).abs() > 1e-6]
    bad_cp = df.index[p_cp != df["cp"]]
    if len(bad_strike) or len(bad_cp):
        problems = []
        for label, idx in (("strike", bad_strike), ("type", bad_cp)):
            if len(idx):
                sample = df.loc[idx, "instrument_name"].head(5).tolist()
                problems.append(f"{len(idx)} {label} mismatches, e.g. {sample}")
        raise ValueError("instrument metadata disagrees with parsed names: "
                         + "; ".join(problems))

    bad_expiry = df.index[p_expiry.dt.date != df["expiry"].dt.date]
    quarantine = df.loc[bad_expiry].copy()
    if len(quarantine):
        quarantine["parsed_expiry"] = p_expiry.loc[bad_expiry]
        quarantine["lifetime_min"] = (
            (quarantine["expiry"] - quarantine["listed"]).dt.total_seconds() / 60)
        log.warning("quarantining %d instruments whose name and metadata "
                    "expiries disagree: %s", len(quarantine),
                    quarantine["instrument_name"].head(6).tolist())
        df = df.drop(index=bad_expiry)

    # Expiry hour is informational only: every downstream time-to-expiry uses
    # the metadata timestamp, not the 08:00 convention. Deribit has listed a
    # minority of contracts expiring at 15:00 UTC.
    hours = df["expiry"].dt.hour.value_counts().to_dict()
    if set(hours) != {config.EXPIRY_HOUR_UTC}:
        log.info("option expiry hours present (UTC): %s", hours)
    return df.reset_index(drop=True), quarantine.reset_index(drop=True)


def build(currency: str) -> pd.DataFrame:
    df, quarantine = validate(fetch_instruments(currency))
    path = config.INSTRUMENTS / f"{currency}_options.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("wrote %s (%d instruments, %s..%s)", path, len(df),
             df["expiry_date"].min(), df["expiry_date"].max())
    if len(quarantine):
        qpath = config.INSTRUMENTS / f"{currency}_quarantined.parquet"
        quarantine.to_parquet(qpath, compression="zstd", index=False)
        log.warning("wrote %s (%d excluded instruments)", qpath, len(quarantine))
    return df


def load(currency: str) -> pd.DataFrame:
    path = config.INSTRUMENTS / f"{currency}_options.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run scripts/run_backfill.py --instruments")
    return pd.read_parquet(path)


def resolve_missing(currency: str, names: list[str]) -> pd.DataFrame:
    """Fetch instruments the bulk listing omitted, one at a time.

    ``get_instruments(expired=true)`` is not exhaustive: as of Aug 2026 it
    returned 1,464 BTC instruments expiring in July 2026 while omitting 26 that
    had traded and that ``get_instrument`` resolves without complaint. Rather
    than drop those trades or guess their terms, look each one up individually,
    cross-check it against the parsed name exactly as the bulk path does, and
    append it to the cached metadata so the gap is filled once.
    """
    rows, failed = [], []
    for name in names:
        try:
            rows.append(api.get("get_instrument", {"instrument_name": name},
                                base=config.HISTORY_BASE))
        except Exception:
            try:
                rows.append(api.get("get_instrument", {"instrument_name": name},
                                    base=config.LIVE_BASE))
            except Exception as exc:
                failed.append((name, str(exc)[:80]))

    if failed:
        log.warning("%s: %d instruments unresolvable individually, e.g. %s",
                    currency, len(failed), failed[:3])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    keep = ["instrument_name", "strike", "expiration_timestamp",
            "creation_timestamp", "option_type", "contract_size",
            "settlement_period", "price_index", "is_active", "tick_size",
            "min_trade_amount", "instrument_id"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["currency"] = currency
    df["cp"] = df["option_type"].str[0].str.upper()
    df["expiry"] = pd.to_datetime(df["expiration_timestamp"], unit="ms", utc=True)
    df["listed"] = pd.to_datetime(df["creation_timestamp"], unit="ms", utc=True)
    df["expiry_date"] = df["expiry"].dt.date

    clean, quarantined = validate(df)
    if len(quarantined):
        log.warning("%s: %d individually-fetched instruments quarantined",
                    currency, len(quarantined))

    if len(clean):
        path = config.INSTRUMENTS / f"{currency}_options.parquet"
        existing = pd.read_parquet(path)
        merged = (pd.concat([existing, clean], ignore_index=True)
                    .drop_duplicates("instrument_name")
                    .reset_index(drop=True))
        merged.to_parquet(path, compression="zstd", index=False)
        log.info("%s: filled %d metadata gaps from get_instrument (%d -> %d)",
                 currency, len(clean), len(existing), len(merged))
    return clean


def load_all() -> pd.DataFrame:
    return pd.concat([load(c) for c in config.CURRENCIES], ignore_index=True)
