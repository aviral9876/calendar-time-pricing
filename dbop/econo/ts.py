"""Time-series tests: does aggregate dealer inventory price the vol surface?

GPP's first prediction. When end users are net long options, dealers are net
short and must be compensated for warehousing that risk, so options trade rich
and subsequent delta-hedged returns to the long side are low. The signs to
expect, with I = dealer vega inventory:

    expensiveness_t  on  -I_{t-1}     positive
    dh_return_{t->t+h} on  I_t        positive

Overlapping forward returns make the errors autocorrelated by construction, so
every standard error here is Newey-West with a bandwidth that covers the
horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def _prep(df: pd.DataFrame, y: str, xs: list[str]) -> tuple:
    cols = [y] + xs
    d = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < 60:
        return None, None, d
    X = sm.add_constant(d[xs], has_constant="add")
    return d[y], X, d


def newey_west(df: pd.DataFrame, y: str, xs: list[str], lags: int | None = None,
               horizon: int = 1) -> dict:
    """OLS with HAC standard errors."""
    yv, X, d = _prep(df, y, xs)
    if yv is None:
        return {"n": len(d), "error": "insufficient observations"}
    L = lags if lags is not None else horizon + 5
    res = sm.OLS(yv, X).fit(cov_type="HAC", cov_kwds={"maxlags": L})
    return {
        "n": int(res.nobs),
        "r2": float(res.rsquared),
        "params": res.params.to_dict(),
        "tstats": res.tvalues.to_dict(),
        "pvalues": res.pvalues.to_dict(),
        "lags": L,
        "res": res,
    }


def inventory_on_expensiveness(market: pd.DataFrame,
                               y: str = "exp_atm_30",
                               inv: str = "dealer_vega_sc_lag",
                               controls: tuple[str, ...] = (
                                   "dvol_lag", "rv_annual_lag", "ret_5d_lag",
                                   "funding_day_lag"),
                               use_controls: bool = True) -> dict:
    """Expensiveness on (minus) lagged dealer vega inventory.

    The regressor is negated so that a positive coefficient means "options are
    richer when dealers are short vol", which is GPP's prediction stated in the
    direction the reader expects.
    """
    d = market.copy()
    d["neg_inv"] = -d[inv]
    xs = ["neg_inv"] + ([c for c in controls if c in d.columns]
                        if use_controls else [])
    return newey_west(d, y, xs, horizon=1)


def inventory_predicts_returns(market: pd.DataFrame, horizon: int = 5,
                               inv: str = "dealer_vega_sc",
                               ret: str = "dh_ret_vw",
                               controls: tuple[str, ...] = (
                                   "dvol_lag", "rv_annual_lag")) -> dict:
    """Forward delta-hedged returns on current dealer inventory.

    The cleanest version of the test: delta-hedged returns are a traded payoff,
    so this needs no volatility forecast at all.
    """
    d = market.sort_values("date").copy()
    d[f"fwd_{horizon}"] = (d[ret].shift(-1).rolling(horizon, min_periods=horizon)
                           .mean().shift(-(horizon - 1)))
    xs = [inv] + [c for c in controls if c in d.columns]
    return newey_west(d, f"fwd_{horizon}", xs, horizon=horizon)


def changes_spec(market: pd.DataFrame, y: str = "exp_atm_30",
                 flow: str = "dealer_vega_sc") -> dict:
    """First differences: does the CHANGE in expensiveness track the day's flow?

    Levels regressions on persistent series risk spurious fit; the differenced
    version is the demanding counterpart.
    """
    d = market.sort_values("date").copy()
    d["d_y"] = d[y].diff()
    d["d_inv"] = -d[flow].diff()
    return newey_west(d, "d_y", ["d_inv"], horizon=1)


def summarize(results: dict[str, dict], key: str) -> pd.DataFrame:
    """Collect several specifications into one comparable table."""
    rows = []
    for label, r in results.items():
        if "error" in r:
            rows.append({"spec": label, "n": r["n"], "beta": np.nan,
                         "t": np.nan, "p": np.nan, "r2": np.nan})
            continue
        rows.append({
            "spec": label,
            "n": r["n"],
            "beta": r["params"].get(key, np.nan),
            "t": r["tstats"].get(key, np.nan),
            "p": r["pvalues"].get(key, np.nan),
            "r2": r["r2"],
        })
    return pd.DataFrame(rows)
