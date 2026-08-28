"""Tests for the wing analysis in scripts/weekend_wings.py.

The script is a discriminator, so the tests are simulations of the things it has
to tell apart. A market whose smile follows the weekend clock, one whose smile
is pinned to the strike, and one that additionally believes weekend returns are
less jump-prone all produce the same qualitative picture -- a weekend discount
in every bucket -- and differ only in how much steeper the wing's discount is
than the money's. If the estimator cannot separate simulated versions of the
three, it cannot be trusted to separate the real ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_wings as W  # noqa: E402


# Strikes run to this many standard deviations either side, and the smile is
# scaled so that squared implied vol is half again its at-the-money value there
# -- about what the real books quote.
Z = 2.2
KAPPA = 0.5 / Z ** 2


def market(theta: float, n_days: int = 500, kappa: float = KAPPA,
           lam: float = 0.45, v0: float = 0.36, seed: int = 0,
           flatten: float = 0.0, noise: float = 0.01) -> pd.DataFrame:
    """A quoted surface with a known theta.

    Total variance to expiry is V = v0 * T * (1 - (1 - lam) * w), so the weekend
    counts for ``lam`` of a weekday. The surface is

        iv^2(x) = (V / T) * (1 + kappa * u^2),
        u = x / (V^((1-theta)/2) * V0^(theta/2))

    which at theta = 0 measures moneyness in the contract's own standard
    deviations -- the clock is fully in the smile -- and at theta = 1 measures
    it against a fixed scale, pinning the relative smile to the strike.

    ``flatten`` adds a belief on top: the smile is scaled down by an extra
    factor in the weekend fraction, which is outside the geometric family
    entirely and must show up as an amplification past the ceiling.
    """
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D", tz="UTC")
    for i, day in enumerate(dates):
        level = v0 * np.exp(rng.normal(0, 0.25))     # a day effect to remove
        expiries = [(0.6, rng.uniform(0.0, 1.0)), (1.0, rng.uniform(0.0, 0.9)),
                    (2.5, rng.uniform(0.0, 0.6)), (4.0, rng.uniform(0.0, 0.45)),
                    (6.0, rng.uniform(0.0, 0.35)), (11.0, rng.uniform(0.1, 0.3))]
        for e, (T, w) in enumerate(expiries):
            Ty = T / 365.0
            V = level * Ty * (1.0 - (1.0 - lam) * w)
            # Strikes laid out in standard deviations, so every bucket of
            # distance-from-the-money is populated at every maturity.
            x = np.linspace(-Z, Z, 70) * np.sqrt(V)
            # The moneyness metric the smile is written in. At theta = 0 it is
            # the contract's own standard deviation; at theta = 1 it is the
            # variance the same maturity would have carried with no weekend in
            # it, so the smile simply does not respond to the clock and a
            # weekend-heavy contract collects a smaller markup at the same
            # number of its own standard deviations. Anchoring the theta = 1
            # case per maturity rather than to one global scale is what keeps
            # the two cases differing in the weekend clock alone.
            V0 = level * Ty
            u = x / (V ** ((1.0 - theta) / 2) * V0 ** (theta / 2))
            shape = 1.0 + kappa * u ** 2
            iv2 = (V / Ty) * (shape * (1.0 - flatten * w)
                              + flatten * w)          # level left untouched
            iv2 = iv2 * np.exp(rng.normal(0, noise, len(x)))
            sig = np.sqrt(iv2)
            d1 = (-x) / (sig * np.sqrt(Ty)) + sig * np.sqrt(Ty) / 2
            delta = stats.norm.cdf(d1)
            rows.append(pd.DataFrame({
                "iv2": iv2, "logm": x, "logT": np.log(T), "T": T,
                "atmness": np.minimum(delta, 1 - delta),
                "is_call": 1.0, "wknd_frac": w, "date": day,
                "expiry": i * 10 + e, "expiry_dow": day.dayofweek,
                "upper": x > 0}))
    return pd.concat(rows, ignore_index=True)


def test_clock_in_the_smile_gives_no_wing_effect():
    r = W.bucketed(market(theta=0.0))
    assert r["amp"] == pytest.approx(1.0, abs=0.06)
    assert abs(r["t"]) < 3.0


def test_smile_pinned_to_strike_amplifies_up_to_the_ceiling():
    d = market(theta=1.0)
    r, e = W.bucketed(d), W.elasticity(d)
    assert r["amp"] > 1.15
    assert r["amp"] == pytest.approx(e["ceiling"], rel=0.20)
    # And it must not break its own ceiling.
    assert r["log_amp"] - np.log(e["ceiling"]) < 2.0 * r["log_amp_se"]


def test_a_belief_about_weekend_tails_breaks_the_ceiling():
    d = market(theta=1.0, flatten=0.5)
    r, e = W.bucketed(d), W.elasticity(d)
    assert r["log_amp"] - np.log(e["ceiling"]) > 2.0 * r["log_amp_se"]


def test_theta_is_recovered_between_the_endpoints():
    for want in (0.0, 0.5, 1.0):
        d = market(theta=want, seed=3)
        r = W.with_ceiling({**W.bucketed(d), **W.elasticity(d)})
        assert r["theta"] == pytest.approx(want, abs=0.35), want


def test_elasticity_recovers_a_planted_smile_slope():
    """iv^2 proportional to |x|^eta inside every cell must come back as eta.

    Each cell carries its own at-the-money quotes as well as its wings, because
    the estimator selects the wing region by standardizing against that level
    rather than against the contract's own implied vol.
    """
    rng = np.random.default_rng(5)
    eta, T, n_cells = 0.8, 3.0, 400
    rows = []
    for c in range(n_cells):
        level = 0.36 * np.exp(rng.normal(0, 0.3))
        scale = np.sqrt(level * T / 365.0)
        atm_x = rng.normal(0, 0.05 * scale, 40)
        wing_x = rng.uniform(1.7, 3.5, 120) * scale * rng.choice([-1.0, 1.0], 120)
        x0 = 2.0 * scale
        rows.append(pd.DataFrame({
            "iv2": np.concatenate([
                np.full(len(atm_x), level),
                level * (np.abs(wing_x) / x0) ** eta]) *
                np.exp(rng.normal(0, 0.005, len(atm_x) + len(wing_x))),
            "logm": np.concatenate([atm_x, wing_x]),
            "atmness": np.concatenate([np.full(len(atm_x), 0.45),
                                       np.full(len(wing_x), 0.05)]),
            "logT": np.log(T), "expiry": c,
            "date": pd.to_datetime("2024-01-01", utc=True)}))
    out = W.elasticity(pd.concat(rows, ignore_index=True))
    assert out["eta"] == pytest.approx(eta, abs=0.03)
    assert out["ceiling"] == pytest.approx(1 / (1 - eta / 2), rel=0.06)


def test_selecting_the_wing_on_delta_would_bias_the_elasticity():
    """The reason the wing region is selected on a cell-level scale.

    Picking the wing by the contract's own distance-from-the-money means that at
    a given strike only the low implied vols qualify, which tilts the selected
    sample and steepens the measured smile. The estimator must not do that, and
    this pins its direction. Only its direction: the size depends on how much
    the quotes scatter at a given strike and on how the strikes are laid out,
    and this simulation's tidy grid understates both. On the real books the
    same substitution moves the elasticity by about 0.15.
    """
    # Quote noise at a given strike is what drives the bias, so it is set to
    # something like the dispersion real wings show rather than the near-exact
    # surface the other tests use.
    d = market(theta=0.5, seed=13, noise=0.10)
    honest = W.elasticity(d)
    biased = d[d["atmness"] < W.ATM_BINS[1]].copy()
    biased["atmness"] = 0.45          # force every row past the ATM filter
    biased = W.elasticity(biased)
    assert biased["eta"] > honest["eta"] + 0.02


def test_purging_removes_within_expiry_variation(tmp_path, monkeypatch):
    from dbop import config
    d = market(theta=0.5, n_days=60)
    # Give one expiry a weekend fraction that drifts through the day, the way a
    # real one does as the clock advances.
    rng = np.random.default_rng(9)
    d.loc[d["expiry"] % 10 == 0, "wknd_frac"] += rng.normal(
        0, 0.05, (d["expiry"] % 10 == 0).sum())
    monkeypatch.setattr(config, "PANELS", tmp_path)
    d.to_parquet(tmp_path / "smile_sample_ZZZ.parquet", index=False)
    raw = W.load("ZZZ", purge=False)
    pur = W.load("ZZZ", purge=True)
    spread = pur.groupby(["date", "expiry"])["wknd_frac"].std().max()
    assert spread == pytest.approx(0.0, abs=1e-12)
    assert raw.groupby(["date", "expiry"])["wknd_frac"].std().max() > 0.01
    # The cell means are preserved, so nothing between expiries is lost.
    a = raw.groupby(["date", "expiry"])["wknd_frac"].mean()
    b = pur.groupby(["date", "expiry"])["wknd_frac"].mean()
    assert np.allclose(a.to_numpy(), b.to_numpy())


def test_curvature_route_works_when_the_smile_really_is_a_parabola():
    """The arithmetic of the curvature estimator is right; its assumption is not.

    These simulated smiles are exactly quadratic, which is the one case the
    estimator is entitled to, and there it recovers theta: the clock leaves the
    curvature alone at theta = 0 and scales it with the level at theta = 1. On
    the real books the smile is far steeper than a parabola in the wings, the
    fitted curvature becomes a statement about the traded strike range, and the
    estimate falls apart -- which is why the paper reads theta off the
    amplification instead. Keeping this test marks exactly where the failure
    comes from.
    """
    lo = W.shape_test(W.smile_shape(market(theta=0.0, seed=11), min_span=0.02))
    hi = W.shape_test(W.smile_shape(market(theta=1.0, seed=11), min_span=0.02))
    assert lo["b_level"] < -0.2 and hi["b_level"] < -0.2
    assert abs(lo["b_curv"]) < abs(hi["b_curv"])
    assert lo["theta_naive"] < hi["theta_naive"]
    # And the span sensitivity it reports is small here, precisely because a
    # parabola fitted over any range returns the same curvature.
    assert abs(lo["span_sensitivity"]) < 0.15
