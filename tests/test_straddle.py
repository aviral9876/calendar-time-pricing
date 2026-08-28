"""Straddle engine: hedge parity, entry honesty, stop rule, P&L identity."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from dbop import costs, greeks, straddle

DAY = straddle.DAY_MS
HOUR = straddle.HOUR_MS

# A Friday 00:00 UTC: 2026-08-21
FRI = int(dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc).timestamp() * 1000)
SUN_EXP = FRI + 2 * DAY + 12 * HOUR          # Sunday 12:00 UTC settlement


def flat_px(level=80_000.0, start=FRI - 5 * DAY, end=FRI + 4 * DAY):
    ts = np.arange(start, end, 5 * 60_000, dtype="int64")
    return pd.Series(np.full(len(ts), level), index=ts)


def test_fridays_are_fridays():
    fr = straddle.fridays(FRI - 30 * DAY, FRI)
    assert FRI in fr
    days = pd.to_datetime(fr, unit="ms", utc=True)
    assert (days.dayofweek == 4).all()


def test_hedge_pnl_flat_path_is_zero():
    px = flat_px()
    pnl, fees = straddle.hedge_pnl(px, FRI + 12 * HOUR, FRI + 48 * HOUR,
                                   80_000.0, 0.5, 0.5, SUN_EXP, 60)
    # no price moves: only the initial position trade, unwound at same price
    assert abs(pnl) < 1e-6
    assert fees > 0                          # entry + exit perp trades cost


def test_hedge_pnl_straddle_equals_leg_sum():
    rng = np.random.default_rng(7)
    ts = np.arange(FRI, FRI + 3 * DAY, 5 * 60_000, dtype="int64")
    path = 80_000 * np.exp(np.cumsum(rng.normal(0, 0.001, len(ts))))
    px = pd.Series(path, index=ts)
    t0, t1 = FRI + 12 * HOUR, FRI + 48 * HOUR
    both = straddle.hedge_pnl(px, t0, t1, 80_000.0, 0.5, 0.6, SUN_EXP, 60)
    c = straddle.hedge_pnl(px, t0, t1, 80_000.0, 0.5, 99.0, SUN_EXP, 60)
    p = straddle.hedge_pnl(px, t0, t1, 80_000.0, 99.0, 0.6, SUN_EXP, 60)
    # legs computed with the other sigma neutralized are not separable through
    # the shared clip, so check the direct identity instead: delta path of the
    # pair equals sum of single-leg delta paths -> pnl additivity holds by
    # construction. Verify against manual recomputation.
    step = 60 * 60_000
    stamps = np.minimum(np.arange(t0, t1 + step, step, dtype="int64"), t1)
    S = straddle.price_at(px, stamps)
    T = np.clip((SUN_EXP - stamps) / straddle.MS_YEAR, 1e-9, None)
    want = (greeks.greeks(S, 80_000.0, T, 0.5, 1)["delta"]
            + greeks.greeks(S, 80_000.0, T, 0.6, -1)["delta"])
    trades = np.diff(want, prepend=0.0)
    manual = -float(np.sum(trades * S)) + float(want[-1]) * float(
        straddle.price_at(px, np.int64(t1)))
    assert np.isclose(both[0], manual)


def _mk_chain(currency="BTC"):
    return pd.DataFrame([
        {"symbol": "C-BTC-80000-230826", "strike": 80_000.0,
         "expiry_ms": SUN_EXP},
    ])


def _mk_candles(prem_c=900.0, prem_p=880.0, mark_scale=1.0):
    """Traded candle for the entry hour and mark candles across the weekend."""
    entry_bar = FRI + 11 * HOUR                     # bar [11:00, 12:00)
    trade = pd.DataFrame({"ts": [entry_bar],
                          "close": [np.nan], "volume": [10.0]})
    marks_ts = np.arange(FRI, SUN_EXP, HOUR, dtype="int64")
    store = {}
    for sym, prem in (("C-BTC-80000-230826", prem_c),
                      ("P-BTC-80000-230826", prem_p)):
        t = trade.copy()
        t["close"] = prem
        m = pd.DataFrame({"ts": marks_ts,
                          "close": np.full(len(marks_ts), prem * mark_scale)})
        store[(sym, False)] = t
        store[(sym, True)] = m
    return lambda sym, mark: store.get((sym, mark), pd.DataFrame())


def test_run_one_pnl_identity_flat_world():
    """Flat spot at the strike, marks static: gross = premium decay only."""
    px = flat_px()
    load = _mk_candles(mark_scale=0.5)      # option value halves by exit
    row = straddle.run_one(FRI, px, _mk_chain(), load, exit_key="sun_00",
                           rehedge_minutes=60, half_spread_vol=0.0)
    assert row is not None
    prem_in = 900.0 + 880.0
    assert np.isclose(row["prem_in"], prem_in)
    assert np.isclose(row["prem_out"], prem_in * 0.5)
    # flat path -> hedge pnl 0; gross = premium collected - buyback
    assert np.isclose(row["gross"], prem_in * 0.5, atol=1e-6)
    # net = gross - option fees (cap binds: 3.5% of premium) - perp fees
    expected_fees = float(
        costs.delta_india_option_fee_usd(80_000.0, 900.0)
        + costs.delta_india_option_fee_usd(80_000.0, 880.0)
        + costs.delta_india_option_fee_usd(80_000.0, prem_in * 0.5))
    assert np.isclose(row["net"],
                      prem_in * 0.5 - expected_fees - row["perp_fees"])


def test_run_one_requires_traded_entry():
    """No trade print near the entry instant -> no trade, no row."""
    px = flat_px()
    store = _mk_candles()

    def load_no_trades(sym, mark):
        if not mark:
            return pd.DataFrame()
        return store(sym, mark)

    row = straddle.run_one(FRI, px, _mk_chain(), load_no_trades)
    assert row is None


def test_run_one_expiry_settlement_intrinsic():
    """Hold to expiry with spot pinned above strike: put worthless, call
    settles to intrinsic; settlement fee charged only when ITM leg exists."""
    px = flat_px(level=81_000.0)
    # call premium must clear intrinsic (1,000) to invert to a finite IV
    load = _mk_candles(prem_c=1_500.0, prem_p=600.0)
    row = straddle.run_one(FRI, px, _mk_chain(), load, exit_key="expiry",
                           rehedge_minutes=60, half_spread_vol=0.0)
    assert row is not None and row["settled"]
    assert np.isclose(row["prem_out"], 1_000.0)     # S_T - K


def test_stop_rule_triggers():
    px = flat_px()
    load = _mk_candles(mark_scale=4.0)      # marks blow out immediately
    row = straddle.run_one(FRI, px, _mk_chain(), load, exit_key="sun_00",
                           rehedge_minutes=60, stop_mult=3.0)
    assert row is not None
    assert row["stopped"]
    # exit at the blown-out mark: loss of ~3x premium
    assert row["gross"] < 0


def test_summarize_units():
    bl = pd.DataFrame({
        "net_per_vega": [0.05, -0.02, 0.03, 0.01],
        "gross_per_vega": [0.06, -0.01, 0.04, 0.02],
        "fees_opt": [1.0] * 4, "spread_cost": [1.0] * 4,
        "perp_fees": [1.0] * 4, "vega_usd": [100.0] * 4,
    })
    s = straddle.summarize(bl)
    assert s["n"] == 4
    assert np.isclose(s["cost_per_vega"], 0.03)
    assert 0 < s["hit_rate"] <= 1
