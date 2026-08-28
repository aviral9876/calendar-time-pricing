"""Small shared helpers.

Date handling is centralized here because the pieces of the pipeline arrive at
"a day" by different routes -- normalizing a UTC timestamp, grouping python
date objects, reading back from parquet -- and pandas treats the results as
different dtypes, which turns an innocent merge into a silent mismatch or a
hard error. Every producer of a ``date`` column routes it through
``to_utc_day`` so joins across the pipeline are exact.
"""
from __future__ import annotations

import pandas as pd


def to_utc_day(s) -> pd.Series:
    """Coerce anything day-like to tz-aware UTC midnight, nanosecond dtype.

    The input index is preserved. An earlier version returned a fresh
    RangeIndex, which is safe only when the caller immediately appends
    ``.to_numpy()``. Assigning the Series directly onto a *filtered* frame
    instead aligns on index, so every row whose label no longer equals its
    position silently became NaT -- and those rows then vanished from any
    groupby or dropna downstream. That cost roughly three quarters of several
    regression samples before it was caught, with no error raised anywhere.
    """
    idx = s.index if isinstance(s, pd.Series) else None
    out = pd.to_datetime(pd.Series(s).values, utc=True)
    res = pd.Series(out).dt.tz_convert("UTC").dt.normalize().astype(
        "datetime64[ns, UTC]")
    if idx is not None:
        res.index = idx
    return res


def normalize_date_col(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    if col in df.columns:
        df = df.copy()
        df[col] = to_utc_day(df[col]).to_numpy()
    return df
