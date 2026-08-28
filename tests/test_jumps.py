"""Tests for the jump/diffusion decomposition behind the risk horse race."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dbop import config, jumps

BARS_PER_DAY = 24 * 60 // config.BAR_MINUTES


def synth(n_days: int = 60, sigma: float = 0.002, seed: int = 0,
          jump_days: dict | None = None) -> pd.DataFrame:
    """A 5-minute bar series with i.i.d. Gaussian returns and planted jumps.

    ``jump_days`` maps a day index to the log jump size inserted midway through
    that day, so a test can ask for a known quantity of jump variance back.
    """
    rng = np.random.default_rng(seed)
    n = n_days * BARS_PER_DAY
    r = rng.normal(0.0, sigma, n)
    for day, size in (jump_days or {}).items():
        r[day * BARS_PER_DAY + BARS_PER_DAY // 2] = size
    ts = pd.date_range("2024-01-01", periods=n + 1,
                       freq=f"{config.BAR_MINUTES}min", tz="UTC")
    close = 100.0 * np.exp(np.concatenate([[0.0], np.cumsum(r)]))
    return pd.DataFrame({"ts": ts, "close": close})


def test_contiguous_returns_drop_gap_spanning_bars():
    b = synth(n_days=3)
    cut = b.drop(index=range(100, 140)).reset_index(drop=True)
    d = jumps.contiguous_returns(cut)
    step = pd.Timedelta(minutes=config.BAR_MINUTES)
    assert (d["ts"].diff().dropna() >= step).all()
    # The one return that would have spanned the hole is gone, not stretched.
    assert d["r"].abs().max() < 0.05


def test_slots_and_weekend_flag():
    d = jumps.contiguous_returns(synth(n_days=10))
    assert d["slot"].min() == 0
    assert d["slot"].max() == BARS_PER_DAY - 1
    assert set(d.loc[d["is_weekend"], "ts"].dt.dayofweek) == {5, 6}


def test_pure_diffusion_has_almost_no_jump_variance():
    day = jumps.decompose(synth(n_days=120, seed=1))
    # Truncation at three local standard deviations always clips a little of a
    # Gaussian, so this is a tolerance rather than an exact zero.
    assert day["jump_share"].mean() < 0.05
    assert np.allclose(day["bpv"], day["rv"], rtol=0.30)


def test_planted_jump_is_recovered():
    size = 0.05                     # ~25 local sd, unmistakably a jump
    day = jumps.decompose(synth(n_days=120, seed=2, jump_days={10: size}))
    hit = day.iloc[10]
    assert hit["n_jumps"] >= 1
    assert hit["jv"] == pytest.approx(size ** 2, rel=0.05)
    # Truncation at three local standard deviations misclassifies roughly 0.3%
    # of Gaussian returns by construction, so the background is small but not
    # zero. What must hold is that it is negligible beside a real jump: the
    # planted day carries an order of magnitude more jump variance than any
    # other day in a series that contains no other jumps.
    others = day.drop(index=10)
    assert others["n_jumps"].mean() / others["n"].mean() < 0.01
    assert hit["jv"] > 10 * others["jv"].max()


def test_ratio_at_kappa_endpoints():
    m = {"c_wd": 0.8, "j_wd": 0.2, "c_we": 0.4, "j_we": 0.2}
    m.update(realized_ratio=(m["c_we"] + m["j_we"]) / (m["c_wd"] + m["j_wd"]),
             jump_ratio=m["j_we"] / m["j_wd"])
    assert jumps.ratio_at_kappa(m, 1.0) == pytest.approx(m["realized_ratio"])
    assert jumps.ratio_at_kappa(m, 0.0) == pytest.approx(0.5)
    assert jumps.ratio_at_kappa(m, 1e9) == pytest.approx(m["jump_ratio"], rel=1e-6)


def test_ratio_at_kappa_is_monotone_and_bounded():
    m = {"c_wd": 0.8, "j_wd": 0.2, "c_we": 0.4, "j_we": 0.2}
    m.update(realized_ratio=0.6, jump_ratio=1.0)
    k = np.linspace(1.0, 500.0, 400)
    r = jumps.ratio_at_kappa(m, k)
    assert np.all(np.diff(r) > 0)
    lo, hi = jumps.reachable_interval(m)
    assert lo <= r.min() and r.max() <= hi + 1e-12


def test_proportional_premium_cancels_in_the_ratio():
    """A premium applied equally to every kind of calendar time is invisible
    here, which is the reason the decomposition has to be by day type."""
    m = {"c_wd": 0.8, "j_wd": 0.2, "c_we": 0.4, "j_we": 0.2}
    scaled = {k: 3.7 * v for k, v in m.items()}
    for k in (1.0, 2.5, 10.0):
        assert jumps.ratio_at_kappa(m, k) == pytest.approx(
            jumps.ratio_at_kappa(scaled, k))


def test_required_kappa_round_trips():
    m = {"c_wd": 0.8, "j_wd": 0.2, "c_we": 0.4, "j_we": 0.2}
    m.update(realized_ratio=0.6, jump_ratio=1.0)
    for k0 in (1.0, 2.0, 4.5, 20.0):
        target = float(jumps.ratio_at_kappa(m, k0))
        assert jumps.required_kappa(m, target) == pytest.approx(k0, rel=1e-8)


def test_required_kappa_is_nan_outside_the_reachable_interval():
    m = {"c_wd": 0.8, "j_wd": 0.2, "c_we": 0.4, "j_we": 0.2}
    m.update(realized_ratio=0.6, jump_ratio=1.0)
    # Below the realized ratio: a jump premium moves the priced ratio up here,
    # so under-pricing the weekend cannot be jump compensation at any size.
    assert np.isnan(jumps.required_kappa(m, 0.45))
    # Above the jump ratio: unreachable in the limit.
    assert np.isnan(jumps.required_kappa(m, 1.20))


def test_regime_means_split_by_day_type():
    day = jumps.decompose(synth(n_days=90, seed=3))
    m = jumps.regime_means(day)
    assert m["n_wd"] + m["n_we"] == len(day)
    assert m["n_we"] == int(day["is_weekend"].sum())
    # i.i.d. returns: nothing distinguishes the two regimes.
    assert m["realized_ratio"] == pytest.approx(1.0, abs=0.15)


def test_week_blocks_group_seven_days():
    day = jumps.decompose(synth(n_days=70, seed=4))
    blocks = jumps.week_blocks(day)
    counts = pd.Series(blocks).value_counts()
    assert counts.max() <= 7
    assert (counts == 7).sum() >= 8


def test_resample_thins_onto_the_coarse_grid():
    b = synth(n_days=5)
    r = jumps.resample(b, 30)
    assert (r["ts"].dt.minute % 30 == 0).all()
    assert (r["ts"].diff().dropna() == pd.Timedelta(minutes=30)).all()
    assert len(r) == pytest.approx(len(b) / 6, rel=0.05)


def test_decompose_honours_a_coarser_sampling_interval():
    b = synth(n_days=60, seed=5)
    day = jumps.decompose(b, step_minutes=30)
    assert day["n"].max() <= 48
    assert (day["n"] >= jumps.min_bars_for(30)).all()
    # Same days, coarser grid: variance is a sum over the day either way, so the
    # level survives even though each estimate is noisier.
    fine = jumps.decompose(b)
    assert day["rv"].mean() == pytest.approx(fine["rv"].mean(), rel=0.25)


def test_signature_is_flat_for_a_series_with_no_weekend_effect():
    sig = jumps.signature(synth(n_days=200, seed=6), steps=(5, 15, 30, 60))
    assert list(sig["step_minutes"]) == [5, 15, 30, 60]
    # i.i.d. returns and no stale prices: nothing to find at any interval.
    assert sig["variance_ratio"].sub(1.0).abs().max() < 0.20
    assert sig["zero_share_wd"].max() == 0.0


def test_stale_prices_do_not_silently_disable_jump_detection():
    """A series whose price repeats most of the time drives the intraday factor
    to zero. The estimator must fall back rather than return NaN thresholds,
    which would classify nothing as a jump and report a jump share of zero."""
    b = synth(n_days=60, seed=7, jump_days={5: 0.05})
    close = b["close"].to_numpy().copy()
    rng = np.random.default_rng(8)
    stale = rng.random(len(close)) < 0.85
    stale[0] = False
    idx = np.flatnonzero(~stale)
    # Hold the last genuine price forward everywhere else.
    close = close[idx[np.searchsorted(idx, np.arange(len(close)), "right") - 1]]
    b = b.assign(close=close)
    day = jumps.decompose(b)
    assert np.isfinite(day["jv"]).all()
    assert day["jv"].sum() > 0


def test_short_days_are_dropped():
    b = synth(n_days=10)
    # Remove most of day 4's bars; it should not survive the bar-count floor.
    lo = 4 * BARS_PER_DAY + 20
    b = b.drop(index=range(lo, lo + BARS_PER_DAY - 60)).reset_index(drop=True)
    day = jumps.decompose(b)
    assert (day["n"] >= jumps.MIN_BARS_PER_DAY).all()
