"""Venue-generic short-straddle backtest engine, candle-based.

Built for Delta Exchange India, where the historical record is 1h traded and
mark candles per contract plus a 5m perpetual series — no tape, no quotes. The
honesty rules that shape everything here:

* Entries are priced off **traded** candles only (the close of the last full
  hour bar before the entry instant). No trade print near the entry, no trade.
* Exits are priced off **mark** candles (00:00 UTC exits rarely print), with
  the quoted-spread haircut charged on top; expiry exits settle to intrinsic
  against the perp price at the settlement instant.
* The hedge runs on the entry-implied vol Black delta, rebalanced on a fixed
  clock — the rule a desk could run without a live surface — matching the
  convention in scripts/weekend_clock.py so results compare across venues.
* The exit/stop lookup sees the full candle record of the traded contract and
  nothing else; contract selection is complete before anything after the entry
  instant is read (the look-ahead lesson documented in weekend_clock).
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import costs, greeks, weekend
from .venues import delta_symbols as ds

log = logging.getLogger(__name__)

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
MS_YEAR = 365.25 * DAY_MS

# Exit instants, hours after Friday 00:00 UTC.
EXITS = {"sat_00": 24, "sun_00": 48, "mon_00": 72, "expiry": None}

ENTRY_MATCH_WINDOW_H = 3      # how stale the entry trade print may be
EXIT_MATCH_WINDOW_H = 3


def weekday_starts(ts_min: int, ts_max: int, dow: int = 4) -> np.ndarray:
    """Every 00:00 UTC of the given weekday (Mon=0) in [ts_min, ts_max].
    Epoch day 0 was a Thursday, so Thursday is offset 3 in the epoch week."""
    first = (ts_min // DAY_MS) * DAY_MS
    days = np.arange(first, ts_max + DAY_MS, DAY_MS, dtype="int64")
    return days[((days // DAY_MS) % 7) == ((dow - 3) % 7)]


def fridays(ts_min: int, ts_max: int) -> np.ndarray:
    """Every Friday 00:00 UTC in [ts_min, ts_max]."""
    return weekday_starts(ts_min, ts_max, 4)


def price_at(px: pd.Series, stamp) -> np.ndarray:
    """Last perp close at or before ``stamp`` (ms)."""
    idx = px.index.to_numpy()
    pos = np.searchsorted(idx, np.asarray(stamp, dtype="int64"),
                          side="right") - 1
    return px.to_numpy()[np.clip(pos, 0, len(px) - 1)]


def candle_close_before(candles: pd.DataFrame, instant_ms: int,
                        window_h: int) -> tuple[float, int] | None:
    """Close of the last bar *ending* at or before ``instant_ms``, no older
    than ``window_h`` hours. Bar timestamps mark the bar open, so a 1h bar has
    ended once ``ts + 1h <= instant``."""
    if candles.empty:
        return None
    ts = candles["ts"].to_numpy()
    end = ts + HOUR_MS
    ok = np.flatnonzero((end <= instant_ms)
                        & (end >= instant_ms - window_h * HOUR_MS))
    if len(ok) == 0:
        return None
    i = ok[-1]
    return float(candles["close"].iloc[i]), int(end[i])


def hedge_pnl(px: pd.Series, t0: int, t1: int, K: float, sigma_c: float,
              sigma_p: float, expiry_ms: int, rehedge_minutes: int,
              fee_fn=costs.delta_india_perp_fee_usd) -> tuple[float, float]:
    """Delta-hedge P&L and perp fees for a SHORT straddle over [t0, t1].

    Vectorized over the rehedge clock; the hedge for a short straddle is long
    (delta_C + delta_P) units of the perpetual, deltas at entry vols.
    """
    step = rehedge_minutes * 60_000
    stamps = np.minimum(np.arange(t0, t1 + step, step, dtype="int64"), t1)
    S = price_at(px, stamps)
    T = np.clip((expiry_ms - stamps) / MS_YEAR, 1e-9, None)
    want = (greeks.greeks(S, K, T, sigma_c, 1)["delta"]
            + greeks.greeks(S, K, T, sigma_p, -1)["delta"])
    trades = np.diff(want, prepend=0.0)
    cash = -float(np.sum(trades * S))
    fees = float(np.sum(fee_fn(np.abs(trades) * S)))
    S_end = float(price_at(px, np.int64(t1)))
    return cash + float(want[-1]) * S_end, fees


def _rv_ann(px: pd.Series, t0: int, t1: int, bar_minutes: int = 5) -> float:
    idx = px.index.to_numpy()
    a, b = np.searchsorted(idx, [t0, t1])
    v = px.to_numpy()[a:b]
    if len(v) < 12:
        return np.nan
    r = np.diff(np.log(v))
    per_year = 365.0 * 24 * 60 / bar_minutes
    return float(np.sqrt(np.mean(r ** 2) * per_year))


def run_one(fri: int, px: pd.Series, chain: pd.DataFrame, load_candles,
            currency: str = "BTC",
            entry_hour: int = 12, exit_key: str = "sun_00",
            rehedge_minutes: int = 60, half_spread_vol: float = 0.0015,
            stop_mult: float | None = None,
            entry_from_mark: bool = False) -> dict | None:
    """One Friday, one configuration. Returns a blotter row or None.

    ``chain``: discovered contracts (symbol, expiry, strike) for the currency.
    ``load_candles(symbol, mark)`` -> hourly candle frame.
    """
    t_in = fri + entry_hour * HOUR_MS

    # -------------------------------------------------- select expiry, strike
    cand = chain[chain["expiry_ms"] > t_in]
    cand = cand[cand["expiry_ms"] <= fri + 4 * DAY_MS]
    if cand.empty:
        return None
    wf = weekend.weekend_fraction(
        np.full(len(cand), t_in), cand["expiry_ms"].to_numpy())
    expiry_ms = int(cand["expiry_ms"].to_numpy()[np.argmax(wf)])
    wknd_frac = float(np.max(wf))
    strikes = cand.loc[cand["expiry_ms"] == expiry_ms, "strike"] \
        .drop_duplicates().sort_values()

    S_in = float(price_at(px, np.int64(t_in)))
    T_in = (expiry_ms - t_in) / MS_YEAR

    # nearest-ATM strike with a fresh trade print on BOTH legs
    entry = None
    for K in strikes.iloc[(strikes - S_in).abs().argsort()].head(3):
        e_date = dt.datetime.fromtimestamp(expiry_ms / 1000,
                                           dt.timezone.utc).date()
        sym_c = ds.format_symbol("C", currency, K, e_date)
        legs = {}
        for cp, sym in ((1, sym_c), (-1, "P" + sym_c[1:])):
            got = candle_close_before(
                load_candles(sym, mark=bool(entry_from_mark)), t_in,
                ENTRY_MATCH_WINDOW_H)
            if got is None:
                legs = {}
                break
            prem, _ = got
            sigma = greeks.implied_vol_scalar(prem, S_in, float(K), T_in, cp)
            if not np.isfinite(sigma):
                legs = {}
                break
            legs[cp] = (sym, prem, sigma)
        if legs:
            entry = (float(K), legs)
            break
    if entry is None:
        return None
    K, legs = entry
    (sym_c, prem_c, sig_c), (sym_p, prem_p, sig_p) = legs[1], legs[-1]
    prem_in = prem_c + prem_p
    vega_usd = float(greeks.greeks(S_in, K, T_in, sig_c, 1)["vega_usd"]
                     + greeks.greeks(S_in, K, T_in, sig_p, -1)["vega_usd"])

    # ------------------------------------------------------------------ exit
    if EXITS[exit_key] is None or fri + EXITS[exit_key] * HOUR_MS >= expiry_ms:
        t_out, settled = expiry_ms, True
    else:
        t_out, settled = fri + EXITS[exit_key] * HOUR_MS, False

    # optional stop: first hour bar whose mark straddle value breaches the
    # multiple. Mark candles of the traded contract only — nothing selective.
    stopped = False
    if stop_mult is not None:
        mc = load_candles(sym_c, mark=True)
        mp = load_candles(sym_p, mark=True)
        m = pd.merge(mc[["ts", "close"]], mp[["ts", "close"]], on="ts",
                     suffixes=("_c", "_p"))
        m = m[(m["ts"] + HOUR_MS > t_in) & (m["ts"] + HOUR_MS <= t_out)]
        breach = m[m["close_c"] + m["close_p"] >= stop_mult * prem_in]
        if not breach.empty:
            t_out = int(breach["ts"].iloc[0]) + HOUR_MS
            settled, stopped = False, True

    if settled:
        S_T = float(price_at(px, np.int64(expiry_ms)))
        prem_out = max(S_T - K, 0.0) + max(K - S_T, 0.0)
    else:
        vals = []
        for sym in (sym_c, sym_p):
            got = candle_close_before(load_candles(sym, mark=True), t_out,
                                      EXIT_MATCH_WINDOW_H)
            if got is None:
                return None
            vals.append(got[0])
        prem_out = float(sum(vals))

    hpnl, perp_fees = hedge_pnl(px, t_in, t_out, K, sig_c, sig_p, expiry_ms,
                                rehedge_minutes)
    gross = (prem_in - prem_out) + hpnl

    fee_legs = 0.0
    for prem in (prem_c, prem_p):
        fee_legs += float(costs.delta_india_option_fee_usd(S_in, prem))
    if settled:
        # settlement fee applies only to the ITM leg's notional
        fee_legs += float(
            costs.DELTA_INDIA["settlement_fee_rate"]
            * (1 + costs.DELTA_INDIA["gst"]) * S_in) if prem_out > 0 else 0.0
    else:
        S_out = float(price_at(px, np.int64(t_out)))
        fee_legs += float(costs.delta_india_option_fee_usd(S_out, prem_out))
    spread_cost = 2.0 * vega_usd * half_spread_vol
    net = gross - fee_legs - spread_cost - perp_fees

    sig_in = 0.5 * (sig_c + sig_p)
    wd_vol = _rv_ann(px, fri - 4 * DAY_MS, t_in)
    fri_move = np.nan
    S_fri0 = float(price_at(px, np.int64(fri)))
    if S_fri0 > 0:
        fri_move = 100.0 * (S_in / S_fri0 - 1.0)

    return {
        "friday": pd.Timestamp(fri, unit="ms", tz="UTC").date(),
        "expiry_ms": expiry_ms, "K": K, "S_in": S_in,
        "prem_in": prem_in, "prem_out": prem_out,
        "sigma_in": sig_in, "vega_usd": vega_usd,
        "wknd_frac": wknd_frac, "T_days": T_in * 365.25,
        "settled": settled, "stopped": stopped,
        "gross": gross, "fees_opt": fee_legs, "spread_cost": spread_cost,
        "perp_fees": perp_fees, "net": net,
        "gross_per_vega": gross / vega_usd, "net_per_vega": net / vega_usd,
        "f_iv": sig_in, "f_wd_vol": wd_vol,
        "f_iv_premium": sig_in / wd_vol if wd_vol and np.isfinite(wd_vol)
        else np.nan,
        "f_friday_move_abs": abs(fri_move),
        "f_wknd_frac": wknd_frac, "f_T_days": T_in * 365.25,
    }


def summarize(bl: pd.DataFrame) -> dict:
    if bl.empty:
        return {}
    r = bl["net_per_vega"]
    n = len(r)
    t = float(r.mean() / (r.std(ddof=1) / np.sqrt(n))) if n > 2 else np.nan
    return {
        "n": n,
        "gross_per_vega": float(bl["gross_per_vega"].mean()),
        "net_per_vega": float(r.mean()),
        "t": t,
        "sharpe_ann": float(r.mean() / r.std(ddof=1) * np.sqrt(52))
        if n > 2 else np.nan,
        "hit_rate": float((r > 0).mean()),
        "worst": float(r.min()),
        "cost_per_vega": float(
            (bl["fees_opt"] + bl["spread_cost"] + bl["perp_fees"])
            .div(bl["vega_usd"]).mean()),
    }
