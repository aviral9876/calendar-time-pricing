"""Tests for scripts/weekend_clock.py.

The clock backtest turns on arithmetic that is easy to get wrong and hard to
see wrong: converting a timestamp to the Friday that owns it, walking a hedge
path over a fixed window, and charging a round trip rather than a settlement.
Each is checked here against a planted answer.

``fridays`` gets its own test because the first version of it was off by a
factor of a million -- pandas builds a millisecond-resolution stamp from
``unit="ms"``, so the usual nanosecond rescaling put every trade in 1970 and the
backtest silently returned no trades at all rather than failing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_clock as C  # noqa: E402


def ms(s: str) -> int:
    return int(pd.Timestamp(s, tz="UTC").timestamp() * 1000)


def flat_px(start: str, hours: int, level: float = 100.0,
            drift: float = 0.0) -> pd.Series:
    t0 = ms(start)
    stamps = np.arange(t0, t0 + hours * C.HOUR_MS, 60_000, dtype="int64")
    vals = level * (1.0 + drift * np.arange(len(stamps)) / len(stamps))
    return pd.Series(vals, index=stamps)


# ---------------------------------------------------------------------- tests

def test_fridays_are_fridays_and_land_in_the_right_decade():
    """The units bug that made this return 1970 must stay fixed."""
    lo, hi = ms("2024-01-01"), ms("2024-03-01")
    fr = C.fridays(lo, hi)
    assert len(fr) == 9
    stamps = pd.to_datetime(fr, unit="ms", utc=True)
    assert (stamps.dayofweek == 4).all()
    assert (stamps.hour == 0).all()
    assert stamps.min() >= pd.Timestamp("2024-01-01", tz="UTC")
    assert stamps.max() <= pd.Timestamp("2024-03-02", tz="UTC")


def test_exit_offsets_name_the_right_instants():
    """sun_00 must be the end of Saturday, not the start of it."""
    fri = ms("2024-03-15")                     # a Friday
    for key, expect in (("sat_00", "2024-03-16 00:00"),
                        ("sat_12", "2024-03-16 12:00"),
                        ("sun_00", "2024-03-17 00:00"),
                        ("mon_00", "2024-03-18 00:00")):
        t = fri + C.DAY_MS + C.EXITS[key] * C.HOUR_MS
        assert pd.Timestamp(t, unit="ms", tz="UTC") == pd.Timestamp(expect,
                                                                    tz="UTC")


def test_sat_00_holds_no_weekend_and_sun_00_holds_one_day():
    """The two readings of "midnight on Saturday" differ by a whole Saturday."""
    fri = ms("2024-03-15")
    t_in = fri + 12 * C.HOUR_MS
    hold = {k: (fri + C.DAY_MS + v * C.HOUR_MS - t_in) / C.HOUR_MS
            for k, v in C.EXITS.items()}
    assert hold["sat_00"] == 12
    assert hold["sun_00"] == 36
    assert hold["sun_00"] - hold["sat_00"] == 24


def test_near_uses_the_index_and_the_scan_identically():
    rng = np.random.default_rng(0)
    t0 = ms("2024-03-15")
    ts = np.sort(t0 + rng.integers(0, 48 * C.HOUR_MS, 500)).astype("int64")
    d = pd.DataFrame({"timestamp": ts, "x": np.arange(500)})
    stamp = t0 + 12 * C.HOUR_MS
    slow = C._near(d, stamp, 45 * 60_000)
    fast = C._near(d, stamp, 45 * 60_000, ts)
    pd.testing.assert_frame_equal(slow, fast)


def test_a_flat_market_costs_only_fees_to_hedge():
    """With no price movement the hedge makes nothing and still pays fees."""
    px = flat_px("2024-03-15", 48)
    t0, t1 = ms("2024-03-15 12:00"), ms("2024-03-17 00:00")
    pnl, fees = C.hedge_pnl(px, t0, t1, K=100.0, cp=1.0, sigma=0.5,
                            expiry=ms("2024-03-18 08:00"), rehedge_minutes=60)
    assert pnl == pytest.approx(0.0, abs=1e-9)
    # One rebalance at entry still crosses the perpetual.
    assert fees > 0


def test_rehedging_more_often_costs_more_on_a_path_that_wanders():
    """The ladder in section 6.3 only means something if this holds.

    Rehedging cost scales with the total variation of the delta path, not with
    the number of rebalances: on a monotone path the trades telescope and every
    frequency pays the same. It is only because prices oscillate that finer
    rehedging costs more, so the simulator here has to wander rather than drift.
    """
    rng = np.random.default_rng(4)
    t0m = ms("2024-03-15")
    stamps = np.arange(t0m, t0m + 48 * C.HOUR_MS, 60_000, dtype="int64")
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 2e-4, len(stamps)))),
                   index=stamps)
    t0, t1 = ms("2024-03-15 12:00"), ms("2024-03-17 00:00")
    args = dict(K=100.0, cp=1.0, sigma=0.5, expiry=ms("2024-03-18 08:00"))
    fees = [C.hedge_pnl(px, t0, t1, rehedge_minutes=m, **args)[1]
            for m in (5, 30, 60, 240)]
    assert fees == sorted(fees, reverse=True)
    # On the real tape the same ratio is about 2.3x (0.090 against 0.039
    # per unit vega), so the bar is set below that rather than at it.
    assert fees[0] > 2 * fees[-1]


def test_rehedging_frequency_is_free_on_a_monotone_path():
    """The other side of the same fact, pinned so the first test reads right."""
    px = flat_px("2024-03-15", 48, drift=0.02)
    t0, t1 = ms("2024-03-15 12:00"), ms("2024-03-17 00:00")
    args = dict(K=100.0, cp=1.0, sigma=0.5, expiry=ms("2024-03-18 08:00"))
    fees = [C.hedge_pnl(px, t0, t1, rehedge_minutes=m, **args)[1]
            for m in (5, 240)]
    assert fees[0] == pytest.approx(fees[1], rel=0.02)


def test_the_hedge_offsets_a_short_call_in_a_rising_market():
    """A short call loses as spot rises; a long-delta hedge must gain."""
    px = flat_px("2024-03-15", 48, drift=0.05)
    t0, t1 = ms("2024-03-15 12:00"), ms("2024-03-17 00:00")
    pnl, _ = C.hedge_pnl(px, t0, t1, K=100.0, cp=1.0, sigma=0.5,
                         expiry=ms("2024-03-18 08:00"), rehedge_minutes=60)
    assert pnl > 0


def test_summarize_annualizes_on_a_weekly_trade():
    """This trade is on once a week, so 52 is the right root, not 252."""
    rng = np.random.default_rng(3)
    n = 400
    bl = pd.DataFrame({
        "net_per_vega": rng.normal(0.05, 0.2, n),
        "gross_per_vega": rng.normal(0.12, 0.2, n),
        "hold_hours": np.full(n, 36.0), "iv_change": np.zeros(n),
        "perp_fees": np.full(n, 1.0), "option_fees": np.full(n, 1.0),
        "spread_cost": np.full(n, 1.0), "vega_usd": np.full(n, 100.0),
    })
    st = C.summarize(bl, asset="TEST")
    s = bl["net_per_vega"]
    assert st["sharpe"] == pytest.approx(
        s.mean() / s.std() * np.sqrt(52), rel=1e-9)
    assert st["cost_per_vega"] == pytest.approx(0.03)


def test_summarize_survives_an_empty_blotter():
    st = C.summarize(pd.DataFrame(), asset="TEST", exit="sun_00")
    assert st["n"] == 0
    assert st["asset"] == "TEST"


def test_paired_keeps_only_fridays_common_to_every_exit():
    """The comparison across exits is meaningless on different samples."""
    def bl(days):
        return pd.DataFrame({
            "entry_ts": pd.to_datetime(days, utc=True),
            "net_per_vega": np.linspace(0.01, 0.05, len(days)),
            "gross_per_vega": np.linspace(0.05, 0.09, len(days)),
            "hold_hours": np.full(len(days), 36.0),
            "iv_change": np.zeros(len(days)),
        })
    a = ["2024-03-01", "2024-03-08", "2024-03-15"]
    b = ["2024-03-08", "2024-03-15", "2024-03-22"]
    out = C.paired({"sun_00": bl(a), "mon_00": bl(b)}, "TEST")
    assert set(out["n_common"]) == {2}


def test_paired_returns_nothing_when_no_friday_is_shared():
    def bl(days):
        return pd.DataFrame({
            "entry_ts": pd.to_datetime(days, utc=True),
            "net_per_vega": [0.01] * len(days),
            "gross_per_vega": [0.05] * len(days),
            "hold_hours": [36.0] * len(days), "iv_change": [0.0] * len(days),
        })
    out = C.paired({"a": bl(["2024-03-01"]), "b": bl(["2024-03-08"])}, "TEST")
    assert out.empty


def test_iv_rank_never_reads_the_future():
    """The rank at trade i must use only trades before i.

    A filter fitted on a series whose level trends -- which section 5.5 says
    implied volatility does -- would look best precisely when it is peeking, so
    this is the property that has to hold.
    """
    import weekend_filters as F
    n = 80
    b = pd.DataFrame({
        "entry_ts": pd.date_range("2020-01-03", periods=n, freq="7D", tz="UTC"),
        # Monotonically falling IV: every observation is the lowest so far, so
        # a causal rank must be 0 throughout and a peeking one would not be.
        "f_iv": np.linspace(1.0, 0.2, n),
    })
    out = F.derive(b)
    seen = out["f_iv_rank"].dropna()
    assert len(seen) == n - 12
    assert (seen == 0.0).all()


def test_iv_rank_is_one_when_the_level_only_rises():
    import weekend_filters as F
    n = 60
    b = pd.DataFrame({
        "entry_ts": pd.date_range("2020-01-03", periods=n, freq="7D", tz="UTC"),
        "f_iv": np.linspace(0.2, 1.0, n),
    })
    out = F.derive(b)
    assert (out["f_iv_rank"].dropna() == 1.0).all()


def test_within_transform_absorbs_a_group_effect():
    """The fixed effect in section 6.5 is absorbed by demeaning, not by dummies."""
    import weekend_content as W
    codes = np.repeat(np.arange(5), 20)
    rng = np.random.default_rng(12)
    level = np.repeat(rng.normal(0, 10, 5), 20)      # a large group effect
    x = rng.normal(0, 1, 100)
    y = level + 2.0 * x + rng.normal(0, 0.01, 100)
    xd, yd = W._within(x, codes), W._within(y, codes)
    beta = float(np.linalg.lstsq(xd[:, None], yd, rcond=None)[0][0])
    assert beta == pytest.approx(2.0, abs=0.01)
    # The group means are gone, which is the point.
    assert np.allclose(np.bincount(codes, weights=yd), 0, atol=1e-9)


def test_weekend_share_of_life_and_of_window_can_differ():
    """The two regressors of section 6.5 must not be the same number.

    Entering Thursday noon and holding 36 hours gives a window with no weekend
    at all, while the contract sold still has a weekend in its remaining life.
    A design where these coincide is the one section 6.4 could not identify.
    """
    from dbop import weekend as W
    thu = ms("2024-03-14 12:00")
    out = thu + 36 * C.HOUR_MS                      # Saturday 00:00
    mon_expiry = ms("2024-03-18 08:00")
    life = float(W.weekend_fraction(np.array([thu]), np.array([mon_expiry]))[0])
    hold = float(W.weekend_fraction(np.array([thu]), np.array([out]))[0])
    assert hold == pytest.approx(0.0, abs=1e-9)
    assert life > 0.3


def test_the_pnl_attribution_adds_up():
    """attributed + residual must reconstruct the gross P&L exactly.

    The decomposition of section 6.6 is only interpretable if the residual is
    genuinely everything the five terms do not explain, so this is an identity
    rather than an approximation and is checked as one.
    """
    import pandas as pd
    from dbop import config
    for cur in ("BTC", "ETH"):
        f = config.TABLES / f"w46_content_trades_{cur}.csv"
        if not f.exists():
            pytest.skip("content trades not built")
        t = pd.read_csv(f)
        terms = ["term_gamma", "term_theta", "term_vega", "term_volga",
                 "term_vanna"]
        # The stored file is written at six significant figures, so the tolerance
        # is set by the format rather than by the arithmetic.
        assert np.allclose(t[terms].sum(axis=1), t["attributed"], atol=1e-4)
        assert np.allclose(t["attributed"] + t["residual"],
                           t["gross_per_vega"], atol=1e-4)


def test_the_vega_term_is_just_the_move_in_implied_vol():
    """Per unit vega the first-order volatility term reduces to -d(sigma)."""
    import pandas as pd
    from dbop import config
    f = config.TABLES / "w46_content_trades_BTC.csv"
    if not f.exists():
        pytest.skip("content trades not built")
    t = pd.read_csv(f)
    assert np.allclose(t["term_vega"], -(t["iv_out"] - t["iv_in"]), atol=1e-4)


# ------------------------------------------------------- the exit index

def _marks(rows) -> pd.DataFrame:
    """A print tape: (instrument, when, sigma, forward)."""
    return pd.DataFrame(
        [{"instrument_name": n, "timestamp": ms(t), "sigma": s, "F": f}
         for n, t, s, f in rows]).sort_values("timestamp")


def test_exit_index_finds_the_closest_print_and_only_inside_the_window():
    ix = C.InstIndex(_marks([
        ("BTC-A", "2024-03-03 23:10:00", 0.50, 100.0),
        ("BTC-A", "2024-03-04 00:20:00", 0.60, 110.0),
        ("BTC-B", "2024-03-01 00:00:00", 0.70, 120.0),
    ]))
    t = ms("2024-03-04 00:00:00")
    assert ix.nearest("BTC-A", t, 45 * C.HOUR_MS // 60)["sigma"] == 0.60
    # 50 minutes away on one side, 20 on the other; a 45-minute window keeps one.
    assert ix.nearest("BTC-A", t, 15 * 60_000) is None
    assert ix.nearest("BTC-B", t, 45 * 60_000) is None
    assert ix.nearest("BTC-NOT-LISTED", t, 45 * 60_000) is None


def test_exit_index_keeps_instruments_apart():
    ix = C.InstIndex(_marks([
        ("BTC-A", "2024-03-04 00:01:00", 0.50, 100.0),
        ("BTC-B", "2024-03-04 00:02:00", 0.90, 200.0),
    ]))
    t = ms("2024-03-04 00:00:00")
    assert ix.nearest("BTC-A", t, C.HOUR_MS)["F"] == 100.0
    assert ix.nearest("BTC-B", t, C.HOUR_MS)["F"] == 200.0


def test_exit_index_window_filter_keeps_prints_near_the_instants():
    tape = _marks([("BTC-A", "2024-03-04 00:05:00", 0.5, 100.0),
                   ("BTC-A", "2024-03-06 12:00:00", 0.5, 100.0)])
    instants = np.array([ms("2024-03-04 00:00:00")], dtype="int64")
    ix = C.InstIndex(tape, instants, 45 * 60_000)
    assert len(ix) == 1
    assert ix.nearest("BTC-A", ms("2024-03-04 00:00:00"), 45 * 60_000) is not None
    assert ix.nearest("BTC-A", ms("2024-03-06 12:00:00"), 45 * 60_000) is None


def test_a_contract_that_leaves_the_delta_band_is_still_marked_at_the_exit():
    """The defect this index was written to remove.

    The old exit lookup was built from the delta-banded entry frame, so a
    contract that had drifted out of the money by the exit had no mark and the
    trade vanished from the blotter. Options leave the band when the index
    moves and a delta-hedged short loses when the index moves, so that dropped
    the losing weekends and inflated the result. An unbanded index marks it.
    """
    fri = ms("2024-03-01 00:00:00")
    entry = fri + 12 * C.HOUR_MS
    exit_t = fri + C.DAY_MS + C.EXITS["sun_00"] * C.HOUR_MS
    expiry = fri + 7 * C.DAY_MS

    d = pd.DataFrame([{
        "timestamp": entry, "instrument_name": "BTC-1MAR24-100-C",
        "strike": 100.0, "cp_sign": 1.0, "sigma": 0.60, "F": 100.0,
        "expiration_timestamp": expiry, "delta": 0.52,
    }])
    # By the exit the index has run to 160: the option is deep in the money and
    # far outside the 0.35-0.65 band it was entered in.
    banded = _marks([("BTC-1MAR24-100-C", "2024-03-02 12:00:00", 0.60, 100.0)])
    unbanded = _marks([("BTC-1MAR24-100-C", "2024-03-02 12:00:00", 0.60, 100.0),
                       ("BTC-1MAR24-100-C", "2024-03-03 00:00:00", 0.62, 160.0)])
    px = flat_px("2024-03-01 00:00:00", 72, level=100.0)

    got = C.run_one(d, px, 12, "sun_00", 0.0, C.InstIndex(unbanded),
                    rehedge_minutes=60)
    assert len(got) == 1
    assert got.iloc[0]["index_out"] == 160.0

    # The banded index has no print at the exit instant, so the trade is lost.
    assert C.run_one(d, px, 12, "sun_00", 0.0, C.InstIndex(banded),
                     rehedge_minutes=60).empty
    assert exit_t > entry
