"""Trading costs, measured from the tape rather than assumed.

Two components matter for anything claiming to be tradeable:

* **Fees.** Deribit charges 0.03% of the underlying on options, capped at 12.5%
  of the premium, and about 0.05% taker on the perpetual. The cap binds
  constantly for short-dated out-of-the-money contracts, where the premium is a
  tiny fraction of notional, so it cannot be ignored.
* **Spread.** We have no order book, only trades — but every trade carries the
  aggressor side, so the average implied vol paid by buyers minus that received
  by sellers in the same instrument on the same day is twice the effective half
  spread. That is the Roll intuition applied in volatility units, and it is what
  a taker actually pays.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

OPTION_FEE_RATE = 0.0003          # 0.03% of underlying
OPTION_FEE_CAP = 0.125            # ... capped at 12.5% of the premium
PERP_TAKER_FEE = 0.0005           # 0.05% of notional
DELIVERY_FEE_RATE = 0.00015       # 0.015% of underlying at settlement, same cap


def option_fee_usd(underlying_usd, premium_usd, rate: float = OPTION_FEE_RATE,
                   cap: float = OPTION_FEE_CAP) -> np.ndarray:
    """Per-contract option fee in USD, with the premium cap applied."""
    underlying_usd = np.asarray(underlying_usd, dtype="float64")
    premium_usd = np.asarray(premium_usd, dtype="float64")
    return np.minimum(rate * underlying_usd, cap * np.abs(premium_usd))


def perp_fee_usd(notional_usd, rate: float = PERP_TAKER_FEE) -> np.ndarray:
    return rate * np.abs(np.asarray(notional_usd, dtype="float64"))


def effective_spread_iv(df: pd.DataFrame, min_trades: int = 20) -> pd.DataFrame:
    """Effective half-spread in vol points, per (instrument, day).

    Buyer-paid minus seller-received implied vol is the full effective spread;
    half of it is what one side pays. Requires both sides present on the day, so
    instruments that traded one-way are dropped rather than imputed.
    """
    d = df[["date", "instrument_name", "direction", "sigma"]].dropna()
    d = d[np.isfinite(d["sigma"])]
    g = d.groupby(["date", "instrument_name", "direction"])["sigma"].agg(
        ["mean", "size"]).reset_index()
    piv = g.pivot_table(index=["date", "instrument_name"], columns="direction",
                        values=["mean", "size"])
    if (1 not in piv["mean"].columns) or (-1 not in piv["mean"].columns):
        return pd.DataFrame()
    out = pd.DataFrame({
        "iv_buy": piv["mean"][1], "iv_sell": piv["mean"][-1],
        "n_buy": piv["size"][1], "n_sell": piv["size"][-1],
    }).dropna()
    out = out[(out["n_buy"] + out["n_sell"]) >= min_trades]
    out["half_spread_vol"] = (out["iv_buy"] - out["iv_sell"]) / 2.0
    return out.reset_index()


def summarize_spread(spread: pd.DataFrame) -> dict:
    if spread.empty:
        return {}
    h = spread["half_spread_vol"]
    return {
        "n_instrument_days": int(len(spread)),
        "median_half_spread_volpts": float(h.median() * 100),
        "mean_half_spread_volpts": float(h.mean() * 100),
        "p90_half_spread_volpts": float(h.quantile(0.9) * 100),
        "share_negative": float((h < 0).mean()),
    }


# ----------------------------------------------------- Delta Exchange India
#
# Same fee *rate* as Deribit but a much tighter premium cap (3.5% vs 12.5%),
# which binds for near-ATM short-dated contracts rather than only deep OTM,
# and 18% GST on every fee. Verified against delta.exchange/fees 2026-08.

DELTA_INDIA = {
    "option_fee_rate": 0.0003,     # 0.03% of underlying notional
    "option_fee_cap": 0.035,       # ... capped at 3.5% of premium
    "perp_taker_fee": 0.0005,      # 0.05% of notional
    "settlement_fee_rate": 0.0005, # taker fee charged on contracts held to expiry
    "gst": 0.18,                   # applied to every fee above
}


def delta_india_option_fee_usd(underlying_usd, premium_usd,
                               fees: dict = DELTA_INDIA) -> np.ndarray:
    """Per-unit option taker fee in USD, GST included."""
    base = np.minimum(fees["option_fee_rate"] * np.abs(np.asarray(underlying_usd, dtype="float64")),
                      fees["option_fee_cap"] * np.abs(np.asarray(premium_usd, dtype="float64")))
    return base * (1.0 + fees["gst"])


def delta_india_perp_fee_usd(notional_usd, fees: dict = DELTA_INDIA) -> np.ndarray:
    return fees["perp_taker_fee"] * (1.0 + fees["gst"]) * \
        np.abs(np.asarray(notional_usd, dtype="float64"))


def round_trip_hedged_cost(F_in, F_out, prem_in, prem_out, vega_usd,
                           half_spread_vol, perp_fees_usd,
                           venue: str = "delta_india",
                           settled: bool = False) -> np.ndarray:
    """Total cost in USD of one short-hedged-option round trip, per unit.

    Components: option taker fee on entry and (unless held to settlement)
    exit; the effective spread crossed both ways, charged in vega terms; and
    the perp hedging fees accumulated along the path (computed by the hedging
    engine, passed in). This is the assembly previously copy-pasted across the
    weekend scripts, factored once.
    """
    if venue == "delta_india":
        fee_in = delta_india_option_fee_usd(F_in, prem_in)
        fee_out = np.where(
            settled,
            DELTA_INDIA["settlement_fee_rate"] * (1.0 + DELTA_INDIA["gst"])
            * np.abs(np.asarray(F_out, dtype="float64")),
            delta_india_option_fee_usd(F_out, prem_out))
    elif venue == "deribit":
        fee_in = option_fee_usd(F_in, prem_in)
        fee_out = np.where(settled,
                           np.minimum(DELIVERY_FEE_RATE * np.abs(np.asarray(F_out, dtype="float64")),
                                      OPTION_FEE_CAP * np.abs(np.asarray(prem_out, dtype="float64"))),
                           option_fee_usd(F_out, prem_out))
    else:
        raise ValueError(f"unknown venue {venue!r}")
    spread = 2.0 * np.abs(np.asarray(vega_usd, dtype="float64")) * \
        np.abs(np.asarray(half_spread_vol, dtype="float64"))
    return fee_in + fee_out + spread + np.asarray(perp_fees_usd, dtype="float64")


def quoted_spread_table(tickers: list[dict]) -> pd.DataFrame:
    """Half-spread in vol points by |delta| bucket x days-to-expiry, from a
    live Delta ticker snapshot. Delta quotes bid_iv/ask_iv directly (decimals),
    which Deribit never did; this replaces the Roll proxy for that venue.
    """
    rows = []
    now = pd.Timestamp.utcnow()
    for t in tickers:
        q = t.get("quotes") or {}
        g = t.get("greeks") or {}
        try:
            bid, ask = float(q["bid_iv"]), float(q["ask_iv"])
            delta = abs(float(g["delta"]))
        except (KeyError, TypeError, ValueError):
            continue
        sym = t.get("symbol", "")
        try:
            from .venues.delta_symbols import parse_symbol, expiry_ts_ms
            exp_ms = expiry_ts_ms(parse_symbol(sym)["expiry_date"])
        except ValueError:
            continue
        tdays = (exp_ms / 1000 - now.timestamp()) / 86400.0
        if tdays <= 0 or ask <= bid <= 0:
            continue
        rows.append({"symbol": sym, "abs_delta": delta, "t_days": tdays,
                     "half_spread_vol": (ask - bid) / 2.0})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["delta_bucket"] = pd.cut(df["abs_delta"], [0, 0.125, 0.375, 0.625, 1.0],
                                labels=["dotm", "otm", "atm", "itm"])
    df["tau_bucket"] = pd.cut(df["t_days"], [0, 2, 7, 30, 10_000],
                              labels=["0-2d", "2-7d", "7-30d", "30d+"])
    return df
