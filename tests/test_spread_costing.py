"""The spread must pay both legs' costs.

This file exists because it did not. Every trading result in the project ran
through `net_weekend - net_weekday`, where both stored legs are the P&L of a
SHORT contract and the engine always subtracts costs. Negating the second leg
therefore turned its costs into a credit, and the reported edge was overstated
by exactly twice the long leg's cost -- more than the entire edge at fine
rehedging.

The bug was invisible to every test in the suite because each leg was
individually correct. Only the *combination* was wrong, so the combination is
what gets pinned here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_commercial as wc  # noqa: E402


def test_a_spread_pays_both_legs_costs():
    """The defining property: costs add across legs, they do not cancel."""
    gs, gl = 1.00, 0.60          # gross P&L of each leg, priced as a short
    cs, cl = 0.05, 0.04          # costs of each leg, always positive
    got = wc.spread_pnl(gs, gl, cs, cl)
    assert got == pytest.approx((gs - gl) - (cs + cl))
    assert got == pytest.approx(0.31)


def test_the_old_construction_overstates_by_twice_the_long_legs_cost():
    """Pins the size of the error, not merely its direction."""
    gs, gl, cs, cl = 1.00, 0.60, 0.05, 0.04
    as_coded = (gs - cs) - (gl - cl)          # what the project used to compute
    implementable = wc.spread_pnl(gs, gl, cs, cl)
    assert as_coded - implementable == pytest.approx(2 * cl)


def test_costs_never_improve_a_spread():
    """Whatever the legs do, charging costs cannot raise the P&L."""
    rng = np.random.default_rng(0)
    gs, gl = rng.normal(0, 1, 500), rng.normal(0, 1, 500)
    cs, cl = rng.uniform(0, 0.3, 500), rng.uniform(0, 0.3, 500)
    assert (wc.spread_pnl(gs, gl, cs, cl) <= gs - gl + 1e-12).all()


def test_a_maker_earns_the_spread_instead_of_paying_it():
    """The maker's advantage is four half-spreads: two not paid, two earned."""
    gs, gl = 1.00, 0.60
    fee_s, fee_l = 0.03, 0.028
    half = 0.004
    taker = wc.spread_pnl(gs, gl, fee_s + half, fee_l + half)
    maker = wc.spread_pnl(gs, gl, fee_s, fee_l, earns_spread=half)
    assert maker - taker == pytest.approx(4 * half)
    # And fees fall on both alike, so they cannot be the source of the gap.
    assert taker == pytest.approx((gs - gl) - fee_s - fee_l - 2 * half)


def test_the_maker_still_pays_exchange_and_hedging_fees():
    gs, gl, fee_s, fee_l, half = 1.00, 0.60, 0.03, 0.028, 0.004
    maker = wc.spread_pnl(gs, gl, fee_s, fee_l, earns_spread=half)
    assert maker == pytest.approx((gs - gl) - fee_s - fee_l + 2 * half)
    assert maker < gs - gl          # never better than the gross signal
