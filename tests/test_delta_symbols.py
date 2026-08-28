"""Delta India symbol grammar, expiry clock, strike ladder, client envelope."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from dbop.venues import delta_india as dx
from dbop.venues import delta_symbols as ds


def test_parse_roundtrip():
    p = ds.parse_symbol("C-BTC-80000-210826")
    assert p["cp"] == "C" and p["cp_sign"] == 1
    assert p["currency"] == "BTC"
    assert p["strike"] == 80000.0
    assert p["expiry_date"] == dt.date(2026, 8, 21)
    assert not p["is_mark"]
    assert ds.format_symbol("C", "BTC", 80000, dt.date(2026, 8, 21)) == \
        "C-BTC-80000-210826"


def test_parse_mark_prefix():
    p = ds.parse_symbol("MARK:P-ETH-4600-040926")
    assert p["is_mark"] and p["cp_sign"] == -1
    assert p["strike"] == 4600.0
    assert p["expiry_date"] == dt.date(2026, 9, 4)
    assert ds.mark_symbol("P-ETH-4600-040926") == "MARK:P-ETH-4600-040926"
    assert ds.mark_symbol("MARK:P-ETH-4600-040926") == "MARK:P-ETH-4600-040926"


def test_parse_rejects_garbage():
    for bad in ("BTC-27JUN25-60000-C", "X-BTC-80000-210826",
                "C-BTC-80000-2108", "C-BTC--210826"):
        with pytest.raises(ValueError):
            ds.parse_symbol(bad)


def test_expiry_ts_is_noon_utc():
    ms = ds.expiry_ts_ms(dt.date(2026, 8, 21))
    t = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)
    assert (t.hour, t.minute) == (12, 0)
    assert t.date() == dt.date(2026, 8, 21)


def test_strike_ladder_grid_and_width():
    spot = 80_123.0
    ks = ds.strike_ladder(spot, "BTC")
    step = ds.PROBE_STEP["BTC"]
    # every strike on the venue grid
    assert np.allclose(ks % step, 0.0)
    # covers +/- 25% inclusively
    assert ks.min() <= spot * 0.75 and ks.max() >= spot * 1.25
    # contiguous
    assert np.allclose(np.diff(ks), step)


def test_envelope_unwrap():
    assert dx.unwrap({"success": True, "result": [1, 2]}) == [1, 2]
    with pytest.raises(dx.DeltaError):
        dx.unwrap({"success": False, "error": {"code": "not_found"}})
    with pytest.raises(dx.DeltaError):
        dx.unwrap([1, 2])


def test_chunk_stays_under_page():
    for res, sec in dx.RESOLUTION_SECONDS.items():
        assert dx.chunk_seconds(res) // sec <= dx.MAX_CANDLES_PER_REQUEST
