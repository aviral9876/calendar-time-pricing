"""Rate-limited client for Deribit's public history API.

All endpoints here are public GET with no authentication. The base host matters:
history.deribit.com serves the complete archive since platform inception, while
www.deribit.com only answers for a recent window. Everything that backfills uses
the history host.

The limiter is a shared token bucket so that a threaded backfill still respects
one global request rate.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

# Deribit's "too many requests" code, returned inside a 200 body as well as
# alongside HTTP 429.
ERR_TOO_MANY_REQUESTS = 10028
ERR_TOO_MANY_SUBSCRIPTIONS = 10066


class RateLimiter:
    """Token bucket shared across threads."""

    def __init__(self, rate_per_sec: float, burst: float | None = None):
        self.rate = float(rate_per_sec)
        self.capacity = float(burst if burst is not None else max(rate_per_sec, 1.0))
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, n: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = n - self._tokens
                wait = deficit / self.rate
            time.sleep(wait)


_LIMITER = RateLimiter(config.RATE_LIMIT_RPS)

_thread_local = threading.local()


def _session() -> requests.Session:
    """One Session per thread; connection reuse matters over ~100k requests."""
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "dbop-research/0.1"})
        _thread_local.session = s
    return s


class DeribitError(RuntimeError):
    pass


def get(endpoint: str, params: dict[str, Any], base: str | None = None,
        timeout: int | None = None, retries: int | None = None) -> Any:
    """GET a public endpoint and return the parsed ``result``.

    Retries on transport errors, 429/5xx, and Deribit's in-body rate-limit code,
    with exponential backoff plus jitter.
    """
    base = base or config.HISTORY_BASE
    timeout = timeout or config.REQUEST_TIMEOUT
    retries = retries or config.MAX_RETRIES
    url = base + endpoint

    last_exc: Exception | None = None
    for attempt in range(retries):
        _LIMITER.acquire()
        try:
            r = _session().get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise DeribitError(f"HTTP {r.status_code} from {endpoint}")
            r.raise_for_status()
            payload = r.json()
            if "error" in payload and payload["error"] is not None:
                err = payload["error"]
                code = err.get("code") if isinstance(err, dict) else None
                if code in (ERR_TOO_MANY_REQUESTS, ERR_TOO_MANY_SUBSCRIPTIONS):
                    raise DeribitError(f"rate limited: {err}")
                raise DeribitError(f"{endpoint} error: {err}")
            return payload["result"]
        except (requests.RequestException, DeribitError, ValueError, KeyError) as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            backoff = min(60.0, 2.0 ** attempt) * (0.5 + random.random())
            log.warning("retry %d/%d for %s (%s); sleeping %.1fs",
                        attempt + 1, retries, endpoint, exc, backoff)
            time.sleep(backoff)
    raise DeribitError(f"GET {endpoint} failed after {retries} attempts: {last_exc}")


# ------------------------------------------------------------------ endpoints


def get_last_trades_by_currency_and_time(
    currency: str,
    start_ms: int,
    end_ms: int,
    kind: str = "option",
    count: int = config.TRADES_PAGE_SIZE,
    sorting: str = "asc",
) -> tuple[list[dict], bool]:
    """One page of trades in [start_ms, end_ms]. Returns (trades, has_more)."""
    res = get(
        "get_last_trades_by_currency_and_time",
        {
            "currency": currency,
            "kind": kind,
            "start_timestamp": int(start_ms),
            "end_timestamp": int(end_ms),
            "count": int(count),
            "sorting": sorting,
        },
    )
    return res.get("trades", []), bool(res.get("has_more", False))


def get_instruments(currency: str, kind: str = "option",
                    expired: bool = False) -> list[dict]:
    """Instrument metadata. expired=True returns delisted instruments, which is
    most of the sample for a study that runs back to 2016."""
    return get(
        "get_instruments",
        {"currency": currency, "kind": kind, "expired": str(expired).lower()},
        base=config.LIVE_BASE if not expired else config.HISTORY_BASE,
    )


def get_funding_rate_history(instrument_name: str, start_ms: int,
                             end_ms: int) -> list[dict]:
    """Hourly funding history for a perpetual. Each record carries the 8h and
    1h interest measures plus the index price.

    Only served by www; the history host returns HTTP 400 for this endpoint.
    """
    return get(
        "get_funding_rate_history",
        {
            "instrument_name": instrument_name,
            "start_timestamp": int(start_ms),
            "end_timestamp": int(end_ms),
        },
        base=config.LIVE_BASE,
    )


def get_tradingview_chart_data(instrument_name: str, start_ms: int, end_ms: int,
                               resolution: str = "5") -> dict:
    """OHLCV bars. Resolution is in minutes as a string ('1','5','60','1D')."""
    return get(
        "get_tradingview_chart_data",
        {
            "instrument_name": instrument_name,
            "start_timestamp": int(start_ms),
            "end_timestamp": int(end_ms),
            "resolution": resolution,
        },
    )


def get_volatility_index_data(currency: str, start_ms: int, end_ms: int,
                              resolution: str = "3600") -> dict:
    """DVOL history as [timestamp, open, high, low, close] rows.

    Resolution is in SECONDS here ('60', '3600', '43200', '1D'), unlike the
    chart endpoint which uses minutes. Only served by www.
    """
    return get(
        "get_volatility_index_data",
        {
            "currency": currency,
            "start_timestamp": int(start_ms),
            "end_timestamp": int(end_ms),
            "resolution": resolution,
        },
        base=config.LIVE_BASE,
    )


def get_index_price(index_name: str) -> dict:
    return get("get_index_price", {"index_name": index_name}, base=config.LIVE_BASE)
