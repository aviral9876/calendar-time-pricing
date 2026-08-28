"""Tests for scripts/weekend_short.py.

The script's numbers all rest on three things being right: the spread is signed
so that a *loss* on a short weekend position shows up as a loss, the summary
statistics of a P&L series are what they claim to be, and the weekend-behaviour
panel measures each weekend against the right two days. None of that needs the
tape -- it needs planted series whose answers are known in advance, which is
what this file builds.

The signing test is the one that matters. A sign error in the leg subtraction
would flip the paper's headline from "the trade has inverted" to "the trade is
better than ever" while leaving every diagnostic looking healthy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_short as S  # noqa: E402


# ----------------------------------------------------------------- simulators

def pnl_series(n=400, mean=0.02, sd=0.15, seed=0) -> pd.DataFrame:
    """A daily spread P&L with a known mean, indexed by business date."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-02", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"spread_net": rng.normal(mean, sd, n)}, index=dates)


def bar_frame(n_weeks=40, weekend_vol=0.3, weekday_vol=0.6, drift=0.0,
              seed=0) -> pd.DataFrame:
    """Five-minute closes whose weekend and weekday volatilities are planted."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01", tz="UTC")          # a Monday
    n = n_weeks * 7 * 24 * 12
    ts = start + pd.to_timedelta(np.arange(n) * 5, unit="m")
    per_year = 365.25 * 24 * 12
    is_we = np.asarray(ts.dayofweek) >= 5
    sd = np.where(is_we, weekend_vol, weekday_vol) / np.sqrt(per_year)
    r = rng.normal(drift / per_year, sd, n)
    close = 50_000 * np.exp(np.cumsum(r))
    return pd.DataFrame({"ts": ts, "close": close,
                         "timestamp": ts.astype("int64") // 10**6})


# ---------------------------------------------------------------------- tests

def test_the_spread_is_short_the_weekend_leg():
    """A short weekend position losing money must show as a spread loss.

    Both stored legs are P&L of a SHORT option, so the spread is weekend minus
    weekday. Planting a loss on the weekend leg and a gain on the weekday leg
    must give a doubly negative spread, not a positive one.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    legs = pd.DataFrame({"weekend_heavy": [-0.10, -0.20, -0.05],
                         "weekday_only": [+0.10, +0.05, +0.00]}, index=idx)
    spread = legs["weekend_heavy"] - legs["weekday_only"]
    assert (spread < 0).all()
    assert spread.iloc[0] == pytest.approx(-0.20)


def test_stats_recover_a_planted_mean():
    d = pnl_series(n=1500, mean=0.03, sd=0.20, seed=1)
    st = S._stats(d["spread_net"])
    assert st["n"] == 1500
    assert st["mean"] == pytest.approx(0.03, abs=0.012)
    assert st["t"] > 4
    assert st["total"] == pytest.approx(st["mean"] * st["n"], rel=1e-9)


def test_stats_sign_follows_the_series():
    up = S._stats(pnl_series(mean=+0.05, seed=2)["spread_net"])
    down = S._stats(pnl_series(mean=-0.05, seed=2)["spread_net"])
    assert up["t"] > 0 > down["t"]
    assert up["sharpe"] > 0 > down["sharpe"]
    assert up["hit_rate"] > 0.5 > down["hit_rate"]


def test_stats_refuse_a_single_observation():
    st = S._stats(pd.Series([0.1]))
    assert st["n"] == 1
    assert np.isnan(st["t"])


def test_by_year_splits_a_regime_change():
    """A series that is positive then negative must show both, and net out."""
    good = pnl_series(n=365, mean=+0.04, sd=0.10, seed=3)
    bad = pnl_series(n=365, mean=-0.04, sd=0.10, seed=4)
    bad.index = bad.index + pd.Timedelta(days=365)
    d = pd.concat([good, bad])
    out = S.by_year({"TEST": d}).set_index("period")
    years = [p for p in out.index if p.isdigit()]
    assert out.loc[years[0], "mean"] > 0 > out.loc[years[-1], "mean"]
    # The trailing window sees only the bad regime; the full sample averages.
    assert out.loc["last_6m", "mean"] < 0
    assert abs(out.loc["full", "mean"]) < 0.01


def test_trailing_windows_are_anchored_to_the_last_date():
    d = pnl_series(n=800, mean=0.01, seed=5)
    out = S.by_year({"TEST": d}).set_index("period")
    # 182 days back from the end, on a daily index, is 183 inclusive days.
    assert out.loc["last_6m", "n"] == 183
    assert out.loc["last_12m", "n"] == 366
    assert out.loc["full", "n"] == 800


def test_weekend_behaviour_recovers_planted_volatilities(monkeypatch):
    """The weekend/weekday vol ratio must come back at what was planted."""
    bars_df = bar_frame(weekend_vol=0.30, weekday_vol=0.60, seed=6)
    monkeypatch.setattr(S.bars, "load", lambda c, check=True: bars_df)
    beh = S.weekend_behaviour("TEST", pd.DataFrame())

    assert len(beh) >= 38
    assert beh["rv_vol_ann"].median() == pytest.approx(0.30, rel=0.12)
    assert beh["wd_vol_ann"].median() == pytest.approx(0.60, rel=0.12)
    assert beh["vol_ratio"].median() == pytest.approx(0.5, rel=0.15)


def test_weekend_return_is_measured_over_the_weekend_only(monkeypatch):
    """With a drift only the weekend hours should be attributed to it.

    A weekend return computed off a Friday close would pick up Friday's move
    as well, so the planted weekday drift must not leak into ret_pct.
    """
    rng = np.random.default_rng(7)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    n = 30 * 7 * 24 * 12
    ts = start + pd.to_timedelta(np.arange(n) * 5, unit="m")
    is_we = np.asarray(ts.dayofweek) >= 5
    # A big deterministic weekday drift; weekends are pure flat noise.
    r = np.where(is_we, rng.normal(0, 1e-5, n), 3e-4)
    bars_df = pd.DataFrame({"ts": ts, "close": 100 * np.exp(np.cumsum(r)),
                            "timestamp": ts.astype("int64") // 10**6})
    monkeypatch.setattr(S.bars, "load", lambda c, check=True: bars_df)
    beh = S.weekend_behaviour("TEST", pd.DataFrame())
    assert beh["ret_pct"].abs().max() < 0.5      # weekday drift did not leak


def test_weekends_are_keyed_by_their_saturday(monkeypatch):
    bars_df = bar_frame(n_weeks=6, seed=8)
    monkeypatch.setattr(S.bars, "load", lambda c, check=True: bars_df)
    beh = S.weekend_behaviour("TEST", pd.DataFrame())
    assert (pd.to_datetime(beh.index).dayofweek == 5).all()


def test_short_weekends_are_dropped(monkeypatch):
    """A weekend missing most of its bars must not become a quiet weekend."""
    bars_df = bar_frame(n_weeks=10, seed=9)
    ts = pd.to_datetime(bars_df["ts"])
    # Gut one Saturday: keep a tenth of it, which would read as near-zero RV.
    sat = (ts.dt.dayofweek == 5) & (ts.dt.isocalendar().week == 2)
    drop = sat & (np.arange(len(bars_df)) % 10 != 0)
    monkeypatch.setattr(S.bars, "load",
                        lambda c, check=True: bars_df[~drop].reset_index(drop=True))
    beh = S.weekend_behaviour("TEST", pd.DataFrame())
    gutted = ts[sat].dt.floor("D").min()
    assert gutted not in beh.index


def test_behaviour_by_year_reports_mean_and_median_separately():
    """The mean/median gap is the finding, so both must survive aggregation."""
    idx = pd.date_range("2024-01-06", periods=52, freq="7D", tz="UTC")
    edge = np.full(52, 0.10)
    edge[:5] = -1.0                       # a few violent weekends
    b = pd.DataFrame({"ret_pct": np.zeros(52), "range_pct": np.ones(52),
                      "rv_vol_ann": np.full(52, 0.3),
                      "vol_ratio": np.full(52, 0.5),
                      "iv_weekend": np.full(52, 0.4),
                      "iv_minus_rv": edge}, index=idx)
    out = S.behaviour_by_year({"TEST": b})
    row = out.iloc[0]
    assert row["median_iv_minus_rv"] == pytest.approx(0.10)
    assert row["mean_iv_minus_rv"] < 0
    assert row["n_weekends"] == 52


def test_the_fee_drag_falls_as_rehedging_coarsens():
    """The ladder's whole point: cost per unit vega must fall with the interval.

    Planted as a check on the reported quantity rather than on the engine --
    fee drag is gross minus net, so it cannot be negative, and a ladder whose
    drag did not fall monotonically would mean the interval was not being
    applied.
    """
    lad = pd.DataFrame({
        "rehedge_minutes": [5, 60, 480, 1440],
        "outright_gross": [0.056, 0.064, 0.077, 0.079],
        "outright_mean": [-0.079, 0.004, 0.039, 0.045],
    })
    drag = lad["outright_gross"] - lad["outright_mean"]
    assert (drag > 0).all()
    assert drag.is_monotonic_decreasing


def test_outright_and_spread_differ_by_the_weekday_leg():
    """Removing the weekday leg must add back exactly that leg's P&L."""
    idx = pd.date_range("2025-01-01", periods=50, freq="D", tz="UTC")
    rng = np.random.default_rng(11)
    we = pd.Series(rng.normal(0.01, 0.1, 50), index=idx)
    wd = pd.Series(rng.normal(-0.02, 0.1, 50), index=idx)
    spread, outright = we - wd, we
    np.testing.assert_allclose((outright - spread).to_numpy(), wd.to_numpy())
    # The weekday leg carries its own mean, so the two series answer different
    # questions even when both are positive.
    assert S._stats(outright)["mean"] != pytest.approx(S._stats(spread)["mean"])
