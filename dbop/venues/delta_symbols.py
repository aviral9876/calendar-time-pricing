"""Delta Exchange India option symbol grammar and strike-ladder generation.

Delta symbols read ``C-BTC-80000-210826``: side, underlying, strike, expiry as
DDMMYY. Mark-model candles for the same contract live under a ``MARK:`` prefix.
Deribit's grammar (``BTC-27JUN25-60000-C``) is different enough that sharing a
parser would help nobody.

The strike ladder matters for discovery-by-probe: expired instruments are not
listed by any endpoint, so historical symbols are reconstructed as a grid of
plausible strikes around the spot price on each expiry date and probed against
the candle endpoint. The observed BTC spacing on daily expiries is 400 USD near
the money; probing at the finest spacing finds every coarser contract too,
since coarser strikes are multiples of the fine step.
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np

from . import delta_india

_SYMBOL_RE = re.compile(
    r"^(MARK:)?([CP])-([A-Z0-9]+)-(\d+(?:\.\d+)?)-(\d{6})$")

# Probe spacing per underlying, USD. Fine enough to hit every listed strike.
PROBE_STEP = {"BTC": 400.0, "ETH": 10.0}
# Ladder half-width around spot, as a fraction. Wide wings exist but carry no
# volume worth backtesting; the ladder is a discovery tool, not a census.
PROBE_WIDTH = 0.25


def parse_symbol(symbol: str) -> dict:
    """``C-BTC-80000-210826`` -> fields. Accepts the MARK: prefix."""
    m = _SYMBOL_RE.match(symbol)
    if not m:
        raise ValueError(f"not a Delta option symbol: {symbol!r}")
    mark, side, cur, strike, ddmmyy = m.groups()
    day, month, year = int(ddmmyy[:2]), int(ddmmyy[2:4]), 2000 + int(ddmmyy[4:6])
    return {
        "is_mark": bool(mark),
        "cp": side,                      # "C" or "P"
        "cp_sign": 1 if side == "C" else -1,
        "currency": cur,
        "strike": float(strike),
        "expiry_date": dt.date(year, month, day),
    }


def format_symbol(cp: str, currency: str, strike: float,
                  expiry: dt.date) -> str:
    if cp not in ("C", "P"):
        raise ValueError(f"cp must be 'C' or 'P', got {cp!r}")
    k = int(strike) if float(strike).is_integer() else strike
    return f"{cp}-{currency}-{k}-{expiry:%d%m%y}"


def mark_symbol(symbol: str) -> str:
    return symbol if symbol.startswith("MARK:") else f"MARK:{symbol}"


def expiry_ts_ms(expiry: dt.date) -> int:
    """Settlement instant: 12:00 UTC on the expiry date."""
    t = dt.datetime(expiry.year, expiry.month, expiry.day,
                    delta_india.EXPIRY_HOUR_UTC, tzinfo=dt.timezone.utc)
    return int(t.timestamp() * 1000)


def strike_ladder(spot: float, currency: str,
                  step: float | None = None,
                  width: float = PROBE_WIDTH) -> np.ndarray:
    """Strikes on the venue's grid within ``spot * (1 +/- width)``.

    Snapped to multiples of the probe step so generated symbols can actually
    have existed.
    """
    step = step or PROBE_STEP[currency]
    lo = np.floor(spot * (1.0 - width) / step) * step
    hi = np.ceil(spot * (1.0 + width) / step) * step
    return np.arange(lo, hi + step / 2, step)
