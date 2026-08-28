"""Rate-limited client for Delta Exchange India's public REST API.

All endpoints used are public GET with no authentication. Differences from the
Deribit client (dbop.api) that justify a separate module rather than a flag:

* Envelope. Delta wraps every response as ``{"success": bool, "result": ...}``
  (plus ``{"error": {...}}`` on failure) instead of Deribit's JSON-RPC
  ``{"result": ..., "error": ...}``.
* Rate limit. Delta grants 10,000 request-units per rolling 5-minute window
  with per-endpoint weights (reads are 1-3 units), not a requests-per-second
  cap. We run the shared token bucket at a deliberately conservative rate so a
  many-hour discovery probe never trips HTTP 429 mid-run.
* Candles. ``/v2/history/candles`` takes unix *seconds*, returns newest-first,
  and silently truncates to the most recent 4,000 candles in the window
  (measured 2026-08-26) -- the same class of silent truncation that once
  inflated Deribit realized vol 222x, so the chunking here never requests more
  than one page's worth.

Verified availability (2026-08-26): BTCUSD daily candles from 2023-12-29,
ETHUSD from 2024-02-06; 15m/1h from 2024-01-10; 1m from at latest 2025-01-01.
Expired options keep both traded candles (``C-BTC-80000-210826``) and
mark-model candles (``MARK:C-BTC-80000-210826``). Option ticker IVs are
decimals (0.33), unlike Deribit's percent convention.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

from .. import config
from ..api import RateLimiter

log = logging.getLogger(__name__)

BASE = "https://api.india.delta.exchange/v2"

# 10,000 units / 300 s = 33 units/s ceiling; candle reads weigh ~3 units, so
# ~11 req/s is the true limit. Run at half that.
RATE_LIMIT_RPS = 5.0
BACKFILL_RETRIES = 10
MAX_CANDLES_PER_REQUEST = 4000
SAFETY = 0.9

RESOLUTION_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400, "1w": 604800,
}

# Options settle at 12:00 UTC (17:30 IST): the last 1h candle of an expiring
# contract stamps 11:00 UTC (verified on C-BTC-80000-210826).
EXPIRY_HOUR_UTC = 12

# First candle on the venue, per currency (probed; the perp launched with the
# India entity, long after the global Delta exchange).
SAMPLE_START = {"BTC": "2023-12-29", "ETH": "2024-02-06"}

PERPETUAL = {"BTC": "BTCUSD", "ETH": "ETHUSD"}

_LIMITER = RateLimiter(RATE_LIMIT_RPS)

_session: requests.Session | None = None


def _sess() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": "dbop-research/0.1"})
    return _session


class DeltaError(RuntimeError):
    pass


def unwrap(payload: dict) -> Any:
    """Delta's envelope: {"success": true, "result": ...} or an error body."""
    if not isinstance(payload, dict):
        raise DeltaError(f"unexpected payload type {type(payload)}")
    if not payload.get("success", False):
        raise DeltaError(f"api error: {payload.get('error', payload)}")
    return payload["result"]


def get(path: str, params: dict[str, Any] | None = None,
        timeout: int | None = None, retries: int | None = None) -> Any:
    """GET a public endpoint and return the unwrapped ``result``.

    Retries on transport errors and 429/5xx with exponential backoff plus
    jitter. A 404 or an in-body error is raised immediately: during
    discovery-by-probe a miss is an answer, not a fault to retry.
    """
    timeout = timeout or config.REQUEST_TIMEOUT
    retries = retries or BACKFILL_RETRIES
    url = f"{BASE}/{path.lstrip('/')}"

    last_exc: Exception | None = None
    for attempt in range(retries):
        _LIMITER.acquire()
        try:
            r = _sess().get(url, params=params or {}, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise DeltaError(f"HTTP {r.status_code} from {path}")
            if r.status_code == 404:
                raise DeltaNotFound(path)
            r.raise_for_status()
            return unwrap(r.json())
        except DeltaNotFound:
            raise
        except (requests.RequestException, DeltaError, ValueError) as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            backoff = min(60.0, 2.0 ** attempt) * (0.5 + random.random())
            log.warning("retry %d/%d for %s (%s); sleeping %.1fs",
                        attempt + 1, retries, path, exc, backoff)
            time.sleep(backoff)
    raise DeltaError(f"GET {path} failed after {retries} attempts: {last_exc}")


class DeltaNotFound(DeltaError):
    pass


# ------------------------------------------------------------------ endpoints


def get_candles(symbol: str, resolution: str, start_s: int, end_s: int) -> list[dict]:
    """One page of OHLCV candles, oldest-first.

    The API returns newest-first and truncates to the newest 4,000 in range;
    callers must keep the window under the page size (see ``chunk_seconds``).
    """
    res = get("history/candles", {
        "symbol": symbol, "resolution": resolution,
        "start": int(start_s), "end": int(end_s),
    })
    return list(reversed(res))


def chunk_seconds(resolution: str) -> int:
    """Window length that stays safely under one candle page."""
    return int(MAX_CANDLES_PER_REQUEST * SAFETY) * RESOLUTION_SECONDS[resolution]


def get_tickers(contract_types: str | None = None,
                underlying_asset_symbols: str | None = None) -> list[dict]:
    params: dict[str, Any] = {}
    if contract_types:
        params["contract_types"] = contract_types
    if underlying_asset_symbols:
        params["underlying_asset_symbols"] = underlying_asset_symbols
    return get("tickers", params)


def get_products(contract_types: str | None = None,
                 states: str = "live") -> list[dict]:
    params: dict[str, Any] = {"states": states}
    if contract_types:
        params["contract_types"] = contract_types
    return get("products", params)


def get_trades(symbol: str) -> list[dict]:
    """Recent public trades (no history; the venue keeps only a short window)."""
    return get(f"trades/{symbol}")
