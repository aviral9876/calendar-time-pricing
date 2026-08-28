"""Why do the wings discount the weekend harder than the money?

Section 7's smile test found that the far wings of every book price weekend
variance below the at-the-money contracts of the same book on the same day. It
was built to falsify the jump-premium reading and does, since a jump premium
would push the wings the other way. It does not say what the wings are doing
instead. This script asks that, and in the course of asking it finds the
original estimate was pooled across maturities in a way that flattered it.

**The mechanism, stated so it can be bounded.** A smile is a function of
moneyness measured in standard deviations, and the weekend clock changes how
many standard deviations a given strike is. Write the total variance to expiry
as V(w), falling in the weekend fraction w, and the surface as

    iv^2(x) = (V/T) * G(x / V^{(1-theta)/2})

with x log-moneyness and G the smile shape. Theta says what the market's
moneyness metric is pinned to:

*   **theta = 0** -- the smile is a function of standardized moneyness. A
    contract spanning a weekend has less variance, so a fixed strike is further
    out in standard deviations and earns a *larger* relative wing markup, which
    partly offsets the fall in its level. At fixed delta the relative weekend
    effect is then identical at every delta and there is no wing effect at all.

*   **theta = 1** -- the relative smile is pinned to the strike. The markup does
    not grow when the clock shortens, so at fixed delta a weekend-heavy contract
    sits at a smaller absolute moneyness, collects a smaller markup, and its
    squared implied vol falls by more than its level does.

The second case has a hard ceiling, and that is what makes this a test rather
than a story. With eta the smile's elasticity in the wing, the amplification of
the far wing's relative weekend slope over the at-the-money one is

    A = [1 - eta (1 - theta) / 2] / [1 - eta / 2]

so A = 1 at theta = 0 and A = 1 / (1 - eta/2) at theta = 1, and nothing in the
family reaches past that. An amplification beyond the ceiling would not be
geometry at all and would have to be a belief about the shape of weekend
returns. Eta is measured inside each day and expiry rather than assumed; the
wing region is selected by standardizing against the *cell's* own at-the-money
level, never against the contract's own implied vol, because at a given strike
only the low implied vols are far enough out to qualify and selecting on delta
therefore steepens the measured smile by about 0.15.

**A route that does not work, kept so it is not tried again.** Theta also equals
the ratio of two coefficients from a fitted smile -- how the curvature responds
to the weekend fraction over how the level does -- which looks like a cleaner
estimator that needs no bucketing. It is not one. A real smile is not a
parabola, so the curvature of a quadratic fitted to it is mostly a statement
about how wide a strike range it was fitted over: the correlation between log
curvature and log span is -0.74, and the implied theta swings from -0.27 to
-5.43 across quartiles of span while the level coefficient changes sign. The
strike range moves with the weekend fraction, and no polynomial control in span
fixes it. The estimator is computed anyway, with and without that control, so
the gap between them is on the record.

**Identification, which turns out to matter more than the mechanism.** The
paper's design compares contracts quoted at the same instant with different
weekend exposure. Day fixed effects do not enforce that: within a trade day the
weekend fraction of a *single* expiry also drifts with the clock as the day
passes, and for contracts expiring within a day that drift is most of the
variation there is. The baseline here therefore replaces each trade's weekend
fraction with its (day, expiry) mean, which leaves only differences between
expiries quoted on the same day -- the variation the design claims. It is
reported alongside the unpurged version, and the diagnostic that motivates it is
printed as a table.

Outputs: w22 (amplification and theta by maturity), w23 (smile shape),
w25 (identification diagnostic). Nothing in the paper rests on w24 -- the
anatomy splits by wing side, expiry thickness and expiry weekday -- and it costs
more than the rest of the script put together, so it runs only under --anatomy.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import config

log = logging.getLogger("weekend_wings")

# Distance from the money in delta terms, as in section 7.
ATM_BINS = (0.02, 0.10, 0.20, 0.35, 0.50)
ATM_LABELS = ("far wing", "wing", "near", "at the money")

# Maturity bands. Reported separately rather than pooled because the wing effect
# turns out to differ across them by more than an order of magnitude, and
# because the band under one day is the one whose identification does not hold
# up.
BANDS = ((0.25, 1.0, "under 1d"), (1.0, 3.0, "1-3d"), (3.0, 7.0, "3-7d"),
         (7.0, 14.0, "7-14d"))

# Standard deviations from the money at which the smile elasticity, and so the
# ceiling, is evaluated. Roughly where the far-wing delta bucket lives.
WING_Z = 1.6

CONTROLS = ("logT", "is_call")


def load(currency: str, purge: bool = True) -> pd.DataFrame:
    """The cached smile sample, with the weekend fraction optionally purged of
    its within-expiry (intraday) variation."""
    p = config.PANELS / f"smile_sample_{currency}.parquet"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing; run weekend_riskrace.py once to build the cache")
    d = pd.read_parquet(p)
    d["T"] = np.exp(d["logT"])
    d["upper"] = d["logm"] > 0
    d = d.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["logm", "iv2", "wknd_frac"])
    if purge:
        d["wknd_frac"] = d.groupby(["date", "expiry"],
                                   observed=True)["wknd_frac"].transform("mean")
    return d


def bucketed(d: pd.DataFrame, extra=()) -> dict:
    """Weekend slope per delta bucket, fitted jointly so differences have a s.e.

    One block per bucket, every coefficient bucket-specific, squared implied vol
    scaled by its own bucket mean so the slopes are relative weekend effects and
    comparable across buckets quoting different variance levels. The design is
    block diagonal, so it is fitted a block at a time and only the per-day score
    vectors are stacked -- the point estimates are those of separate fits and
    the joint form supplies only the covariance the contrast needs.
    """
    d = d.assign(_b=pd.cut(d["atmness"], ATM_BINS, labels=ATM_LABELS,
                           include_lowest=True))
    d = d[d["_b"].notna()]
    ctl = ["atmness"] + list(CONTROLS) + list(extra)
    k, p = len(ATM_LABELS), 3 + len(ctl)
    days = np.sort(d["date"].unique())
    day_ix = pd.Series(np.arange(len(days)), index=days)
    G = len(days)
    scores = np.zeros((G, k * p))
    breads, betas, counts, means = [], [], [], []
    for j, lab in enumerate(ATM_LABELS):
        s = d[d["_b"] == lab]
        if len(s) < 2000:
            return {}
        means.append(float(s["iv2"].mean()))
        cols = ["y", "wknd_frac"] + ctl
        f = pd.DataFrame({"y": s["iv2"].to_numpy() / means[-1],
                          "wknd_frac": s["wknd_frac"].to_numpy(),
                          **{c: s[c].to_numpy(dtype="float64") for c in ctl},
                          "date": s["date"].to_numpy()})
        dm = f[cols] - f.groupby("date")[cols].transform("mean")
        X = np.column_stack([dm["wknd_frac"]] + [dm[c] for c in ctl]
                            + [dm["logT"] ** 2, dm["logT"] ** 3])
        y = dm["y"].to_numpy()
        XtX = X.T @ X
        # Pseudo-inverse throughout: the polynomial maturity terms go singular
        # whenever a subsample carries only a handful of distinct expiries, and
        # the weekend coefficient is not part of that collinearity.
        inv = np.linalg.pinv(XtX)
        beta = inv @ (X.T @ y)
        r = y - X @ beta
        gi = day_ix.reindex(f["date"].to_numpy()).to_numpy()
        for c in range(p):
            scores[:, j * p + c] = np.bincount(gi, weights=X[:, c] * r,
                                               minlength=G)
        breads.append(inv)
        betas.append(beta)
        counts.append(len(s))
    beta = np.concatenate(betas)
    bread = np.zeros((k * p, k * p))
    for j, b in enumerate(breads):
        bread[j * p:(j + 1) * p, j * p:(j + 1) * p] = b
    cov = bread @ (scores.T @ scores) @ bread * (G / max(G - 1, 1))
    ix = [j * p for j in range(k)]
    jw, ja = ATM_LABELS.index("far wing"), ATM_LABELS.index("at the money")
    bw, ba = float(beta[ix[jw]]), float(beta[ix[ja]])

    out = {"n": int(sum(counts)), "n_days": G,
           **{f"slope_{ATM_LABELS[j].replace(' ', '_')}": float(beta[ix[j]])
              for j in range(k)},
           **{f"iv2_{ATM_LABELS[j].replace(' ', '_')}": means[j]
              for j in range(k)}}
    if not (bw / ba > 0):
        # A bucket slope that has crossed zero makes the ratio meaningless;
        # returning NaN is the honest outcome and happens at long maturities
        # where the weekend fraction barely varies.
        out.update(amp=np.nan, log_amp=np.nan, log_amp_se=np.nan,
                   amp_bound=means[jw] / means[ja], theta=np.nan, theta_se=np.nan)
        return out
    # Amplification in logs: the model's prediction is multiplicative, and both
    # slopes are safely negative where this is reported.
    g = np.zeros(k * p)
    g[ix[jw]], g[ix[ja]] = 1.0 / bw, -1.0 / ba
    log_amp = float(np.log(bw / ba))
    log_amp_se = float(np.sqrt(g @ cov @ g))
    # The parabola shortcut on the ceiling, kept only as a reference point: for
    # a quadratic smile it equals 1/(1 - eta/2), and the gap between the two is
    # a measure of how far from quadratic the real wing is.
    out.update(amp=float(np.exp(log_amp)), log_amp=log_amp,
               log_amp_se=log_amp_se,
               amp_bound_quadratic=float(means[jw] / means[ja]),
               t=log_amp / log_amp_se if log_amp_se else np.nan)
    return out


def with_ceiling(row: dict) -> dict:
    """Attach theta and the two point tests, given a measured elasticity.

    Solving the model for theta rather than reading it off a log ratio. With
    amplification A and smile elasticity eta,

        A = [1 - eta (1 - theta) / 2] / [1 - eta / 2]   so   theta = (A - 1)(2 - eta) / eta

    which is exact and reduces to the two endpoints: A = 1 gives theta = 0, and
    A = 1 / (1 - eta/2) -- the ceiling -- gives theta = 1. The log-ratio version
    is a decent approximation and a needless one.
    """
    eta = row.get("eta", np.nan)
    A = row.get("amp", np.nan)
    if not (np.isfinite(eta) and 0 < eta < 2 and np.isfinite(A) and A > 0):
        return row
    se_A = A * row["log_amp_se"]                    # delta method off log A
    k = (2.0 - eta) / eta
    lc = np.log(row["ceiling"])
    row = dict(row)
    row.update(theta=(A - 1.0) * k, theta_se=se_A * k,
               t_vs_ceiling=(row["log_amp"] - lc) / row["log_amp_se"],
               p_theta0=float(2 * (1 - stats.norm.cdf(
                   abs(row["log_amp"] / row["log_amp_se"])))),
               p_theta1=float(2 * (1 - stats.norm.cdf(
                   abs((row["log_amp"] - lc) / row["log_amp_se"])))))
    return row


def elasticity(d: pd.DataFrame) -> dict:
    """The smile's elasticity in the wing region, and the ceiling it implies.

    eta = d ln iv^2 / d ln|log-moneyness|, measured inside (day, expiry) cells
    so that it is the shape of one smile at one instant rather than a mixture
    across days. The largest amplification a theta = 1 market can produce is
    1 / (1 - eta/2).

    Measured rather than inferred. The ratio of squared implied vols between two
    buckets gives the same number for a parabola, but a real smile is steeper
    than a parabola in the wings, and the whole force of the ceiling comes from
    it not being an assumption.
    """
    # The wing region has to be selected on something the contract's own
    # implied vol does not enter. Selecting on delta looks natural and is wrong:
    # at a given strike only the *low* implied vols are far enough out to
    # qualify, so the selected sample slopes upward in moneyness for a reason
    # that has nothing to do with the smile, and eta comes back too steep. The
    # cell's own at-the-money level is a level, not a contract quantity, so
    # standardizing by it leaves the selection exogenous.
    d = d[d["logm"].abs() > 1e-4].copy()
    cell = pd.factorize(d["date"].astype("int64").astype(str) + "|"
                        + d["expiry"].astype(str))[0]
    d["_c"] = cell
    near = d[d["atmness"] >= 0.35].groupby("_c")["iv2"].mean()
    scale = np.sqrt(near.reindex(d["_c"]).to_numpy()
                    * np.exp(d["logT"].to_numpy()) / config.YEAR)
    z = np.abs(d["logm"].to_numpy()) / scale
    s = d[np.isfinite(z) & (z > WING_Z)]
    if len(s) < 5000:
        return {}
    cell = pd.factorize(s["_c"])[0]
    y = np.log(s["iv2"].to_numpy())
    x = np.log(s["logm"].abs().to_numpy())
    yd = y - pd.Series(y).groupby(cell).transform("mean").to_numpy()
    xd = x - pd.Series(x).groupby(cell).transform("mean").to_numpy()
    denom = float(xd @ xd)
    if denom < 1e-12:
        return {}
    eta = float((xd @ yd) / denom)
    r = yd - eta * xd
    sc = np.bincount(cell, weights=xd * r, minlength=cell.max() + 1)
    return {"eta": eta, "eta_se": float(np.sqrt(sc @ sc) / denom),
            "ceiling": float(1 / (1 - eta / 2)) if eta < 2 else np.inf,
            "n_wing": int(len(s))}


def identification(currency: str) -> pd.DataFrame:
    """Where the weekend fraction actually varies within a trade day.

    Splits the within-day variance of the weekend fraction into the part that
    comes from different expiries quoted the same day -- what the design
    intends -- and the part that comes from the clock advancing on one expiry,
    which day fixed effects do not remove.
    """
    d = load(currency, purge=False)
    rows = []
    for lo, hi, lab in BANDS:
        s = d[(d["T"] >= lo) & (d["T"] < hi)]
        if len(s) < 3000:
            continue
        w = s["wknd_frac"].to_numpy()
        wd = w - s.groupby("date")["wknd_frac"].transform("mean").to_numpy()
        cell = pd.factorize(s["date"].astype("int64").astype(str) + "|"
                            + s["expiry"].astype(str))[0]
        wc = w - pd.Series(w).groupby(cell).transform("mean").to_numpy()
        tot, resid = float(np.var(wd)), float(np.var(wc))
        rows.append({"asset": currency, "band": lab, "n": int(len(s)),
                     "expiries_per_day": float(
                         s.groupby("date")["expiry"].nunique().mean()),
                     "sd_within_day": float(np.sqrt(tot)),
                     "between_expiry_share": 1 - resid / tot if tot > 0 else np.nan})
    return pd.DataFrame(rows)


def smile_shape(d: pd.DataFrame, min_trades: int = 12,
                min_span: float = 0.04) -> pd.DataFrame:
    """Fit level, skew and curvature per trade day and expiry.

    Squared implied vol on log-moneyness and its square, one fit per (day,
    expiry) cell carrying enough strikes and a wide enough spread of them for a
    curvature to mean anything. Cells whose fitted curvature is not positive are
    dropped and counted: the test below is on its log, and a smile that fits
    concave is noise rather than a flat smile.
    """
    rows = []
    for (day, exp), s in d.groupby(["date", "expiry"], observed=True):
        if len(s) < min_trades:
            continue
        x = s["logm"].to_numpy()
        if x.max() - x.min() < min_span:
            continue
        X = np.column_stack([np.ones_like(x), x, x ** 2])
        try:
            b = np.linalg.lstsq(X, s["iv2"].to_numpy(), rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        rows.append({"date": day, "expiry": exp, "n": len(s), "level": b[0],
                     "skew": b[1], "curv": b[2],
                     "wknd_frac": float(s["wknd_frac"].mean()),
                     "logT": float(s["logT"].mean()),
                     "span": float(x.max() - x.min())})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["ok"] = (out["curv"] > 0) & (out["level"] > 0)
    return out


def shape_test(sh: pd.DataFrame) -> dict:
    """What the weekend fraction does to the level and to the curvature.

    Two within-day regressions on the same cells. The level is the reference and
    should reproduce the weekend discount. The curvature is the test: zero says
    the smile's shape in strike space is untouched by the clock (theta = 1,
    since the relative smile is then pinned to the strike); equal to the level
    coefficient says the whole smile scales down together (theta = 0, the clock
    fully in the smile). Theta is the ratio, estimated with no reference to any
    bucketing.
    """
    s = sh[sh["ok"]].copy()
    if len(s) < 300 or s["date"].nunique() < 60:
        return {}
    s["log_level"] = np.log(s["level"])
    s["log_curv"] = np.log(s["curv"])
    s["log_ratio"] = s["log_curv"] - s["log_level"]
    out = {"n_cells": int(len(s)), "n_days": int(s["date"].nunique()),
           "dropped_concave": int((~sh["ok"]).sum())}
    # Fitted with and without the strike-range control, because the difference
    # between the two is the whole verdict on this estimator. See the note in
    # the module docstring: the curvature of a quadratic fitted to a smile that
    # is not one is mostly a statement about how wide a range it was fitted
    # over, and that range moves with the weekend fraction.
    for name, dep, ctl in (("level", "log_level", True),
                           ("curv", "log_curv", True),
                           ("ratio", "log_ratio", True),
                           ("curv_nospan", "log_curv", False)):
        # Span is a control, not a nuisance to ignore: a real smile is not a
        # parabola, so a quadratic fitted over a narrow range of strikes
        # recovers a different curvature from one fitted over a wide range, and
        # the range narrows with maturity, which correlates with the weekend
        # fraction. Without it the test would read strike coverage as a belief.
        cols = [dep, "wknd_frac", "logT", "span"]
        dm = s[cols] - s.groupby("date")[cols].transform("mean")
        parts = [dm["wknd_frac"], dm["logT"], dm["logT"] ** 2]
        if ctl:
            parts += [dm["span"], dm["span"] ** 2]
        X = np.column_stack(parts)
        y = dm[dep].to_numpy()
        XtX = X.T @ X
        # Pseudo-inverse rather than a solve: inside a narrow maturity band the
        # log-maturity terms are nearly collinear and the normal equations are
        # singular. The coefficient of interest is the weekend fraction, which
        # is not part of that collinearity, so a minimum-norm solution leaves it
        # unchanged where the solve would simply fail.
        inv = np.linalg.pinv(XtX)
        beta = inv @ (X.T @ y)
        r = y - X @ beta
        gi = pd.factorize(s["date"])[0]
        G = gi.max() + 1
        sc = np.column_stack([np.bincount(gi, weights=X[:, j] * r, minlength=G)
                              for j in range(X.shape[1])])
        cov = inv @ (sc.T @ sc) @ inv * (G / max(G - 1, 1))
        se = float(np.sqrt(cov[0, 0]))
        out[f"b_{name}"] = float(beta[0])
        out[f"se_{name}"] = se
        out[f"t_{name}"] = float(beta[0] / se) if se else np.nan
    # In a world where the fitted curvature meant what it looks like, theta would
    # be the ratio of the two coefficients. It is reported, and so is the same
    # coefficient without the strike-range control, because the gap between them
    # is what disqualifies it.
    if abs(out["b_level"]) < 1e-9:
        return out
    out["theta_naive"] = out["b_curv"] / out["b_level"]
    out["theta_naive_nospan"] = out["b_curv_nospan"] / out["b_level"]
    out["span_sensitivity"] = out["b_curv"] - out["b_curv_nospan"]
    return out


def combine(rows: list[tuple[float, float]]) -> tuple[float, float]:
    """Inverse-variance average of log amplifications across assets."""
    a = np.array([r for r in rows if np.isfinite(r[0]) and r[1] > 0])
    if len(a) < 2:
        return np.nan, np.nan
    w = 1.0 / a[:, 1] ** 2
    m = float((a[:, 0] * w).sum() / w.sum())
    return m, float(np.sqrt(1.0 / w.sum()))


def main() -> int:
    ap = argparse.ArgumentParser()
    # Opt-in: the anatomy is two dozen more fits over multi-million-row frames
    # for robustness the paper does not cite, so running it by default would
    # make the pipeline stage several times longer for nothing.
    ap.add_argument("--anatomy", action="store_true",
                    help="also split the wing effect by side, expiry thickness "
                         "and expiry weekday (slow)")
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    # --------------------------------------------- 0. identification diagnostic
    ident = pd.concat([identification(c) for c in config.CURRENCIES],
                      ignore_index=True)
    ident.round(6).to_csv(config.TABLES / "w25_wing_identification.csv",
                          index=False)
    print("\nWhere the weekend fraction varies within a trade day")
    print("=" * 78)
    print(f"  {'asset':>6} {'band':>9} {'expiries/day':>13} {'sd within day':>14} "
          f"{'between-expiry':>15}")
    for _, r in ident.iterrows():
        print(f"  {r['asset']:>6} {r['band']:>9} {r['expiries_per_day']:>13.2f} "
              f"{r['sd_within_day']:>14.4f} {r['between_expiry_share']:>15.3f}")
    print("\n  Only the between-expiry share is the comparison the design")
    print("  claims. Under one day it is a minority of the variation, so the")
    print("  baseline below purges the rest.")

    # ------------------------------------- 1. amplification, pooled and by band
    rows = []
    for c in config.CURRENCIES:
        for purge in (True, False):
            d = load(c, purge=purge)
            r = bucketed(d)
            if r:
                rows.append(with_ceiling({"asset": c, "band": "pooled",
                                          "purged": purge, **r,
                                          **elasticity(d)}))
            if not purge:
                continue
            for lo, hi, lab in BANDS:
                s = d[(d["T"] >= lo) & (d["T"] < hi)]
                r = bucketed(s)
                if r:
                    rows.append(with_ceiling({"asset": c, "band": lab,
                                              "purged": True, **r,
                                              **elasticity(s)}))
    amp = pd.DataFrame(rows)
    amp.round(6).to_csv(config.TABLES / "w22_wing_amplification.csv", index=False)

    print("\nHow much steeper is the wing's weekend slope than the money's?")
    print("=" * 78)
    print("  1.00 = the smile follows the weekend clock exactly (theta = 0).")
    print("  bound = it is pinned to the strike and does not follow (theta = 1).")
    print("  Above the bound is not geometry at all.")
    print(f"\n  {'asset':>6} {'band':>9} {'purged':>7} {'amp':>7} {'bound':>7} "
          f"{'t vs 1':>7} {'theta':>7} {'se':>6}")
    for _, r in amp.iterrows():
        if not np.isfinite(r["amp"]):
            print(f"  {r['asset']:>6} {r['band']:>9} {str(r['purged']):>7} "
                  f"{'--':>7}  (a bucket slope crosses zero)")
            continue
        print(f"  {r['asset']:>6} {r['band']:>9} {str(r['purged']):>7} "
              f"{r['amp']:>7.3f} {r['ceiling']:>7.3f} {r['t']:>+7.2f} "
              f"{r['theta']:>7.3f} {r['theta_se']:>6.3f}")

    print("\n  Combined across the four books, purged. The ceiling here is the")
    print("  measured one, 1/(1 - eta/2), not the parabola shortcut:")
    print(f"  {'band':>9} {'amp':>7} {'t vs 1':>8} {'ceiling':>8} "
          f"{'t vs ceiling':>13} {'eta':>6}")
    for band in ["pooled"] + [b[2] for b in BANDS]:
        s = amp[(amp["band"] == band) & amp["purged"]]
        m, se = combine(list(zip(s["log_amp"], s["log_amp_se"])))
        if not np.isfinite(m):
            continue
        ceil = float(s["ceiling"].mean())
        print(f"  {band:>9} {np.exp(m):>7.3f} {m/se:>+8.2f} {ceil:>8.3f} "
              f"{(m - np.log(ceil)) / se:>+13.2f} {float(s['eta'].mean()):>6.3f}")

    # ------------------------------------------------- 2. the smile shape test
    rows = []
    for c in config.CURRENCIES:
        d = load(c)
        for lab, s in [("pooled", d)] + [(l, d[(d["T"] >= lo) & (d["T"] < hi)])
                                         for lo, hi, l in BANDS]:
            sh = smile_shape(s)
            if sh.empty:
                continue
            t = shape_test(sh)
            if t:
                rows.append({"asset": c, "band": lab, **t})
    shape = pd.DataFrame(rows)
    shape.round(6).to_csv(config.TABLES / "w23_smile_shape.csv", index=False)

    print("\nWhat the weekend fraction does to a fitted smile")
    print("=" * 78)
    print("  The curvature route to theta, and why it is not used: the two")
    print("  right-hand columns are the same coefficient with and without the")
    print("  strike-range control, and they should agree.")
    print(f"  {'asset':>6} {'band':>9} {'cells':>7} {'d ln level':>15} "
          f"{'d ln curv':>15} {'no span ctl':>13} {'theta (naive)':>14}")
    for _, r in shape.iterrows():
        naive = r.get("theta_naive", np.nan)
        print(f"  {r['asset']:>6} {r['band']:>9} {r['n_cells']:>7,} "
              f"{r['b_level']:>+8.3f} (t{r['t_level']:+5.1f}) "
              f"{r['b_curv']:>+9.3f} (t{r['t_curv']:+4.1f}) "
              f"{r.get('b_curv_nospan', np.nan):>+13.3f} {naive:>14.2f}")

    # ------------------------------------------------------- 3. wing anatomy
    if not a.anatomy:
        for f in ("w22_wing_amplification", "w23_smile_shape",
                  "w25_wing_identification"):
            print(f"-> {config.TABLES / (f + '.csv')}")
        print("  (anatomy splits skipped; pass --anatomy to add w24)")
        return 0
    rows = []
    for c in config.CURRENCIES:
        d = load(c)
        splits = [("upper wing (K > F)", d[d["upper"]]),
                  ("lower wing (K < F)", d[~d["upper"]])]
        n_cell = d.groupby(["date", "expiry"], observed=True)["iv2"].transform("size")
        cut = n_cell.median()
        splits += [("thin expiries", d[n_cell <= cut]),
                   ("thick expiries", d[n_cell > cut])]
        for lab, s in splits:
            r = bucketed(s)
            if r:
                rows.append({"asset": c, "split": lab, **r})
        dd = d.assign(**{f"e{k}": (d["expiry_dow"] == k).astype("float64")
                         for k in range(6)})
        r = bucketed(dd, extra=tuple(f"e{k}" for k in range(6)))
        if r:
            rows.append({"asset": c, "split": "expiry-weekday controls", **r})
    anat = pd.DataFrame(rows)
    anat.round(6).to_csv(config.TABLES / "w24_wing_anatomy.csv", index=False)

    print("\nAmplification, split every way the data allows (pooled, purged)")
    print("=" * 78)
    print(f"  {'asset':>6} {'split':>24} {'amp':>7} {'bound':>7} {'t vs 1':>7}")
    for _, r in anat.iterrows():
        if not np.isfinite(r["amp"]):
            continue
        print(f"  {r['asset']:>6} {r['split']:>24} {r['amp']:>7.3f} "
              f"{r['t']:>+7.2f}")

    for f in ("w22_wing_amplification", "w23_smile_shape", "w24_wing_anatomy",
              "w25_wing_identification"):
        print(f"-> {config.TABLES / (f + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
