"""Assemble the regression panels from the constructed pieces.

Two units of observation:

``market_panel``   one row per (currency, date). Drives the time-series tests
                   and the funding-cost instrument.
``bucket_panel``   one row per (currency, date, bucket). Drives the
                   cross-sectional test, where day fixed effects absorb the
                   market-wide level of vol and identification comes from which
                   parts of the surface dealers are short.

Everything that enters the right-hand side is lagged or predetermined at the
point of use; the lagging happens here, once, rather than in each regression.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import bars, config, expensiveness, funding, inventory, rv, util

log = logging.getLogger(__name__)


def _match_horizon(tau_days: float) -> int:
    return min(config.HAR_HORIZONS_DAYS, key=lambda h: abs(h - tau_days))


def build_market(currency: str, market: pd.DataFrame, grid: pd.DataFrame,
                 dh_agg: pd.DataFrame, mfiv: pd.DataFrame | None = None
                 ) -> pd.DataFrame:
    """One row per date: dealer inventory, expensiveness, controls."""
    rvd = util.normalize_date_col(rv.load(currency))
    fnd = util.normalize_date_col(funding.daily(currency))

    df = util.normalize_date_col(market)
    df["currency"] = currency

    # Inventory legitimately runs to each instrument's expiry, so the position
    # panel extends past the last day the market was observed -- for BTC as far
    # as 2027. Those rows have exposures but no prices, so they are not
    # observations of anything; cut the panel at the last day with a surface.
    g = util.normalize_date_col(grid)
    if len(g):
        last = g["date"].max()
        n_future = int((df["date"] > last).sum())
        if n_future:
            log.info("%s: dropping %d panel rows beyond the last observed "
                     "trading day (%s)", currency, n_future, last.date())
            df = df[df["date"] <= last]
    df = df.merge(g, on="date", how="left", suffixes=("", "_grid"))
    df = df.merge(rvd, on="date", how="left", suffixes=("", "_rv"))
    df = df.merge(fnd[["date", "funding_day", "funding_8h_mean",
                       "funding_1h_std"]], on="date", how="left")
    df = df.merge(util.normalize_date_col(dh_agg), on="date", how="left")
    if mfiv is not None and len(mfiv):
        # variance_risk_premium carries rv columns along for its own
        # arithmetic; keep only what is new here or the merge collides with the
        # forecast columns already joined above.
        mf = util.normalize_date_col(mfiv)
        new = ["date"] + [c for c in mf.columns
                          if c not in df.columns and c != "date"]
        df = df.merge(mf[new], on="date", how="left")

    try:
        dv = util.normalize_date_col(bars.dvol_daily(currency))
        df = df.merge(dv[["date", "dvol"]], on="date", how="left")
    except FileNotFoundError:
        log.warning("%s: no DVOL file; control will be missing", currency)
        df["dvol"] = np.nan

    # Expensiveness at each grid maturity against the matched forecast horizon.
    for tau in config.GRID_TAUS_DAYS:
        atm, h = f"atm_{tau}", _match_horizon(tau)
        if atm in df.columns:
            df[f"exp_atm_{tau}"] = df[atm] - df[f"erv_{h}"]
            df[f"expost_atm_{tau}"] = df[atm] - df[f"rvfwd_{h}"]

    # Underlying return and its trailing window, as risk-appetite controls.
    df = df.sort_values("date").reset_index(drop=True)
    df["ret_1d"] = np.log(df["F"]).diff()
    df["ret_5d"] = np.log(df["F"]).diff(5)

    # Scale inventory by trailing gross vega traded (market size), lagged so
    # the scaler is knowable on the day.
    for c in ("dealer_vega", "dealer_gamma", "dealer_delta_usd"):
        scale = (df["open_interest"]
                 .rolling(config.INVENTORY_SCALE_WINDOW_DAYS, min_periods=5)
                 .mean().shift(1))
        df[f"{c}_sc"] = df[c] / scale.replace(0, np.nan)

    # Rolling z-score as the alternative normalization.
    for c in ("dealer_vega", "dealer_gamma"):
        m = df[c].rolling(252, min_periods=60).mean().shift(1)
        s = df[c].rolling(252, min_periods=60).std().shift(1)
        df[f"{c}_z"] = (df[c] - m) / s.replace(0, np.nan)

    for c in ("dealer_vega_sc", "dealer_gamma_sc", "dealer_delta_usd_sc",
              "dealer_vega_z", "dealer_gamma_z", "funding_day", "dvol",
              "rv_annual", "ret_5d"):
        if c in df.columns:
            df[f"{c}_lag"] = df[c].shift(1)

    df["abs_delta_usd_lag"] = df["abs_delta_usd"].shift(1)
    return df


def build_buckets(currency: str, buckets: pd.DataFrame) -> pd.DataFrame:
    """One row per (date, bucket), with bucket expensiveness and lagged demand."""
    rvd = util.normalize_date_col(rv.load(currency))
    df = util.normalize_date_col(buckets)
    df["currency"] = currency
    df = df.merge(rvd[["date"] + [f"erv_{h}" for h in config.HAR_HORIZONS_DAYS]],
                  on="date", how="left")

    # Each bucket's expensiveness uses the forecast horizon closest to the
    # bucket's own mean maturity.
    h_col = df["mean_tau"].map(_match_horizon)
    erv = np.full(len(df), np.nan)
    for h in config.HAR_HORIZONS_DAYS:
        m = (h_col == h).to_numpy()
        erv[m] = df.loc[m, f"erv_{h}"].to_numpy()
    df["erv_matched"] = erv
    df["exp_bucket"] = df["iv_bucket"] - df["erv_matched"]

    df = df.sort_values(["bucket", "date"])
    g = df.groupby("bucket", observed=True)

    # Scale each bucket's inventory by its own trailing gross vega, so buckets
    # of very different size are comparable.
    scale = g["gross_vega"].transform(
        lambda s: s.rolling(config.INVENTORY_SCALE_WINDOW_DAYS,
                            min_periods=5).mean().shift(1))
    for c in ("dealer_vega", "dealer_gamma"):
        df[f"{c}_sc"] = df[c] / scale.replace(0, np.nan)

    g = df.groupby("bucket", observed=True)
    for c in ("dealer_vega_sc", "dealer_gamma_sc", "exp_bucket"):
        df[f"{c}_lag"] = g[c].shift(1)
    df["d_exp_bucket"] = df["exp_bucket"] - df["exp_bucket_lag"]
    return df.reset_index(drop=True)


def save(currency: str, market: pd.DataFrame, buckets: pd.DataFrame) -> None:
    market.to_parquet(config.PANELS / f"{currency}_market.parquet",
                      compression="zstd", index=False)
    buckets.to_parquet(config.PANELS / f"{currency}_buckets.parquet",
                       compression="zstd", index=False)
    log.info("%s: market panel %d rows, bucket panel %d rows",
             currency, len(market), len(buckets))


def load_market(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.PANELS / f"{currency}_market.parquet")


def load_buckets(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.PANELS / f"{currency}_buckets.parquet")


def load_market_all() -> pd.DataFrame:
    return pd.concat([load_market(c) for c in config.CURRENCIES],
                     ignore_index=True)


def load_buckets_all() -> pd.DataFrame:
    return pd.concat([load_buckets(c) for c in config.CURRENCIES],
                     ignore_index=True)
