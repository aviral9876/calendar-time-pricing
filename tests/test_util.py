"""Index handling in the date helpers.

These exist because a Series that silently drops its index is far more
dangerous than one that raises: assigning it onto a filtered DataFrame aligns
on the wrong labels, turns most rows into NaT, and every groupby downstream
quietly shrinks instead of failing.
"""
import numpy as np
import pandas as pd
import pytest

from dbop import util


def _frame(n=10):
    return pd.DataFrame({
        "timestamp": np.arange(n, dtype="int64") * 86_400_000 + 1_700_000_000_000,
        "x": np.arange(n),
    })


def test_to_utc_day_preserves_index():
    df = _frame()
    filtered = df[df["x"] % 3 == 0]          # non-contiguous index: 0, 3, 6, 9
    ts = pd.to_datetime(filtered["timestamp"], unit="ms", utc=True)
    out = util.to_utc_day(ts)
    assert list(out.index) == list(filtered.index)


def test_assignment_onto_filtered_frame_has_no_nat():
    """The exact failure mode: assign without .to_numpy() onto a filtered frame."""
    df = _frame(50)
    filtered = df[df["x"] % 3 == 0].copy()
    filtered["date"] = util.to_utc_day(
        pd.to_datetime(filtered["timestamp"], unit="ms", utc=True))
    assert filtered["date"].notna().all(), "index misalignment produced NaT"
    assert filtered["date"].dt.year.notna().all()


def test_to_utc_day_accepts_arrays():
    arr = np.array([1_700_000_000_000, 1_700_086_400_000], dtype="int64")
    out = util.to_utc_day(pd.to_datetime(arr, unit="ms", utc=True))
    assert len(out) == 2
    assert str(out.dtype) == "datetime64[ns, UTC]"


def test_to_utc_day_normalizes_to_midnight():
    ts = pd.Series(pd.to_datetime(
        ["2026-08-14 08:00:00+00:00", "2026-08-14 23:59:59+00:00"], utc=True))
    out = util.to_utc_day(ts)
    assert (out.dt.hour == 0).all()
    assert out.nunique() == 1


def test_to_numpy_call_sites_still_work():
    """dbop modules append .to_numpy(); that must remain valid."""
    df = _frame()
    ts = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    arr = util.to_utc_day(ts).to_numpy()
    assert len(arr) == len(df)
    df2 = df[df["x"] > 5].copy()
    ts2 = pd.to_datetime(df2["timestamp"], unit="ms", utc=True)
    df2["date"] = util.to_utc_day(ts2).to_numpy()
    assert df2["date"].notna().all()


def test_normalize_date_col_roundtrip():
    df = _frame()
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    out = util.normalize_date_col(df)
    assert out["date"].notna().all()
    assert (out["date"].dt.hour == 0).all()
