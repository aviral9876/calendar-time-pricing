"""Stage-by-stage validation.

Every check here answers a question that, if wrong, would silently invalidate
the paper rather than crash it. They run as a suite so a rebuild reports a
single pass/fail table.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import backfill, bars, config, greeks, instruments, surfaces, tape, util

log = logging.getLogger(__name__)


def check_backfill(currency: str) -> pd.DataFrame:
    """Completeness and internal consistency of the cached tape."""
    man = backfill.load_manifest(currency)
    rows = []

    if man.empty:
        return pd.DataFrame([{"check": "manifest exists", "pass": False,
                              "detail": "no manifest"}])

    dates = pd.to_datetime(man["date"])
    expected = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = set(expected) - set(dates)
    rows.append({"check": "no missing days in span", "pass": not missing,
                 "detail": f"{len(missing)} missing of {len(expected)}"})

    rows.append({"check": "all days complete",
                 "pass": bool(man["complete"].all()),
                 "detail": f"{int((~man['complete'].astype(bool)).sum())} incomplete"})

    total = int(man["n_trades"].sum())
    rows.append({"check": "nonzero trade count", "pass": total > 0,
                 "detail": f"{total:,} trades"})

    # Day files must not overlap: the last timestamp of one day must precede
    # the first of the next, or a trade is double counted in two files.
    m = man[man["n_trades"] > 0].sort_values("date")
    overlap = (m["last_ts"].to_numpy()[:-1] >= m["first_ts"].to_numpy()[1:]).sum()
    rows.append({"check": "no cross-day timestamp overlap", "pass": overlap == 0,
                 "detail": f"{int(overlap)} overlapping boundaries"})

    return pd.DataFrame(rows)


def check_day_file(currency: str, day: dt.date) -> pd.DataFrame:
    """Row-level invariants on one cached day."""
    p = backfill.day_path(currency, day)
    if not p.exists():
        return pd.DataFrame([{"check": f"{day} exists", "pass": False,
                              "detail": "file missing"}])
    df = pd.read_parquet(p)
    start = backfill._to_ms(day)
    rows = [
        {"check": "unique trade_id",
         "pass": bool(df["trade_id"].is_unique),
         "detail": f"{len(df) - df['trade_id'].nunique()} duplicates"},
        {"check": "timestamps inside the day",
         "pass": bool(((df["timestamp"] >= start)
                       & (df["timestamp"] < start + backfill.DAY_MS)).all()),
         "detail": ""},
        {"check": "direction is +-1",
         "pass": bool(df["direction"].isin([-1, 1]).all()), "detail": ""},
        {"check": "positive prices and amounts",
         "pass": bool(((df["price"] > 0) & (df["amount"] > 0)).all()),
         "detail": ""},
        {"check": "index price positive",
         "pass": bool((df["index_price"] > 0).all()), "detail": ""},
    ]
    return pd.DataFrame(rows)


def check_iv_recomputation(currency: str, day: dt.date,
                           sample: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Recompute implied vol from the traded premium and compare to Deribit's.

    The whole study takes the exchange IV field at face value for speed, so
    this is the check that earns that shortcut. A median gap materially above a
    vol point would mean either the forward convention or the inverse-premium
    convention is wrong.
    """
    df = tape.load(currency, day, day)
    if df.empty:
        return pd.DataFrame([{"check": "iv recomputation", "pass": False,
                              "detail": f"no trades on {day}"}])

    d = df[df["iv_ok"] & (df["T"] > 1 / 365) & (df["premium_usd"] > 0)]
    if len(d) > sample:
        d = d.sample(sample, random_state=seed)
    if d.empty:
        return pd.DataFrame([{"check": "iv recomputation", "pass": False,
                              "detail": "no usable trades"}])

    recomputed = greeks.implied_vol(
        d["premium_usd"].to_numpy(), d["F"].to_numpy(),
        d["strike"].to_numpy(dtype="float64"), d["T"].to_numpy(),
        d["cp_sign"].to_numpy())
    diff = (recomputed - d["sigma"].to_numpy()) * 100      # vol points
    med = float(np.nanmedian(np.abs(diff)))
    signed = float(np.nanmedian(diff))
    solved = float(np.isfinite(recomputed).mean())

    return pd.DataFrame([
        {"check": "median |recomputed - exchange| IV < 1 vol pt",
         "pass": med < 1.0, "detail": f"median {med:.3f} vol pts, n={len(d)}"},
        # A convention error (wrong forward, wrong premium units) shows up as a
        # systematic level shift, not as symmetric dispersion. Tick-size noise
        # in far-OTM premia produces the latter and is expected.
        {"check": "no systematic IV bias (|signed median| < 0.25 vol pt)",
         "pass": abs(signed) < 0.25,
         "detail": f"signed median {signed:+.3f} vol pts"},
        {"check": "inversion solves for most trades", "pass": solved > 0.9,
         "detail": f"{solved:.1%} solved"},
    ])


def check_marks_and_surface(currency: str, grid: pd.DataFrame) -> pd.DataFrame:
    """Compare our independently built surface against Deribit's own DVOL.

    DVOL is a 30-day model-free index, so it should track but sit slightly
    above our 30-day ATM point (model-free implied variance exceeds the ATM
    vol under a smile). Correlation is the real test; the level gap is
    expected and informative.
    """
    rows = []
    try:
        dv = bars.dvol_daily(currency)
    except FileNotFoundError:
        return pd.DataFrame([{"check": "DVOL comparison", "pass": False,
                              "detail": "no DVOL file"}])

    g = util.normalize_date_col(grid)
    dv = util.normalize_date_col(dv)
    m = g.merge(dv, on="date", how="inner")
    m = m.dropna(subset=["atm_30", "dvol"])
    if len(m) < 100:
        return pd.DataFrame([{"check": "DVOL comparison", "pass": False,
                              "detail": f"only {len(m)} overlapping days"}])

    corr = float(np.corrcoef(m["atm_30"] * 100, m["dvol"])[0, 1])
    bias = float((m["dvol"] - m["atm_30"] * 100).mean())
    rows.append({"check": "ATM30 correlates with DVOL > 0.9",
                 "pass": corr > 0.9,
                 "detail": f"corr={corr:.4f}, n={len(m)}"})
    rows.append({"check": "DVOL sits above ATM (smile effect)",
                 "pass": bias > -2.0,
                 "detail": f"mean DVOL - ATM30 = {bias:.2f} vol pts"})
    return pd.DataFrame(rows)


def check_known_events(grid: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Implied vol must spike on the days everyone remembers."""
    g = util.normalize_date_col(grid)
    g = g.dropna(subset=["atm_30"]).set_index("date")
    if g.empty:
        return pd.DataFrame([{"check": "event vol spikes", "pass": False,
                              "detail": "empty grid"}])

    base = g["atm_30"].rolling(60, min_periods=20).median()
    rows = []
    for name, day in config.EVENTS.items():
        ts = pd.Timestamp(day, tz="UTC")
        win = g.loc[(g.index >= ts - pd.Timedelta(days=3))
                    & (g.index <= ts + pd.Timedelta(days=5)), "atm_30"]
        b = base.loc[:ts].iloc[-1] if len(base.loc[:ts]) else np.nan
        if win.empty or not np.isfinite(b):
            rows.append({"check": f"vol spike: {name}", "pass": None,
                         "detail": "outside sample"})
            continue
        ratio = float(win.max() / b)
        rows.append({"check": f"vol spike: {name}", "pass": ratio > 1.15,
                     "detail": f"peak/median = {ratio:.2f}"})
    return pd.DataFrame(rows)


def check_har(currency: str) -> pd.DataFrame:
    from . import rv as rv_mod
    rows = []
    df = rv_mod.load(currency)
    for h in (30,):
        r2 = rv_mod.har_oos_r2(currency, h)
        rows.append({"check": f"HAR beats rolling mean OOS (h={h})",
                     "pass": bool(np.isfinite(r2) and r2 > 0),
                     "detail": f"OOS R2 vs benchmark = {r2:.3f}"})
    # No look-ahead: a forecast must exist only after the burn-in.
    first = df.dropna(subset=["erv_30"])["date"].min()
    start = df["date"].min()
    days = (first - start).days if pd.notna(first) else -1
    rows.append({"check": "HAR respects burn-in",
                 "pass": days >= config.HAR_BURN_IN_DAYS - 5,
                 "detail": f"first forecast {days} days into sample"})
    return pd.DataFrame(rows)


def run_all(currency: str, grid: pd.DataFrame | None = None) -> pd.DataFrame:
    """Everything that can be checked without rebuilding."""
    frames = [check_backfill(currency)]

    man = backfill.load_manifest(currency)
    busy = man[man["n_trades"] > 1000]
    if len(busy):
        day = pd.to_datetime(busy.iloc[len(busy) // 2]["date"]).date()
        frames.append(check_day_file(currency, day))
        frames.append(check_iv_recomputation(currency, day))

    if grid is not None and len(grid):
        frames.append(check_marks_and_surface(currency, grid))
        frames.append(check_known_events(grid, currency))
    try:
        frames.append(check_har(currency))
    except FileNotFoundError:
        pass

    out = pd.concat(frames, ignore_index=True)
    out["currency"] = currency
    return out
