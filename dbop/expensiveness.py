"""Expensiveness measures and delta-hedged option returns.

Three complementary dependent variables, because each has a different weakness
and GPP's argument should not rest on one of them:

1. ``EXP`` — implied vol minus the out-of-sample HAR forecast of realized vol,
   at fixed points on the (delta, maturity) grid. This is GPP's own measure.
   It inherits any error in the vol forecast.

2. ``VRP`` — model-free implied variance (Bakshi-Kapadia-Madan) against
   realized. Free of a parametric smile assumption, but needs the wings, where
   crypto quotes are thin.

3. Delta-hedged returns — the realized profit of buying an option and hedging
   it in the perpetual. Free of any vol forecast at all, since it is a traded
   payoff, and it is the direct test of whether inventory earns a premium.
   For an inverse option the hedge ratio is the premium-adjusted delta, and the
   perp hedge pays funding, which is subtracted explicitly: ignoring it would
   attribute the carry cost of hedging to the option's own return.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config, greeks, surfaces

log = logging.getLogger(__name__)


# ------------------------------------------------------------- expensiveness


def expensiveness_grid(grid: pd.DataFrame, rv: pd.DataFrame) -> pd.DataFrame:
    """IV minus expected realized vol at each grid point.

    Maturities are matched to the closest available HAR horizon so that the
    forecast horizon lines up with the option's own life.
    """
    df = grid.merge(rv[["date"] + [f"erv_{h}" for h in config.HAR_HORIZONS_DAYS]
                       + [f"rvfwd_{h}" for h in config.HAR_HORIZONS_DAYS]],
                    on="date", how="left")

    for tau in config.GRID_TAUS_DAYS:
        h = min(config.HAR_HORIZONS_DAYS, key=lambda x: abs(x - tau))
        atm = f"atm_{tau}"
        if atm in df.columns:
            df[f"exp_atm_{tau}"] = df[atm] - df[f"erv_{h}"]
            # Ex-post counterpart: what the position actually earned in vol
            # terms, used as the realized-premium check.
            df[f"expost_atm_{tau}"] = df[atm] - df[f"rvfwd_{h}"]
        for d in config.GRID_DELTAS:
            if d == 0.50:
                continue
            for side in ("c", "p"):
                col = f"{side}{int(d*100)}_{tau}"
                if col in df.columns:
                    df[f"exp_{col}"] = df[col] - df[f"erv_{h}"]
    return df


def bkm_implied_variance(slices: pd.DataFrame, tau_days: int = 30
                         ) -> pd.DataFrame:
    """Model-free implied variance by the Bakshi-Kapadia-Madan integral.

    Uses the discrete approximation V = (2/T) * sum over OTM strikes of
    (dK / K^2) * Q(K), with Q the OTM option price in USD. Strikes are taken
    from the fitted surface so the integrand is on a regular grid; the wings
    are extrapolated flat in implied vol, which is conservative (a flat wing
    understates the tails rather than inventing them).
    """
    T = tau_days / config.YEAR
    rows = []
    for date, g in slices.groupby("date", observed=True):
        surf = surfaces.DaySurface(g)
        if not surf:
            continue
        F = surf.expiries[0]["F"]
        # Integrate over a wide but finite log-moneyness range.
        ks = np.linspace(-1.2, 1.2, 241)
        Ks = F * np.exp(ks)
        ivs = np.array([surf.iv(k, T) for k in ks])
        ok = np.isfinite(ivs)
        if ok.sum() < 50:
            continue
        Ks, ivs, ks = Ks[ok], ivs[ok], ks[ok]

        cp = np.where(Ks >= F, 1.0, -1.0)          # OTM leg on each side
        Q = greeks.price_usd(F, Ks, T, ivs, cp)
        dK = np.gradient(Ks)
        # V = (2/T) * integral of Q(K)/K^2 dK. Both Q and K are in USD, so
        # Q/K^2 * dK is already dimensionless -- dividing by the forward as
        # well would scale the result by roughly sqrt(F), which is how this
        # first read as a variance risk premium of -0.61.
        v = (2.0 / T) * np.sum(dK / Ks ** 2 * Q)
        rows.append({"date": date, f"mfiv_{tau_days}": np.sqrt(max(v, 1e-12))})
    return pd.DataFrame(rows)


def variance_risk_premium(mfiv: pd.DataFrame, rv: pd.DataFrame,
                          tau_days: int = 30) -> pd.DataFrame:
    """MFIV against both the forecast (ex ante) and the outturn (ex post)."""
    h = min(config.HAR_HORIZONS_DAYS, key=lambda x: abs(x - tau_days))
    df = mfiv.merge(rv[["date", f"erv_{h}", f"rvfwd_{h}"]], on="date", how="left")
    df[f"vrp_ante_{tau_days}"] = df[f"mfiv_{tau_days}"] - df[f"erv_{h}"]
    df[f"vrp_post_{tau_days}"] = df[f"mfiv_{tau_days}"] - df[f"rvfwd_{h}"]
    return df


# ------------------------------------------------------- delta-hedged returns


def delta_hedged_returns(marks: pd.DataFrame, instruments_meta: pd.DataFrame,
                         funding_daily: pd.DataFrame) -> pd.DataFrame:
    """Daily delta-hedged P&L per contract, normalized per unit of vega.

    The position is long one option, hedged in the perpetual at the
    premium-adjusted delta, held one day, rebalanced daily:

        pnl = (C_t+1 - C_t) - delta_adj_t * (F_t+1 - F_t)
              - delta_adj_t * F_t * funding_t

    all in USD. Dividing by the option's vega expresses the result in vol
    points, which makes positions of very different size and moneyness
    comparable and matches how the expensiveness measures are scaled.
    """
    meta = instruments_meta.set_index("instrument_name")
    df = marks.copy()
    keep = df["instrument_name"].isin(meta.index)
    df = df.loc[keep].copy()

    df["expiration_timestamp"] = meta.loc[
        df["instrument_name"], "expiration_timestamp"].to_numpy()
    df["strike"] = meta.loc[df["instrument_name"], "strike"].to_numpy()
    df["cp"] = meta.loc[df["instrument_name"], "cp"].to_numpy()

    day_end_ms = (df["date"].astype("int64") // 10 ** 6) + 86_400_000
    df["T"] = greeks.time_to_expiry(day_end_ms, df["expiration_timestamp"])
    # Marks carry the forward when greeks were attached upstream; the hedge
    # ratio has to be computed against the same forward the option is priced
    # off, or the delta used to hedge will not be the delta that was earned.
    if "F" not in df.columns or df["F"].isna().all():
        df["F"] = df["index_price"].astype("float64")
    df["F"] = df["F"].fillna(df["index_price"]).astype("float64")
    df["sigma"] = df["mark_iv"].astype("float64") / 100.0
    cp_sign = np.where(df["cp"].to_numpy() == "C", 1.0, -1.0)
    g = greeks.greeks(df["F"], df["strike"], df["T"], df["sigma"], cp_sign)
    for k, v in g.items():
        df[k] = v
    # Value the option in USD from its coin-quoted mark.
    df["C_usd"] = df["mark_price"].astype("float64") * df["F"]

    df = df.sort_values(["instrument_name", "date"])
    grp = df.groupby("instrument_name", observed=True)
    df["C_next"] = grp["C_usd"].shift(-1)
    df["F_next"] = grp["F"].shift(-1)
    df["date_next"] = grp["date"].shift(-1)

    # Only hold over consecutive days; a gap means the instrument did not trade
    # and the mark is not a clean closing price for the interval.
    one_day = (df["date_next"] - df["date"]).dt.days == 1

    fund = funding_daily.set_index("date")["funding_day"]
    df["funding"] = df["date"].map(fund).astype("float64")

    pnl = ((df["C_next"] - df["C_usd"])
           - df["delta_adj"] * (df["F_next"] - df["F"])
           - df["delta_adj"] * df["F"] * df["funding"])
    df["dh_pnl_usd"] = np.where(one_day, pnl, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["dh_ret_vega"] = df["dh_pnl_usd"] / df["vega_usd"].replace(0, np.nan)

    # A single day of vega-normalized P&L beyond a few vol points is a stale or
    # erroneous mark, not an economic return.
    df.loc[df["dh_ret_vega"].abs() > 1.0, "dh_ret_vega"] = np.nan
    return df


def aggregate_dh_returns(dh: pd.DataFrame) -> pd.DataFrame:
    """Vega-weighted market-level delta-hedged return per day."""
    d = dh.dropna(subset=["dh_ret_vega", "vega_usd"])
    d = d[d["vega_usd"] > 0]

    def _w(g):
        w = g["vega_usd"].to_numpy()
        return np.average(g["dh_ret_vega"].to_numpy(), weights=w)

    out = d.groupby("date", observed=True).apply(
        _w, include_groups=False).rename("dh_ret_vw").reset_index()
    out["dh_ret_ew"] = d.groupby("date", observed=True)[
        "dh_ret_vega"].mean().to_numpy()
    out["dh_pnl_usd"] = d.groupby("date", observed=True)[
        "dh_pnl_usd"].sum().to_numpy()
    out["n_positions"] = d.groupby("date", observed=True).size().to_numpy()
    return out
