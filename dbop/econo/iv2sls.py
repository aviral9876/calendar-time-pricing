"""The funding-cost instrument.

The identification problem in any demand-pressure regression is that
expensiveness and demand are jointly determined: options may be rich because
dealers are short, or dealers may be short because options got rich and
end users sold. GPP handled this with the institutional claim that end-user
demand is exogenous to dealers. Crypto offers something better.

A dealer who warehouses option risk hedges delta in the perpetual, and the
perpetual charges funding continuously. Funding is set by the perp basis --
leverage demand in the *linear* market -- and moves for reasons that have
nothing to do with anyone's view on options. It shifts the cost of carrying
inventory without shifting the desire to buy options. That gives a supply-side
cost shifter.

The instrument is Bartik-shaped:

    HC_t   = |delta inventory|_t  x  funding_t          (hedging cost)
    z_t    = fundshock_t x |delta inventory|_{t-1}      (shock x exposure)

with exposure predetermined. The exclusion restriction is that a funding
surprise affects option expensiveness only through what it costs dealers to
carry their hedge. It is not automatic -- funding and option demand can both
respond to a leverage cycle -- so ``falsification_suite`` implements three
tests that should fail if the restriction fails:

1. Placebo on buckets that are barely delta-hedged in the perp (far OTM, long
   dated). The channel cannot operate there, so the coefficient should vanish.
2. Sign flip. A funding shock should make options richer when dealers are
   short and cheaper when they are long. A coefficient that does not flip with
   the sign of inventory is picking up a common factor, not a cost channel.
3. Reduced form on the shock alone, which should be weak once inventory is
   near zero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS


# --------------------------------------------------------------- the shock


def funding_shock(market: pd.DataFrame, lags: int = 5,
                  controls: tuple[str, ...] = ("rv_annual_lag", "ret_5d_lag",
                                               "dvol_lag")) -> pd.DataFrame:
    """Residualize funding on its own lags and the lagged state.

    What a dealer could already have anticipated is not a shock. Projecting
    funding on its own history plus the lagged volatility and return state
    leaves the unforecastable component, which is what should shift hedging
    costs without being a proxy for the vol environment.
    """
    d = market.sort_values("date").copy()
    y = d["funding_day"]

    X = pd.DataFrame(index=d.index)
    for L in range(1, lags + 1):
        X[f"fund_l{L}"] = y.shift(L)
    for c in controls:
        if c in d.columns:
            X[c] = d[c]

    ok = y.notna() & X.notna().all(axis=1)
    d["funding_shock"] = np.nan
    if ok.sum() > 100:
        res = sm.OLS(y[ok], sm.add_constant(X[ok], has_constant="add")).fit()
        d.loc[ok, "funding_shock"] = res.resid
        d.attrs["shock_r2"] = float(res.rsquared)

    # Alternative measures kept alongside so the paper can show the result is
    # not an artifact of one construction.
    d["funding_surprise"] = d["funding_day"] - d["funding_day"].shift(1)
    d["funding_abs_shock"] = d["funding_shock"].abs()
    return d


def add_instrument(market: pd.DataFrame) -> pd.DataFrame:
    """Build the hedging-cost regressor and its Bartik instrument."""
    d = funding_shock(market)

    # Cost of carrying the delta hedge, in USD: the funding paid on the
    # notional the dealer must hold in the perp.
    d["hedge_cost"] = d["abs_delta_usd"] * d["funding_day"]
    # Scale so the coefficient is not dominated by market growth.
    scale = d["open_interest"].rolling(30, min_periods=5).mean().shift(1)
    d["hedge_cost_sc"] = d["hedge_cost"] / (scale * d["F"]).replace(0, np.nan)

    d["exposure_lag"] = d["abs_delta_usd_lag"] / (
        scale * d["F"]).replace(0, np.nan)
    d["z_bartik"] = d["funding_shock"] * d["exposure_lag"]
    return d


# ------------------------------------------------------------------- 2SLS


def first_stage(d: pd.DataFrame, endog: str = "hedge_cost_sc",
                instr: str = "z_bartik",
                controls: tuple[str, ...] = ("dvol_lag", "rv_annual_lag",
                                             "ret_5d_lag")) -> dict:
    xs = [instr] + [c for c in controls if c in d.columns]
    sub = d[[endog] + xs].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 100:
        return {"n": len(sub), "error": "insufficient observations"}
    res = sm.OLS(sub[endog], sm.add_constant(sub[xs], has_constant="add")).fit(
        cov_type="HAC", cov_kwds={"maxlags": 10})
    t = float(res.tvalues.get(instr, np.nan))
    return {
        "n": int(res.nobs),
        "coef": float(res.params.get(instr, np.nan)),
        "t": t,
        "F": t ** 2,           # single instrument: F is the squared t
        "r2": float(res.rsquared),
        "res": res,
    }


def two_stage(d: pd.DataFrame, y: str = "exp_atm_30",
              endog: str = "hedge_cost_sc", instr: str = "z_bartik",
              controls: tuple[str, ...] = ("dvol_lag", "rv_annual_lag",
                                           "ret_5d_lag")) -> dict:
    ctrl = [c for c in controls if c in d.columns]
    sub = d[[y, endog, instr] + ctrl].replace([np.inf, -np.inf],
                                              np.nan).dropna()
    if len(sub) < 100:
        return {"n": len(sub), "error": "insufficient observations"}

    exog = sm.add_constant(sub[ctrl], has_constant="add") if ctrl else \
        pd.DataFrame({"const": np.ones(len(sub))}, index=sub.index)
    res = IV2SLS(sub[y], exog, sub[[endog]], sub[[instr]]).fit(
        cov_type="kernel", kernel="bartlett")

    ols = sm.OLS(sub[y], sm.add_constant(sub[[endog] + ctrl],
                                         has_constant="add")).fit(
        cov_type="HAC", cov_kwds={"maxlags": 10})

    return {
        "n": int(res.nobs),
        "beta_iv": float(res.params.get(endog, np.nan)),
        "t_iv": float(res.tstats.get(endog, np.nan)),
        "beta_ols": float(ols.params.get(endog, np.nan)),
        "t_ols": float(ols.tvalues.get(endog, np.nan)),
        "first_stage": first_stage(d, endog, instr, controls),
        "res": res,
    }


# --------------------------------------------------------------- falsification


def sign_flip_test(d: pd.DataFrame, y: str = "exp_atm_30",
                   inv: str = "dealer_vega_sc_lag") -> dict:
    """Reduced form interacted with the sign of dealer inventory.

    If the funding channel is real, a funding shock should push expensiveness
    in opposite directions depending on whether dealers are short or long the
    risk being carried. A common-factor story predicts no such flip.
    """
    s = d.copy()
    s["short_dealer"] = (s[inv] < 0).astype(float)
    s["shock_x_short"] = s["funding_shock"] * s["short_dealer"]
    xs = ["funding_shock", "shock_x_short", "dvol_lag", "rv_annual_lag"]
    xs = [c for c in xs if c in s.columns]
    sub = s[[y] + xs].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 100:
        return {"n": len(sub), "error": "insufficient observations"}
    res = sm.OLS(sub[y], sm.add_constant(sub[xs], has_constant="add")).fit(
        cov_type="HAC", cov_kwds={"maxlags": 10})
    return {
        "n": int(res.nobs),
        "beta_shock": float(res.params.get("funding_shock", np.nan)),
        "beta_interaction": float(res.params.get("shock_x_short", np.nan)),
        "t_interaction": float(res.tvalues.get("shock_x_short", np.nan)),
        "res": res,
    }


def placebo_by_bucket(buckets: pd.DataFrame, market: pd.DataFrame,
                      y: str = "exp_bucket") -> pd.DataFrame:
    """Run the reduced form bucket by bucket.

    Deep OTM long-dated buckets carry little delta and are hardly hedged in the
    perp, so the funding channel cannot reach them. Finding the same
    coefficient there would indicate the instrument is picking up something
    other than hedging cost.
    """
    m = market[["date", "funding_shock", "dvol_lag", "rv_annual_lag"]].copy()
    d = buckets.merge(m, on="date", how="left")

    rows = []
    for b, g in d.groupby("bucket", observed=True):
        xs = [c for c in ("funding_shock", "dvol_lag", "rv_annual_lag")
              if c in g.columns]
        sub = g[[y] + xs + ["mean_abs_delta", "mean_tau"]].replace(
            [np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 150:
            continue
        res = sm.OLS(sub[y], sm.add_constant(sub[xs], has_constant="add")).fit(
            cov_type="HAC", cov_kwds={"maxlags": 10})
        rows.append({
            "bucket": b,
            "n": int(res.nobs),
            "mean_abs_delta": float(sub["mean_abs_delta"].mean()),
            "mean_tau": float(sub["mean_tau"].mean()),
            "beta_shock": float(res.params.get("funding_shock", np.nan)),
            "t_shock": float(res.tvalues.get("funding_shock", np.nan)),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("mean_abs_delta") if len(out) else out


def falsification_suite(market: pd.DataFrame,
                        buckets: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = add_instrument(market)
    out = {}

    fs = first_stage(d)
    out["first_stage"] = pd.DataFrame([{
        k: v for k, v in fs.items() if k != "res"}])

    ts = two_stage(d)
    out["two_stage"] = pd.DataFrame([{
        "n": ts.get("n"), "beta_iv": ts.get("beta_iv"), "t_iv": ts.get("t_iv"),
        "beta_ols": ts.get("beta_ols"), "t_ols": ts.get("t_ols"),
        "first_stage_F": ts.get("first_stage", {}).get("F"),
    }])

    sf = sign_flip_test(d)
    out["sign_flip"] = pd.DataFrame([{
        k: v for k, v in sf.items() if k != "res"}])

    out["placebo_buckets"] = placebo_by_bucket(buckets, d)
    return out
