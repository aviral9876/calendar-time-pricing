"""Forward-curve interpolation.

The forward sets log-moneyness, which sets the delta buckets, which is how the
cross-sectional test is defined -- so an error here would not crash anything,
it would just quietly reassign options to the wrong bucket.
"""
import numpy as np

from dbop.forwards import ForwardCurve


def _curve():
    # 1.0% basis at 3 months, 2.0% at 6 months.
    return ForwardCurve(np.array([0.25, 0.5]), np.array([0.01, 0.02]))


def test_zero_maturity_is_spot():
    assert abs(_curve().basis(0.0)) < 1e-12
    assert abs(float(_curve().forward(50000.0, 0.0)) - 50000.0) < 1e-9


def test_interpolates_between_observed_points():
    c = _curve()
    # Halfway between 0.25 and 0.5 in maturity is halfway in log basis.
    assert abs(float(c.basis(0.375)) - 0.015) < 1e-12
    # Halfway between 0 and 0.25 interpolates against the zero anchor.
    assert abs(float(c.basis(0.125)) - 0.005) < 1e-12


def test_flat_beyond_the_longest_future():
    c = _curve()
    assert abs(float(c.basis(5.0)) - 0.02) < 1e-12


def test_forward_exceeds_spot_in_contango():
    c = _curve()
    F = float(c.forward(50000.0, 0.5))
    assert F > 50000.0
    assert abs(F - 50000.0 * np.exp(0.02)) < 1e-6


def test_backwardation_gives_forward_below_spot():
    c = ForwardCurve(np.array([0.25]), np.array([-0.03]))
    assert float(c.forward(50000.0, 0.25)) < 50000.0


def test_unsorted_input_is_handled():
    a = ForwardCurve(np.array([0.5, 0.25]), np.array([0.02, 0.01]))
    b = ForwardCurve(np.array([0.25, 0.5]), np.array([0.01, 0.02]))
    assert abs(float(a.basis(0.375)) - float(b.basis(0.375))) < 1e-12


def test_vectorized():
    c = _curve()
    out = c.forward(np.full(3, 50000.0), np.array([0.0, 0.25, 0.5]))
    assert out.shape == (3,)
    assert np.all(np.diff(out) > 0)          # contango is increasing in T
