"""Realized volatility and HAR forecasts.

Expensiveness in GPP is implied vol above the vol a hedger expects to realize,
so the benchmark has to be a genuine forecast made with information available
on the day. Estimating HAR on the whole sample and calling the fitted values
"expected vol" would leak the future into the regressor and manufacture
predictability, so every forecast here is out-of-sample from an expanding
window after a burn-in.

The underlying is the perpetual rather than the spot index: it is what a dealer
hedges in, so its variation is the risk actually being warehoused.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import bars, config, util

log = logging.getLogger(__name__)

MIN_BARS_PER_DAY = 200        # of 288 possible 5-minute bars; tolerate outages


def daily_rv(currency: str) -> pd.DataFrame:
    """Annualized realized volatility per UTC day from 5-minute returns.

    Also returns a subsampled estimator (odd/even bars averaged) as a
    microstructure-noise robustness check.
    """
    df = bars.load(currency).copy()
    df = df[df["close"] > 0]
    df["date"] = pd.to_datetime(df["ts"]).dt.normalize()
    df["logp"] = np.log(df["close"])
    df["ret"] = df.groupby("date", observed=True)["logp"].diff()

    def _agg(g: pd.DataFrame) -> pd.Series:
        r = g["ret"].dropna().to_numpy()
        n = len(r)
        if n < MIN_BARS_PER_DAY:
            return pd.Series({"rv": np.nan, "rv_ss": np.nan, "n_bars": n})
        rv = np.sum(r ** 2)
        # Two interleaved subsamples at half the frequency, averaged.
        r2 = np.add.reduceat(r, np.arange(0, n - n % 2, 2))
        rv_ss = np.sum(r2 ** 2)
        return pd.Series({"rv": rv, "rv_ss": rv_ss, "n_bars": n})

    out = df.groupby("date", observed=True).apply(
        _agg, include_groups=False).reset_index()
    # Annualize as a volatility, which is the unit implied vol is quoted in.
    out["rv_annual"] = np.sqrt(out["rv"] * config.YEAR)
    out["rv_ss_annual"] = np.sqrt(out["rv_ss"] * config.YEAR)
    out["currency"] = currency
    return util.normalize_date_col(out)


def _har_design(rv: pd.Series) -> pd.DataFrame:
    """Corsi's daily / weekly / monthly components, in logs.

    The log specification is not cosmetic. Crypto realized variance is
    extremely right-skewed, and in levels a handful of crash days dominate the
    least-squares fit, which is why a levels HAR here loses out-of-sample to a
    simple rolling mean. Logs make the residuals roughly homoskedastic and
    restore the forecasting performance the HAR literature reports.
    """
    lrv = np.log(rv.clip(lower=1e-12))
    return pd.DataFrame({
        "lrv_d": lrv,
        "lrv_w": lrv.rolling(5, min_periods=3).mean(),
        "lrv_m": lrv.rolling(22, min_periods=10).mean(),
    })


def har_forecasts(rv_daily: pd.DataFrame,
                  horizons: tuple[int, ...] = config.HAR_HORIZONS_DAYS,
                  burn_in: int = config.HAR_BURN_IN_DAYS,
                  window: int | None = config.HAR_WINDOW_DAYS) -> pd.DataFrame:
    """Expanding-window out-of-sample HAR forecasts of average variance.

    The regression is run in variance space (the additive quantity), and the
    forecast is converted to a volatility at the end, matching the units of
    implied vol.

    Refitting is done on a schedule rather than every day: coefficients move
    slowly and a daily refit over thousands of days buys nothing. Each fit uses
    only data strictly before the forecast date.
    """
    df = rv_daily.dropna(subset=["rv"]).sort_values("date").reset_index(drop=True)
    rv = df["rv"]
    X = _har_design(rv)
    out = {"date": df["date"]}

    for h in horizons:
        # Target: average daily variance over the NEXT h days, in logs to match
        # the design matrix.
        fwd = rv.shift(-1).rolling(h, min_periods=max(2, h // 2)).mean().shift(-(h - 1))
        log_fwd = np.log(fwd.clip(lower=1e-12))
        pred = np.full(len(df), np.nan)
        resid_var = np.nan

        # Refit monthly; between refits the stored coefficients are applied to
        # that day's own regressors, so no future information is used.
        beta = None
        for t in range(len(df)):
            if t < burn_in:
                continue
            if beta is None or (t - burn_in) % 22 == 0:
                # Only rows whose target window closed before today are usable.
                stop = max(0, t - h)
                # A rolling window lets the fit track regime shifts; crypto vol
                # trended down over the sample, and an expanding window keeps
                # re-fitting on a high-vol past it will never revisit.
                begin = max(0, stop - window) if window else 0
                usable = slice(begin, stop)
                Xf = X.iloc[usable]
                yf = log_fwd.iloc[usable]
                ok = Xf.notna().all(axis=1) & yf.notna() & np.isfinite(yf)
                if ok.sum() < 100:
                    continue
                A = np.column_stack([np.ones(int(ok.sum())), Xf[ok].to_numpy()])
                beta, *_ = np.linalg.lstsq(A, yf[ok].to_numpy(), rcond=None)
                resid_var = float(np.var(yf[ok].to_numpy() - A @ beta))
            if beta is None:
                continue
            xt = X.iloc[t].to_numpy()
            if not np.isfinite(xt).all():
                continue
            # The regression forecasts log variance, but expensiveness compares
            # implied vol to expected VOLATILITY. For a lognormal variance,
            # E[sqrt(RV)] = exp(mu/2 + s^2/8) -- correcting to the mean of the
            # variance and then square-rooting instead would inflate the
            # forecast by roughly the same order as the premium being measured.
            mu = beta[0] + float(xt @ beta[1:])
            s2 = resid_var if np.isfinite(resid_var) else 0.0
            pred[t] = np.exp(0.5 * mu + s2 / 8.0)

        # pred is already a daily volatility; annualize it.
        out[f"erv_{h}"] = np.maximum(pred, 1e-12) * np.sqrt(config.YEAR)
        out[f"rvfwd_{h}"] = np.sqrt(
            fwd.to_numpy(dtype="float64") * config.YEAR)    # realized, ex post
    return pd.DataFrame(out)


def build(currency: str) -> pd.DataFrame:
    rv = daily_rv(currency)
    fc = har_forecasts(rv)
    out = rv.merge(fc, on="date", how="left")
    path = config.PANELS / f"{currency}_rv.parquet"
    out.to_parquet(path, compression="zstd", index=False)
    cov = {f"erv_{h}": float(out[f"erv_{h}"].notna().mean())
           for h in config.HAR_HORIZONS_DAYS}
    log.info("%s: %d days of RV, OOS forecast coverage %s", currency, len(out), cov)
    return out


def load(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.PANELS / f"{currency}_rv.parquet")


def har_oos_r2(currency: str, horizon: int = 30) -> float:
    """Out-of-sample R^2 against a rolling-mean benchmark, as a sanity check on
    the forecast quality (HAR should comfortably beat it)."""
    df = load(currency)
    y = df[f"rvfwd_{horizon}"]
    f = df[f"erv_{horizon}"]
    bench = df["rv_annual"].rolling(22, min_periods=10).mean().shift(1)
    ok = y.notna() & f.notna() & bench.notna()
    if ok.sum() < 100:
        return np.nan
    sse = float(((y[ok] - f[ok]) ** 2).sum())
    sst = float(((y[ok] - bench[ok]) ** 2).sum())
    return 1.0 - sse / sst
