"""Net end-user demand and reconstructed dealer inventory.

The paper's central measurement. Two distinct objects, and the distinction
matters because GPP's model speaks to both:

*Flow* is the signed quantity that changes hands on a day, valued at the
greeks prevailing when it traded. It is what hits a dealer's book that day.

*Stock* is the accumulated position: the sum of all past end-user demand in an
instrument, still outstanding until expiry. Dealer inventory is its negative.
This is the quantity GPP's dealers must warehouse, and it must be revalued each
day at current greeks, because an option bought when it was at the money is a
different risk exposure three weeks later. Instruments that did not trade today
still carry risk, so revaluation reads implied vol off the day's fitted
surface rather than off a trade.

Positions are reconstructed from the tape, not observed. Every option ever
traded on Deribit is in the sample and open interest starts at zero when an
instrument lists, so cumulative signed flow identifies the outstanding end-user
position exactly, up to the assumption that the passive side is the
intermediary. That assumption is the paper's main measurement risk and
``validate_signing`` below is what probes it.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config, greeks, surfaces

log = logging.getLogger(__name__)


# ------------------------------------------------------------------- flow


def daily_flow(trades: pd.DataFrame) -> pd.DataFrame:
    """Signed end-user demand per instrument-day, valued at trade-time greeks."""
    g = trades.groupby(["date", "instrument_name"], observed=True)
    out = g.agg(
        net_amount=("signed_amount", "sum"),
        net_vega=("signed_vega", "sum"),
        net_gamma=("signed_gamma", "sum"),
        gross_amount=("amount", "sum"),
        gross_vega=("vega_usd", lambda s: np.nansum(np.abs(s))),
        n_trades=("trade_id", "size"),
        taker_buy_share=("direction", lambda s: (s > 0).mean()),
    ).reset_index()
    return out


# ------------------------------------------------------------------- stock


def positions(flow: pd.DataFrame, instruments_meta: pd.DataFrame,
              max_days: int | None = None) -> pd.DataFrame:
    """Expand instrument-day flow into a daily outstanding-position panel.

    End-user position is the running sum of signed demand; the dealer holds its
    negative. The panel runs from an instrument's first trade to its expiry,
    carrying the position forward on days with no trades, because an untraded
    position is still an open exposure.
    """
    meta = instruments_meta.set_index("instrument_name")
    flow = flow.sort_values(["instrument_name", "date"])
    flow["pos_enduser"] = flow.groupby("instrument_name", observed=True)[
        "net_amount"].cumsum()

    frames = []
    for name, g in flow.groupby("instrument_name", observed=True, sort=False):
        if name not in meta.index:
            continue
        expiry = meta.at[name, "expiry"]
        start = g["date"].iloc[0]
        end = min(pd.Timestamp(expiry).normalize(), g["date"].iloc[-1]
                  if pd.isna(expiry) else pd.Timestamp(expiry).normalize())
        if max_days is not None:
            end = min(end, start + pd.Timedelta(days=max_days))
        if end < start:
            end = start
        idx = pd.date_range(start, end, freq="D", tz="UTC")

        s = g.set_index("date")["pos_enduser"].reindex(idx).ffill()
        frames.append(pd.DataFrame({
            "date": idx,
            "instrument_name": name,
            "pos_enduser": s.to_numpy(),
        }))

    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["pos_dealer"] = -panel["pos_enduser"]
    # Positions below dust are rounding residue from partial closes.
    panel = panel[panel["pos_enduser"].abs() > 1e-9].reset_index(drop=True)
    return panel


def revalue(panel: pd.DataFrame, instruments_meta: pd.DataFrame,
            day_surfaces: dict, index_by_date: pd.Series) -> pd.DataFrame:
    """Value each outstanding position at the day's surface and spot.

    Adds current greeks and the bucket assignment. Buckets use CURRENT delta
    and CURRENT time to expiry, so a position migrates across buckets as spot
    moves and time passes; that is intended, since GPP weight demand by the
    risk a dealer bears now, not by the risk it bore at trade time.
    """
    meta = instruments_meta.set_index("instrument_name")
    keep = panel["instrument_name"].isin(meta.index)
    panel = panel.loc[keep].copy()

    panel["strike"] = meta.loc[panel["instrument_name"], "strike"].to_numpy()
    panel["expiration_timestamp"] = meta.loc[
        panel["instrument_name"], "expiration_timestamp"].to_numpy()
    panel["cp"] = meta.loc[panel["instrument_name"], "cp"].to_numpy()

    day_end_ms = (panel["date"].astype("int64") // 10 ** 6) + 86_400_000
    panel["T"] = greeks.time_to_expiry(day_end_ms, panel["expiration_timestamp"])
    panel["F"] = panel["date"].map(index_by_date).to_numpy(dtype="float64")
    panel["k"] = np.log(panel["strike"].to_numpy(dtype="float64") / panel["F"])

    # Read implied vol off each day's fitted surface.
    sigma = np.full(len(panel), np.nan)
    for date, idx in panel.groupby("date", observed=True).groups.items():
        surf = day_surfaces.get(date)
        if surf is None or not surf:
            continue
        loc = panel.index.get_indexer(idx)
        ks = panel.loc[idx, "k"].to_numpy()
        Ts = panel.loc[idx, "T"].to_numpy()
        sigma[loc] = [surf.iv(k, T) for k, T in zip(ks, Ts)]
    panel["sigma"] = sigma

    cp_sign = np.where(panel["cp"].to_numpy() == "C", 1.0, -1.0)
    g = greeks.greeks(panel["F"], panel["strike"], panel["T"],
                      panel["sigma"], cp_sign)
    for k, v in g.items():
        panel[k] = v

    pos = panel["pos_dealer"].to_numpy(dtype="float64")
    panel["dealer_vega"] = pos * panel["vega_usd"].to_numpy()
    panel["dealer_gamma"] = pos * panel["gamma_usd"].to_numpy()
    panel["dealer_delta"] = pos * panel["delta_adj"].to_numpy()
    # Delta exposure in dollars is what the perp hedge must offset, and what
    # funding is charged on.
    panel["dealer_delta_usd"] = panel["dealer_delta"] * panel["F"]

    panel["abs_delta"] = panel["delta"].abs()
    panel["delta_bucket"] = pd.cut(panel["abs_delta"], bins=config.DELTA_BINS,
                                   labels=[f"d{i}" for i in
                                           range(len(config.DELTA_BINS) - 1)])
    panel["tau_days"] = panel["T"] * config.YEAR
    panel["tau_bucket"] = pd.cut(panel["tau_days"], bins=config.TAU_BINS_DAYS,
                                 labels=[f"t{i}" for i in
                                         range(len(config.TAU_BINS_DAYS) - 1)])
    panel["bucket"] = (panel["delta_bucket"].astype(str) + "_"
                       + panel["tau_bucket"].astype(str))
    return panel


# -------------------------------------------------------------- aggregation


def bucket_panel(revalued: pd.DataFrame) -> pd.DataFrame:
    """Dealer inventory by (date, bucket) — the cross-sectional unit.

    Carries a vega-weighted implied vol for the bucket as well, so that
    expensiveness can be measured on the very instruments dealers actually
    hold rather than on an interpolated grid point that may sit where nothing
    is outstanding.
    """
    d = revalued.copy()
    w = d["vega_usd"].to_numpy(dtype="float64")
    s = d["sigma"].to_numpy(dtype="float64")
    ok = np.isfinite(w) & np.isfinite(s) & (w > 0)
    d["_w"] = np.where(ok, np.abs(w), 0.0)
    d["_ws"] = np.where(ok, np.abs(w) * s, 0.0)

    g = d.groupby(["date", "bucket"], observed=True)
    out = g.agg(
        dealer_vega=("dealer_vega", "sum"),
        dealer_gamma=("dealer_gamma", "sum"),
        dealer_delta_usd=("dealer_delta_usd", "sum"),
        gross_vega=("_w", "sum"),
        wsum=("_ws", "sum"),
        n_instruments=("instrument_name", "nunique"),
        mean_tau=("tau_days", "mean"),
        mean_abs_delta=("abs_delta", "mean"),
    ).reset_index()
    out["iv_bucket"] = out["wsum"] / out["gross_vega"].replace(0, np.nan)
    return out.drop(columns=["wsum"])


def market_panel(revalued: pd.DataFrame) -> pd.DataFrame:
    """Market-wide dealer inventory — the time-series unit."""
    g = revalued.groupby("date", observed=True)
    out = g.agg(
        dealer_vega=("dealer_vega", "sum"),
        dealer_gamma=("dealer_gamma", "sum"),
        dealer_delta_usd=("dealer_delta_usd", "sum"),
        open_interest=("pos_enduser", lambda s: np.abs(s).sum()),
        n_instruments=("instrument_name", "nunique"),
    ).reset_index()
    out["abs_delta_usd"] = revalued.groupby("date", observed=True)[
        "dealer_delta_usd"].apply(lambda s: np.abs(s).sum()).to_numpy()
    return out


def normalize(panel: pd.DataFrame, cols: list[str], by: str | None = None,
              window: int = config.INVENTORY_SCALE_WINDOW_DAYS) -> pd.DataFrame:
    """Scale inventory by a trailing market-size proxy.

    Raw vega inventory is wildly non-stationary: the market grew by orders of
    magnitude over the sample, so an unscaled regression would be dominated by
    the growth trend rather than by demand pressure. The primary scaling is
    trailing gross vega traded, a market-size proxy that is observable at the
    time and does not use the contemporaneous position.
    """
    panel = panel.sort_values("date").copy()
    grouper = panel.groupby(by, observed=True) if by else None

    for c in cols:
        if grouper is not None:
            scale = (grouper["gross_vega"]
                     .transform(lambda s: s.rolling(window, min_periods=5)
                                .mean().shift(1)))
        else:
            scale = panel["gross_vega"].rolling(window, min_periods=5).mean().shift(1)
        panel[f"{c}_scaled"] = panel[c] / scale.replace(0, np.nan)
    return panel


# -------------------------------------------------------------- validation


def validate_positions(panel: pd.DataFrame, revalued: pd.DataFrame,
                       instruments_meta: pd.DataFrame) -> dict:
    """Internal identities that must hold for the reconstruction to be sound."""
    checks = {}
    checks["dealer_equals_neg_enduser"] = bool(
        np.allclose(panel["pos_dealer"], -panel["pos_enduser"]))

    meta = instruments_meta.set_index("instrument_name")
    exp = pd.to_datetime(
        meta.loc[revalued["instrument_name"], "expiry"].to_numpy(), utc=True)
    checks["no_positions_after_expiry"] = bool(
        (revalued["date"].to_numpy() <= exp.normalize().to_numpy()).all())
    checks["nonneg_time_to_expiry"] = bool((revalued["T"] >= 0).all())
    checks["surface_iv_coverage"] = float(revalued["sigma"].notna().mean())
    checks["n_instrument_days"] = int(len(revalued))
    return checks


def validate_signing(flow: pd.DataFrame, n_shuffles: int = 20,
                     seed: int = 0, window: int = 252) -> pd.DataFrame:
    """Probe the 'passive side is the intermediary' assumption.

    If aggressor signs carry information about who accumulates risk, then
    reconstructed inventory should mean-revert on an economically sensible
    horizon, because dealers lay risk off. If the signs were noise, cumulative
    flow would be a random walk and revert far more slowly.

    The comparison must be made on a *stationary* series. Raw cumulative vega
    over this sample is dominated by market growth of two orders of magnitude,
    and an AR(1) fitted to it returns no mean reversion at all for the true
    series while the sign-shuffled placebos happen to look better behaved --
    which says something about the trend, not about the signs. Both the true
    series and the placebos are therefore scaled by trailing gross vega, the
    same normalization the regressions use, before the half-life is estimated.
    """
    rng = np.random.default_rng(seed)

    def half_life(x: np.ndarray) -> float:
        x = x[np.isfinite(x)]
        if len(x) < 50:
            return np.nan
        dx, lag = np.diff(x), x[:-1]
        keep = np.isfinite(dx) & np.isfinite(lag)
        if keep.sum() < 50:
            return np.nan
        beta = np.polyfit(lag[keep], dx[keep], 1)[0]
        if beta >= 0 or not np.isfinite(beta):
            return np.inf
        return float(-np.log(2) / np.log1p(beta))

    daily = flow.groupby("date", observed=True).agg(
        net=("net_vega", "sum"),
        gross=("gross_vega", "sum")).sort_index()
    scale = (daily["gross"].rolling(window, min_periods=20).mean()
             .shift(1).replace(0, np.nan))

    def scaled_half_life(net_series: np.ndarray) -> float:
        return half_life((np.cumsum(net_series) / scale.to_numpy()))

    true_hl = scaled_half_life(daily["net"].to_numpy())

    # Placebos preserve each day's gross size and randomize only the sign, so
    # the comparison isolates the information in the signs.
    gross_day = daily["gross"].to_numpy()
    placebo = [scaled_half_life(gross_day * rng.choice([-1.0, 1.0],
                                                       size=len(gross_day)))
               for _ in range(n_shuffles)]

    finite = [p for p in placebo if np.isfinite(p)]
    summary = ([float(np.mean(finite)), float(np.percentile(finite, 5)),
                float(np.percentile(finite, 95))] if finite
               else [np.nan, np.nan, np.nan])

    return pd.DataFrame({
        "measure": ["true", "placebo_mean", "placebo_p05", "placebo_p95"],
        "half_life_days": [true_hl] + summary,
        "n_finite_placebos": [len(finite)] * 4,
    })
