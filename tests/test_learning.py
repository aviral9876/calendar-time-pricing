"""Tests for scripts/weekend_learning.py.

The module's whole claim is that two estimators of "the weekend variance ratio"
have been telling different stories, and that the difference between them is
economics rather than measurement. Both halves of that are simulatable, so both
are simulated here rather than argued.

The market simulations plant a known truth in the *shape* of the daily variance
distribution -- in one, the mean ratio moves and in another only the centre does
-- and check that the arithmetic and geometric estimators each recover their own
estimand and neither recovers the other's. The microstructure simulations plant
noise instead of economics and check that the sampling ladder, which is the
paper's only defence against a measurement artefact, points the right way in
both directions: a real trend seen through noise strengthens as the interval
coarsens, and a trend manufactured by shrinking noise disappears.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_learning as L  # noqa: E402


# ----------------------------------------------------------------- simulators

def daily_panel(n_days: int = 1400, ratio0: float = 0.7,
                ratio_trend: float = 0.0, sd0: float = 0.8,
                we_sd_trend: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Daily realized variance with a known *arithmetic* weekend ratio.

    Variance is lognormal: log RV ~ N(m_g(t), s_g(t)^2). Writing the mean as
    exp(m + s^2/2) and solving for m keeps the ratio of means pinned at exactly
    ``ratio0 * exp(ratio_trend * t)`` whatever the dispersion does, which is what
    lets ``we_sd_trend`` move the centre of the weekend distribution without
    touching its mean. That configuration -- flat mean, falling centre -- is the
    one the module says the real data is in, and no estimator that cannot tell
    it from a flat market is any use here.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_days, freq="D", tz="UTC")
    t = np.arange(n_days) / 365.25
    we = np.asarray(dates.dayofweek) >= 5
    sd = np.where(we, sd0 + we_sd_trend * t, sd0)
    mean = np.where(we, ratio0 * np.exp(ratio_trend * t), 1.0)
    # A volatility cycle the fixed effects must absorb, common to both day types.
    cycle = np.exp(0.5 * np.sin(2 * np.pi * t / 1.3) + 0.3 * rng.normal(0, 1, n_days).cumsum() / np.sqrt(n_days))
    m = np.log(mean * cycle) - sd ** 2 / 2
    rv = np.exp(rng.normal(m, sd))
    return pd.DataFrame({"date": dates, "rv": rv, "n": 288,
                         "zero_share": 0.0, "is_weekend": we})


def bar_series(n_days: int = 900, ratio0: float = 0.8,
               ratio_trend: float = 0.0, noise: float = 0.0,
               noise_trend: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """Five-minute closes carrying a known weekend ratio, observed through noise.

    The observed log price is the efficient one plus an iid error, the standard
    microstructure model. That error contributes a fixed amount to every day's
    measured variance regardless of day type, so it pushes the measured ratio
    toward one, and it does so hardest at the finest sampling where there are
    most returns to contaminate. ``noise_trend`` shrinks the error over the
    sample, which is what improving liquidity looks like and which manufactures
    a downward trend in the measured ratio out of nothing.
    """
    rng = np.random.default_rng(seed)
    per_day = 288
    ts = pd.date_range("2020-01-01", periods=n_days * per_day, freq="5min",
                       tz="UTC")
    t = (np.arange(len(ts)) / per_day) / 365.25
    we = np.asarray(ts.dayofweek) >= 5
    day_var = np.where(we, ratio0 * np.exp(ratio_trend * t), 1.0) * 0.0004
    r = rng.normal(0, np.sqrt(day_var / per_day))
    logp = np.log(30000.0) + r.cumsum()
    nu = noise * np.exp(noise_trend * t)
    logp = logp + rng.normal(0, 1, len(ts)) * nu
    return pd.DataFrame({"ts": ts, "close": np.exp(logp)})


def ladder(bars_df, steps=(5, 60), monkeypatch=None):
    from dbop import bars as bars_mod
    monkeypatch.setattr(bars_mod, "load", lambda c, check=True: bars_df)
    return {s: L.ratio_trend(L.daily_rv("BTC", s), "geometric") for s in steps}


# ------------------------------------------------------- the two estimands

def test_arithmetic_estimator_recovers_a_planted_mean_trend():
    d = daily_panel(ratio_trend=-0.15, seed=1)
    r = L.ratio_trend(d, "arithmetic")
    assert r["trend_per_year"] == pytest.approx(-0.15, abs=0.05)
    assert r["t"] < -2


def test_both_agree_when_only_the_mean_moves():
    """With dispersion held fixed the two moments are the same statement.

    They agree on the truth, and they agree with each other to within the
    arithmetic estimator's own precision -- which is the loose one of the pair,
    and the reason the paper's original reading had no power.
    """
    d = daily_panel(ratio_trend=-0.15, seed=2)
    a = L.ratio_trend(d, "arithmetic")
    g = L.ratio_trend(d, "geometric")
    assert g["trend_per_year"] == pytest.approx(-0.15, abs=0.05)
    assert abs(g["trend_per_year"] - a["trend_per_year"]) < 2.5 * a["trend_se"]


def test_the_moments_separate_when_only_the_centre_moves():
    """The configuration the paper claims: flat mean, falling centre.

    The weekend's mean variance is pinned exactly constant and only its spread
    grows, which drags the geometric mean down while leaving the arithmetic one
    alone. An estimator that cannot see this would have read the real data the
    way section 5.5 originally did.
    """
    d = daily_panel(ratio_trend=0.0, we_sd_trend=0.22, n_days=2600, seed=3)
    a = L.ratio_trend(d, "arithmetic")
    g = L.ratio_trend(d, "geometric")
    assert abs(a["t"]) < 2.0, a
    assert g["trend_per_year"] < -0.05 and g["t"] < -3, g
    assert g["trend_per_year"] < a["trend_per_year"] - 0.05


def test_level_is_recovered_through_a_volatility_cycle():
    d = daily_panel(ratio0=0.55, n_days=2000, seed=4)
    assert L.ratio_trend(d, "arithmetic")["ratio_mid"] == pytest.approx(
        0.55, rel=0.12)


# ------------------------------------------------- the microstructure ladder

def test_noise_attenuates_a_real_trend_and_coarsening_restores_it(monkeypatch):
    """A genuine trend seen through constant noise steepens to the right.

    This is the signature Bitcoin and Ether show, and the test pins that it is
    the signature of a real trend rather than of a measurement one.
    """
    b = bar_series(ratio_trend=-0.20, noise=0.0006, seed=5)
    out = ladder(b, (5, 60), monkeypatch)
    assert out[5]["trend_per_year"] > -0.20     # attenuated toward zero
    assert out[60]["trend_per_year"] < out[5]["trend_per_year"]
    assert out[60]["trend_per_year"] == pytest.approx(-0.20, abs=0.07)


def test_shrinking_noise_manufactures_a_trend_that_coarsening_removes(monkeypatch):
    """The artefact the ladder exists to catch, and it points the other way.

    Here the true weekend ratio never moves; only the observation error shrinks,
    as it would if the weekend book were getting more liquid. That alone puts a
    downward trend in the measured ratio -- but only on the fine grid, because
    coarse sampling barely sees the noise in the first place.
    """
    b = bar_series(ratio_trend=0.0, noise=0.0016, noise_trend=-1.1, seed=6)
    out = ladder(b, (5, 60), monkeypatch)
    assert out[5]["trend_per_year"] < -0.03, out[5]
    assert out[60]["trend_per_year"] > out[5]["trend_per_year"] + 0.02
    assert abs(out[60]["trend_per_year"]) < abs(out[5]["trend_per_year"])


# --------------------------------------------------------------- the ladders

def test_trimming_reveals_a_trend_hidden_by_a_contaminated_tail():
    """A handful of huge late weekend days can flatten the mean's trend.

    This is the mechanism the trimming ladder is built to expose: the ratio of
    means stays flat because rare violent weekends hold it up, and cutting a
    small share off the top of each day type brings the underlying decline back.
    """
    d = daily_panel(ratio_trend=-0.20, n_days=2000, seed=7).copy()
    late = d["date"] > d["date"].quantile(0.55)
    hit = d.index[(late & d["is_weekend"]).to_numpy()][::30]
    d.loc[hit, "rv"] = d["rv"].quantile(0.999) * 1.5
    untrimmed = L.ratio_trend(d, "arithmetic")
    lad = L.trimming_ladder({c: d for c in ("BTC", "ETH", "SOL", "XRP")})
    lad = lad[lad["asset"] == "BTC"].set_index("trim")
    # Contaminating three and a half per cent of the later weekend days -- about
    # one a month -- is enough to hide a 20%-a-year decline from the ratio of
    # means completely, and to leave it looking like a mild move the other way.
    assert abs(untrimmed["t"]) < 2.0, untrimmed
    # Cutting five per cent off the top of each day type recovers the truth.
    assert lad.loc[0.05, "trend_per_year"] == pytest.approx(-0.20, abs=0.07)
    assert lad.loc[0.05, "t"] < -3
    assert lad.loc[0.05, "trend_per_year"] < untrimmed["trend_per_year"] - 0.10


def test_trimming_is_neutral_when_there_is_nothing_in_the_tail():
    d = daily_panel(ratio_trend=-0.12, n_days=1600, seed=8)
    lad = L.trimming_ladder({c: d for c in ("BTC", "ETH", "SOL", "XRP")})
    lad = lad[lad["asset"] == "BTC"].set_index("trim")
    assert lad.loc[0.10, "trend_per_year"] == pytest.approx(
        lad.loc[0.0, "trend_per_year"], abs=0.06)


def test_the_wedge_measures_right_tail_weight():
    """log mean - mean log is half the log variance for a lognormal."""
    d = daily_panel(sd0=0.9, we_sd_trend=0.0, n_days=1500, seed=9)
    w = L.wedge({c: d for c in ("BTC", "ETH", "SOL", "XRP")})
    w = w[w["asset"] == "BTC"]
    assert w["wedge_weekend"].mean() == pytest.approx(0.9 ** 2 / 2, abs=0.15)
    assert abs(w["wedge_diff"].mean()) < 0.12


# ------------------------------------------------------------ the estimators

def test_poisson_qmle_recovers_a_log_linear_mean():
    rng = np.random.default_rng(11)
    n = 6000
    x = rng.normal(0, 1, n)
    mu = np.exp(0.4 + 0.8 * x)
    y = mu * rng.gamma(2.0, 0.5, n)      # not Poisson, and it must not matter
    X = np.column_stack([np.ones(n), x])
    b, cov, _ = L.poisson_qmle(y, X, np.arange(n) // 50)
    assert b[1] == pytest.approx(0.8, abs=0.03)
    assert abs(b[1] - 0.8) < 3 * np.sqrt(cov[1, 1])


def test_attenuation_correction_undoes_known_regressor_noise():
    """Adding noise to the regressor must halve the slope and the fix restore it."""
    rng = np.random.default_rng(12)
    n = 240
    per = pd.period_range("2020Q1", periods=n // 4, freq="Q").astype(str)
    asset = np.repeat(["BTC", "ETH", "SOL", "XRP"], n // 4)
    truth = rng.normal(0, 0.30, n)
    noise_sd = 0.30                       # equal signal and noise -> reliability 1/2
    imp = pd.DataFrame({"asset": asset, "period": list(per) * 4,
                        "t_mid": pd.to_datetime("2020-01-01", utc=True)
                        + pd.to_timedelta(np.tile(np.arange(n // 4) * 91, 4), "D"),
                        "log_ratio": 1.0 * truth + rng.normal(0, 0.02, n)})
    real = pd.DataFrame({"asset": asset, "period": list(per) * 4,
                         "log_geometric": truth + rng.normal(0, noise_sd, n),
                         "log_geometric_se": noise_sd,
                         "log_arithmetic": truth,
                         "log_arithmetic_se": 1e-6})
    r = L.horse_race(imp, real).set_index("moment")
    assert r.loc["geometric", "beta"] < 0.75           # attenuated
    assert r.loc["geometric", "reliability"] == pytest.approx(0.5, abs=0.15)
    assert r.loc["geometric", "beta_corrected"] == pytest.approx(1.0, abs=0.25)
    # The cleanly measured regressor needs no correction and must not get one.
    assert r.loc["arithmetic", "reliability"] == pytest.approx(1.0, abs=0.02)
    assert r.loc["arithmetic", "beta"] == pytest.approx(1.0, abs=0.05)


def test_compare_reports_the_difference_and_its_sign():
    imp = pd.DataFrame([{"asset": "BTC", "trend_per_year": -0.19,
                         "trend_se": 0.02}])
    real = pd.DataFrame([
        {"asset": "BTC", "moment": "geometric", "trend_per_year": -0.18,
         "trend_se": 0.02},
        {"asset": "BTC", "moment": "arithmetic", "trend_per_year": -0.02,
         "trend_se": 0.03}])
    out = L.compare(imp, real).set_index("moment")
    assert abs(out.loc["geometric", "t"]) < 1.0
    assert out.loc["arithmetic", "t"] < -3.0
