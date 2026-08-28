"""Tests for the vintage-versus-window analysis in scripts/weekend_split.py.

The claim these guard is that the implied weekend discount has a trend and the
realized one does not. That is a statement about a weighted fit to seven annual
estimates, so the weighting and the standard error are the whole result -- an
unweighted fit would let the sparse early years, whose slopes are barely
identified, set the trend for the decade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_split as S  # noqa: E402


def test_wls_trend_recovers_a_planted_slope():
    x = np.arange(2020.0, 2027.0)
    y = 0.5 - 0.13 * (x - 2020)
    se = np.full_like(x, 0.01)
    t = S.wls_trend(x, y, se)
    assert t["slope_per_year"] == pytest.approx(-0.13, abs=1e-9)
    assert t["n_years"] == 7
    assert t["first"] == pytest.approx(0.5)
    assert t["last"] == pytest.approx(0.5 - 0.13 * 6)


def test_wls_trend_downweights_the_imprecise_years():
    """A wild early observation with a wild standard error must not set the
    trend. This is exactly the pre-2020 situation: no daily expiries, so the
    slope is barely identified and its own standard error says so."""
    x = np.arange(2020.0, 2027.0)
    y = 0.5 - 0.10 * (x - 2020)
    se = np.full_like(x, 0.01)
    y[0], se[0] = 6.0, 3.0            # unidentified first year
    t = S.wls_trend(x, y, se)
    assert t["slope_per_year"] == pytest.approx(-0.10, abs=0.01)
    # Equal weights let that one year manufacture a trend seven times the size.
    flat = S.wls_trend(x, y, np.full_like(x, 0.5))
    assert flat["slope_per_year"] < -0.3


def test_wls_trend_finds_nothing_in_a_flat_series():
    rng = np.random.default_rng(0)
    x = np.arange(2020.0, 2027.0)
    se = np.full_like(x, 0.05)
    y = 0.6 + rng.normal(0, 0.05, len(x))
    t = S.wls_trend(x, y, se)
    assert abs(t["t"]) < 2.5


def test_wls_trend_needs_enough_years():
    x = np.arange(2024.0, 2027.0)
    assert S.wls_trend(x, x * 0 + 1.0, x * 0 + 0.1) == {}


def test_clip_is_half_open_on_the_right():
    d = pd.DataFrame({"date": pd.to_datetime(
        ["2024-01-01", "2024-06-01", "2025-01-01"], utc=True)})
    lo = pd.Timestamp("2024-01-01", tz="UTC")
    hi = pd.Timestamp("2025-01-01", tz="UTC")
    out = S.clip(d, lo, hi)
    assert len(out) == 2
    assert out["date"].max() == pd.Timestamp("2024-06-01", tz="UTC")


def test_realized_reports_the_ratio_and_its_own_standard_error():
    rng = np.random.default_rng(1)
    n = 700
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    we = dates.dayofweek >= 5
    rv = pd.DataFrame({"date": dates, "is_weekend": we,
                       "rv_daily": np.where(we, 0.5, 1.0)
                       * rng.lognormal(0, 0.3, n)})
    out = S.realized(rv)
    assert out["realized_ratio"] == pytest.approx(0.5, abs=0.08)
    assert 0.0 < out["realized_ratio_se"] < 0.15
    assert out["n_we"] + out["n_wd"] == n


def test_realized_declines_a_window_too_short_to_measure():
    dates = pd.date_range("2024-01-01", periods=12, freq="D", tz="UTC")
    rv = pd.DataFrame({"date": dates, "is_weekend": dates.dayofweek >= 5,
                       "rv_daily": np.ones(12)})
    assert S.realized(rv) == {}
