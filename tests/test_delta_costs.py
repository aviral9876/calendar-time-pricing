"""Delta India fee schedule: cap boundary, GST, round-trip assembly."""
from __future__ import annotations

import numpy as np

from dbop import costs


def test_notional_leg_when_premium_rich():
    # premium so large the 3.5% cap does not bind: fee = 0.03% notional + GST
    fee = costs.delta_india_option_fee_usd(80_000.0, 5_000.0)
    assert np.isclose(fee, 80_000 * 0.0003 * 1.18)


def test_cap_binds_for_cheap_options():
    # deep-OTM daily: premium 20 USD on 80k notional; cap = 3.5% * 20 = 0.70
    fee = costs.delta_india_option_fee_usd(80_000.0, 20.0)
    assert np.isclose(fee, 20.0 * 0.035 * 1.18)
    assert fee < 80_000 * 0.0003          # far below the notional leg


def test_cap_boundary():
    # cap binds exactly when premium = rate/cap * notional
    boundary_prem = 0.0003 / 0.035 * 80_000.0
    lo = costs.delta_india_option_fee_usd(80_000.0, boundary_prem * 0.999)
    hi = costs.delta_india_option_fee_usd(80_000.0, boundary_prem * 1.001)
    at = costs.delta_india_option_fee_usd(80_000.0, boundary_prem)
    assert lo < at <= hi + 1e-9
    assert np.isclose(at, 80_000 * 0.0003 * 1.18, rtol=1e-3)


def test_gst_is_18_percent():
    f0 = costs.delta_india_option_fee_usd(
        80_000.0, 5_000.0, fees={**costs.DELTA_INDIA, "gst": 0.0})
    f1 = costs.delta_india_option_fee_usd(80_000.0, 5_000.0)
    assert np.isclose(f1 / f0, 1.18)


def test_perp_fee():
    assert np.isclose(costs.delta_india_perp_fee_usd(10_000.0),
                      10_000 * 0.0005 * 1.18)


def test_round_trip_assembly_identity():
    # round trip = entry fee + exit fee + 2 * vega * half_spread + perp fees
    F, prem, vega, hs, perp = 80_000.0, 900.0, 120.0, 0.005, 33.0
    total = costs.round_trip_hedged_cost(F, F, prem, prem, vega, hs, perp)
    expected = (2 * costs.delta_india_option_fee_usd(F, prem)
                + 2 * vega * hs + perp)
    assert np.isclose(total, expected)


def test_round_trip_settlement_leg():
    F, prem, vega = 80_000.0, 900.0, 120.0
    settled = costs.round_trip_hedged_cost(F, F, prem, 0.0, vega, 0.0, 0.0,
                                           settled=True)
    expected = costs.delta_india_option_fee_usd(F, prem) \
        + 0.0005 * 1.18 * F
    assert np.isclose(settled, expected)


def test_deribit_venue_matches_legacy_helpers():
    F, prem = 80_000.0, 900.0
    total = costs.round_trip_hedged_cost(F, F, prem, prem, 0.0, 0.0, 0.0,
                                         venue="deribit")
    assert np.isclose(total, 2 * costs.option_fee_usd(F, prem))
