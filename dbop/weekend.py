"""Weekend risk: how much of an option's life falls on a weekend, and is it priced?

Crypto trades continuously, but the traditional financial system does not.
Realized variance still falls sharply at the weekend -- 42% for BTC, 39% for
ETH and 34% for SOL -- which
separates two things equity markets cannot: information arriving during
traditional market hours, and the mechanical effect of an exchange being shut.

Deribit lists daily expiries on all seven weekdays, so the fraction of an
option's remaining life that lands on a Saturday or Sunday varies continuously
across contracts trading at the same instant. That fraction is the regressor
this module builds; everything else here tests whether implied volatility
responds to it by as much as realized volatility does.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)

# Deribit expiries settle at 08:00 UTC.
EXPIRY_HOUR = config.EXPIRY_HOUR_UTC
HOUR_NS = 3_600_000_000_000

# The minimum raw columns needed to price a trade and apply the baseline
# filter. Loading the full ~40-column tape and filtering afterwards needs two
# copies of a 24m-row frame and runs out of memory; pass this to tape.load.
# Note these are the *stored* names: the block/combo/liquidation flags are
# derived once at write time and persisted, so the raw id columns they came
# from are not what downstream code reads.
LEAN_COLS = ["trade_id", "timestamp", "instrument_name", "price", "amount",
             "direction", "iv", "index_price", "mark_price",
             "is_block", "is_combo", "is_liq"]


DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
# 1970-01-01 was a Thursday, so within a week measured from the epoch, Saturday
# starts two days in and Sunday ends four days in.
_SAT_START = 2 * DAY_MS
_SUN_END = 4 * DAY_MS


def _ms_on_days_before(x: np.ndarray, day_start: int, day_end: int) -> np.ndarray:
    """Milliseconds falling in [day_start, day_end) of the epoch-week, over the
    interval [0, x). Closed form: whole weeks contribute a fixed amount and the
    remainder is a single clipped overlap."""
    span = day_end - day_start
    whole = (x // WEEK_MS) * span
    rem = x % WEEK_MS
    partial = np.clip(np.minimum(rem, day_end) - day_start, 0, span)
    return whole + partial


def weekend_fraction(start_ms, expiry_ms) -> np.ndarray:
    """Fraction of the interval [start, expiry) that falls on Sat or Sun (UTC).

    Exact and closed-form. Deribit expiries land at 08:00 UTC, so most contracts
    cover part-days at both ends and whole-day counting is wrong; an earlier
    version stepped through each contract's life in one-hour blocks, which was
    both approximate and slow enough (``np.add.at`` over a million rows, 336
    times) to dominate the runtime of every script that used it.
    """
    a = np.asarray(start_ms, dtype="int64")
    b = np.asarray(expiry_ms, dtype="int64")
    out = np.full(a.shape, np.nan, dtype="float64")
    span = (b - a).astype("float64")
    good = span > 0
    if not good.any():
        return out
    we = (_ms_on_days_before(b, _SAT_START, _SUN_END)
          - _ms_on_days_before(a, _SAT_START, _SUN_END)).astype("float64")
    out[good] = we[good] / span[good]
    return out


def all_day_fractions(start_ms, expiry_ms) -> np.ndarray:
    """Fraction of [start, expiry) falling on each weekday, shape (n, 7).

    Same closed form as ``weekend_fraction``, applied to each weekday in turn:
    Monday is three days into the epoch-week (1970-01-01 was a Thursday), and
    the columns are ordered Monday-first to match ``pandas`` dayofweek.
    """
    a = np.asarray(start_ms, dtype="int64")
    b = np.asarray(expiry_ms, dtype="int64")
    n = a.shape[0]
    out = np.full((n, 7), np.nan, dtype="float64")
    span = (b - a).astype("float64")
    good = span > 0
    if not good.any():
        return out
    for dow in range(7):
        offset = ((dow - 3) % 7) * DAY_MS      # Thursday epoch -> weekday slot
        ms = (_ms_on_days_before(b, offset, offset + DAY_MS)
              - _ms_on_days_before(a, offset, offset + DAY_MS)).astype("float64")
        out[good, dow] = ms[good] / span[good]
    return out


def attach(df: pd.DataFrame, ts_col: str = "timestamp",
           expiry_col: str = "expiration_timestamp") -> pd.DataFrame:
    """Add the weekend-coverage regressor and its companions to a trade frame."""
    out = df.copy()
    out["wknd_frac"] = weekend_fraction(out[ts_col].to_numpy(),
                                        out[expiry_col].to_numpy())
    exp = pd.to_datetime(out[expiry_col], unit="ms", utc=True)
    out["expiry_dow"] = exp.dt.dayofweek.astype("int8")
    out["expiry_is_weekend"] = (out["expiry_dow"] >= 5)
    # A calendar-time-neutral benchmark: 2/7 of any long-dated contract's life
    # is a weekend, so the interesting variation is the deviation from that.
    out["wknd_excess"] = out["wknd_frac"] - 2.0 / 7.0
    return out


def realized_by_daytype(bars_df: pd.DataFrame) -> pd.DataFrame:
    """Annualized realized vol per day, tagged weekday/weekend."""
    b = bars_df.copy()
    b["ts"] = pd.to_datetime(b["ts"], utc=True)
    b["r"] = np.log(b["close"].astype("float64")).diff()
    b["date"] = b["ts"].dt.normalize()
    rv = b.groupby("date")["r"].apply(lambda s: np.nansum(s.to_numpy() ** 2))
    rv = rv[rv > 0]
    out = pd.DataFrame({"rv_daily": rv})
    out["dow"] = out.index.dayofweek
    out["is_weekend"] = out["dow"] >= 5
    out["ann_vol"] = np.sqrt(out["rv_daily"] * config.YEAR)
    return out.reset_index()


def weekend_variance_ratio(rv: pd.DataFrame) -> dict:
    """Realized weekend variance relative to weekday, in variance units.

    Reported in variance rather than volatility because that is the unit an
    option prices: an implied vol quote for a contract spanning a weekend is a
    time-weighted average of variance over its life.

    The difference ``var_weekend - var_weekday`` is the realized counterpart of
    the fitted implied slope, and it carries a standard error that any test
    treating it as a known constant would understate -- SOL's rests on a
    quarter as many weekend days as BTC's. Daily realized variance is strongly
    right-skewed, so the reported standard error is the usual unequal-variance
    one on the difference of means, which is asymptotically fine at these
    sample sizes but should not be read as exact in small ones.
    """
    wk = rv.loc[~rv["is_weekend"], "rv_daily"]
    we = rv.loc[rv["is_weekend"], "rv_daily"]
    ratio = float(we.mean() / wk.mean())
    se_diff = float(np.sqrt(we.var(ddof=1) / len(we) + wk.var(ddof=1) / len(wk)))
    return {
        "var_weekday": float(wk.mean()),
        "var_weekend": float(we.mean()),
        "variance_ratio": ratio,
        "vol_ratio": float(np.sqrt(ratio)),
        "diff": float(we.mean() - wk.mean()),
        "se_diff": se_diff,
        "n_weekday": int(len(wk)),
        "n_weekend": int(len(we)),
    }


def implied_weekend_ratio(fit_slope: float, fit_intercept: float) -> float:
    """Back out the implied weekend/weekday variance ratio from a regression.

    Total variance over an option's life is
        sigma^2 * T = v_wd * (1 - w) * T + v_we * w * T
    with w the weekend fraction, so
        sigma^2 = v_wd + (v_we - v_wd) * w.
    Regressing squared implied vol on w gives intercept v_wd and slope
    (v_we - v_wd), hence the ratio below. A market that ignored weekends
    entirely would produce a slope of zero and a ratio of one.
    """
    if fit_intercept <= 0:
        return float("nan")
    return float((fit_intercept + fit_slope) / fit_intercept)
