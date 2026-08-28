"""Load the option trade tape and attach instrument metadata and greeks.

This is the layer where the raw exchange feed becomes economic quantities: a
signed quantity of vega and gamma changing hands between an aggressor and a
passive counterparty.

Sign convention, used everywhere downstream:
    direction = +1  taker bought   -> END-USER demand +amount,
                                      passive side (presumed dealer) -amount
    direction = -1  taker sold     -> END-USER demand -amount,
                                      passive side (presumed dealer) +amount

The identifying assumption is that the passive side of a maker-taker book is
the intermediary. GPP observed end-user positions directly from OCC open/close
codes; we infer them from who crossed the spread. inventory.py carries the
tests that probe how far that assumption holds.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import backfill, config, greeks, instruments, util

log = logging.getLogger(__name__)

META_COLS = ["instrument_name", "strike", "expiration_timestamp", "cp",
             "contract_size", "settlement_period", "listed"]


def attach_instruments(df: pd.DataFrame, currency: str,
                       repair: bool = True) -> pd.DataFrame:
    """Join instrument metadata, repairing gaps in the bulk listing.

    A trade whose instrument has no strike or expiry cannot be priced or
    bucketed, so it must never be silently dropped. The bulk
    ``get_instruments`` listing turns out to be incomplete, so unknown
    instruments are first looked up individually (and cached); only if that
    also fails does this raise.
    """
    meta = instruments.load(currency)[META_COLS]
    out = df.merge(meta, on="instrument_name", how="left", validate="many_to_one")

    missing = out["strike"].isna()
    if missing.any() and repair:
        names = sorted(out.loc[missing, "instrument_name"].dropna().unique())
        log.info("%s: %d trades reference %d instruments absent from the bulk "
                 "listing; resolving individually", currency,
                 int(missing.sum()), len(names))
        instruments.resolve_missing(currency, names)
        meta = instruments.load(currency)[META_COLS]
        out = df.merge(meta, on="instrument_name", how="left",
                       validate="many_to_one")
        missing = out["strike"].isna()

    if missing.any():
        names = out.loc[missing, "instrument_name"].unique()
        raise ValueError(
            f"{int(missing.sum())} trades reference {len(names)} instruments "
            f"that are absent from {currency} metadata and could not be "
            f"resolved individually, e.g. {list(names[:5])}")
    return out


def load(currency: str, start: dt.date | None = None, end: dt.date | None = None,
         with_greeks: bool = True, columns: list[str] | None = None,
         curves: dict | None = None) -> pd.DataFrame:
    """Load a span of the tape, enriched with metadata and trade-time greeks.

    ``curves`` are the daily forward curves from dbop.forwards; when omitted
    they are loaded automatically if built, since using the raw index as the
    forward biases every greek in contango.
    """
    df = backfill.load_days(currency, start, end, columns=columns)
    if df.empty:
        return df

    df = attach_instruments(df, currency)
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["date"] = util.to_utc_day(df["ts"]).to_numpy()

    if with_greeks:
        if curves is None:
            from . import forwards
            try:
                curves = forwards.curves_by_date(currency)
            except FileNotFoundError:
                log.warning("%s: no forward curve built; falling back to the "
                            "index as forward", currency)
                curves = None
        df = greeks.enrich(df, iv_col="iv", curves=curves,
                           linear=config.LINEAR.get(currency, False))
        # Signed end-user demand in risk units, valued at the trade's own
        # greeks: this is the flow that hits dealer books at that instant.
        signed = df["direction"].to_numpy(dtype="float64") * \
            df["amount"].to_numpy(dtype="float64")
        df["signed_amount"] = signed
        df["signed_vega"] = signed * df["vega_usd"].to_numpy()
        df["signed_gamma"] = signed * df["gamma_usd"].to_numpy()
        df["notional_usd"] = df["amount"].to_numpy() * df["F"].to_numpy()
    return df


def baseline_filter(df: pd.DataFrame, exclude_blocks: bool = True,
                    exclude_combos: bool = True,
                    exclude_liquidations: bool = False) -> pd.DataFrame:
    """The demand sample used in the headline specifications.

    Block trades are negotiated bilaterally off the order book, so neither side
    is necessarily an intermediary absorbing flow, and the aggressor label
    carries a different meaning. Combo legs are reported alongside their parent
    and would double-count the same risk transfer. Liquidations are kept by
    default (forced flow is still flow a dealer must warehouse) and dropped
    only in robustness runs.
    """
    keep = pd.Series(True, index=df.index)
    if exclude_blocks:
        keep &= ~df["is_block"]
    if exclude_combos:
        keep &= ~df["is_combo"]
    if exclude_liquidations:
        keep &= ~df["is_liq"]
    return df.loc[keep].copy()


def daily_marks(df: pd.DataFrame) -> pd.DataFrame:
    """End-of-day mark per instrument, taken from its last trade of the day.

    Deribit's mark price is the exchange's own fitted surface value and is what
    margin and settlement use, so the last trade's mark_price/iv is a cleaner
    daily observation than the last traded price. Instruments whose last trade
    is old are flagged stale rather than dropped, so that the staleness can be
    conditioned on instead of silently biasing the surface.
    """
    df = df.sort_values("timestamp")
    g = df.groupby(["date", "instrument_name"], observed=True)
    agg = dict(
        mark_price=("mark_price", "last"),
        mark_iv=("iv", "last"),
        last_ts=("timestamp", "last"),
        index_price=("index_price", "last"),
        strike=("strike", "last"),
        cp=("cp", "last"),
        expiration_timestamp=("expiration_timestamp", "last"),
        n_trades=("trade_id", "size"),
        volume=("amount", "sum"),
    )
    # Carry the forward through when greeks have been attached; the surface
    # must be built in log-moneyness against the forward, not the index.
    if "F" in df.columns:
        agg["F"] = ("F", "last")
    out = g.agg(**agg).reset_index()

    day_end_ms = (out["date"].astype("int64") // 10 ** 6) + backfill.DAY_MS
    out["stale_hours"] = (day_end_ms - out["last_ts"]) / 3_600_000.0
    out["is_stale"] = out["stale_hours"] > config.MARK_STALENESS_HOURS
    return out


def volume_summary(currency: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-year descriptives for the market-structure table.

    Takes a narrow view of the frame rather than copying it: the enriched tape
    is ~24m rows by ~40 columns, and a full copy needs several gigabytes to
    produce a dozen summary rows.
    """
    if df is None:
        df = load(currency, with_greeks=False)
    if df.empty:
        return pd.DataFrame()

    cols = ["timestamp", "amount", "instrument_name", "is_block", "is_combo",
            "is_liq", "direction"]
    df = df[[c for c in cols if c in df.columns]]
    year = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.year
    g = df.groupby(year.rename("year"))
    out = pd.DataFrame({
        "n_trades": g.size(),
        "volume_coin": g["amount"].sum(),
        "n_instruments": g["instrument_name"].nunique(),
        "block_share": g["is_block"].mean(),
        "combo_share": g["is_combo"].mean(),
        "liq_share": g["is_liq"].mean(),
        "taker_buy_share": g["direction"].apply(lambda s: (s > 0).mean()),
    }).reset_index()
    out["currency"] = currency
    return out
