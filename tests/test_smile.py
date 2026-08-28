"""Tests for the moneyness (smile) test in scripts/weekend_riskrace.py.

The directional contrast this test guards is the one the risk horse race turns
on: a jump-risk premium is priced away from the money, so if the weekend
discount were jump compensation it would have to weaken toward the wings. Getting
the sign or the bucket ordering wrong would answer that question backwards while
producing entirely plausible numbers, which is what happened once -- pandas
factorizes a categorical in order of first appearance, not in category order.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekend_riskrace as R  # noqa: E402


def panel(slopes: dict, n_days: int = 240, per_cell: int = 60,
          seed: int = 0) -> pd.DataFrame:
    """Squared implied vol generated with a known weekend slope per bucket.

    Each day carries its own level so the within-day demeaning has something to
    remove, and every bucket sits at the same mean level so that the scaling by
    bucket mean inside the estimator is a no-op and the recovered coefficients
    are directly comparable with the slopes asked for.
    """
    rng = np.random.default_rng(seed)
    # One representative distance-from-the-money per bucket, inside its bin.
    centres = dict(zip(R.ATM_LABELS, (0.06, 0.15, 0.27, 0.43)))
    rows = []
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D", tz="UTC")
    for d in dates:
        level = 1.0 + rng.normal(0, 0.3)
        for label, atm in centres.items():
            w = rng.uniform(0.0, 0.6, per_cell)
            rows.append(pd.DataFrame({
                "iv2": level + slopes[label] * (w - 0.3)
                       + rng.normal(0, 0.02, per_cell),
                "wknd_frac": w,
                "logT": rng.uniform(0.0, 2.6, per_cell),
                "atmness": atm + rng.normal(0, 0.004, per_cell),
                "is_call": rng.integers(0, 2, per_cell).astype(float),
                "date": d,
            }))
    d = pd.concat(rows, ignore_index=True)
    d["bucket"] = pd.cut(d["atmness"], R.ATM_BINS, labels=R.ATM_LABELS,
                         include_lowest=True)
    return d


def test_contrast_is_far_wing_minus_at_the_money():
    """The far wing discounts the weekend far harder than the money, so the
    contrast (wing minus money) must come out clearly negative."""
    slopes = {"far wing": -0.9, "wing": -0.6, "near": -0.4,
              "at the money": -0.3}
    out = R.smile_wald(panel(slopes))
    assert out["wing_minus_atm"] == pytest.approx(-0.6, abs=0.05)
    assert out["wing_minus_atm_t"] < -5
    assert out["p_equal"] < 0.01


def test_contrast_flips_with_the_data():
    """Reversed data must reverse the sign. A contrast that reports the same
    thing either way is reading the wrong pair of buckets."""
    slopes = {"far wing": -0.3, "wing": -0.4, "near": -0.6,
              "at the money": -0.9}
    out = R.smile_wald(panel(slopes))
    assert out["wing_minus_atm"] == pytest.approx(+0.6, abs=0.05)
    assert out["wing_minus_atm_t"] > 5


def test_flat_smile_is_not_rejected():
    slopes = {lab: -0.5 for lab in R.ATM_LABELS}
    out = R.smile_wald(panel(slopes, seed=3))
    assert abs(out["wing_minus_atm"]) < 0.05
    assert out["p_equal"] > 0.05


def test_slopes_are_reported_against_the_right_labels():
    slopes = {"far wing": -0.9, "wing": -0.6, "near": -0.4,
              "at the money": -0.3}
    out = R.smile_wald(panel(slopes))
    for label, want in slopes.items():
        got = out[f"slope_{label.replace(' ', '_')}"]
        assert got == pytest.approx(want, abs=0.05), label


def test_bucket_order_does_not_depend_on_row_order():
    slopes = {"far wing": -0.9, "wing": -0.6, "near": -0.4,
              "at the money": -0.3}
    d = panel(slopes)
    shuffled = d.sample(frac=1.0, random_state=7).reset_index(drop=True)
    a, b = R.smile_wald(d), R.smile_wald(shuffled)
    assert a["wing_minus_atm"] == pytest.approx(b["wing_minus_atm"], rel=1e-6)
