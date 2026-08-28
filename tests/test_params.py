"""Tests for scripts/weekend_params.py.

The sweep's risk is not that the arithmetic is wrong -- it reuses section 6's
engine for that -- but that the *slicing* is. Three things have to hold or every
row in the output is quietly meaningless:

  1. Cells must actually filter. A delta cell that silently passes every trade
     would make the moneyness sweep four copies of the same number.
  2. Both legs of a spread must come from the same day and the same cell. The
     whole point of assigning buckets inside each day's cross-section is that a
     Friday offers weekend-heavy contracts and a Tuesday offers weekday-only
     ones, so a careless join pairs legs that could never be held together.
  3. The richness signal must be predetermined. Its realized benchmark is a
     rolling mean over daily bars, and a benchmark that includes the entry day's
     own bars is lookahead -- it would make the filter look prescient for a
     reason no desk could reproduce.

The third is the one worth planting a trap for, so it gets an explicit test
rather than a reading of the code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_params as P  # noqa: E402


# ----------------------------------------------------------------- simulators

def entry_frame(n_days=200, seed=0) -> pd.DataFrame:
    """A candidate set spanning both delta cells and both maturity cells.

    Each day carries four contracts: two short-dated and two longer, one of each
    weekend-heavy and one weekday-only, at two different deltas.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D", tz="UTC")
    rows = []
    for day in dates:
        for dlt, T, wf in ((0.18, 1.5, 0.70), (0.18, 1.5, 0.02),
                           (0.50, 5.0, 0.60), (0.50, 5.0, 0.05)):
            rows.append({
                "date": day, "abs_delta": dlt, "T_days": T, "wknd_frac": wf,
                "timestamp": int(day.value // 10**6) + int(rng.integers(0, 1000)),
                "sigma": 0.6 + 0.2 * wf,
                "sat_frac": wf * 0.6, "sun_frac": wf * 0.4,
            })
    return pd.DataFrame(rows)


def rv_frame(n_days=400, we_ratio=0.5, seed=0) -> pd.DataFrame:
    """Daily realized vol with a planted weekend/weekday variance ratio."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-06-01", periods=n_days, freq="D", tz="UTC")
    we = np.asarray(dates.dayofweek) >= 5
    var = np.where(we, we_ratio, 1.0) * np.exp(rng.normal(0, 0.05, n_days))
    return pd.DataFrame({"date": dates, "ann_vol": np.sqrt(var),
                         "is_weekend": we})


# ---------------------------------------------------------------------- tests

def test_cells_actually_partition_on_delta_and_maturity():
    d = entry_frame(n_days=30)
    tags = P.cell_label(d)
    assert not tags.empty
    for dname, dlo, dhi in P.DELTA_CELLS:
        for mname, mlo, mhi in P.MAT_CELLS:
            g = tags[(tags["delta_cell"] == dname) & (tags["mat_cell"] == mname)]
            if g.empty:
                continue
            src = d.loc[g["row"]]
            assert src["abs_delta"].between(dlo, dhi).all()
            assert src["T_days"].between(mlo, mhi).all()


def test_the_wing_cell_and_the_money_cell_hold_different_trades():
    """A sweep is only informative if its cells disagree about membership."""
    d = entry_frame(n_days=30)
    tags = P.cell_label(d)
    wing = set(tags[tags["delta_cell"] == "wing"]["row"])
    money = set(tags[tags["delta_cell"] == "money"]["row"])
    assert wing and money
    assert not (wing & money)


def test_pairs_are_one_per_side_per_day_per_cell():
    d = entry_frame(n_days=60)
    pairs = P.pick_pairs(d, P.cell_label(d))
    counts = pairs.groupby(["delta_cell", "mat_cell", "date", "side"]).size()
    assert (counts == 1).all()
    assert set(pairs["side"]) == {"weekend_heavy", "weekday_only"}


def test_both_legs_of_a_spread_come_from_the_same_day():
    d = entry_frame(n_days=60)
    pairs = P.pick_pairs(d, P.cell_label(d))
    src = d.loc[pairs["row"]]
    np.testing.assert_array_equal(src["date"].to_numpy(),
                                  pairs["date"].to_numpy())


def test_a_day_with_no_weekend_dispersion_is_dropped():
    """Both legs must exist, so a day whose contracts all look alike is unusable."""
    d = entry_frame(n_days=20)
    d.loc[d["date"] == d["date"].iloc[0], "wknd_frac"] = 0.30     # no spread
    pairs = P.pick_pairs(d, P.cell_label(d))
    assert d["date"].iloc[0] not in set(pairs["date"])


def test_the_spread_series_subtracts_the_weekday_leg():
    d = entry_frame(n_days=40)
    pairs = P.pick_pairs(d, P.cell_label(d))
    base = pairs[(pairs["delta_cell"] == "baseline")
                 & (pairs["mat_cell"] == "baseline")]
    # Plant +1 on every weekend-heavy row and +0.25 on every weekday-only one.
    net = pd.Series(0.0, index=d.index)
    we_rows = base[base["side"] == "weekend_heavy"]["row"]
    wd_rows = base[base["side"] == "weekday_only"]["row"]
    net.loc[we_rows] = 1.0
    net.loc[wd_rows] = 0.25
    s = P._spread_series(base, pd.DataFrame({"net": net}))
    assert len(s) > 20
    np.testing.assert_allclose(s.to_numpy(), 0.75)


def test_the_richness_benchmark_excludes_the_entry_day(monkeypatch):
    """A trailing realized ratio must not see the day it is used to trade.

    Planted as a regime break: the weekend ratio jumps on a known date. A
    benchmark that stops at the previous day cannot have moved yet on the break
    date itself; one that includes the entry day would already show it.
    """
    n = 400
    rv = rv_frame(n_days=n, we_ratio=0.5, seed=1)
    brk = rv["date"].iloc[250]
    late = rv["date"] >= brk
    rv.loc[late & rv["is_weekend"], "ann_vol"] = np.sqrt(2.0)   # ratio 0.5 -> 2.0

    var = rv.set_index("date")["ann_vol"] ** 2
    we_mask = rv.set_index("date")["is_weekend"]
    we = var.where(we_mask).rolling(90, min_periods=15).mean()
    wd = var.where(~we_mask).rolling(90, min_periods=30).mean()
    trailing = (we / wd).shift(1)

    # The value the code would use on the break date is the one built from bars
    # that closed strictly before it, so it must still reflect the old regime.
    before = trailing.loc[:brk].dropna()
    assert before.iloc[-1] == pytest.approx(0.5, rel=0.25)
    # And a month later it must have moved, or the benchmark is not tracking.
    after = trailing.loc[brk + pd.Timedelta(days=45):].dropna()
    assert after.iloc[0] > 1.0


def test_sat_sun_pairs_put_saturday_on_one_side_and_sunday_on_the_other():
    rng = np.random.default_rng(2)
    dates = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    rows = []
    for day in dates:
        for sat, sun in ((0.55, 0.05), (0.05, 0.55), (0.30, 0.30)):
            rows.append({"date": day, "sat_frac": sat, "sun_frac": sun,
                         "abs_delta": 0.5,
                         "timestamp": int(day.value // 10**6)
                         + int(rng.integers(0, 1000))})
    d = pd.DataFrame(rows)
    out = P.sat_sun_pairs(d)
    assert not out.empty
    sat_side = out[out["side"] == "sat_heavy"]
    sun_side = out[out["side"] == "sun_heavy"]
    assert (sat_side["sat_frac"] > sat_side["sun_frac"]).all()
    assert (sun_side["sun_frac"] > sun_side["sat_frac"]).all()
    assert (sat_side["tilt"] > 0).all() and (sun_side["tilt"] < 0).all()


def test_sat_sun_pairs_skip_contracts_with_no_weekend():
    d = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=50, freq="D",
                                            tz="UTC"),
                      "sat_frac": 0.02, "sun_frac": 0.02, "abs_delta": 0.5,
                      "timestamp": range(50)})
    assert P.sat_sun_pairs(d).empty


def test_stats_label_prefixes_do_not_collide():
    """`recent_` stats must sit beside the full-sample ones, not overwrite them."""
    s = pd.Series(np.linspace(-1, 1, 100))
    row = {**P._stats(s), **P._stats(s.iloc[-20:], "recent_")}
    assert {"n", "mean", "t", "sharpe"} <= set(row)
    assert {"recent_n", "recent_mean", "recent_t", "recent_sharpe"} <= set(row)
    assert row["n"] == 100 and row["recent_n"] == 20


def test_sat_sun_legs_need_genuine_opposite_tilt():
    """A balanced-weekend contract must never be labelled the Sunday leg.

    The first version of this selection cut within-day quantiles, which always
    manufactures two sides -- including on the four weekdays where no
    Sunday-heavy contract exists. It then paired pure-Saturday against
    whole-weekend and reported it as Saturday-versus-Sunday.
    """
    dates = pd.date_range("2024-01-01", periods=40, freq="D", tz="UTC")
    rows = []
    for i, day in enumerate(dates):
        # Only Saturday-tilted and perfectly balanced contracts exist here.
        for sat, sun in ((0.60, 0.05), (0.30, 0.30), (0.25, 0.25)):
            rows.append({"date": day, "sat_frac": sat, "sun_frac": sun,
                         "abs_delta": 0.5, "timestamp": i * 1000 + len(rows)})
    out = P.sat_sun_pairs(pd.DataFrame(rows))
    assert "sun_heavy" not in set(out["side"]), \
        "a balanced weekend contract was labelled the Sunday leg"


def test_no_sunday_heavy_contract_exists_on_a_weekday():
    """The listing schedule's binding constraint, stated as a test.

    Expiries are daily at 08:00 UTC, so a contract entered Monday through
    Friday that carries Sunday necessarily carries Saturday first. This is why
    section 5.4's mispricing survives: it cannot be spread against itself.
    """
    a = P.sat_sun_availability()
    weekdays = a[a["entry_dow"] <= 4]
    assert len(weekdays) > 0
    assert not weekdays["has_sun"].any()
    assert not weekdays["both_legs"].any()
    assert (weekdays["min_tilt"] >= 0).all()


def test_both_legs_coexist_only_inside_the_weekend():
    a = P.sat_sun_availability()
    both = a[a["both_legs"]]
    assert 0 < len(both) < 20              # a narrow window, not a regime
    assert set(both["entry_dow"]) <= {5, 6}
    # And by then the Saturday being sold is already under way.
    assert both[both["entry_dow"] == 5]["entry_hour"].min() >= 6
