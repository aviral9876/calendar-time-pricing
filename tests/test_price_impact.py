"""Tests for the price translation in scripts/weekend_price_impact.py.

The script's job is arithmetic, not inference, so the tests are identities
rather than simulations: the effect has to vanish exactly where the clock does
nothing, the exact repricing has to agree with the first-order vega
approximation in the limit where the approximation is entitled to hold, and the
choice to measure percentages on the out-of-the-money leg has to be shown to be
the one that leaves the dollar effect alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_price_impact as P  # noqa: E402

from dbop import config, greeks  # noqa: E402


def sample(n=400, R_planted=0.6, seed=0) -> pd.DataFrame:
    """A tape-shaped frame whose quotes were built by a known clock.

    Each contract carries a weekday variance of its own and a weekend fraction
    of its own, and the quoted variance is the first damped by the second. The
    repricing must then hand the weekday variance back.
    """
    rng = np.random.default_rng(seed)
    T_days = rng.uniform(0.3, 14.0, n)
    v_wd = 0.4 * np.exp(rng.normal(0, 0.3, n))
    w = rng.uniform(0.0, 1.0, n)
    iv2 = v_wd * P.damp(w, R_planted)
    sig = np.sqrt(iv2)
    logm = rng.normal(0, 1.2, n) * sig * np.sqrt(T_days / config.YEAR)
    return pd.DataFrame({
        "iv2": iv2, "logT": np.log(T_days), "T_days": T_days,
        "atmness": np.full(n, 0.4), "is_call": (logm > 0).astype(float),
        "logm": logm, "wknd_frac": w, "size": rng.uniform(0.1, 10.0, n),
        "F": np.full(n, 50_000.0), "_v_wd": v_wd,
    })


def test_damp_is_one_with_no_weekend_and_the_ratio_with_nothing_else():
    assert P.damp(0.0, 0.5) == pytest.approx(1.0)
    assert P.damp(1.0, 0.5) == pytest.approx(0.5)
    assert P.damp(0.5, 0.6) == pytest.approx(0.8)


def test_elasticity_is_one_at_the_money_and_rises_into_the_wings():
    T, sig = 7 / 365.0, 0.7
    at = float(P.elasticity(1.0, 1.0, T, sig, 1.0))
    assert at == pytest.approx(1.0, abs=0.02)
    prev = at
    for z in (0.5, 1.0, 2.0, 3.0):
        K = float(np.exp(z * sig * np.sqrt(T)))
        e = float(P.elasticity(1.0, K, T, sig, 1.0))
        assert e > prev
        prev = e


def test_repricing_recovers_the_planted_weekday_volatility():
    d = sample()
    r = P.reprice(d, np.full(len(d), 0.6), np.full(len(d), 0.6))
    # With the quoted and the fair clock equal there is no gap anywhere.
    assert np.allclose(r["price_gap_pct"].to_numpy(), 0.0, atol=1e-9)
    # And the volatility the clock is switched off to is the planted weekday one.
    sig_flat = np.sqrt(d["iv2"].to_numpy()) / (1 + r["vol_cut_pct"].to_numpy() / 100)
    assert np.allclose(sig_flat, np.sqrt(d["_v_wd"].to_numpy()), rtol=1e-10)


def test_no_weekend_in_the_contract_means_no_effect():
    d = sample()
    d["wknd_frac"] = 0.0
    r = P.reprice(d, np.full(len(d), 0.5), np.full(len(d), 0.8))
    for c in ("vol_cut_pct", "vol_cut_points", "price_cut_pct", "price_gap_pct"):
        assert np.allclose(r[c].to_numpy(), 0.0, atol=1e-9), c


def test_a_ratio_of_one_is_a_clock_that_does_nothing():
    d = sample()
    r = P.reprice(d, np.ones(len(d)), np.ones(len(d)))
    assert np.allclose(r["price_cut_pct"].to_numpy(), 0.0, atol=1e-9)
    assert np.allclose(r["eff_time_frac"].to_numpy(), 1.0)


def test_the_gap_flips_sign_with_the_side_of_realized_the_quote_falls_on():
    """Over-discounting is a cheap option; under-discounting is a rich one."""
    d = sample()
    over = P.reprice(d, np.full(len(d), 0.45), np.full(len(d), 0.62))
    under = P.reprice(d, np.full(len(d), 0.75), np.full(len(d), 0.62))
    assert (over["price_gap_pct"].to_numpy() < 0).all()
    assert (under["price_gap_pct"].to_numpy() > 0).all()


def test_first_order_and_exact_agree_for_a_small_clock_and_not_for_a_large_one():
    """The vega approximation is a local statement, and the wings are not local.

    A clock that barely bites is repriced to within a tenth of a percent by
    elasticity times the volatility change. The real one, two standard
    deviations out on a Saturday daily, is not: the linear approximation puts
    the contract past worthless while the exact repricing leaves 18% of its
    premium standing. That is why every number in the tables is an exact
    repricing rather than a vega multiplication.
    """
    T, sig_wd = 3 / 365.0, np.sqrt(0.44)
    K = float(np.exp(2.0 * sig_wd * np.sqrt(T)))
    for R, w, tol in ((0.999, 0.05, 1e-3),):
        sig = sig_wd * np.sqrt(float(P.damp(w, R)))
        exact = (float(greeks.price_usd(1.0, K, T, sig, 1.0))
                 / float(greeks.price_usd(1.0, K, T, sig_wd, 1.0)) - 1)
        lin = float(P.elasticity(1.0, K, T, sig_wd, 1.0)) * (sig / sig_wd - 1)
        assert abs(exact - lin) < tol
    sig = sig_wd * np.sqrt(float(P.damp(1.0, 0.635)))
    exact = (float(greeks.price_usd(1.0, K, T, sig, 1.0))
             / float(greeks.price_usd(1.0, K, T, sig_wd, 1.0)) - 1)
    lin = float(P.elasticity(1.0, K, T, sig_wd, 1.0)) * (sig / sig_wd - 1)
    assert lin < -1.0 < exact          # the approximation leaves the real line
    assert exact == pytest.approx(-0.82, abs=0.01)


def test_measuring_on_the_out_of_the_money_leg_preserves_the_dollar_effect():
    """Why the percentages are quoted on time value.

    A deep in-the-money call and the put at its strike differ by the forward,
    which carries no volatility, so the two premia move by exactly the same
    number of dollars when the clock changes. Dividing that common move by the
    in-the-money premium instead of by time value understates the effect several
    times over without any of the arithmetic being different.
    """
    T, sig_wd = 7 / 365.0, np.sqrt(0.44)
    K = float(np.exp(-2.0 * sig_wd * np.sqrt(T)))     # a deep in-the-money call
    sig = sig_wd * np.sqrt(float(P.damp(2 / 3, 0.635)))
    call0 = float(greeks.price_usd(1.0, K, T, sig_wd, 1.0))
    call1 = float(greeks.price_usd(1.0, K, T, sig, 1.0))
    put0 = float(greeks.price_usd(1.0, K, T, sig_wd, -1.0))
    put1 = float(greeks.price_usd(1.0, K, T, sig, -1.0))
    assert (call1 - call0) == pytest.approx(put1 - put0, abs=1e-12)
    assert abs(put1 / put0 - 1) > 5 * abs(call1 / call0 - 1)


def test_the_reported_effect_is_the_out_of_the_money_one_whichever_leg_traded():
    d = sample(n=200)
    calls, puts = d.copy(), d.copy()
    calls["is_call"], puts["is_call"] = 1.0, 0.0
    a = P.reprice(calls, np.full(200, 0.6), np.full(200, 0.58))
    b = P.reprice(puts, np.full(200, 0.6), np.full(200, 0.58))
    for c in ("price_cut_pct", "price_gap_pct", "elasticity", "tv_usd"):
        assert np.allclose(a[c].to_numpy(), b[c].to_numpy(), equal_nan=True), c
    # Only the premium actually handed over depends on which leg it was.
    assert not np.allclose(a["prem_paid_usd"].to_numpy(),
                           b["prem_paid_usd"].to_numpy())


def test_decay_matches_the_flat_calendar_when_the_clock_is_off():
    d = P.decay("BTC", 1.0)
    assert np.allclose(d["decay_clock_pct"], d["decay_flat_pct"], atol=1e-9)
    assert np.allclose(d["premium_saved_pct"], 0.0, atol=1e-9)
    assert np.allclose(d["friday_markdown_pct"], 0.0, atol=1e-9)


def test_the_weekend_clock_always_saves_premium_across_the_weekend():
    """A position held Friday to Monday loses less than the calendar says.

    Three calendar days pass and fewer effective ones do, so the decay is
    slower. The saving shrinks with maturity because a long contract's weekend
    fraction barely moves over one weekend.
    """
    d = P.decay("BTC", 0.635)
    assert (d["premium_saved_pct"] > 0).all()
    assert (d["decay_clock_pct"] > d["decay_flat_pct"]).all()
    assert d["premium_saved_pct"].iloc[0] > d["premium_saved_pct"].iloc[-1]


def test_stylized_map_is_monotone_in_the_weekend_fraction():
    s = P.stylized("BTC", 0.635, 0.584)
    for (T, m), g in s.groupby(["T_days", "moneyness"]):
        g = g.sort_values("wknd_frac")
        assert g["price_cut_pct"].is_monotonic_decreasing, (T, m)
        assert g["eff_time_frac"].is_monotonic_decreasing, (T, m)
    # The gap is signed by which side of realized the quote falls on: BTC
    # discounts less than realized, so its weekend contracts are rich.
    assert (s.loc[s["wknd_frac"] > 0, "price_gap_pct"] > 0).all()
