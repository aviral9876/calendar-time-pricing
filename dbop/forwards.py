"""The forward curve, built from Deribit's dated futures.

Why this module exists. Deribit prices an option against the forward for its own
expiry, not against the spot index -- the live book summary reports a distinct
``underlying_price`` per expiry, running from +0.02% at one day to +0.58% at six
weeks in a typical contango. Option *trade* records, however, carry only
``index_price``. Using the index as the forward therefore biases every
recomputed implied vol, and the bias grows with the basis: on 2021-04-15 the
median signed IV error reached +12 vol points at the 162-day expiry, where the
basis was 12.9%.

The forward could be backed out of put-call parity on the day's marks, and that
helps in calm periods, but it fails exactly when the paper most needs it: during
the FTX collapse the call and put marks used were struck hours apart while spot
moved 20%, implying an absurd -9.5% basis on an 8-day contract.

Dated futures solve it with traded prices rather than an estimate. There are
only ~480 of them per currency across the whole sample, so the whole curve is
cheap to collect. Only 19% of option expiries have an exactly matching future,
so the curve is interpolated in log-basis against maturity, anchored at zero
basis for zero maturity, and held flat beyond the longest listed future.

The forward matters for more than implied vol: it sets log-moneyness, which
sets the delta buckets, which is how the cross-sectional test is defined.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import api, bars, config, util

log = logging.getLogger(__name__)

CURVE_DIR = config.DATA / "forwards"
CURVE_DIR.mkdir(parents=True, exist_ok=True)


def list_dated_futures(currency: str) -> pd.DataFrame:
    """Every dated future ever listed, excluding the perpetual.

    USDC-settled books live under the exchange's "USDC" umbrella and have to be
    filtered back out by prefix, exactly as the option listing does. Querying
    with our own currency name instead returned nothing for SOL and XRP, and the
    caller treated that as "this asset has no futures" rather than as an error,
    so those two silently priced every option off the spot index.
    """
    api_cur = config.API_CURRENCY.get(currency, currency)
    prefix = config.INSTRUMENT_PREFIX.get(currency, f"{currency}-")
    rows = api.get_instruments(api_cur, kind="future", expired=True) + \
        api.get_instruments(api_cur, kind="future", expired=False)
    df = pd.DataFrame(rows)
    df = df[df["instrument_name"].str.startswith(prefix)]
    df = df[~df["instrument_name"].str.contains("PERPETUAL")].copy()
    if df.empty:
        raise RuntimeError(f"{currency}: no dated futures matched {prefix!r}")
    df = df.drop_duplicates("instrument_name")
    df["expiry"] = pd.to_datetime(df["expiration_timestamp"], unit="ms", utc=True)
    df["listed"] = pd.to_datetime(df["creation_timestamp"], unit="ms", utc=True)
    return df[["instrument_name", "expiration_timestamp", "expiry", "listed",
               "settlement_period"]].reset_index(drop=True)


def fetch_future_closes(currency: str) -> pd.DataFrame:
    """Daily closes for every dated future, over its own listed life."""
    fut = list_dated_futures(currency)
    frames = []
    for i, r in fut.iterrows():
        start = r["listed"].date()
        end = min(r["expiry"].date(),
                  dt.datetime.now(dt.timezone.utc).date())
        if end < start:
            continue
        b = bars.fetch_bars(r["instrument_name"], start, end, resolution="1D")
        if b.empty:
            continue
        b = b[["ts", "close"]].copy()
        b["instrument_name"] = r["instrument_name"]
        b["expiration_timestamp"] = r["expiration_timestamp"]
        frames.append(b)
        if (i + 1) % 50 == 0:
            log.info("%s: %d/%d futures fetched", currency, i + 1, len(fut))

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = util.to_utc_day(df["ts"]).to_numpy()
    df = df[df["close"] > 0]
    return df.groupby(["date", "instrument_name", "expiration_timestamp"],
                      as_index=False)["close"].last()


def build(currency: str, index_by_date: pd.Series | None = None) -> pd.DataFrame:
    """Store the (date, expiry, forward) points that define the daily curve."""
    df = fetch_future_closes(currency)
    if df.empty:
        log.warning("%s: no futures data", currency)
        return df

    if index_by_date is None:
        # The perpetual tracks spot closely and spans the whole futures era, so
        # it anchors the short end. Fetch it directly when the 5-minute bar
        # cache has not been built yet, so that building the curve does not
        # depend on the order the collectors happen to run in.
        try:
            pb = bars.load_daily(currency).copy()
        except FileNotFoundError:
            log.info("%s: daily perp bars missing, fetching them for the curve "
                     "anchor", currency)
            pb = bars.fetch_bars(config.PERPETUAL[currency],
                                 df["date"].min().date(),
                                 df["date"].max().date(), resolution="1D")
        if pb.empty:
            log.warning("%s: no perpetual data to anchor the curve", currency)
            return pd.DataFrame()
        pb["date"] = util.to_utc_day(pb["ts"]).to_numpy()
        index_by_date = pb.groupby("date")["close"].last()

    df["index_price"] = df["date"].map(index_by_date).astype("float64")
    df = df.dropna(subset=["index_price"])

    day_end_ms = (df["date"].astype("int64") // 10 ** 6) + 86_400_000
    ms_per_year = config.YEAR * 24 * 3600 * 1000
    df["T"] = np.maximum(
        (df["expiration_timestamp"] - day_end_ms) / ms_per_year, 0.0)
    df["log_basis"] = np.log(df["close"] / df["index_price"])

    # A future about to expire converges to spot mechanically; keeping those
    # points would let convergence noise dominate the short end of the curve.
    df = df[(df["T"] > 1 / 365) & df["log_basis"].abs().lt(1.0)]

    path = CURVE_DIR / f"{currency}_curve_points.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("%s: %d curve points over %d days (%s..%s)", currency, len(df),
             df["date"].nunique(), df["date"].min().date(),
             df["date"].max().date())
    return df


def load(currency: str) -> pd.DataFrame:
    return pd.read_parquet(CURVE_DIR / f"{currency}_curve_points.parquet")


class ForwardCurve:
    """One day's forward curve: log-basis interpolated against maturity.

    Anchored at zero basis for zero maturity (a forward to right now is spot)
    and flat beyond the longest listed future, which avoids extrapolating a
    slope into maturities nothing trades at.
    """

    def __init__(self, T: np.ndarray, log_basis: np.ndarray):
        order = np.argsort(T)
        self.T = np.concatenate([[0.0], np.asarray(T)[order]])
        self.b = np.concatenate([[0.0], np.asarray(log_basis)[order]])

    def basis(self, T) -> np.ndarray:
        T = np.asarray(T, dtype="float64")
        return np.interp(T, self.T, self.b, left=0.0, right=self.b[-1])

    def forward(self, index_price, T) -> np.ndarray:
        return np.asarray(index_price, dtype="float64") * np.exp(self.basis(T))


def curves_by_date(currency: str) -> dict:
    pts = load(currency)
    return {d: ForwardCurve(g["T"].to_numpy(), g["log_basis"].to_numpy())
            for d, g in pts.groupby("date", observed=True)}


def attach_forward(df: pd.DataFrame, curves: dict,
                   index_col: str = "index_price",
                   t_col: str = "T") -> np.ndarray:
    """Vectorized forward lookup for a frame carrying date, index price and T.

    Falls back to the index on days with no futures data, which is correct
    behaviour rather than a silent gap: before the futures curve exists the
    index is the only forward available.
    """
    out = df[index_col].to_numpy(dtype="float64").copy()
    for date, idx in df.groupby("date", observed=True).groups.items():
        curve = curves.get(date)
        if curve is None:
            continue
        loc = df.index.get_indexer(idx)
        out[loc] = curve.forward(df.loc[idx, index_col].to_numpy(),
                                 df.loc[idx, t_col].to_numpy())
    return out
