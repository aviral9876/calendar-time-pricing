"""Why do two books over-price the weekend and two over-discount it?

The paper's headline pricing errors divide cleanly by the age of the book: the
two listed before 2020 price roughly 85% of their own realized weekend effect,
the two listed in 2024 roughly 130% of theirs, and the same division recurs in
the pooled test, the day-of-week profile and the trading P&L. That is the
paper's most interesting loose end, and "the young books have not recalibrated
yet" is only one of three explanations for it. The others are that the two
groups are measured over different calendar periods, and that they differ in
liquidity rather than in age.

The three are separable in this data:

*   **Period.** Bitcoin and Ether are averaged over 2016-2026 while Solana and
    XRP exist only from 2024. Restricting every book to the window all four
    share holds the period fixed and lets book age vary.

*   **Age.** Running each book over its own first years holds age fixed and lets
    the period vary. This one is compromised for the mature books and the script
    measures why rather than asserting it: before 2020 Deribit did not list
    daily expiries, so within-day variation in weekend exposure is half what it
    later became and the early slopes are barely identified.

*   **Liquidity.** In the matched window the four books still differ by a factor
    of thirty in trade count. Size and listing date are perfectly confounded
    across four assets, so the cross-section cannot separate them -- but the
    smile test of section 7 already does, *within* each asset and period, by
    comparing thin far-wing contracts with thick at-the-money ones.

Everything here runs off the cached smile samples rather than the option tapes,
so the whole script is seconds rather than an hour. It reproduces the headline
implied ratios to within 0.005 (the cached sample carries distance-from-the-money
where the headline specification carries |delta|; the at-the-money fits are
indistinguishable).

Outputs: w16 (windows), w17 (trajectory), w18 (identification), w19 (contrast).
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import bars, config, weekend

log = logging.getLogger("weekend_split")

CONTROLS = ["logT", "atmness", "is_call"]
# The headline band: |delta| in [0.30, 0.70] is distance-from-the-money >= 0.30.
ATM_FLOOR = 0.30
MATURE, YOUNG = ("BTC", "ETH"), ("SOL", "XRP")


def load(currency: str) -> pd.DataFrame:
    p = config.PANELS / f"smile_sample_{currency}.parquet"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing; run weekend_riskrace.py once to build the cache")
    d = pd.read_parquet(p)
    return d[d["atmness"] >= ATM_FLOOR].reset_index(drop=True)


def realized_days(currency: str) -> pd.DataFrame:
    rv = weekend.realized_by_daytype(bars.load(currency, check=False))
    rv["date"] = pd.to_datetime(rv["date"], utc=True)
    return rv


def clip(d: pd.DataFrame, lo, hi) -> pd.DataFrame:
    if lo is not None:
        d = d[d["date"] >= lo]
    if hi is not None:
        d = d[d["date"] < hi]
    return d


def fit(d: pd.DataFrame) -> dict:
    """Within-day OLS of squared IV on weekend fraction, day-clustered."""
    cols = ["iv2", "wknd_frac"] + CONTROLS
    dd = d.dropna(subset=cols)
    if len(dd) < 2000 or dd["date"].nunique() < 30:
        return {}
    dm = dd[cols] - dd.groupby("date")[cols].transform("mean")
    X = np.column_stack([dm["wknd_frac"]] + [dm[c] for c in CONTROLS]
                        + [dm["logT"] ** 2])
    y = dm["iv2"].to_numpy()
    XtX = X.T @ X
    try:
        beta = np.linalg.solve(XtX, X.T @ y)
    except np.linalg.LinAlgError:
        return {}
    r = y - X @ beta
    days = dd["date"].to_numpy()
    order = np.argsort(days)
    Xo, ro = X[order], r[order]
    _, starts = np.unique(days[order], return_index=True)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for a, b in zip(starts, list(starts[1:]) + [len(Xo)]):
        s = Xo[a:b].T @ ro[a:b]
        meat += np.outer(s, s)
    inv = np.linalg.inv(XtX)
    G = len(starts)
    se = float(np.sqrt(np.diag(inv @ meat @ inv * (G / max(G - 1, 1)))[0]))
    base = float((dd["iv2"] - beta[0] * dd["wknd_frac"]).mean())
    return {"n": int(len(dd)), "n_days": G, "slope": float(beta[0]), "slope_se": se,
            "implied_ratio": float((base + beta[0]) / base),
            "implied_ratio_se": float(se / base)}


def realized(rv: pd.DataFrame) -> dict:
    we = rv.loc[rv["is_weekend"], "rv_daily"].to_numpy()
    wd = rv.loc[~rv["is_weekend"], "rv_daily"].to_numpy()
    if len(we) < 10 or len(wd) < 20:
        return {}
    a, b = float(wd.mean()), float(we.mean())
    va = float(wd.var(ddof=1) / len(wd))
    vb = float(we.var(ddof=1) / len(we))
    # Delta method on a ratio of two means.
    se = float(np.sqrt(vb / a ** 2 + va * b ** 2 / a ** 4))
    return {"realized_ratio": b / a, "realized_ratio_se": se,
            "n_we": len(we), "n_wd": len(wd),
            "rel_effect": (b - a) / float(rv["rv_daily"].mean())}


def row(cur, d, rv, label) -> dict | None:
    f, r = fit(d), realized(rv)
    if not f or not r:
        return None
    gap = f["implied_ratio"] - r["realized_ratio"]
    se = float(np.hypot(f["implied_ratio_se"], r["realized_ratio_se"]))
    return {"asset": cur, "window": label, **f, **r, "gap": gap,
            "gap_se": se, "gap_t": gap / se if se > 0 else np.nan}


# ------------------------------------------------------------------ the tests

def windows(opt: dict, rvs: dict, matched: pd.Timestamp) -> pd.DataFrame:
    specs = [("full", None), ("2020+", pd.Timestamp("2020-01-01", tz="UTC")),
             ("2022+", pd.Timestamp("2022-01-01", tz="UTC")),
             ("matched", matched)]
    out = []
    for label, lo in specs:
        for c in config.CURRENCIES:
            r = row(c, clip(opt[c], lo, None), clip(rvs[c], lo, None), label)
            if r:
                out.append(r)
    # Book age held fixed instead of the period: each book over its own first
    # span of the length the youngest book has lived.
    span = (opt["XRP"]["date"].max() - opt["XRP"]["date"].min())
    for c in config.CURRENCIES:
        st = opt[c]["date"].min()
        r = row(c, clip(opt[c], st, st + span), clip(rvs[c], st, st + span),
                "first years")
        if r:
            out.append(r)
    return pd.DataFrame(out)


def trajectory(opt: dict, rvs: dict) -> pd.DataFrame:
    out = []
    for c in config.CURRENCIES:
        for y in sorted(opt[c]["date"].dt.year.unique()):
            d = opt[c][opt[c]["date"].dt.year == y]
            f = fit(d)
            if not f:
                continue
            r = realized(rvs[c][rvs[c]["date"].dt.year == y])
            # Scaled by the year's own implied variance level so that a year of
            # high volatility does not read as a year of heavy weekend
            # discounting: this is the relative weekend effect, the same
            # unit-free quantity the cross-asset pooled test compares.
            v = float(d["iv2"].mean())
            out.append({"asset": c, "year": int(y), **f, **(r or {}),
                        "rel_implied": f["slope"] / v,
                        "rel_implied_se": f["slope_se"] / v,
                        "gap": (f["implied_ratio"] - r["realized_ratio"]
                                if r else np.nan)})
    return pd.DataFrame(out)


def wls_trend(x: np.ndarray, y: np.ndarray, se: np.ndarray) -> dict:
    """Slope of y on x, weighted by 1/se^2, with the usual weighted s.e.

    Fitting the trend to the yearly *estimates* rather than to the trades keeps
    the two sides on the same footing -- the realized ratio can only be measured
    a year at a time -- and inverse-variance weights stop the sparse early years
    from driving a decade-long trend.
    """
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(se) & (se > 0)
    x, y, se = x[ok], y[ok], se[ok]
    if len(x) < 4:
        return {}
    w = 1.0 / se ** 2
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(w)
    XtWX_inv = np.linalg.inv(X.T @ W @ X)
    b = XtWX_inv @ (X.T @ W @ y)
    resid = y - X @ b
    # Heteroskedasticity-robust, because the yearly estimates' own standard
    # errors are not the whole story: each year is a draw from a market that
    # also moves for reasons the within-year standard error cannot see.
    meat = X.T @ W @ np.diag(resid ** 2) @ W @ X
    cov = XtWX_inv @ meat @ XtWX_inv
    s = float(np.sqrt(cov[1, 1]))
    return {"slope_per_year": float(b[1]), "se": s, "t": float(b[1] / s),
            "n_years": int(len(x)), "first": float(y[0]), "last": float(y[-1])}


def trend_by_maturity(opt: dict) -> pd.DataFrame:
    """The same trend inside fixed maturity bands.

    The obvious alternative to a market changing its mind is a market changing
    its product: Deribit's short-dated book grew enormously over this period,
    and if short-dated contracts carry a different weekend discount then a shift
    in the maturity mix would show up as a trend even with no repricing at all.
    Holding the band fixed removes that. The 7-14 day band is reported but
    barely identified -- within a single day, contracts that far out differ
    hardly at all in weekend exposure (section 5.3).
    """
    bands = ((0.25, 3.0), (3.0, 7.0), (7.0, 14.0))
    out = []
    for c in config.CURRENCIES:
        d = opt[c].assign(T=np.exp(opt[c]["logT"]))
        for lo, hi in bands:
            s = d[(d["T"] >= lo) & (d["T"] < hi)]
            rows = []
            for y in sorted(s["date"].dt.year.unique()):
                if y < 2020:
                    continue
                g = s[s["date"].dt.year == y]
                if len(g) < 5000:
                    continue
                f = fit(g)
                if f:
                    v = float(g["iv2"].mean())
                    rows.append((y, f["slope"] / v, f["slope_se"] / v))
            if len(rows) < 4:
                continue
            a = np.asarray(rows)
            t = wls_trend(a[:, 0], a[:, 1], a[:, 2])
            if t:
                out.append({"asset": c, "band": f"{lo:g}-{hi:g}d", **t})
    return pd.DataFrame(out)


def trends(tr: pd.DataFrame) -> pd.DataFrame:
    """Has the implied weekend discount deepened, and has the realized one?

    Restricted to 2020 onward for the mature books: before that, daily expiries
    did not exist and the implied slope is not identified (see w18), so
    including those years would fit a trend to noise and call it learning.
    """
    out = []
    for c in config.CURRENCIES:
        s = tr[(tr["asset"] == c) & (tr["year"] >= 2020)].sort_values("year")
        if len(s) < 4:
            continue
        x = s["year"].to_numpy(dtype="float64")
        for label, col, sec in (("implied (relative effect)", "rel_implied",
                                 "rel_implied_se"),
                                ("realized (ratio)", "realized_ratio",
                                 "realized_ratio_se")):
            t = wls_trend(x, s[col].to_numpy(), s[sec].to_numpy())
            if t:
                out.append({"asset": c, "series": label, **t})
    return pd.DataFrame(out)


def identification(opt: dict) -> pd.DataFrame:
    """Within-day dispersion of the weekend fraction, by asset-year.

    This is the identifying variation itself: with no daily expiries every
    contract quoted on a given day shares nearly the same weekend exposure, the
    regressor has almost no within-day variance, and the slope is whatever the
    few odd contracts say. Reported rather than assumed because it is what
    disqualifies the pre-2020 half of the age comparison.
    """
    out = []
    for c in config.CURRENCIES:
        d = opt[c]
        for y in sorted(d["date"].dt.year.unique()):
            s = d[d["date"].dt.year == y]
            if len(s) < 2000:
                continue
            dm = s["wknd_frac"] - s.groupby("date")["wknd_frac"].transform("mean")
            out.append({"asset": c, "year": int(y), "n": int(len(s)),
                        "within_day_sd": float(dm.std()),
                        "raw_sd": float(s["wknd_frac"].std())})
    return pd.DataFrame(out)


def pooled(opt: dict, rvs: dict, lo, label: str, n_boot: int,
           seed: int = 0) -> dict:
    """Mature minus young, in relative weekend-effect units, with a real s.e.

    The implied side is one stacked regression with an asset-specific slope,
    demeaned within asset-day and clustered on asset-day, so the four slopes
    arrive with a joint covariance rather than four separate ones -- the assets
    trade on the same days and their pricing errors are not independent.

    The realized side is block-bootstrapped over whole weeks, resampling the
    *same* weeks for every asset, which preserves the cross-asset correlation
    that makes crypto assets move together. Treating four correlated realized
    effects as independent would understate the contrast's standard error badly.
    """
    frames = []
    for c in config.CURRENCIES:
        d = clip(opt[c], lo, None)[["date", "iv2", "wknd_frac"] + CONTROLS]
        if len(d) < 2000:
            continue
        d = d.assign(cur=c, iv2s=d["iv2"] / d["iv2"].mean())
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    assets = [c for c in config.CURRENCIES if (d["cur"] == c).any()]
    k = len(assets)

    cols = ["iv2s", "wknd_frac"] + CONTROLS
    key = pd.factorize(d["cur"].astype(str) + "|" + d["date"].astype(str))[0]
    dm = d[cols] - d.groupby(key)[cols].transform("mean")
    codes = pd.Categorical(d["cur"], categories=assets).codes
    X = np.column_stack([dm["wknd_frac"].to_numpy() * (codes == j)
                         for j in range(k)]
                        + [dm[c] for c in CONTROLS] + [dm["logT"] ** 2])
    y = dm["iv2s"].to_numpy()
    XtX = X.T @ X
    beta = np.linalg.solve(XtX, X.T @ y)
    r = y - X @ beta
    G = key.max() + 1
    scores = np.column_stack([np.bincount(key, weights=X[:, j] * r, minlength=G)
                              for j in range(X.shape[1])])
    inv = np.linalg.inv(XtX)
    cov = inv @ (scores.T @ scores) @ inv * (G / max(G - 1, 1))
    imp, imp_cov = beta[:k], cov[:k, :k]

    # Realized relative effects, and their joint covariance by week block.
    days = {c: clip(rvs[c], lo, None) for c in assets}
    weeks = sorted(set().union(*[
        set((s["date"].dt.isocalendar().year * 100
             + s["date"].dt.isocalendar().week).astype(int)) for s in days.values()]))
    idx = {c: (days[c]["date"].dt.isocalendar().year * 100
               + days[c]["date"].dt.isocalendar().week).astype(int).to_numpy()
           for c in assets}

    def rel(s):
        we = s.loc[s["is_weekend"], "rv_daily"]
        wd = s.loc[~s["is_weekend"], "rv_daily"]
        if len(we) < 5 or len(wd) < 10:
            return np.nan
        return float((we.mean() - wd.mean()) / s["rv_daily"].mean())

    real = np.array([rel(days[c]) for c in assets])
    rng = np.random.default_rng(seed)
    weeks = np.asarray(weeks)
    draws = np.full((n_boot, k), np.nan)
    picks = {c: {w: np.flatnonzero(idx[c] == w) for w in weeks} for c in assets}
    for b in range(n_boot):
        take = rng.integers(0, len(weeks), len(weeks))
        chosen = weeks[take]
        for j, c in enumerate(assets):
            rows = np.concatenate([picks[c][w] for w in chosen
                                   if len(picks[c][w])])
            if len(rows) < 30:
                continue
            draws[b, j] = rel(days[c].iloc[rows])
    real_cov = np.cov(draws[~np.isnan(draws).any(axis=1)].T)

    # Mature minus young, each group's gaps averaged.
    n_m = sum(c in MATURE for c in assets)
    n_y = sum(c in YOUNG for c in assets)
    w = np.array([1.0 / n_m if c in MATURE else -1.0 / n_y for c in assets])
    gap = imp - real
    contrast = float(w @ gap)
    var = float(w @ imp_cov @ w + w @ real_cov @ w)
    se = float(np.sqrt(var))

    # And the joint test that all four gaps are equal.
    R = np.zeros((k - 1, k))
    for j in range(k - 1):
        R[j, j], R[j, j + 1] = 1.0, -1.0
    V = R @ (imp_cov + real_cov) @ R.T
    diff = R @ gap
    chi2 = float(diff @ np.linalg.solve(V, diff))
    return {"window": label, "n": int(len(d)), "n_asset_days": int(G),
            **{f"gap_{c}": float(gap[j]) for j, c in enumerate(assets)},
            "contrast": contrast, "contrast_se": se,
            "contrast_t": contrast / se if se > 0 else np.nan,
            "contrast_p": float(2 * (1 - stats.norm.cdf(abs(contrast / se)))),
            "chi2_equal": chi2, "df": k - 1,
            "p_equal": float(1 - stats.chi2.cdf(chi2, k - 1))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    opt = {c: load(c) for c in config.CURRENCIES}
    rvs = {c: realized_days(c) for c in config.CURRENCIES}
    matched = max(opt[c]["date"].min() for c in config.CURRENCIES)

    ident = identification(opt)
    ident.round(6).to_csv(config.TABLES / "w18_split_identification.csv",
                          index=False)
    print("\nIdentifying variation: within-day sd of the weekend fraction")
    print("=" * 78)
    yrs = sorted(ident["year"].unique())
    print(f"  {'asset':>6} " + " ".join(f"{y:>6}" for y in yrs))
    for c in config.CURRENCIES:
        s = ident[ident["asset"] == c].set_index("year")["within_day_sd"]
        print(f"  {c:>6} " + " ".join(
            (f"{s[y]:>6.3f}" if y in s.index else f"{'--':>6}") for y in yrs))
    print("\n  Daily expiries arrive around 2020 and roughly double the")
    print("  identifying variation. The 2024 books have it from listing.")

    win = windows(opt, rvs, matched)
    win.round(6).to_csv(config.TABLES / "w16_split_windows.csv", index=False)
    print(f"\nPricing gap by window (matched window starts {matched.date()})")
    print("=" * 78)
    print(f"  {'window':>12} {'asset':>6} {'n':>10} {'implied':>9} "
          f"{'realized':>9} {'gap':>9} {'t':>6}")
    for label in ("full", "2020+", "2022+", "matched", "first years"):
        for _, r in win[win["window"] == label].iterrows():
            print(f"  {label:>12} {r['asset']:>6} {r['n']:>10,.0f} "
                  f"{r['implied_ratio']:>9.4f} {r['realized_ratio']:>9.4f} "
                  f"{r['gap']:>+9.4f} {r['gap_t']:>+6.2f}")
        print()

    tr = trajectory(opt, rvs)
    tr.round(6).to_csv(config.TABLES / "w17_split_trajectory.csv", index=False)
    print("Implied weekend ratio by year (the realized ratio is too noisy "
          "annually to\ncarry the comparison, and is in w17 for reference)")
    print("=" * 78)
    yrs = sorted(tr["year"].unique())
    print(f"  {'asset':>6} " + " ".join(f"{y:>6}" for y in yrs))
    for c in config.CURRENCIES:
        s = tr[tr["asset"] == c].set_index("year")["implied_ratio"]
        print(f"  {c:>6} " + " ".join(
            (f"{s[y]:>6.2f}" if y in s.index else f"{'--':>6}") for y in yrs))

    td = trends(tr)
    td.round(6).to_csv(config.TABLES / "w20_split_trends.csv", index=False)
    print("\nTrend in the weekend discount, 2020 onward, weighted by each "
          "year's precision")
    print("=" * 78)
    print(f"  {'asset':>6} {'series':>26} {'per year':>10} {'se':>8} {'t':>7} "
          f"{'first':>7} {'last':>7}")
    for _, r in td.iterrows():
        print(f"  {r['asset']:>6} {r['series']:>26} {r['slope_per_year']:>+10.4f} "
              f"{r['se']:>8.4f} {r['t']:>+7.2f} {r['first']:>7.3f} "
              f"{r['last']:>7.3f}")

    mb = trend_by_maturity(opt)
    mb.round(6).to_csv(config.TABLES / "w21_split_trend_by_maturity.csv",
                       index=False)
    print("\n  Same trend inside fixed maturity bands, so it is not the "
          "maturity mix:")
    for _, r in mb.iterrows():
        print(f"  {r['asset']:>6} {r['band']:>8} {r['slope_per_year']:>+9.4f} "
              f"per year (t {r['t']:+.2f})")

    tests = pd.DataFrame([
        pooled(opt, rvs, None, "full", a.boot),
        pooled(opt, rvs, pd.Timestamp("2020-01-01", tz="UTC"), "2020+", a.boot),
        pooled(opt, rvs, matched, "matched", a.boot)])
    tests.round(6).to_csv(config.TABLES / "w19_split_contrast.csv", index=False)
    print("\nIs the split real? Mature minus young, in relative weekend-effect")
    print("units, implied side stacked and clustered, realized side "
          "week-bootstrapped")
    print("=" * 78)
    print(f"  {'window':>10} {'contrast':>10} {'se':>8} {'t':>7} {'p':>7}   "
          f"{'chi2 all equal':>15} {'p':>7}")
    for _, r in tests.iterrows():
        print(f"  {r['window']:>10} {r['contrast']:>+10.4f} {r['contrast_se']:>8.4f} "
              f"{r['contrast_t']:>+7.2f} {r['contrast_p']:>7.3f}   "
              f"{r['chi2_equal']:>15.2f} {r['p_equal']:>7.3f}")

    for f in ("w16_split_windows", "w17_split_trajectory",
              "w18_split_identification", "w19_split_contrast",
              "w20_split_trends", "w21_split_trend_by_maturity"):
        print(f"-> {config.TABLES / (f + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
