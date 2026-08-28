"""Tests for scripts/weekend_moneyness.py.

The moneyness ladder is one rule run across five delta buckets, so the things
worth pinning are the ones that decide which bucket a contract lands in, and the
regression that keeps the buckets from being maturity in disguise.

The within-Friday test is the important one. An earlier design controlled
maturity by hand, forcing every bucket onto one expiry, and it starved the
wings; the replacement controls it in the regression instead. That only works if
the fixed effect really does absorb the entry instant, so the test plants a
Friday effect large enough to swamp the bucket effects and checks that the
pooled specification is fooled by it and the absorbed one is not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_moneyness as M  # noqa: E402


# ------------------------------------------------------------------ buckets

def test_buckets_tile_the_ladder_without_overlap():
    edges = [(lo, hi) for _, lo, hi, _ in M.BUCKETS]
    for (lo, hi) in edges:
        assert lo < hi
    # Written high-delta first, and each bucket's floor is the next one's ceiling.
    for (lo, _), (_, hi_next) in zip(edges[:-1], edges[1:]):
        assert lo == hi_next


def test_label_puts_each_delta_in_exactly_one_bucket():
    deltas = np.linspace(0.02, 0.999, 400)
    got = M.label(deltas)
    assert (got != "").all()
    for name, lo, hi, mid in M.BUCKETS:
        assert M.label(np.array([mid]))[0] == name
        # The floor belongs to the bucket, the ceiling to the one above.
        assert M.label(np.array([lo]))[0] == name


def test_label_leaves_deltas_outside_the_ladder_unlabelled():
    assert M.label(np.array([0.0]))[0] == ""
    assert M.label(np.array([1.0]))[0] == ""


def test_bucket_slugs_are_distinct_and_identifier_safe():
    slugs = [M._slug(b) for b in M.BUCKET_ORDER]
    assert len(set(slugs)) == len(slugs)
    assert all(s.isidentifier() for s in slugs)


# ------------------------------------------------------------------ summary

def _synthetic(n_fri: int = 60, bucket_effect: dict | None = None,
               friday_sd: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """A trade sheet with a planted bucket effect and a planted Friday effect."""
    bucket_effect = bucket_effect or {b: 0.0 for b in M.BUCKET_ORDER}
    rng = np.random.default_rng(seed)
    fridays = pd.date_range("2023-01-06", periods=n_fri, freq="7D", tz="UTC")
    rows = []
    for i, f in enumerate(fridays):
        shock = rng.normal(0.0, friday_sd)
        for b in M.BUCKET_ORDER:
            rows.append({
                "entry_ts": f + pd.Timedelta(hours=12),
                "bucket": b,
                "cp": "C" if (i + len(b)) % 2 else "P",
                "abs_delta": dict((n, m) for n, _, _, m in M.BUCKETS)[b],
                # These carry no planted effect, but they have to vary: the
                # later specifications control for them, and a constant column
                # is singular once the fixed effect has been swept out.
                "T_days": float(rng.uniform(1.0, 10.0)),
                "wknd_frac": float(rng.uniform(0.2, 0.8)),
                "volga_per_vega": float(rng.normal()),
                "gamma_per_vega": float(rng.normal()),
                "vega_usd": 100.0,
                "net_per_vega": bucket_effect[b] + shock + rng.normal(0, 0.01),
                "gross_per_vega": 0.0, "cost_per_vega": 0.0,
                "half_spread_volpts": 0.0, "net_usd": 0.0, "iv_change": 0.0,
                "term_gamma": 0.0, "term_theta": 0.0, "term_vega": 0.0,
                "term_volga": 0.0, "term_vanna": 0.0,
            })
    return pd.DataFrame(rows)


def test_summarize_reports_the_planted_mean_and_hit_rate():
    eff = {b: 0.05 for b in M.BUCKET_ORDER}
    eff["deep OTM"] = -0.05
    s = M.summarize({"BTC": _synthetic(bucket_effect=eff)})
    got = s.set_index("bucket")["net_per_vega"]
    assert got["ATM"] == pytest.approx(0.05, abs=5e-3)
    assert got["deep OTM"] == pytest.approx(-0.05, abs=5e-3)
    hit = s.set_index("bucket")["hit_rate"]
    assert hit["ATM"] > 0.95 and hit["deep OTM"] < 0.05


def test_summarize_refuses_to_report_a_bucket_it_cannot_measure():
    """This is not hypothetical: Ether's deep ITM wing printed once."""
    t = _synthetic(n_fri=40)
    t = t[(t["bucket"] != "deep ITM")
          | (t["entry_ts"] == t["entry_ts"].iloc[0])]
    s = M.summarize({"BTC": t}).set_index("bucket")
    assert s.loc["deep ITM", "n"] == 1
    assert pd.isna(s.loc["deep ITM", "net_per_vega"])
    assert not pd.isna(s.loc["ATM", "net_per_vega"])


# -------------------------------------------------------------- regressions

def test_friday_fixed_effect_absorbs_a_common_shock_and_pooling_does_not():
    """The whole design rests on this: compare buckets within one instant."""
    eff = {b: 0.0 for b in M.BUCKET_ORDER}
    eff["deep OTM"] = -0.04
    # Only the wing trades on high-shock Fridays, so pooling confounds the two.
    t = _synthetic(n_fri=200, bucket_effect=eff, friday_sd=0.30, seed=7)
    fri = t["entry_ts"].dt.date.astype(str)
    keep = (fri.astype("category").cat.codes % 2 == 0) | (t["bucket"] != "deep OTM")
    t = t[keep]

    reg = M.regressions({"BTC": t})
    pooled = reg[(reg.spec == "A. buckets, pooled")
                 & (reg.term == "b_deep_otm")].iloc[0]
    absorbed = reg[(reg.spec == "B. + Friday fixed effect")
                   & (reg.term == "b_deep_otm")].iloc[0]

    assert abs(absorbed.beta - (-0.04)) < 0.01
    assert abs(absorbed.beta - (-0.04)) < abs(pooled.beta - (-0.04))
    assert absorbed.se < pooled.se


def test_regressions_omit_the_money_as_the_reference_bucket():
    reg = M.regressions({"BTC": _synthetic(n_fri=100)})
    terms = set(reg[reg.spec == "A. buckets, pooled"]["term"])
    assert "b_atm" not in terms
    assert {"b_deep_itm", "b_itm", "b_otm", "b_deep_otm"} <= terms


def test_regressions_skip_a_book_too_thin_to_estimate():
    assert M.regressions({"XRP": _synthetic(n_fri=5)}).empty


# ------------------------------------------------------------------ parity

def test_parity_check_splits_by_option_type_and_drops_thin_cells():
    t = _synthetic(n_fri=40)
    t.loc[t["bucket"] == "deep ITM", "cp"] = "C"  # no puts at all in that wing
    p = M.parity_check(t)
    deep = p[p.bucket == "deep ITM"]
    assert set(deep["cp"]) == {"C"}
    assert set(p[p.bucket == "ATM"]["cp"]) == {"C", "P"}
