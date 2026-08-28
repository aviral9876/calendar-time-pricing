"""Pricer and greek identities. These guard every downstream exposure weight."""
import numpy as np
import pytest
from scipy.stats import norm

from dbop import greeks


def test_put_call_parity():
    F, K, T, s = 60000.0, 62000.0, 0.25, 0.55
    c = float(greeks.price_usd(F, K, T, s, 1))
    p = float(greeks.price_usd(F, K, T, s, -1))
    # r = 0, so C - P = F - K exactly.
    assert abs((c - p) - (F - K)) < 1e-8


def test_atm_price_matches_closed_form():
    # At F == K the Black-76 value collapses to F*(2*N(sigma*sqrt(T)/2) - 1).
    F = K = 50000.0
    T, s = 0.5, 0.8
    expected = F * (2 * norm.cdf(s * np.sqrt(T) / 2) - 1)
    assert abs(float(greeks.price_usd(F, K, T, s, 1)) - expected) < 1e-6


def test_intrinsic_at_expiry():
    assert float(greeks.price_usd(60000, 50000, 0.0, 0.5, 1)) == 10000.0
    assert float(greeks.price_usd(60000, 50000, 0.0, 0.5, -1)) == 0.0
    assert float(greeks.price_usd(40000, 50000, 0.0, 0.5, -1)) == 10000.0


def test_monotonic_in_vol():
    v = [float(greeks.price_usd(60000, 65000, 0.3, s, 1))
         for s in (0.2, 0.4, 0.6, 0.9)]
    assert all(b > a for a, b in zip(v, v[1:]))


def test_coin_quotation_roundtrip():
    F, K, T, s = 60000.0, 60000.0, 0.25, 0.6
    usd = float(greeks.price_usd(F, K, T, s, 1))
    coin = float(greeks.price_coin(F, K, T, s, 1))
    assert abs(coin * F - usd) < 1e-8
    assert 0.0 < coin < 1.0


@pytest.mark.parametrize("cp", [1, -1])
@pytest.mark.parametrize("K", [40000.0, 60000.0, 85000.0])
def test_implied_vol_roundtrip(cp, K):
    F, T, s = 60000.0, 0.35, 0.72
    p = float(greeks.price_usd(F, K, T, s, cp))
    back = greeks.implied_vol_scalar(p, F, K, T, cp)
    assert abs(back - s) < 1e-6


def test_implied_vol_rejects_arbitrage_violations():
    # Below intrinsic has no root.
    assert np.isnan(greeks.implied_vol_scalar(100.0, 60000, 50000, 0.25, 1))
    # Above the upper bound (call worth more than the forward) has no root.
    assert np.isnan(greeks.implied_vol_scalar(70000.0, 60000, 50000, 0.25, 1))
    assert np.isnan(greeks.implied_vol_scalar(-5.0, 60000, 60000, 0.25, 1))


def test_vega_matches_numerical_derivative():
    F, K, T, s = 60000.0, 63000.0, 0.4, 0.65
    h = 1e-5
    num = (float(greeks.price_usd(F, K, T, s + h, 1))
           - float(greeks.price_usd(F, K, T, s - h, 1))) / (2 * h)
    assert abs(float(greeks.greeks(F, K, T, s, 1)["vega_usd"]) - num) < 1e-3


def test_delta_matches_numerical_derivative():
    F, K, T, s = 60000.0, 63000.0, 0.4, 0.65
    h = 1e-2
    num = (float(greeks.price_usd(F + h, K, T, s, 1))
           - float(greeks.price_usd(F - h, K, T, s, 1))) / (2 * h)
    assert abs(float(greeks.greeks(F, K, T, s, 1)["delta"]) - num) < 1e-6


def test_gamma_matches_numerical_second_derivative():
    F, K, T, s = 60000.0, 63000.0, 0.4, 0.65
    h = 1.0
    num = (float(greeks.price_usd(F + h, K, T, s, 1))
           - 2 * float(greeks.price_usd(F, K, T, s, 1))
           + float(greeks.price_usd(F - h, K, T, s, 1))) / h ** 2
    got = float(greeks.greeks(F, K, T, s, 1)["gamma"])
    assert abs(got - num) / abs(num) < 1e-4


def test_call_put_share_vega_and_gamma():
    F, K, T, s = 60000.0, 63000.0, 0.4, 0.65
    gc = greeks.greeks(F, K, T, s, 1)
    gp = greeks.greeks(F, K, T, s, -1)
    assert abs(float(gc["vega_usd"]) - float(gp["vega_usd"])) < 1e-8
    assert abs(float(gc["gamma"]) - float(gp["gamma"])) < 1e-12
    # Black deltas differ by exactly one under r = 0.
    assert abs((float(gc["delta"]) - float(gp["delta"])) - 1.0) < 1e-12


def test_premium_adjusted_delta_is_hedge_ratio():
    """For an inverse option the coin-denominated hedge ratio is the Black
    delta less the coin premium."""
    F, K, T, s = 60000.0, 63000.0, 0.4, 0.65
    g = greeks.greeks(F, K, T, s, 1)
    coin = float(greeks.price_coin(F, K, T, s, 1))
    assert abs(float(g["delta_adj"]) - (float(g["delta"]) - coin)) < 1e-12
    assert float(g["delta_adj"]) < float(g["delta"])


def test_deep_itm_and_otm_deltas():
    F, T, s = 60000.0, 0.25, 0.6
    assert float(greeks.greeks(F, 1000.0, T, s, 1)["delta"]) > 0.99
    assert abs(float(greeks.greeks(F, 500000.0, T, s, 1)["delta"])) < 0.01


def test_time_to_expiry():
    ms_year = 365 * 24 * 3600 * 1000
    assert abs(float(greeks.time_to_expiry(0, ms_year)) - 1.0) < 1e-12
    # Expired options clamp at zero rather than going negative.
    assert float(greeks.time_to_expiry(ms_year, 0)) == 0.0


def test_vectorized_shapes():
    F = np.full(4, 60000.0)
    K = np.array([40000.0, 55000.0, 65000.0, 90000.0])
    T = np.full(4, 0.3)
    s = np.full(4, 0.7)
    cp = np.array([1.0, -1.0, 1.0, -1.0])
    g = greeks.greeks(F, K, T, s, cp)
    assert all(v.shape == (4,) for v in g.values())
    assert np.all(np.isfinite(g["vega_usd"]))


# --------------------------------------------------- second-order exposures

def _fd(f, x, h):
    """Central difference, which is the only check worth trusting on a Greek."""
    return (f(x + h) - f(x - h)) / (2 * h)


@pytest.mark.parametrize("cp", [1.0, -1.0])
@pytest.mark.parametrize("K", [45_000.0, 50_000.0, 62_000.0])
def test_vanna_matches_a_finite_difference(cp, K):
    F, T, sig = 50_000.0, 0.08, 0.55
    got = float(greeks.greeks(F, K, T, sig, cp)["vanna"])
    want = _fd(lambda f: float(greeks.greeks(f, K, T, sig, cp)["vega_usd"]),
               F, 1.0)
    assert got == pytest.approx(want, rel=2e-4, abs=1e-6)


@pytest.mark.parametrize("cp", [1.0, -1.0])
@pytest.mark.parametrize("K", [45_000.0, 50_000.0, 62_000.0])
def test_volga_matches_a_finite_difference(cp, K):
    F, T, sig = 50_000.0, 0.08, 0.55
    got = float(greeks.greeks(F, K, T, sig, cp)["volga"])
    want = _fd(lambda v: float(greeks.greeks(F, K, T, v, cp)["vega_usd"]),
               sig, 1e-4)
    assert got == pytest.approx(want, rel=2e-4, abs=1e-6)


@pytest.mark.parametrize("cp", [1.0, -1.0])
@pytest.mark.parametrize("K", [45_000.0, 50_000.0, 62_000.0])
def test_charm_is_the_delta_drift_from_one_day_passing(cp, K):
    """Sign convention: positive means delta rises as a day elapses."""
    F, T, sig = 50_000.0, 0.08, 0.55
    got = float(greeks.greeks(F, K, T, sig, cp)["charm_per_day"])
    day = 1.0 / 365.0
    want = (float(greeks.greeks(F, K, T - day / 2, sig, cp)["delta"])
            - float(greeks.greeks(F, K, T + day / 2, sig, cp)["delta"])) / 1.0
    assert got == pytest.approx(want, rel=5e-3, abs=1e-7)


def test_volga_vanishes_at_the_money_and_is_positive_in_the_wings():
    F, T, sig = 50_000.0, 0.08, 0.55
    atm = F * np.exp(0.5 * sig ** 2 * T)      # the strike where d1*d2 = 0
    assert float(greeks.greeks(F, atm, T, sig, 1.0)["volga"]) == pytest.approx(
        0.0, abs=1e-6)
    for K in (35_000.0, 75_000.0):
        assert float(greeks.greeks(F, K, T, sig, 1.0)["volga"]) > 0


def test_second_order_greeks_are_the_same_for_calls_and_puts():
    """Put-call parity is linear in F, so it cannot touch these."""
    F, K, T, sig = 50_000.0, 58_000.0, 0.08, 0.55
    c = greeks.greeks(F, K, T, sig, 1.0)
    p = greeks.greeks(F, K, T, sig, -1.0)
    for k in ("vanna", "volga", "gamma", "vega_usd"):
        assert float(c[k]) == pytest.approx(float(p[k]), rel=1e-12)


def test_degenerate_rows_get_zero_second_order_greeks():
    g = greeks.greeks(np.array([50_000.0, 50_000.0]), np.array([50_000.0] * 2),
                      np.array([0.0, 0.08]), np.array([0.55, 0.0]),
                      np.array([1.0, 1.0]))
    for k in ("vanna", "volga", "charm_per_day"):
        assert np.allclose(g[k], 0.0)
