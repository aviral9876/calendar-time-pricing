"""Why is the market still deepening its weekend discount?

Section 5.5 leaves the paper with a puzzle it states as a contradiction: the
implied weekend discount has fallen for six straight years, and the realized
weekend effect it is supposed to be tracking has not moved at all. A market
drifting away from its own benchmark and not stopping at the right answer needs
an explanation from outside the data -- convention, hedging cost, inventory --
and none of those is testable on a public trade tape.

The contradiction is an artefact of how the realized side is measured. The
benchmark everywhere else in the paper is the ratio of *mean* weekend variance
to *mean* weekday variance, which is the right object for pricing an option: an
option pays off on expected total variance, so arithmetic means are what it
needs. But daily realized variance is violently right-skewed and a handful of
days sets each year's mean. Fitting a line to seven such ratios has almost no
power, and "no significant trend" was read as "no trend".

Measuring the same ratio at the *centre* of the distribution rather than at its
mean reverses the conclusion. This module estimates the weekend ratio at a
ladder of moments, from the arithmetic mean down through trimmed means to the
geometric mean, and asks which of them the market has been tracking.

*   **The realized weekend ratio has been falling, and the paper missed it.**
    At the centre of the distribution it falls at 0.136 log points a year in
    Bitcoin and 0.098 in Ether, at t = -7.5 and -6.3. The flatness of the ratio
    of means is bought entirely in the extreme right tail: trimming the top
    *one per cent* of days from each day type -- three weekend days a year --
    takes Bitcoin's arithmetic trend from -0.062 (t = -1.2) to -0.132
    (t = -4.9). Even
    untrimmed, the arithmetic trend reaches t = -3.3 once the sampling interval
    is coarsened enough to shed microstructure noise.

*   **The market is tracking the centre, not the mean.** The implied ratio falls
    at 0.186 log points a year in Bitcoin and 0.149 in Ether. Against the
    geometric trend the difference is 0.05 a year; against the arithmetic trend
    it is twice that, and at the coarse sampling intervals the implied and
    geometric trends become indistinguishable. In the backward-looking level
    race -- last
    quarter's realized ratio against this quarter's quote, which is what
    "calibration" means -- the attenuation-corrected slope is 1.15 on the
    geometric ratio and 0.48 on the arithmetic one.

So the market is not drifting away from the data. It is tracking the data, and
tracking a statistic of it that is not the one an option pays off on. The wedge
between the two -- weekend variance increasingly concentrated in rare violent
days, which is section 7's fat-tail finding seen from the other side -- has
itself been widening, and that is the level counterpart of section 5.1's
residual gap.

What the cross-section can and cannot do here is worth stating plainly. Solana
and XRP show no trend on either side, but their standard errors are three to
thirteen times the mature books' and their implied trends rest on nine or ten
quarters, so no difference test rejects anything for either book. They neither
confirm the mechanism nor contradict it, and they are reported rather than
leaned on.

Two threats have to be ruled out before any of this is safe, and both are tested
rather than asserted:

*   **Staleness.** A weekend that looks quiet because its prices stopped
    updating would depress measured variance on exactly the ordinary days and
    leave the violent ones alone, producing this whole pattern out of nothing.
    It does not: the geometric trend gets *stronger* as the sampling interval
    coarsens, which is the opposite of what stale prices do, and the zero-return
    share has no upward drift in either mature book.

*   **Attenuation.** In the level horse race a noisier realized measure is
    mechanically less able to explain the implied ratio, and the arithmetic
    ratio is the noisier of the two. Estimates are corrected for that using each
    period's own sampling variance, and reported raw beside corrected. The
    correction is large -- reliability runs 0.47 to 0.61 -- so the corrected
    numbers carry more model than the raw ones and the ranking, not the level,
    is what should be read off them.

Outputs: w26 (trend by moment), w27 (sampling ladder), w28 (trimming ladder and
staleness), w29 (implied trend and the comparison), w30 (mean-to-centre wedge).
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import bars, config, jumps
import weekend_split as split

log = logging.getLogger("weekend_learning")

# Bitcoin and Ether are cut at 2020 for the reason section 5.5 cuts them there:
# before daily expiries the implied slope is not identified, so an earlier start
# would fit a trend to noise on one side of the comparison and to data on the
# other.
START = {"BTC": pd.Timestamp("2020-01-01", tz="UTC"),
         "ETH": pd.Timestamp("2020-01-01", tz="UTC")}

STEPS = (5, 15, 30, 60, 120)
TRIMS = (0.0, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50)
# A day needs this share of its sampling grid present to be used at all. At two
# hours that is seven of twelve returns: loose enough to keep a day with a short
# feed outage, tight enough to drop one that is mostly missing.
MIN_COVERAGE = 0.6


# ---------------------------------------------------------------- estimators

def _fe(keys) -> np.ndarray:
    codes, uniq = pd.factorize(keys)
    D = np.zeros((len(codes), len(uniq)))
    D[np.arange(len(codes)), codes] = 1.0
    return D


def _cluster_cov(X: np.ndarray, resid: np.ndarray, bread: np.ndarray,
                 cluster) -> tuple[np.ndarray, int]:
    codes = pd.factorize(cluster)[0]
    G = int(codes.max()) + 1
    agg = np.zeros((G, X.shape[1]))
    np.add.at(agg, codes, X * resid[:, None])
    return bread @ (agg.T @ agg) @ bread * (G / max(G - 1, 1)), G


def ols_cluster(y: np.ndarray, X: np.ndarray, cluster) -> tuple:
    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ y)
    cov, G = _cluster_cov(X, y - X @ b, np.linalg.inv(XtX), cluster)
    return b, cov, G


def poisson_qmle(y: np.ndarray, X: np.ndarray, cluster,
                 maxit: int = 200, tol: float = 1e-11) -> tuple:
    """Log-link QMLE for the ratio of conditional *means*.

    The estimand is the same one the paper's benchmark uses -- mean weekend
    variance over mean weekday variance -- but fitted multiplicatively, so the
    weekend coefficient is a log ratio and can carry a time interaction. Under a
    log link the Poisson score is (y - mu)x, which is unbiased for the
    conditional mean whatever the true variance function; the quasi-likelihood
    label is doing real work here, because nothing assumes realized variance is
    Poisson, only that its mean is exponential in the covariates.
    """
    b = np.zeros(X.shape[1])
    b[0] = np.log(max(float(y.mean()), 1e-300))
    for _ in range(maxit):
        mu = np.exp(np.clip(X @ b, -60, 60))
        step = np.linalg.solve((X * mu[:, None]).T @ X, X.T @ (y - mu))
        b = b + step
        if np.max(np.abs(step)) < tol:
            break
    mu = np.exp(np.clip(X @ b, -60, 60))
    bread = np.linalg.inv((X * mu[:, None]).T @ X)
    cov, G = _cluster_cov(X, y - mu, bread, cluster)
    return b, cov, G


def ratio_trend(rv: pd.DataFrame, moment: str, fe_unit: str = "month") -> dict:
    """Level and trend of the log weekend/weekday variance ratio.

    The design is a within-period contrast: a fixed effect for every month
    absorbs the volatility cycle entirely, so the weekend coefficient is
    identified only by comparing weekend days against weekday days that sit
    beside them, and the trend interaction asks whether that contrast has been
    widening. Time is centred, which makes the level coefficient the ratio in
    the middle of the sample rather than at an arbitrary origin.

    ``moment`` decides what "the weekend ratio" means. ``arithmetic`` is the
    ratio of means, the object an option prices. ``geometric`` is the ratio of
    geometric means, which is where the centre of a right-skewed distribution
    sits. The two differ only through the tail, and the finding of this module
    is that they have been moving apart.
    """
    date = rv["date"]
    if fe_unit == "month":
        key = date.dt.strftime("%Y-%m").to_numpy()
    elif fe_unit == "week":
        iso = date.dt.isocalendar()
        key = (iso.year * 100 + iso.week).astype(int).astype(str).to_numpy()
    else:
        raise ValueError(fe_unit)
    we = rv["is_weekend"].to_numpy().astype("float64")
    s = ((date - date.min()).dt.total_seconds() / 86400 / 365.25).to_numpy()
    centred = s - s.mean()
    X = np.column_stack([_fe(key), we, we * centred])
    y = rv["rv"].to_numpy()
    # Clustering is on the month whichever fixed effect is used: weekly dummies
    # remove the week's level but not the persistence that runs across weeks
    # inside one volatility episode, and that persistence is exactly what a
    # week-clustered standard error would miss.
    month = date.dt.strftime("%Y-%m").to_numpy()
    if moment == "arithmetic":
        b, cov, G = poisson_qmle(y / y.mean(), X, month)
    elif moment == "geometric":
        b, cov, G = ols_cluster(np.log(y), X, month)
    else:
        raise ValueError(moment)
    lvl, tr = float(b[-2]), float(b[-1])
    se_l, se_t = float(np.sqrt(cov[-2, -2])), float(np.sqrt(cov[-1, -1]))
    t = tr / se_t if se_t > 0 else np.nan
    return {"moment": moment, "n": int(len(rv)), "n_months": G,
            "log_ratio_mid": lvl, "log_ratio_mid_se": se_l,
            "ratio_mid": float(np.exp(lvl)),
            "trend_per_year": tr, "trend_se": se_t, "t": t,
            "p": float(2 * (1 - stats.norm.cdf(abs(t)))) if se_t > 0 else np.nan,
            "span_years": float(s.max() - s.min()),
            "ratio_first": float(np.exp(lvl + tr * (s.min() - s.mean()))),
            "ratio_last": float(np.exp(lvl + tr * (s.max() - s.mean())))}


# ------------------------------------------------------------------- the data

def daily_rv(currency: str, step: int = config.BAR_MINUTES) -> pd.DataFrame:
    """Daily realized variance at a chosen sampling interval.

    Built through ``jumps.contiguous_returns`` rather than by differencing the
    bar series directly, so a return spanning a feed gap is dropped instead of
    recorded as one interval's move. That matters more here than elsewhere:
    this module reads the *shape* of the daily variance distribution, and a
    handful of gap-spanning returns land squarely in the right tail it is
    trying to measure.
    """
    b = bars.load(currency, check=False)
    d = jumps.contiguous_returns(jumps.resample(b, step), step)
    g = d.groupby("date")
    out = pd.DataFrame({
        "rv": g["r"].apply(lambda s: float(np.sum(s.to_numpy() ** 2))),
        "n": g["r"].size(),
        "zero_share": g["r"].apply(lambda s: float(np.mean(s.to_numpy() == 0))),
    }).reset_index()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out = out[(out["n"] >= MIN_COVERAGE * 1440 / step) & (out["rv"] > 0)]
    out["is_weekend"] = out["date"].dt.dayofweek >= 5
    lo = START.get(currency)
    if lo is not None:
        out = out[out["date"] >= lo]
    return out.reset_index(drop=True)


# --------------------------------------------------------------- realized side

def trend_by_moment(rvs: dict) -> pd.DataFrame:
    out = []
    for c in config.CURRENCIES:
        for moment in ("arithmetic", "geometric"):
            out.append({"asset": c, **ratio_trend(rvs[c], moment)})
    return pd.DataFrame(out)


def sampling_ladder(currencies=config.CURRENCIES) -> pd.DataFrame:
    """The staleness test, and the only one that can settle it.

    Stale prices depress measured variance on quiet days and leave violent ones
    alone, which is precisely the pattern this module attributes to economics.
    The two are separable because staleness is a fine-sampling phenomenon: at
    two-hour spacing, a price that failed to update for five minutes has long
    since caught up. If the geometric trend were an artefact of a weekend that
    increasingly stopped printing, it would have to fade as the interval
    coarsens.
    """
    out = []
    for c in currencies:
        for step in STEPS:
            rv = daily_rv(c, step)
            for moment in ("arithmetic", "geometric"):
                out.append({"asset": c, "step_minutes": step,
                            **ratio_trend(rv, moment)})
    return pd.DataFrame(out)


def staleness(rvs: dict) -> pd.DataFrame:
    out = []
    for c in config.CURRENCIES:
        rv = rvs[c]
        for y in sorted(rv["date"].dt.year.unique()):
            s = rv[rv["date"].dt.year == y]
            we, wd = s[s["is_weekend"]], s[~s["is_weekend"]]
            if len(we) < 20 or len(wd) < 40:
                continue
            out.append({"asset": c, "year": int(y),
                        "zero_share_weekend": float(we["zero_share"].mean()),
                        "zero_share_weekday": float(wd["zero_share"].mean()),
                        "n_weekend": int(len(we)), "n_weekday": int(len(wd))})
    return pd.DataFrame(out)


def trimming_ladder(rvs: dict) -> pd.DataFrame:
    """From the mean to the centre, one trim at a time.

    Trimming happens inside (year, day type) cells rather than pooled, because
    a pooled trim would cut mostly weekday days in a year when weekdays were the
    wilder side and would then read as a weekend effect. Cutting the same share
    from each side of the comparison in each year keeps the trim neutral, and
    leaves the ladder measuring one thing only: how far into the tail one has to
    go before the trend appears.
    """
    out = []
    for c in config.CURRENCIES:
        rv = rvs[c]
        rv_v = rv["rv"].to_numpy()
        yr = rv["date"].dt.year.to_numpy()
        we = rv["is_weekend"].to_numpy()
        for q in TRIMS:
            r = rv
            if q > 0:
                keep = np.ones(len(rv), dtype=bool)
                for y in np.unique(yr):
                    for w in (True, False):
                        m = (yr == y) & (we == w)
                        if m.sum() < 20:
                            continue
                        thr = np.quantile(rv_v[m], 1 - q)
                        keep &= ~(m & (rv_v > thr))
                r = rv[keep]
            out.append({"asset": c, "trim": q, "kept": int(len(r)),
                        **ratio_trend(r.reset_index(drop=True), "arithmetic")})
    return pd.DataFrame(out)


def wedge(rvs: dict) -> pd.DataFrame:
    """How far the mean sits above the centre, by day type and year.

    ``log mean - mean log`` is a scale-free measure of right-tail weight: zero
    for a degenerate distribution, half the log variance for a lognormal one.
    If the weekend's has been growing relative to the weekday's then the mean
    and the centre of the weekend distribution are separating, which is the only
    way a falling geometric ratio and a flat arithmetic one can both be true.
    """
    out = []
    for c in config.CURRENCIES:
        rv = rvs[c]
        for y in sorted(rv["date"].dt.year.unique()):
            s = rv[rv["date"].dt.year == y]
            row, ok = {"asset": c, "year": int(y)}, True
            for w, lab in ((True, "weekend"), (False, "weekday")):
                v = s.loc[s["is_weekend"] == w, "rv"].to_numpy()
                if len(v) < 20:
                    ok = False
                    break
                row[f"wedge_{lab}"] = float(np.log(v.mean()) - np.log(v).mean())
                row[f"n_{lab}"] = int(len(v))
            if ok:
                row["wedge_diff"] = row["wedge_weekend"] - row["wedge_weekday"]
                out.append(row)
    return pd.DataFrame(out)


# --------------------------------------------------------------- implied side

def implied_by_period(opt: dict, freq: str = "quarter") -> pd.DataFrame:
    """The implied weekend ratio, fitted period by period.

    Reuses section 5.5's fit unchanged, so both sides of the comparison rest on
    the estimator the paper already reports; only the re-expression in logs is
    new, and that is what puts it in the same units as the realized trends.
    Quarterly rather than annual because Solana and XRP have three calendar
    years between them and a trend needs more points than that.
    """
    out = []
    for c in config.CURRENCIES:
        d = opt[c]
        lo = START.get(c)
        if lo is not None:
            d = d[d["date"] >= lo]
        per = (d["date"].dt.year.astype(str) if freq == "year"
               else d["date"].dt.to_period("Q").astype(str))
        per = np.asarray(per)
        for p in sorted(pd.unique(per)):
            g = d[per == p]
            f = split.fit(g)
            if not f or f["implied_ratio"] <= 0:
                continue
            mid = g["date"].min() + (g["date"].max() - g["date"].min()) / 2
            out.append({"asset": c, "period": str(p), "t_mid": mid, **f,
                        "log_ratio": float(np.log(f["implied_ratio"])),
                        "log_ratio_se": float(f["implied_ratio_se"]
                                              / f["implied_ratio"])})
    return pd.DataFrame(out)


def implied_trend(imp: pd.DataFrame) -> pd.DataFrame:
    out = []
    for c in config.CURRENCIES:
        s = imp[imp["asset"] == c].sort_values("t_mid")
        if len(s) < 4:
            continue
        x = ((s["t_mid"] - s["t_mid"].min()).dt.total_seconds()
             / 86400 / 365.25).to_numpy()
        t = split.wls_trend(x, s["log_ratio"].to_numpy(),
                            s["log_ratio_se"].to_numpy())
        if t:
            out.append({"asset": c, "n_periods": int(len(s)),
                        "trend_per_year": t["slope_per_year"],
                        "trend_se": t["se"], "t": t["t"],
                        "ratio_first": float(np.exp(t["first"])),
                        "ratio_last": float(np.exp(t["last"]))})
    return pd.DataFrame(out)


def compare_ladder(imp_tr: pd.DataFrame, ladder: pd.DataFrame) -> pd.DataFrame:
    """The same comparison at every sampling interval.

    Which interval to believe is not a free choice. Microstructure noise adds a
    roughly constant amount to every day's measured variance, weekend and
    weekday alike, so it pushes a measured ratio toward one -- and pushes it
    further the further the true ratio is from one. As the true ratio falls, the
    bias grows with it, which attenuates any downward trend measured on a fine
    grid. Coarsening the interval shrinks the noise term and removes the
    attenuation, and the ladder carries exactly that signature: both the level
    and the trend move monotonically away from one as the interval grows. The
    coarse estimates are therefore the less biased ones. This table reports the
    comparison against all of them rather than choosing one.
    """
    out = []
    for _, i in imp_tr.iterrows():
        for _, r in ladder[ladder["asset"] == i["asset"]].iterrows():
            diff = float(i["trend_per_year"] - r["trend_per_year"])
            se = float(np.hypot(i["trend_se"], r["trend_se"]))
            t = diff / se if se > 0 else np.nan
            out.append({"asset": i["asset"], "moment": r["moment"],
                        "step_minutes": int(r["step_minutes"]),
                        "implied_trend": float(i["trend_per_year"]),
                        "realized_trend": float(r["trend_per_year"]),
                        "realized_t": float(r["t"]),
                        "difference": diff, "difference_se": se, "t": t,
                        "p": float(2 * (1 - stats.norm.cdf(abs(t))))
                        if se > 0 else np.nan})
    return pd.DataFrame(out)


def compare(imp_tr: pd.DataFrame, real_tr: pd.DataFrame) -> pd.DataFrame:
    """Implied trend against each realized trend, difference and standard error.

    The two sides are estimated on different data -- option quotes and index
    bars -- and are treated as independent when their difference is tested.
    They are not quite: a volatile week moves both. The dependence is positive,
    which makes the reported standard error on the difference conservative for
    the comparison that matters, where the null entertained is that the two
    trends are equal.
    """
    out = []
    for _, i in imp_tr.iterrows():
        for _, r in real_tr[real_tr["asset"] == i["asset"]].iterrows():
            diff = float(i["trend_per_year"] - r["trend_per_year"])
            se = float(np.hypot(i["trend_se"], r["trend_se"]))
            t = diff / se if se > 0 else np.nan
            out.append({"asset": i["asset"], "moment": r["moment"],
                        "implied_trend": float(i["trend_per_year"]),
                        "implied_se": float(i["trend_se"]),
                        "realized_trend": float(r["trend_per_year"]),
                        "realized_se": float(r["trend_se"]),
                        "difference": diff, "difference_se": se, "t": t,
                        "p": float(2 * (1 - stats.norm.cdf(abs(t))))
                        if se > 0 else np.nan})
    return pd.DataFrame(out)


# ------------------------------------------------------- the level horse race

def realized_by_period(rvs: dict, freq: str = "quarter") -> pd.DataFrame:
    """Both weekend ratios, period by period, each with its own standard error.

    The standard errors are what make the horse race below interpretable. The
    arithmetic ratio is the noisier measure of the two by some distance, and a
    noisier regressor explains less of anything for reasons that have nothing to
    do with economics.
    """
    out = []
    for c in config.CURRENCIES:
        rv = rvs[c]
        per = (rv["date"].dt.year.astype(str) if freq == "year"
               else rv["date"].dt.to_period("Q").astype(str))
        per = np.asarray(per)
        for p in sorted(pd.unique(per)):
            s = rv[per == p]
            if (s["is_weekend"].sum() < 12) or ((~s["is_weekend"]).sum() < 25):
                continue
            we = s["is_weekend"].to_numpy().astype("float64")
            X = np.column_stack([np.ones(len(s)), we])
            iso = s["date"].dt.isocalendar()
            wk = (iso.year * 100 + iso.week).astype(int).astype(str).to_numpy()
            y = s["rv"].to_numpy()
            row = {"asset": c, "period": str(p), "n_days": int(len(s))}
            b, cov, _ = poisson_qmle(y / y.mean(), X, wk)
            row["log_arithmetic"] = float(b[1])
            row["log_arithmetic_se"] = float(np.sqrt(cov[1, 1]))
            b, cov, _ = ols_cluster(np.log(y), X, wk)
            row["log_geometric"] = float(b[1])
            row["log_geometric_se"] = float(np.sqrt(cov[1, 1]))
            out.append(row)
    return pd.DataFrame(out)


def horse_race(imp: pd.DataFrame, real: pd.DataFrame,
               lag: int = 0) -> pd.DataFrame:
    """Does the implied ratio move with the mean of realized variance, or its centre?

    One regression per candidate moment, of the log implied weekend ratio on the
    log realized one, with asset fixed effects so the comparison runs within a
    book over time rather than across books. A market pricing the object an
    option pays off on gives a coefficient near one on the arithmetic ratio; a
    market pricing what a quiet weekend usually looks like gives it on the
    geometric one.

    Both are corrected for attenuation. Each period's realized ratio arrives
    with a sampling error whose variance is estimated alongside it, and dividing
    the raw slope by the reliability ratio -- the share of the regressor's
    within-asset variance that is not sampling noise -- removes the mechanical
    advantage the more precisely measured moment would otherwise enjoy. The
    correction inflates both slopes. It is reported because it inflates the
    arithmetic one by more, and the ranking has to survive that.
    """
    out = []
    for moment in ("arithmetic", "geometric"):
        d = imp.merge(real, on=["asset", "period"]).sort_values(
            ["asset", "t_mid"]).copy()
        col = f"log_{moment}"
        if lag:
            d[col] = d.groupby("asset")[col].shift(lag)
        d = d.dropna(subset=["log_ratio", col])
        if len(d) < 8:
            continue
        y = d["log_ratio"].to_numpy()
        x = d[col].to_numpy()
        codes = pd.factorize(d["asset"])[0]
        X = np.column_stack([_fe(codes), x])
        b, cov, G = ols_cluster(y, X, d["asset"].to_numpy())
        beta, se = float(b[-1]), float(np.sqrt(cov[-1, -1]))
        # Reliability: the within-asset variance of the measured regressor, less
        # the average sampling variance that should not be in it.
        xd = x - pd.Series(x).groupby(codes).transform("mean").to_numpy()
        noise = float(np.mean(d[col + "_se"].to_numpy() ** 2))
        var = float(np.var(xd, ddof=1))
        rel = max((var - noise) / var, 1e-6) if var > 0 else np.nan
        out.append({"moment": moment, "lag": lag, "n": int(len(d)),
                    "n_assets": int(G), "beta": beta, "se": se,
                    "t": beta / se if se > 0 else np.nan,
                    "reliability": rel, "beta_corrected": beta / rel,
                    "se_corrected": se / rel,
                    "regressor_sd": float(np.sqrt(var)),
                    "noise_sd": float(np.sqrt(noise))})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", default="quarter", choices=("quarter", "year"))
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    rvs = {c: daily_rv(c) for c in config.CURRENCIES}
    opt = {c: split.load(c) for c in config.CURRENCIES}

    # -- 1. the realized trend, at the mean and at the centre
    tm = trend_by_moment(rvs)
    tm.round(6).to_csv(config.TABLES / "w26_trend_by_moment.csv", index=False)
    print("\nTrend in the realized weekend variance ratio, 2020 onward for the")
    print("mature books, with a fixed effect for every month")
    print("=" * 78)
    print(f"  {'asset':>6} {'moment':>11} {'ratio mid':>10} {'per year':>9} "
          f"{'se':>7} {'t':>7} {'first':>7} {'last':>7}")
    for _, r in tm.iterrows():
        print(f"  {r['asset']:>6} {r['moment']:>11} {r['ratio_mid']:>10.3f} "
              f"{r['trend_per_year']:>+9.4f} {r['trend_se']:>7.4f} "
              f"{r['t']:>+7.2f} {r['ratio_first']:>7.3f} {r['ratio_last']:>7.3f}")
    print("\n  The ratio of means is flat. The ratio of geometric means -- the")
    print("  same days, the same months, the centre of the distribution rather")
    print("  than its mean -- falls hard in the two mature books and in neither")
    print("  of the two young ones.")

    # -- 2. is it staleness?
    lad = sampling_ladder()
    lad.round(6).to_csv(config.TABLES / "w27_sampling_ladder.csv", index=False)
    print("\nThe same trend at coarser sampling. Stale prices are a fine-grid")
    print("phenomenon, so an artefact would fade to the right; this strengthens")
    print("=" * 78)
    geo = lad[lad["moment"] == "geometric"]
    print(f"  {'asset':>6} " + " ".join(f"{s:>14}m" for s in STEPS))
    for c in config.CURRENCIES:
        s = geo[geo["asset"] == c].set_index("step_minutes")
        print(f"  {c:>6} " + " ".join(
            f"{s.loc[k, 'trend_per_year']:>+8.4f}({s.loc[k, 't']:>+5.1f})"
            for k in STEPS))

    st = staleness(rvs)
    st.round(6).to_csv(config.TABLES / "w28_staleness.csv", index=False)
    print("\n  Share of five-minute returns that are exactly zero, weekend vs")
    print("  weekday, by year -- no upward drift in either mature book:")
    for c in config.CURRENCIES:
        s = st[st["asset"] == c]
        print(f"  {c:>6} " + " ".join(
            f"{int(r['year'])}:{r['zero_share_weekend']:>4.1%}/"
            f"{r['zero_share_weekday']:<4.1%}" for _, r in s.iterrows()))

    # -- 3. where in the distribution the two answers separate
    tl = trimming_ladder(rvs)
    tl.round(6).to_csv(config.TABLES / "w28_trimming_ladder.csv", index=False)
    print("\nTrend in the ratio of means, trimming the top q of days from each")
    print("day type within each year: the mean's flatness is bought in the tail")
    print("=" * 78)
    print(f"  {'asset':>6} " + " ".join(f"{q:>13.0%}" for q in TRIMS))
    for c in config.CURRENCIES:
        s = tl[tl["asset"] == c].set_index("trim")
        print(f"  {c:>6} " + " ".join(
            f"{s.loc[q, 'trend_per_year']:>+8.4f}({s.loc[q, 't']:>+4.1f})"
            for q in TRIMS))

    wd = wedge(rvs)
    wd.round(6).to_csv(config.TABLES / "w30_tail_wedge.csv", index=False)
    print("\n  log mean - mean log, weekend minus weekday, by year. This is the")
    print("  gap between the two answers, and it has been widening:")
    for c in config.CURRENCIES:
        s = wd[wd["asset"] == c]
        print(f"  {c:>6} " + " ".join(
            f"{int(r['year'])}:{r['wedge_diff']:>+5.2f}" for _, r in s.iterrows()))

    # -- 4. which of them is the market tracking?
    imp = implied_by_period(opt, a.freq)
    itr = implied_trend(imp)
    cmp_ = compare(itr, tm)
    cl = compare_ladder(itr, lad)
    real = realized_by_period(rvs, a.freq)

    # The three series side by side, one row per asset-year: what the market
    # quoted, and the same weekend ratio measured at the mean and at the centre
    # of the realized distribution. This is the figure's input and the most
    # direct statement of the result, so it is written whatever --freq says.
    by_year = implied_by_period(opt, "year").merge(
        realized_by_period(rvs, "year"), on=["asset", "period"], how="outer")
    by_year["year"] = by_year["period"].astype(int)
    by_year["arithmetic_ratio"] = np.exp(by_year["log_arithmetic"])
    by_year["geometric_ratio"] = np.exp(by_year["log_geometric"])
    by_year.sort_values(["asset", "year"]).round(6).to_csv(
        config.TABLES / "w31_ratio_by_year.csv", index=False)

    races = pd.concat([horse_race(imp, real, lag=lg) for lg in (0, 1)],
                      ignore_index=True)
    pd.concat([itr.assign(table="implied trend"),
               cmp_.assign(table="comparison"),
               cl.assign(table="comparison by step"),
               races.assign(table="horse race")],
              ignore_index=True).round(6).to_csv(
        config.TABLES / "w29_learning_race.csv", index=False)

    print("\nTrend in the implied weekend ratio, same log units, fitted "
          f"{a.freq} by {a.freq}")
    print("=" * 78)
    print(f"  {'asset':>6} {'periods':>8} {'per year':>9} {'se':>7} {'t':>7} "
          f"{'first':>7} {'last':>7}")
    for _, r in itr.iterrows():
        print(f"  {r['asset']:>6} {r['n_periods']:>8.0f} "
              f"{r['trend_per_year']:>+9.4f} {r['trend_se']:>7.4f} "
              f"{r['t']:>+7.2f} {r['ratio_first']:>7.3f} {r['ratio_last']:>7.3f}")

    print("\nImplied trend minus realized trend, by which moment is taken as "
          "the benchmark")
    print("=" * 78)
    print(f"  {'asset':>6} {'moment':>11} {'implied':>9} {'realized':>9} "
          f"{'diff':>9} {'se':>7} {'t':>7} {'p':>7}")
    for _, r in cmp_.iterrows():
        print(f"  {r['asset']:>6} {r['moment']:>11} {r['implied_trend']:>+9.4f} "
              f"{r['realized_trend']:>+9.4f} {r['difference']:>+9.4f} "
              f"{r['difference_se']:>7.4f} {r['t']:>+7.2f} {r['p']:>7.3f}")

    print("\n  The same difference against the realized trend measured at each")
    print("  sampling interval. Fine-grid noise attenuates the realized trend,")
    print("  so the coarse columns are the less biased comparison:")
    for moment in ("arithmetic", "geometric"):
        print(f"    {moment}")
        for c in config.CURRENCIES:
            s = cl[(cl["asset"] == c) & (cl["moment"] == moment)]
            if s.empty:
                continue
            s = s.set_index("step_minutes")
            print(f"      {c:>4} implied {s['implied_trend'].iloc[0]:>+7.4f}  vs "
                  + " ".join(f"{k:>3}m {s.loc[k, 'realized_trend']:>+7.4f}"
                             f"(diff t {s.loc[k, 't']:>+5.1f})" for k in STEPS))

    print("\nLevel horse race: log implied weekend ratio on log realized, "
          "asset fixed effects")
    print("=" * 78)
    print(f"  {'lag':>4} {'moment':>11} {'n':>5} {'beta':>8} {'se':>7} "
          f"{'t':>7} {'reliab':>7} {'corrected':>10} {'se':>7}")
    for _, r in races.iterrows():
        print(f"  {r['lag']:>4.0f} {r['moment']:>11} {r['n']:>5.0f} "
              f"{r['beta']:>+8.3f} {r['se']:>7.3f} {r['t']:>+7.2f} "
              f"{r['reliability']:>7.3f} {r['beta_corrected']:>+10.3f} "
              f"{r['se_corrected']:>7.3f}")

    for f in ("w26_trend_by_moment", "w27_sampling_ladder", "w28_staleness",
              "w28_trimming_ladder", "w29_learning_race", "w30_tail_wedge"):
        print(f"-> {config.TABLES / (f + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
