"""Daily implied-volatility surfaces and their shape factors.

Two jobs. First, produce the expensiveness measures the paper regresses:
level, skew and curvature at a fixed (delta, maturity) grid, so that a series
is comparable across days even though the traded strike ladder moves with spot.
Second, provide an IV for *any* (log-moneyness, maturity) pair, which the
inventory valuation needs: a dealer holds positions in instruments that did not
trade today, and those still carry vega.

Construction follows the cleaning logic of the rough-vol pipeline's
build_surface: keep the OTM leg on each side (under put-call parity the two
legs carry the same information, and the OTM one is the liquid, tighter-quoted
side), drop unusable IVs, and weight by vega so that ATM points, where vol is
well identified from the premium, dominate the fit.

Interpolation is in total variance w = sigma^2 * T rather than in vol, because
total variance is the quantity that must be monotone in T for the surface to be
calendar-arbitrage-free.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from scipy.stats import norm

from . import config, greeks

log = logging.getLogger(__name__)

MIN_POINTS_PER_EXPIRY = 4
MAX_ABS_K = 1.5          # crypto smiles are wide; keep far more than equities
MIN_T = 1.0 / 365.0      # under a day the IV is dominated by microstructure


def _clean_slice(g: pd.DataFrame) -> pd.DataFrame:
    """One expiry's worth of marks -> clean (k, iv, weight) points.

    Moneyness is measured against the forward for this expiry where one is
    available; falling back to the index would shift the whole smile sideways
    by the basis and mislabel which options are out of the money.
    """
    fwd_col = "F" if "F" in g.columns and g["F"].notna().any() else "index_price"
    F = float(g[fwd_col].median())
    k = np.log(g["strike"].to_numpy(dtype="float64") / F)
    cp = np.where(g["cp"].to_numpy() == "C", 1.0, -1.0)

    # Keep the OTM leg only: calls above the forward, puts below.
    otm = ((cp > 0) & (k >= 0)) | ((cp < 0) & (k < 0))
    iv = g["mark_iv"].to_numpy(dtype="float64") / 100.0
    ok = otm & np.isfinite(iv) & (iv > config.IV_MIN) & (iv < config.IV_MAX) \
        & (np.abs(k) < MAX_ABS_K)
    if ok.sum() < MIN_POINTS_PER_EXPIRY:
        return pd.DataFrame()

    T = float(g["T"].median())
    d1 = (k[ok] * -1 + 0.5 * iv[ok] ** 2 * T) / (iv[ok] * np.sqrt(T))
    weight = F * norm.pdf(d1) * np.sqrt(T)

    out = pd.DataFrame({"k": k[ok], "iv": iv[ok], "T": T, "F": F,
                        "weight": np.maximum(weight, 1e-8)})
    # Collapse duplicate strikes (both legs can survive at k == 0).
    out = (out.groupby("k")
             .apply(lambda s: pd.Series({
                 "iv": np.average(s["iv"], weights=s["weight"]),
                 "T": s["T"].iloc[0], "F": s["F"].iloc[0],
                 "weight": s["weight"].sum()}), include_groups=False)
             .reset_index())
    return out.sort_values("k").reset_index(drop=True)


def build_daily_slices(marks: pd.DataFrame) -> pd.DataFrame:
    """Clean surface points for every (date, expiry) with enough observations."""
    marks = marks.copy()
    marks["T"] = greeks.time_to_expiry(
        (marks["date"].astype("int64") // 10 ** 6) + 86_400_000,
        marks["expiration_timestamp"])
    marks = marks[marks["T"] >= MIN_T]

    rows = []
    for (date, exp), g in marks.groupby(["date", "expiration_timestamp"],
                                        observed=True):
        s = _clean_slice(g)
        if s.empty:
            continue
        s["date"] = date
        s["expiration_timestamp"] = exp
        rows.append(s)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------- interpolation


class DaySurface:
    """One day's surface: interpolates total variance in k, then across T.

    Extrapolation is deliberately flat in k beyond the observed strike range
    (the wings are where quotes are least reliable and a fitted slope would
    invent signal) and flat in T beyond the observed expiries.
    """

    def __init__(self, slices: pd.DataFrame):
        self.expiries = []
        for T, g in slices.groupby("T"):
            g = g.sort_values("k")
            if len(g) < 2:
                continue
            w = (g["iv"].to_numpy() ** 2) * T
            self.expiries.append({
                "T": float(T),
                "F": float(g["F"].iloc[0]),
                "k": g["k"].to_numpy(),
                "w": w,
                "interp": PchipInterpolator(g["k"].to_numpy(), w,
                                            extrapolate=False),
                "k_lo": float(g["k"].iloc[0]),
                "k_hi": float(g["k"].iloc[-1]),
            })
        self.expiries.sort(key=lambda e: e["T"])
        self.T_grid = np.array([e["T"] for e in self.expiries])

    def __bool__(self) -> bool:
        return len(self.expiries) > 0

    def _w_at(self, e, k):
        k_clipped = np.clip(k, e["k_lo"], e["k_hi"])
        return float(e["interp"](k_clipped))

    def iv(self, k: float, T: float) -> float:
        """Implied vol at log-moneyness k and maturity T."""
        if not self.expiries or not np.isfinite(k) or T <= 0:
            return np.nan
        Ts = self.T_grid
        if T <= Ts[0]:
            w = self._w_at(self.expiries[0], k) * (T / Ts[0])
        elif T >= Ts[-1]:
            w = self._w_at(self.expiries[-1], k) * (T / Ts[-1])
        else:
            j = int(np.searchsorted(Ts, T))
            e0, e1 = self.expiries[j - 1], self.expiries[j]
            w0, w1 = self._w_at(e0, k), self._w_at(e1, k)
            lam = (T - e0["T"]) / (e1["T"] - e0["T"])
            w = (1 - lam) * w0 + lam * w1        # linear in total variance
        if not np.isfinite(w) or w <= 0:
            return np.nan
        return float(np.sqrt(w / T))

    def iv_at_delta(self, delta: float, T: float, cp: int) -> float:
        """Invert for the strike with the requested Black delta, then read IV.

        Solving |delta(k)| = target is a fixed point because delta depends on
        the vol that itself depends on k; Brent on k is stable here since the
        surface is monotone enough over the bracket.
        """
        if not self.expiries or T <= 0:
            return np.nan
        F = self.expiries[0]["F"]

        def f(k):
            s = self.iv(k, T)
            if not np.isfinite(s):
                return np.nan
            d = greeks.greeks(F, F * np.exp(k), T, s, cp)["delta"]
            return abs(float(d)) - delta

        lo, hi = -MAX_ABS_K, MAX_ABS_K
        try:
            f_lo, f_hi = f(lo), f(hi)
            if not (np.isfinite(f_lo) and np.isfinite(f_hi)) or f_lo * f_hi > 0:
                return np.nan
            k_star = brentq(f, lo, hi, maxiter=100, xtol=1e-8)
        except (ValueError, RuntimeError):
            return np.nan
        return self.iv(k_star, T)


def grid_from_slices(slices: pd.DataFrame) -> pd.DataFrame:
    """Interpolate every day onto the fixed (delta, tau) grid and derive the
    level/skew/curvature factors."""
    rows = []
    for date, g in slices.groupby("date", observed=True):
        surf = DaySurface(g)
        if not surf:
            continue
        rec = {"date": date, "n_expiries": len(surf.expiries),
               "F": surf.expiries[0]["F"]}
        for tau_d in config.GRID_TAUS_DAYS:
            T = tau_d / config.YEAR
            atm = surf.iv(0.0, T)
            rec[f"atm_{tau_d}"] = atm
            for d in config.GRID_DELTAS:
                if d == 0.50:
                    continue
                c = surf.iv_at_delta(d, T, 1)
                p = surf.iv_at_delta(d, T, -1)
                rec[f"c{int(d*100)}_{tau_d}"] = c
                rec[f"p{int(d*100)}_{tau_d}"] = p
                if np.isfinite(c) and np.isfinite(p):
                    # Risk reversal: positive when calls are bid over puts.
                    rec[f"rr{int(d*100)}_{tau_d}"] = c - p
                    if np.isfinite(atm):
                        rec[f"bf{int(d*100)}_{tau_d}"] = 0.5 * (c + p) - atm
        rows.append(rec)
    return pd.DataFrame(rows)


def build(currency: str, marks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    slices = build_daily_slices(marks)
    grid = grid_from_slices(slices)
    grid["currency"] = currency
    slices.to_parquet(config.SURFACES / f"{currency}_slices.parquet",
                      compression="zstd", index=False)
    grid.to_parquet(config.SURFACES / f"{currency}_grid_daily.parquet",
                    compression="zstd", index=False)
    log.info("%s: %d surface points, %d daily grids (%s..%s)", currency,
             len(slices), len(grid),
             grid["date"].min() if len(grid) else None,
             grid["date"].max() if len(grid) else None)
    return slices, grid


def load_slices(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.SURFACES / f"{currency}_slices.parquet")


def load_grid(currency: str) -> pd.DataFrame:
    return pd.read_parquet(config.SURFACES / f"{currency}_grid_daily.parquet")


def day_surfaces(currency: str) -> dict:
    """All daily surfaces keyed by date, for inventory valuation."""
    slices = load_slices(currency)
    return {d: DaySurface(g) for d, g in slices.groupby("date", observed=True)}
