"""Black-76 pricing and greeks for Deribit's inverse options.

Two conventions matter here and both are easy to get silently wrong.

*Inverse quotation.* Deribit option premia are quoted in the underlying coin,
not in dollars: a price of 0.028 means 0.028 BTC. The USD premium is
``price_coin * F``. All greeks below are returned in USD per contract (one
contract = one coin of notional, contract_size = 1.0) unless the name says
otherwise, because the demand-pressure weights in GPP are risk exposures, and
mixing coin- and USD-denominated exposures across a sample where the coin price
moves 100x would make the panel meaningless.

*Zero rates.* Crypto has no clean risk-free curve, and Deribit's own marks use
r = 0 with the forward taken from the index. We follow that: F = index price,
no discounting. The synthetic put-call-parity forward is available as a
robustness check in surfaces.py.

*Hedging in the perp.* A dealer hedges an inverse option with an inverse
perpetual, whose own coin-denominated value depends on the spot. The correct
hedge ratio is therefore the premium-adjusted delta, ``delta_bs - price_coin``,
not the textbook Black delta.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from . import config

SQRT_EPS = 1e-12


def _d1_d2(F, K, T, sigma):
    F = np.asarray(F, dtype="float64")
    K = np.asarray(K, dtype="float64")
    T = np.asarray(T, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    vol_t = sigma * np.sqrt(np.maximum(T, SQRT_EPS))
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / vol_t
        d2 = d1 - vol_t
    return d1, d2


def price_usd(F, K, T, sigma, cp):
    """Black-76 option value in USD, r = 0.

    ``cp`` is +1 for a call, -1 for a put (or an array of those).
    """
    F = np.asarray(F, dtype="float64")
    K = np.asarray(K, dtype="float64")
    T = np.asarray(T, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    cp = np.asarray(cp, dtype="float64")

    intrinsic = np.maximum(cp * (F - K), 0.0)
    d1, d2 = _d1_d2(F, K, T, sigma)
    val = cp * (F * norm.cdf(cp * d1) - K * norm.cdf(cp * d2))
    # At zero maturity or zero vol the formula is 0/0; the option is worth
    # intrinsic value.
    degenerate = (T <= 0) | (sigma <= 0)
    return np.where(degenerate, intrinsic, val)


def price_coin(F, K, T, sigma, cp):
    """Premium in coin units, which is how Deribit quotes and settles."""
    return price_usd(F, K, T, sigma, cp) / np.asarray(F, dtype="float64")


def implied_vol_scalar(price_usd_obs, F, K, T, cp,
                       lo=config.IV_MIN, hi=config.IV_MAX) -> float:
    """Invert Black-76 for one observation; nan when no arbitrage-free root.

    Brent on a monotone function, same approach as the rough-vol pipeline's
    inverter but on the forward measure.
    """
    if not np.isfinite(price_usd_obs) or price_usd_obs <= 0 or T <= 0:
        return np.nan
    intrinsic = max(cp * (F - K), 0.0)
    # Below intrinsic or above the trivial upper bound there is no solution.
    upper = F if cp > 0 else K
    if price_usd_obs < intrinsic - 1e-8 or price_usd_obs > upper + 1e-8:
        return np.nan

    def obj(s):
        return float(price_usd(F, K, T, s, cp)) - price_usd_obs

    try:
        f_lo, f_hi = obj(lo), obj(hi)
        if f_lo > 0 or f_hi < 0:
            return np.nan
        return float(brentq(obj, lo, hi, maxiter=100, xtol=1e-10))
    except (ValueError, RuntimeError):
        return np.nan


def implied_vol(price_usd_obs, F, K, T, cp) -> np.ndarray:
    """Vectorized wrapper. Loops in Python because Brent is scalar; used only
    for validation samples and for the small share of trades whose exchange IV
    is missing or absurd, not for the whole tape."""
    p = np.atleast_1d(np.asarray(price_usd_obs, dtype="float64"))
    F = np.broadcast_to(np.asarray(F, dtype="float64"), p.shape)
    K = np.broadcast_to(np.asarray(K, dtype="float64"), p.shape)
    T = np.broadcast_to(np.asarray(T, dtype="float64"), p.shape)
    cp = np.broadcast_to(np.asarray(cp, dtype="float64"), p.shape)
    out = np.empty(p.shape, dtype="float64")
    for i in range(p.size):
        out.flat[i] = implied_vol_scalar(p.flat[i], F.flat[i], K.flat[i],
                                         T.flat[i], cp.flat[i])
    return out


# ------------------------------------------------------------------- greeks


def greeks(F, K, T, sigma, cp) -> dict[str, np.ndarray]:
    """Per-contract risk exposures for an inverse option.

    Returns
    -------
    delta       Black-76 delta (dimensionless, USD-option convention)
    delta_adj   premium-adjusted delta = the perp hedge ratio for an inverse
                option; this is what the dealer actually trades
    vega_usd    USD change in option value per 1.00 (=100 vol points) change
                in implied vol
    gamma       d(delta)/dF, units 1/USD
    gamma_usd   "dollar gamma": USD change in delta-dollars per 1% move in the
                underlying, = gamma * F^2 / 100
    theta_usd   USD per calendar day
    """
    F = np.asarray(F, dtype="float64")
    K = np.asarray(K, dtype="float64")
    T = np.asarray(T, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    cp = np.asarray(cp, dtype="float64")

    d1, d2 = _d1_d2(F, K, T, sigma)
    pdf = norm.pdf(d1)
    sqrtT = np.sqrt(np.maximum(T, SQRT_EPS))

    # Expired or zero-vol rows divide by zero here; they are replaced with
    # intrinsic-value greeks below, so the warning is noise.
    with np.errstate(divide="ignore", invalid="ignore"):
        delta = cp * norm.cdf(cp * d1)
        vega_usd = F * pdf * sqrtT
        gamma = pdf / (F * sigma * sqrtT)
        gamma_usd = gamma * F ** 2 / 100.0
        theta_usd = -(F * pdf * sigma) / (2.0 * sqrtT) / config.YEAR

    # Second-order exposures. These matter here because section 6.5 shows the
    # weekend's cost to a short arrives through the implied volatility re-rating
    # rather than through realized movement, and it is vega, volga and vanna --
    # not gamma -- that price a change in implied volatility.
    with np.errstate(divide="ignore", invalid="ignore"):
        # d(vega)/dF. Equals -pdf(d1) * d2 / sigma; see the identity
        # sqrt(T) - d1/sigma = -d2/sigma.
        vanna = -pdf * d2 / sigma
        # d(vega)/d(sigma). Positive away from the money, zero at d1*d2 = 0.
        volga = vega_usd * d1 * d2 / sigma
        # d(delta)/dT, then flipped and put on a calendar-day clock so that the
        # number is the drift in delta produced by one day simply passing.
        ddelta_dT = pdf * (-np.log(F / K) / (2.0 * sigma * T * sqrtT)
                           + sigma / (4.0 * sqrtT))
        charm_per_day = -ddelta_dT / config.YEAR

    prem_coin = price_coin(F, K, T, sigma, cp)
    delta_adj = delta - prem_coin

    degenerate = (T <= 0) | (sigma <= 0) | ~np.isfinite(d1)
    zero = np.zeros_like(np.asarray(delta, dtype="float64"))
    intrinsic_delta = np.where(cp * (F - K) > 0, cp, 0.0)
    return {
        "delta": np.where(degenerate, intrinsic_delta, delta),
        "delta_adj": np.where(degenerate, intrinsic_delta, delta_adj),
        "vega_usd": np.where(degenerate, zero, vega_usd),
        "gamma": np.where(degenerate, zero, gamma),
        "gamma_usd": np.where(degenerate, zero, gamma_usd),
        "theta_usd": np.where(degenerate, zero, theta_usd),
        "vanna": np.where(degenerate, zero, vanna),
        "volga": np.where(degenerate, zero, volga),
        "charm_per_day": np.where(degenerate, zero, charm_per_day),
    }


def time_to_expiry(trade_ts_ms, expiry_ts_ms) -> np.ndarray:
    """Year fraction on a 365-day calendar clock. Crypto trades continuously,
    so calendar time is the right clock (no business-day convention)."""
    ms_per_year = config.YEAR * 24 * 3600 * 1000
    t = (np.asarray(expiry_ts_ms, dtype="float64")
         - np.asarray(trade_ts_ms, dtype="float64")) / ms_per_year
    return np.maximum(t, 0.0)


def enrich(df, iv_col: str = "iv", curves: dict | None = None,
           linear: bool = False) -> "pd.DataFrame":
    """Attach T, forward, moneyness and greeks to a trade or mark frame.

    Expects columns: timestamp, expiration_timestamp, strike, cp, index_price,
    price, and an IV column in PERCENT (Deribit's convention).

    ``curves`` supplies per-date forward curves from dbop.forwards. Without
    them the index is used as the forward, which is only correct when the
    basis is negligible -- see the module docstring there.
    """
    import pandas as pd  # local import keeps this module importable standalone

    out = df.copy()
    out["T"] = time_to_expiry(out["timestamp"], out["expiration_timestamp"])
    if curves:
        from . import forwards
        out["F"] = forwards.attach_forward(out, curves)
    else:
        out["F"] = out["index_price"].astype("float64")
    out["cp_sign"] = np.where(out["cp"].to_numpy() == "C", 1.0, -1.0)
    out["sigma"] = out[iv_col].astype("float64") / 100.0

    # The exchange reports iv = 0 for a handful of deep-ITM prints where vol is
    # not identified from the premium. Those are unusable as vol observations;
    # mark them rather than letting a zero propagate into greeks.
    bad = (~np.isfinite(out["sigma"])) | (out["sigma"] < config.IV_MIN) | \
          (out["sigma"] > config.IV_MAX)
    out["iv_ok"] = ~bad

    out["k"] = np.log(out["strike"].to_numpy(dtype="float64")
                      / out["F"].to_numpy(dtype="float64"))
    # Inverse books (BTC, ETH) quote the premium in coin, so the dollar
    # premium is price * forward. Linear books (SOL_USDC) already quote it in
    # dollars per unit of underlying, and multiplying by the forward there
    # would inflate it by two orders of magnitude.
    out["premium_usd"] = (out["price"].astype("float64") if linear
                          else out["price"].astype("float64") * out["F"])

    g = greeks(out["F"], out["strike"], out["T"], out["sigma"], out["cp_sign"])
    for k, v in g.items():
        out[k] = v
    # Greeks computed from an unusable IV are meaningless.
    for k in g:
        out.loc[bad, k] = np.nan
    return out
