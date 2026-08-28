"""Position-reconstruction identities.

These encode the accounting that makes the inventory measure meaningful: every
contract an end user is long, someone is short; positions accumulate; nothing
survives expiry.
"""
import numpy as np
import pandas as pd
import pytest

from dbop import inventory


@pytest.fixture
def flow():
    """Two instruments, a few days of signed demand."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"], utc=True)
    return pd.DataFrame({
        "date": list(dates) * 2,
        "instrument_name": ["BTC-5JAN24-40000-C"] * 3 + ["BTC-5JAN24-45000-P"] * 3,
        "net_amount": [10.0, -4.0, 2.0, -5.0, 1.0, 0.0],
        "net_vega": [100.0, -40.0, 20.0, -50.0, 10.0, 0.0],
        "net_gamma": [1.0, -0.4, 0.2, -0.5, 0.1, 0.0],
        "gross_amount": [12.0, 6.0, 2.0, 7.0, 3.0, 1.0],
        "gross_vega": [120.0, 60.0, 20.0, 70.0, 30.0, 10.0],
        "n_trades": [3, 2, 1, 2, 1, 1],
        "taker_buy_share": [0.9, 0.2, 1.0, 0.1, 0.8, 0.5],
    })


@pytest.fixture
def meta():
    return pd.DataFrame({
        "instrument_name": ["BTC-5JAN24-40000-C", "BTC-5JAN24-45000-P"],
        "strike": [40000.0, 45000.0],
        "expiration_timestamp": [1704441600000, 1704441600000],  # 2024-01-05
        "cp": ["C", "P"],
        "expiry": pd.to_datetime(["2024-01-05", "2024-01-05"], utc=True),
    })


def test_dealer_is_the_negative_of_the_end_user(flow, meta):
    p = inventory.positions(flow, meta)
    assert np.allclose(p["pos_dealer"], -p["pos_enduser"])


def test_position_is_cumulative_flow(flow, meta):
    p = inventory.positions(flow, meta)
    call = p[p["instrument_name"] == "BTC-5JAN24-40000-C"].sort_values("date")
    # 10, then 10-4=6, then 6+2=8, then carried forward to expiry.
    assert call["pos_enduser"].iloc[0] == 10.0
    assert call["pos_enduser"].iloc[1] == 6.0
    assert call["pos_enduser"].iloc[2] == 8.0


def test_position_carries_forward_on_non_trading_days(flow, meta):
    p = inventory.positions(flow, meta)
    call = p[p["instrument_name"] == "BTC-5JAN24-40000-C"].sort_values("date")
    # Flow stops on the 3rd but the position is open until the 5th.
    assert len(call) == 5
    assert call["pos_enduser"].iloc[-1] == 8.0


def test_nothing_survives_expiry(flow, meta):
    p = inventory.positions(flow, meta)
    assert p["date"].max() <= pd.Timestamp("2024-01-05", tz="UTC")


def test_zero_net_position_is_dropped(flow, meta):
    """An instrument whose flow nets to zero holds no risk and should not
    appear as an exposure."""
    f = flow.copy()
    f.loc[f["instrument_name"] == "BTC-5JAN24-45000-P", "net_amount"] = \
        [-5.0, 5.0, 0.0]
    p = inventory.positions(f, meta)
    put = p[p["instrument_name"] == "BTC-5JAN24-45000-P"]
    # Day 1 has -5 outstanding; from day 2 the position is flat and drops out.
    assert len(put) == 1
    assert put["pos_enduser"].iloc[0] == -5.0


def test_unknown_instruments_are_skipped(flow, meta):
    f = pd.concat([flow, pd.DataFrame({
        "date": [pd.Timestamp("2024-01-02", tz="UTC")],
        "instrument_name": ["BTC-5JAN24-99999-C"],
        "net_amount": [1.0], "net_vega": [1.0], "net_gamma": [1.0],
        "gross_amount": [1.0], "gross_vega": [1.0], "n_trades": [1],
        "taker_buy_share": [1.0],
    })], ignore_index=True)
    p = inventory.positions(f, meta)
    assert "BTC-5JAN24-99999-C" not in set(p["instrument_name"])


def test_signing_placebo_returns_all_measures(flow):
    out = inventory.validate_signing(flow, n_shuffles=3)
    assert set(out["measure"]) == {"true", "placebo_mean", "placebo_p05",
                                   "placebo_p95"}
