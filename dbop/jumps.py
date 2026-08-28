"""Separating jump variance from diffusive variance, by day type.

Section 7 of the weekend paper faces the obvious referee objection: options are
priced under the risk-neutral measure, so an implied weekend discount smaller
than the realized one need not be an error. If weekend returns carry more jump
risk, and jump risk earns a premium, the market is right to discount the weekend
by less than realized variance alone suggests.

Testing that requires splitting realized variance into its continuous and jump
parts *within each regime*, because only the jump part can carry a jump premium.
Write the risk-neutral variance a dealer would charge for a day of type g as

    v*_g(kappa) = c_g + kappa * j_g

with c the continuous (diffusive) component, j the jump component and kappa >= 1
the multiple at which jump variance is priced above its physical value. The
observable prediction is a weekend/weekday ratio

    R*(kappa) = (c_we + kappa * j_we) / (c_wd + kappa * j_wd)

which starts at the realized ratio when kappa = 1 and moves monotonically toward
the *jump-variance ratio* j_we / j_wd as kappa grows without bound. That limit is
the sharp part: no jump-risk premium of any size can move the priced weekend
ratio past j_we / j_wd, so an implied ratio beyond it cannot be rationalized by
jump compensation at all. Where the implied ratio does lie inside the reachable
interval, inverting R* gives the premium the market would have to be charging,
which can then be judged against the equity-index estimates in the literature.

Note what this construction deliberately cannot do: a risk premium applied
*proportionally* to all calendar time cancels out of the ratio entirely. Scaling
both c and j by a common factor leaves R* unchanged. Only a premium that loads
differently on weekend and weekday time can explain a gap measured in ratios,
which is why the decomposition has to be by day type and not by asset.

Estimator choices follow the standard practice. The jump part is what a
truncated realized variance discards: returns above ``c`` local standard
deviations are treated as jumps, with the local scale taken from that day's own
bipower variation so a quieter weekend is not mechanically classified as
jump-free. A time-of-day factor is estimated separately for each regime, from
within-slot medians rather than means so that the jumps being measured do not
inflate the threshold meant to detect them.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)

# Truncation level in local standard deviations. Three is the usual choice: high
# enough that ordinary diffusive moves survive, low enough that the estimator
# still has power at 5-minute sampling.
TRUNC_C = 3.0

# Days with fewer usable returns than this are dropped: bipower variation and
# the truncation threshold both need a reasonable count, and a day that has lost
# most of its bars has lost them non-randomly (feed outages cluster on volatile
# days). A full day is 288 five-minute bars, and the floor scales with the
# sampling interval.
MIN_BARS_PER_DAY = 144


def min_bars_for(step_minutes: int) -> int:
    return max(8, int(MIN_BARS_PER_DAY * config.BAR_MINUTES / step_minutes))


# Gaussian scale factor: E|Z| = sqrt(2/pi), so mean absolute return times this
# recovers a standard deviation.
_MU1 = np.sqrt(2.0 / np.pi)


def resample(b: pd.DataFrame, step_minutes: int) -> pd.DataFrame:
    """Thin a 5-minute bar frame onto a coarser grid of closes.

    Sampling every k-th bar rather than aggregating is the right operation here:
    realized variance is built from the price at each grid point, and the closes
    already are those prices. Bars whose timestamp is not on the coarse grid are
    dropped, which also drops any partial bar left by a feed gap.
    """
    ts = pd.to_datetime(b["ts"], utc=True)
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute
    keep = (minute_of_day % step_minutes) == 0
    return pd.DataFrame({"ts": ts[keep].to_numpy(),
                         "close": b["close"].to_numpy()[keep.to_numpy()]})


def contiguous_returns(b: pd.DataFrame,
                       step_minutes: int | None = None) -> pd.DataFrame:
    """Log returns that genuinely span one sampling interval.

    A bar following a gap in the series carries a multi-period return under a
    one-interval label, which inflates both the tail counts and the jump
    component; those are exactly the observations this test must not confuse
    with real jumps, so anything not following its predecessor by one step is
    dropped rather than kept and winsorized.
    """
    step_minutes = step_minutes or config.BAR_MINUTES
    d = pd.DataFrame({"ts": pd.to_datetime(b["ts"], utc=True)})
    d["r"] = np.log(b["close"].astype("float64")).diff()
    d = d.dropna(subset=["r"]).reset_index(drop=True)
    step = pd.Timedelta(minutes=step_minutes)
    d = d[d["ts"].diff() == step].reset_index(drop=True)
    d["date"] = d["ts"].dt.normalize()
    d["is_weekend"] = d["ts"].dt.dayofweek >= 5
    # Slot within the UTC day, used for the intraday seasonality factor.
    d["slot"] = ((d["ts"].dt.hour * 60 + d["ts"].dt.minute)
                 // step_minutes).astype("int16")
    return d


def _day_scale(d: pd.DataFrame) -> pd.DataFrame:
    """Per-day bar count, realized variance and bipower variation.

    Bipower pairs are taken within the UTC day only. Crypto has no session
    boundary so the cross-midnight pair is perfectly well defined, but it is the
    one pair that can straddle a change of regime, and at 288 bars a day the
    cost of dropping it is nil.
    """
    r = d["r"].to_numpy()
    same_day = d["date"].to_numpy()[1:] == d["date"].to_numpy()[:-1]
    prod = np.zeros(len(d))
    prod[1:] = np.where(same_day, np.abs(r[1:] * r[:-1]), 0.0)
    d = d.assign(_bp=prod, _r2=r ** 2)
    g = d.groupby("date")
    out = pd.DataFrame({
        "n": g["_r2"].size(),
        "rv": g["_r2"].sum(),
        "bp_sum": g["_bp"].sum(),
    })
    # Barndorff-Nielsen and Shephard's estimator, with the usual finite-sample
    # correction for the n-1 available pairs.
    out["bpv"] = (np.pi / 2.0) * out["bp_sum"] * out["n"] / (out["n"] - 1).clip(lower=1)
    out["is_weekend"] = out.index.dayofweek >= 5
    return out.drop(columns=["bp_sum"])


def tod_factor(d: pd.DataFrame, day: pd.DataFrame,
               by_regime: bool = True) -> pd.Series:
    """Intraday volatility seasonality, normalized to unit mean square.

    Estimated from within-slot medians of |r| standardized by that day's own
    diffusive scale, so a handful of large moves in one slot cannot raise the
    threshold that is supposed to catch them.

    Estimated separately for weekdays and weekends by default. The two regimes
    need not share an intraday shape -- the weekend has no traditional market
    open to peak around -- and imposing the weekday shape on the weekend would
    put the thresholds in the wrong places on exactly the days the result turns
    on.
    """
    scale = np.sqrt((day["bpv"] / day["n"]).clip(lower=1e-24))
    z = (d["r"].abs().to_numpy()
         / scale.reindex(d["date"]).to_numpy())
    w = pd.DataFrame({"slot": d["slot"].to_numpy(),
                      "regime": d["is_weekend"].to_numpy(), "z": z})
    keys = ["regime", "slot"] if by_regime else ["slot"]
    f = w.groupby(keys)["z"].median() / _MU1
    # A series whose prices are stale most of the time has a within-slot median
    # absolute return of exactly zero, which sends the normalizer to zero and
    # every threshold to NaN -- silently classifying nothing as a jump. PAXG's
    # perpetual, at 88% unchanged closes on a weekend five-minute grid, does
    # this. Fall back to a flat factor and let the caller see it in the log
    # rather than return a factor that disables the estimator.
    if not np.isfinite(f.to_numpy()).all() or (f.to_numpy() <= 0).any():
        log.warning("intraday factor degenerate (stale prices); using a flat "
                    "factor for %d slots", int(len(f)))
        return pd.Series(1.0, index=f.index, name="tod")
    # Normalize within each regime so that the mean square factor is one; the
    # level belongs to bpv, this carries only the shape.
    if by_regime:
        norm = (f ** 2).groupby(level="regime").mean() ** 0.5
        f = f / norm.reindex(f.index.get_level_values("regime")).to_numpy()
    else:
        f = f / np.sqrt(float((f ** 2).mean()))
    return f.rename("tod")


def decompose(b: pd.DataFrame, c: float = TRUNC_C, use_tod: bool = True,
              min_bars: int | None = None,
              step_minutes: int | None = None) -> pd.DataFrame:
    """Per-day continuous and jump variance from a bar frame.

    Returns one row per UTC day with the day's realized variance ``rv``, its
    truncated (continuous) part ``trv``, the jump residual ``jv``, and the count
    of returns classified as jumps.

    ``step_minutes`` coarsens the sampling grid. Jump identification weakens as
    the interval grows -- a jump and a run of diffusive moves become harder to
    tell apart -- so the coarse grids are a robustness check against price
    staleness rather than a better estimator.
    """
    step_minutes = step_minutes or config.BAR_MINUTES
    if min_bars is None:
        min_bars = min_bars_for(step_minutes)
    if step_minutes != config.BAR_MINUTES:
        b = resample(b, step_minutes)
    d = contiguous_returns(b, step_minutes)
    day = _day_scale(d)
    day = day[day["n"] >= min_bars]
    d = d[d["date"].isin(day.index)].copy()

    scale = np.sqrt((day["bpv"] / day["n"]).clip(lower=1e-24))
    thresh = c * scale.reindex(d["date"]).to_numpy()
    if use_tod:
        f = tod_factor(d, day)
        key = pd.MultiIndex.from_arrays([d["is_weekend"].to_numpy(),
                                         d["slot"].to_numpy()],
                                        names=["regime", "slot"])
        thresh = thresh * f.reindex(key).to_numpy()

    r = d["r"].to_numpy()
    is_jump = np.abs(r) > thresh
    d = d.assign(_cont=np.where(is_jump, 0.0, r ** 2), _jump=is_jump.astype(int))
    g = d.groupby("date")
    out = day.join(pd.DataFrame({"trv": g["_cont"].sum(),
                                 "n_jumps": g["_jump"].sum()}))
    # A jump component is a sum of squares and cannot be negative; truncation
    # only ever removes mass, so this clip is a guard against float noise rather
    # than a substantive choice.
    out["jv"] = (out["rv"] - out["trv"]).clip(lower=0.0)
    out["jump_share"] = out["jv"] / out["rv"].where(out["rv"] > 0)
    return out.reset_index()


def regime_means(day: pd.DataFrame) -> dict:
    """Mean continuous and jump variance on weekdays and at weekends.

    Means, not medians, because an option prices the expectation: the whole
    point of a jump component is that it is concentrated in a few days, and any
    robust central measure would define it away.
    """
    out = {}
    we = day["is_weekend"].to_numpy()
    # Positional masks: the bootstrap hands this function a frame with
    # duplicated index labels, and label-based boolean selection is ambiguous
    # there.
    for label, mask in (("wd", ~we), ("we", we)):
        s = day[mask]
        out[f"v_{label}"] = float(s["rv"].mean())
        out[f"c_{label}"] = float(s["trv"].mean())
        out[f"j_{label}"] = float(s["jv"].mean())
        out[f"n_{label}"] = int(len(s))
        out[f"jump_share_{label}"] = float(s["jv"].sum() / s["rv"].sum())
    out["realized_ratio"] = out["v_we"] / out["v_wd"]
    out["cont_ratio"] = out["c_we"] / out["c_wd"]
    out["jump_ratio"] = (out["j_we"] / out["j_wd"] if out["j_wd"] > 0
                         else float("nan"))
    return out


def signature(b: pd.DataFrame,
              steps: tuple[int, ...] = (5, 15, 30, 60, 120, 240)) -> pd.DataFrame:
    """Weekend variance ratio as a function of the sampling interval.

    The realized side of the whole paper is a ratio of mean daily realized
    variance across day types, measured on a five-minute grid. That grid is only
    innocent if prices actually move on it. When a book is thin the close
    repeats, the return is recorded as zero, and realized variance is biased
    down -- by more in the regime where trading is thinner, which is the
    weekend. The bias therefore does not cancel in the ratio.

    Reading the ratio across sampling intervals is the standard diagnostic: a
    ratio that is flat in the interval is not being driven by staleness, and one
    that drifts is. The share of exactly-zero returns is reported alongside as
    the direct measure of the problem.

    This lives here rather than in ``weekend`` because it is built from the same
    resampling and day-scaling machinery as the jump decomposition, and the two
    have to agree bar for bar for the horse race to mean anything.
    """
    rows = []
    for q in steps:
        bb = b if q == config.BAR_MINUTES else resample(b, q)
        d = contiguous_returns(bb, q)
        if d.empty:
            continue
        day = _day_scale(d)
        day = day[day["n"] >= min_bars_for(q)]
        if day.empty or day["is_weekend"].nunique() < 2:
            continue
        we = day["is_weekend"].to_numpy()
        a, c_ = day["rv"].to_numpy()[~we], day["rv"].to_numpy()[we]
        ma, mc = float(a.mean()), float(c_.mean())
        va, vc = float(a.var(ddof=1) / len(a)), float(c_.var(ddof=1) / len(c_))
        # Delta method on a ratio of two independent means.
        se = float(np.sqrt(vc / ma ** 2 + va * mc ** 2 / ma ** 4))
        zr = d.groupby("is_weekend")["r"].apply(lambda s: float((s == 0).mean()))
        rows.append({"step_minutes": q, "n_days": int(len(day)),
                     "n_wd": int((~we).sum()), "n_we": int(we.sum()),
                     "var_weekday": ma, "var_weekend": mc,
                     "variance_ratio": mc / ma, "se_ratio": se,
                     "zero_share_wd": float(zr.get(False, np.nan)),
                     "zero_share_we": float(zr.get(True, np.nan))})
    return pd.DataFrame(rows)


def ratio_at_kappa(m: dict, kappa: float | np.ndarray):
    """Weekend/weekday variance ratio when jump variance is priced at ``kappa``.

    ``kappa = 1`` reproduces the realized ratio; ``kappa = 0`` gives the purely
    diffusive ratio; the limit as kappa grows is ``jump_ratio``.
    """
    k = np.asarray(kappa, dtype="float64")
    return ((m["c_we"] + k * m["j_we"]) / (m["c_wd"] + k * m["j_wd"]))


def reachable_interval(m: dict) -> tuple[float, float]:
    """The set of weekend ratios a jump premium of kappa >= 1 can produce.

    R*(kappa) is a Mobius function of kappa and therefore monotone, so the
    reachable set is the interval between its value at kappa = 1 (the realized
    ratio) and its limit (the jump ratio). Anything outside needs an explanation
    other than jump compensation, whatever the size of the premium.
    """
    a, b = m["realized_ratio"], m["jump_ratio"]
    return (min(a, b), max(a, b))


def required_kappa(m: dict, target_ratio: float) -> float:
    """The jump premium multiple that would reproduce ``target_ratio``.

    Solving (c_we + k j_we) = R (c_wd + k j_wd) for k. Returns NaN when the
    target lies outside the reachable interval -- that is the informative
    outcome, not a failure, and it must not be reported as a large finite
    premium by letting the algebra return the root on the wrong branch.
    """
    lo, hi = reachable_interval(m)
    if not (lo <= target_ratio <= hi):
        return float("nan")
    den = m["j_we"] - target_ratio * m["j_wd"]
    if abs(den) < 1e-18:
        return float("nan")
    k = (target_ratio * m["c_wd"] - m["c_we"]) / den
    return float(k) if np.isfinite(k) and k >= 0 else float("nan")


def week_blocks(day: pd.DataFrame) -> np.ndarray:
    """Block labels for the bootstrap: one block per ISO week.

    Resampling individual days would break the weekday/weekend pairing that the
    ratio is built from and understate its sampling error. A week is the
    smallest block containing a complete instance of the pattern.
    """
    dates = pd.to_datetime(day["date"] if "date" in day else day.index, utc=True)
    iso = dates.dt.isocalendar()
    return (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()


def bootstrap(day: pd.DataFrame, target_ratio: float, target_se: float = 0.0,
              n_boot: int = 2000, seed: int = 0) -> dict:
    """Block-bootstrap CIs for the jump ratio and the required premium.

    Whole weeks are resampled with replacement. When ``target_se`` is given, the
    implied ratio is redrawn from its own normal sampling distribution on each
    replication, so the reported interval for the required premium carries the
    uncertainty of both sides rather than treating the fitted implied ratio as a
    known constant.
    """
    rng = np.random.default_rng(seed)
    blocks = week_blocks(day)
    uniq, inv = np.unique(blocks, return_inverse=True)
    idx_by_block = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    jr, kk, reach = [], [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        rows = np.concatenate([idx_by_block[p] for p in pick])
        s = day.iloc[rows]
        if not s["is_weekend"].any() or s["is_weekend"].all():
            continue
        m = regime_means(s)
        if not np.isfinite(m["jump_ratio"]):
            continue
        tgt = (target_ratio if target_se <= 0
               else float(rng.normal(target_ratio, target_se)))
        lo, hi = reachable_interval(m)
        jr.append(m["jump_ratio"])
        reach.append(lo <= tgt <= hi)
        kk.append(required_kappa(m, tgt))
    jr = np.asarray(jr)
    kk = np.asarray(kk, dtype="float64")
    fin = kk[np.isfinite(kk)]
    return {
        "jump_ratio_lo": float(np.percentile(jr, 2.5)) if len(jr) else np.nan,
        "jump_ratio_hi": float(np.percentile(jr, 97.5)) if len(jr) else np.nan,
        "p_reachable": float(np.mean(reach)) if reach else np.nan,
        "kappa_lo": float(np.percentile(fin, 2.5)) if len(fin) else np.nan,
        "kappa_hi": float(np.percentile(fin, 97.5)) if len(fin) else np.nan,
        "n_boot": int(len(jr)),
    }
