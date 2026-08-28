"""A horse race between the pricing-error reading and a risk-based one.

Section 7 previously observed that weekend returns carry fatter tails and left
the matter there. That is not enough: the first objection any referee raises is
that options are priced under the risk-neutral measure, so an implied weekend
discount that differs from the realized one is not by itself an error. If the
weekend carries more jump risk and jump risk earns a premium, a market that
discounts the weekend by less than realized variance is behaving correctly.

This script prices weekend jump risk explicitly and asks how much of the gap
survives. Three pieces:

0.  A check that the realized benchmark is not itself an artefact. The whole
    comparison rests on realized variance measured on a five-minute grid, which
    is only innocent if prices move on that grid. Thin books repeat their close,
    the return records as zero, and realized variance is biased down -- by more
    at the weekend, when trading is thinner, so the bias does not cancel in the
    ratio. The volatility signature across sampling intervals settles it.

1.  A note on what a risk premium can and cannot do here. The headline compares
    *ratios*, and a premium applied proportionally to all calendar time cancels
    out of a ratio exactly. Only a premium that loads differently on weekend
    time than on weekday time can move the comparison at all. Verified
    numerically rather than asserted.

2.  The jump race. Realized variance is split into continuous and jump parts
    separately for weekdays and weekends, and the weekend ratio is recomputed
    with jump variance priced at a multiple kappa of its physical value. This
    traces a path from the realized ratio at kappa = 1 to the jump-variance
    ratio in the limit, and that limit is a bound: no jump premium of any size
    prices the weekend beyond it. Assets whose implied ratio falls outside the
    reachable interval cannot be explained by jump compensation at all, and for
    those inside it we report the premium the market would have to be charging.

3.  The smile test, which asks the option side of the same question. Jump risk
    is priced in the wings, not at the money. If the weekend discount is small
    because weekend jump risk is being compensated, the discount must shrink as
    one moves away from the money. If it is a calendar-time convention, the
    discount is a property of the clock and should be flat across the smile.

Outputs: w11 (decomposition), w12 (race and bound), w13 (robustness over the
truncation level), w14 (smile), w15 (volatility signature).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import bars, config, jumps, tape, util, weekend

log = logging.getLogger("weekend_riskrace")

MAX_T_DAYS, MIN_T_DAYS = 14, 0.25

# What a usable smile-sample cache has to contain. Checked on load so that
# adding a column here forces the rebuild rather than leaving stale files to be
# discovered downstream.
SAMPLE_COLS = {"iv2", "logT", "atmness", "is_call", "delta", "logm",
               "expiry_dow", "expiry", "size", "prem_quoted", "F", "strike",
               "wknd_frac", "date"}

# The kappa grid reported in the paper. One is the physical measure and
# reproduces the headline comparison; two to four brackets the jump-variance
# premia estimated on equity index options; the bound is the limit as kappa
# grows without bound and is where the argument is actually settled.
KAPPA_GRID = (1.0, 2.0, 3.0, 5.0, 10.0)

# Distance from the money, min(|delta|, 1 - |delta|). Zero is the far wing and
# 0.5 is at the money. Pooling calls and puts on this rather than on |delta|
# puts both wings of the smile in the same bucket, which is what a jump premium
# is supposed to load on; bucketing on |delta| alone would split them and put a
# deep out-of-the-money call with a deep in-the-money put.
ATM_BINS = (0.02, 0.10, 0.20, 0.35, 0.50)
ATM_LABELS = ("far wing", "wing", "near", "at the money")


# --------------------------------------------------------------- the option side

def load_sample(currency: str, cache: bool = True) -> pd.DataFrame:
    """The headline sample, widened across the smile.

    Identical to the headline filter except that the delta band opens from
    [0.30, 0.70] to the full quoted range, because the smile test needs the
    wings the headline deliberately excludes.

    Cached, because this is the one place in the paper that reads an option tape
    for a specification still under revision: Bitcoin's load and greek
    enrichment alone run for half an hour, and the handful of columns that
    survive it are a hundredth of the tape. Delete
    `data/panels/smile_sample_*.parquet` to force a rebuild after changing the
    filter or adding a column.

    The columns beyond the regression's own are there for section 5.6, which
    asks *why* the wings price the weekend differently: signed delta separates
    the upper wing from the lower one, log-moneyness gives the alternative
    bucketing that distinguishes a strike-anchored smile from a delta-anchored
    one, expiry weekday tests whether the effect is really an expiry-composition
    effect, and size is the liquidity proxy.
    """
    p = config.PANELS / f"smile_sample_{currency}.parquet"
    if cache and p.exists():
        out = pd.read_parquet(p)
        missing = SAMPLE_COLS - set(out.columns)
        if not missing:
            return out
        # An older cache written before a column was added. Rebuilding is an
        # hour on Bitcoin, so it has to be a deliberate, logged event rather
        # than something a reader discovers as a KeyError three scripts later.
        log.warning("%s: cached sample is missing %s; rebuilding from the tape",
                    currency, ", ".join(sorted(missing)))
        del out
    df = tape.load(currency, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    ad = d["delta"].abs()
    keep = (d["iv_ok"] & d["delta"].notna()
            & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
            & ad.between(ATM_BINS[0], 1.0 - ATM_BINS[0]))
    d = d.loc[keep]
    out = pd.DataFrame(index=d.index)
    out["iv2"] = (d["sigma"] ** 2).astype("float64")
    out["logT"] = np.log(d["T"].to_numpy() * config.YEAR)
    out["atmness"] = np.minimum(d["delta"].abs(), 1.0 - d["delta"].abs())
    out["is_call"] = (d["delta"] > 0).astype("float64")
    out["delta"] = d["delta"].astype("float64")
    # Log-moneyness against the forward, not the index: in contango the two
    # differ by enough to shift a contract a whole bucket.
    out["logm"] = np.log(d["strike"].to_numpy() / d["F"].to_numpy())
    exp = pd.to_datetime(d["expiration_timestamp"], unit="ms", utc=True)
    out["expiry_dow"] = exp.dt.dayofweek.astype("int8").to_numpy()
    # The expiry itself, so that a whole smile can be fitted per trade-day and
    # expiry: the direct test of whether the market flattens the smile for
    # weekend-heavy contracts needs several strikes on one expiry at once.
    out["expiry"] = d["expiration_timestamp"].astype("int64").to_numpy()
    out["size"] = d["amount"].astype("float64")
    # The premium the trade actually paid, in the units the venue quotes it:
    # coin per unit of underlying on the inverse books, dollars per unit on the
    # linear ones. Everything else in this frame is a volatility, and a
    # volatility is the exchange's own inversion of this number -- keeping the
    # price alongside is what makes it possible to check that inversion and to
    # state effects against money that changed hands rather than against a
    # reconstruction of it.
    out["prem_quoted"] = d["price"].astype("float64")
    out["F"] = d["F"].astype("float64")
    out["strike"] = d["strike"].astype("float64")
    out["wknd_frac"] = weekend.weekend_fraction(
        d["timestamp"].to_numpy(), d["expiration_timestamp"].to_numpy())
    out["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms",
                                                 utc=True))
    del d
    out = out.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    if cache:
        config.PANELS.mkdir(parents=True, exist_ok=True)
        out.to_parquet(p, index=False)
    return out


def within_day_fit(d: pd.DataFrame, controls: list[str]) -> dict:
    """Within-day OLS of squared IV on weekend fraction, day-clustered SEs.

    The same estimator as the headline specification: demeaning by trade day is
    day fixed effects, so the slope is identified only from contracts quoted at
    the same instant with different weekend exposure.
    """
    cols = ["iv2", "wknd_frac"] + controls
    dd = d.dropna(subset=cols)
    if len(dd) < 500 or dd["date"].nunique() < 30:
        return {}
    g = dd.groupby("date")[cols]
    dm = (dd[cols] - g.transform("mean")).dropna()
    X = np.column_stack([dm["wknd_frac"]] + [dm[c] for c in controls]
                        + [dm["logT"] ** 2])
    y = dm["iv2"].to_numpy()
    XtX = X.T @ X
    try:
        beta = np.linalg.solve(XtX, X.T @ y)
    except np.linalg.LinAlgError:
        return {}
    resid = y - X @ beta
    days = dd.loc[dm.index, "date"].to_numpy()
    order = np.argsort(days)
    Xo, ro = X[order], resid[order]
    _, starts = np.unique(days[order], return_index=True)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for a, b in zip(starts, list(starts[1:]) + [len(Xo)]):
        s = Xo[a:b].T @ ro[a:b]
        meat += np.outer(s, s)
    inv = np.linalg.inv(XtX)
    n_g = len(starts)
    cov = inv @ meat @ inv * (n_g / max(n_g - 1, 1))
    se = float(np.sqrt(np.diag(cov))[0])
    base = float((dd.loc[dm.index, "iv2"]
                  - beta[0] * dd.loc[dm.index, "wknd_frac"]).mean())
    ratio = (base + beta[0]) / base if base > 0 else np.nan
    # The ratio is a slope divided by an intercept the fixed effects absorb, so
    # its standard error is the slope's rescaled by that intercept; treating the
    # level as known understates it only trivially at these sample sizes.
    return {"n": int(len(dm)), "n_days": int(n_g), "slope": float(beta[0]),
            "se": se, "t": float(beta[0] / se) if se > 0 else np.nan,
            "v_weekday_implied": base, "implied_ratio": float(ratio),
            "implied_ratio_se": float(se / base) if base > 0 else np.nan}


SMILE_REGRESSORS = ("wknd_frac", "logT", "logT2", "atmness", "is_call")


def smile_wald(d: pd.DataFrame) -> dict:
    """Are the weekend discounts equal across the smile? A Wald test.

    Reading four separately fitted ratios off a table is not a test. This
    estimates the same four fits jointly so that the differences between them
    carry a covariance.

    Every coefficient is bucket-specific, not just the weekend slope. That
    matters: the smile is steeper at short maturities than at long ones, so a
    specification forcing one maturity profile across all four buckets would
    push a bucket-specific maturity effect into the one coefficient being
    compared. Interacting the whole design with the bucket makes the point
    estimates identical to fitting each bucket alone, and the only thing the
    joint form adds is the between-bucket covariance -- which is what the
    contrast needs and separate fits cannot supply.

    Squared implied vol is divided by its own bucket mean first. The wings quote
    a higher variance level than the money, so equal *relative* weekend
    discounts would still produce different raw slopes, and testing raw slopes
    would reject a flat smile on the level of the smile alone -- the same
    problem the cross-asset pooled test solves the same way.

    The design is block diagonal by construction, so it is fitted one block at a
    time and only the per-day score vectors are stacked. Forming the full
    interacted matrix would mean twenty float64 columns over thirteen million
    Bitcoin rows for an answer that is identical.
    """
    # Coded against ATM_LABELS explicitly, not by factorizing. pandas factorizes
    # a categorical in order of first appearance, which would put an arbitrary
    # bucket in position zero and silently turn the directional contrast below
    # into a comparison between two unrelated parts of the smile.
    labels, k = ATM_LABELS, len(ATM_LABELS)
    p = len(SMILE_REGRESSORS)
    days = np.sort(d["date"].unique())
    day_ix = pd.Series(np.arange(len(days)), index=days)
    G = len(days)

    scores = np.zeros((G, k * p))
    breads, betas = [], []
    cols = ["y", "wknd_frac", "logT", "atmness", "is_call"]
    for j, lab in enumerate(labels):
        sub = d[d["bucket"] == lab]
        f = pd.DataFrame({
            "y": sub["iv2"].to_numpy() / float(sub["iv2"].mean()),
            "wknd_frac": sub["wknd_frac"].to_numpy(),
            "logT": sub["logT"].to_numpy(),
            "atmness": sub["atmness"].to_numpy(),
            "is_call": sub["is_call"].to_numpy(),
            "date": sub["date"].to_numpy()})
        dm = f[cols] - f.groupby("date")[cols].transform("mean")
        X = np.column_stack([dm["wknd_frac"], dm["logT"], dm["logT"] ** 2,
                             dm["atmness"], dm["is_call"]])
        y = dm["y"].to_numpy()
        XtX = X.T @ X
        beta = np.linalg.solve(XtX, X.T @ y)
        r = y - X @ beta
        gi = day_ix.reindex(f["date"].to_numpy()).to_numpy()
        for c in range(p):
            scores[:, j * p + c] = np.bincount(gi, weights=X[:, c] * r,
                                               minlength=G)
        breads.append(np.linalg.inv(XtX))
        betas.append(beta)
        del f, dm, X, y, r

    beta = np.concatenate(betas)
    bread = np.zeros((k * p, k * p))
    for j, b in enumerate(breads):
        bread[j * p:(j + 1) * p, j * p:(j + 1) * p] = b
    cov = bread @ (scores.T @ scores) @ bread * (G / max(G - 1, 1))
    slope_ix = [j * p for j in range(k)]

    # H0: the relative weekend discount is the same everywhere on the smile.
    R = np.zeros((k - 1, k * p))
    for j in range(k - 1):
        R[j, slope_ix[j]], R[j, slope_ix[j + 1]] = 1.0, -1.0
    rb = R @ beta
    chi2 = float(rb @ np.linalg.solve(R @ cov @ R.T, rb))
    # The directional contrast the risk story predicts: a jump premium is priced
    # in the wings, so the far wing must discount the weekend LESS than the
    # money, i.e. its (negative) slope must be closer to zero. Bucket 0 is the
    # far wing and the last is at the money.
    c = np.zeros(k * p)
    c[slope_ix[0]], c[slope_ix[-1]] = 1.0, -1.0
    diff = float(c @ beta)
    se = float(np.sqrt(c @ cov @ c))
    return {"chi2_equal": chi2, "df": k - 1, "n_days": G,
            "p_equal": float(1 - stats.chi2.cdf(chi2, k - 1)),
            "wing_minus_atm": diff, "wing_minus_atm_se": se,
            "wing_minus_atm_t": diff / se if se > 0 else np.nan,
            **{f"slope_{labels[j].replace(' ', '_')}": float(beta[slope_ix[j]])
               for j in range(k)}}


def smile_test(currency: str) -> tuple[pd.DataFrame, dict]:
    print(f"  smile: loading {currency} tape", flush=True)
    d = load_sample(currency)
    print(f"  smile: {currency} {len(d):,} trades across the smile", flush=True)
    d["bucket"] = pd.cut(d["atmness"], ATM_BINS, labels=ATM_LABELS,
                         include_lowest=True)
    d = d[d["bucket"].notna()]
    rows = []
    for label in ATM_LABELS:
        sub = d[d["bucket"] == label]
        fit = within_day_fit(sub, ["logT", "atmness", "is_call"])
        if fit:
            rows.append({"currency": currency, "bucket": label,
                         "atmness_mean": float(sub["atmness"].mean()),
                         "iv2_mean": float(sub["iv2"].mean()), **fit})
    wald = {"currency": currency, **smile_wald(d)}
    del d
    return pd.DataFrame(rows), wald


# ----------------------------------------------------------- the realized side

def race_row(cur: str, day: pd.DataFrame, implied: float,
             implied_se: float, n_boot: int) -> dict:
    m = jumps.regime_means(day)
    lo, hi = jumps.reachable_interval(m)
    k_star = jumps.required_kappa(m, implied)
    bs = jumps.bootstrap(day, implied, implied_se, n_boot=n_boot)
    row = {"asset": cur, "implied_ratio": implied, "implied_se": implied_se,
           **{k: m[k] for k in ("realized_ratio", "cont_ratio", "jump_ratio",
                                "jump_share_wd", "jump_share_we",
                                "n_wd", "n_we")},
           "bound_lo": lo, "bound_hi": hi,
           "implied_inside_bound": bool(lo <= implied <= hi),
           "kappa_star": k_star, **bs}
    for k in KAPPA_GRID:
        row[f"ratio_k{k:g}"] = float(jumps.ratio_at_kappa(m, k))
        row[f"gap_k{k:g}"] = implied - float(jumps.ratio_at_kappa(m, k))
    row["gap_bound"] = implied - (hi if implied > m["realized_ratio"] else lo)
    return row


def proportional_premium_check(m: dict) -> float:
    """Largest absolute change in the priced ratio from scaling both variance
    components by a common factor. Zero by construction; computed rather than
    asserted so that the claim in the paper is a checked one."""
    worst = 0.0
    for lam in (0.5, 1.0, 2.0, 7.3):
        s = {k: (lam * v if k in ("c_wd", "c_we", "j_wd", "j_we") else v)
             for k, v in m.items()}
        for k in KAPPA_GRID:
            worst = max(worst, abs(float(jumps.ratio_at_kappa(s, k))
                                   - float(jumps.ratio_at_kappa(m, k))))
    return worst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--skip-smile", action="store_true")
    # The smile is the only part that touches the option tape and it costs
    # roughly an hour; everything else runs off bars in about two minutes. Being
    # able to redo one without the other is the difference between iterating on
    # the specification and not.
    ap.add_argument("--only-smile", action="store_true")
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)
    race_stages = not a.only_smile

    w1 = pd.read_csv(config.TABLES / "w1_weekend_pricing.csv").set_index("currency")
    # The implied ratio's standard error follows from the slope's, rescaled by
    # the weekday variance level the fixed effects absorb.
    imp_se = (w1["se"] / w1["v_weekday_implied"]).to_dict()

    def reference_bars(name: str) -> pd.DataFrame:
        return bars.fetch_bars(config.REFERENCE_ASSETS[name],
                               config.REFERENCE_START[name],
                               dt.datetime.now(dt.timezone.utc).date(),
                               resolution=str(config.BAR_MINUTES))

    if race_stages:
        # -------------------------------------------------- 0. is the benchmark sound
        sig = []
        for cur in config.CURRENCIES:
            s = jumps.signature(bars.load(cur, check=False))
            s.insert(0, "asset", cur)
            sig.append(s)
        for name in config.REFERENCE_ASSETS:
            s = jumps.signature(reference_bars(name))
            s.insert(0, "asset", name)
            sig.append(s)
        sig = pd.concat(sig, ignore_index=True)
        sig.round(6).to_csv(config.TABLES / "w15_volatility_signature.csv", index=False)

        print("\nWeekend variance ratio by sampling interval, with the share of "
              "unchanged closes")
        print("=" * 78)
        steps = sorted(sig["step_minutes"].unique())
        print(f"  {'asset':>6} " + " ".join(f"{s:>5}m" for s in steps)
              + f"  {'drift/se':>9}  {'zero share 5m wd/we':>21}")
        for asset, g in sig.groupby("asset", sort=False):
            g = g.set_index("step_minutes")
            r = [g["variance_ratio"].get(s, np.nan) for s in steps]
            # Drift measured against the five-minute estimate's own standard error:
            # a ratio that wanders less than one standard error across a fortyfold
            # change of sampling interval is not being driven by stale prices.
            drift = (np.nanmax(r) - np.nanmin(r)) / float(g["se_ratio"].iloc[0])
            z0 = g.iloc[0]
            print(f"  {asset:>6} " + " ".join(f"{v:6.3f}" for v in r)
                  + f"  {drift:9.2f}  {z0['zero_share_wd']:9.3f} /"
                    f"{z0['zero_share_we']:9.3f}")

        # ---------------------------------------------------------- decomposition
        # The reference asset is deliberately absent below. Jump identification
        # needs prices that move on the sampling grid, and PAXG's perpetual repeats
        # its close on 78% of weekday and 88% of weekend five-minute bars, which
        # drives bipower variation and every threshold built on it to nearly zero.
        # It has no option pricing estimate to race against in any case.
        days, dec = {}, []
        for cur in config.CURRENCIES:
            days[cur] = jumps.decompose(bars.load(cur, check=False))
            dec.append({"asset": cur, **jumps.regime_means(days[cur])})
        dec = pd.DataFrame(dec)
        dec.round(8).to_csv(config.TABLES / "w11_jump_decomposition.csv", index=False)

        print("\nJump and continuous variance by day type "
              f"(truncation at {jumps.TRUNC_C:g} local sd, intraday factor on)")
        print("=" * 78)
        print(f"  {'asset':>6} {'jump share wd':>14} {'jump share we':>14} "
              f"{'cont ratio':>11} {'jump ratio':>11} {'realized':>10}")
        for _, r in dec.iterrows():
            print(f"  {r['asset']:>6} {r['jump_share_wd']:>14.3f} "
                  f"{r['jump_share_we']:>14.3f} {r['cont_ratio']:>11.4f} "
                  f"{r['jump_ratio']:>11.4f} {r['realized_ratio']:>10.4f}")

        # -------------------------------------------------------------- the race
        rows = [race_row(cur, days[cur], float(w1.loc[cur, "implied_ratio"]),
                         float(imp_se[cur]), a.boot)
                for cur in config.CURRENCIES]
        race = pd.DataFrame(rows)
        race.round(6).to_csv(config.TABLES / "w12_risk_horse_race.csv", index=False)

        worst = max(proportional_premium_check(jumps.regime_means(days[c]))
                    for c in config.CURRENCIES)
        print(f"\nA premium applied proportionally to all calendar time moves the "
              f"weekend ratio by at most {worst:.2e} (it cancels).")

        print("\nHow much of the gap survives pricing weekend jump risk?")
        print("=" * 78)
        head = "  ".join(f"k={k:g}".rjust(8) for k in KAPPA_GRID)
        print(f"  {'asset':>6} {'implied':>8} {head}  {'bound':>8} {'kappa*':>8}")
        for _, r in race.iterrows():
            lad = "  ".join(f"{r[f'gap_k{k:g}']:+8.4f}" for k in KAPPA_GRID)
            ks = "  --" if not np.isfinite(r["kappa_star"]) else f"{r['kappa_star']:8.2f}"
            print(f"  {r['asset']:>6} {r['implied_ratio']:8.4f} {lad}  "
                  f"{r['gap_bound']:+8.4f} {ks}")
        print("\n  gap_k is implied minus the ratio a market pricing jump variance")
        print("  at k times its physical value would quote. 'bound' is the residual")
        print("  at the limit of an unbounded premium; kappa* is the premium that")
        print("  would close the gap, and is undefined when none can.")
        for _, r in race.iterrows():
            inside = "inside" if r["implied_inside_bound"] else "OUTSIDE"
            print(f"  {r['asset']:>6}: implied {r['implied_ratio']:.4f} is {inside} "
                  f"the reachable interval [{r['bound_lo']:.4f}, {r['bound_hi']:.4f}]"
                  f"; bootstrap P(reachable) = {r['p_reachable']:.3f}")

        # Risk compensation also implies an ordering: the asset whose weekend
        # carries relatively more jump risk should be the one whose weekend is
        # priced richest against its own realized variance. Four points cannot test
        # that, but they can contradict it.
        o = race.sort_values("jump_ratio")
        rho = float(o["jump_ratio"].corr(o["gap_k1"], method="spearman"))
        print(f"\nOrdering check (descriptive, n = {len(o)}): sorted by weekend "
              f"jump-risk share,")
        print("  " + "  ".join(f"{r['asset']} {r['jump_ratio']:.3f}->"
                               f"{r['gap_k1']:+.3f}" for _, r in o.iterrows()))
        print(f"  Spearman rank correlation with the pricing gap: {rho:+.2f} "
              f"(risk compensation predicts positive)")

        # -------------------------------------------------------- robustness grid
        rb = []
        for cur in config.CURRENCIES:
            b = bars.load(cur, check=False)
            imp = float(w1.loc[cur, "implied_ratio"])

            def add(m, **kw):
                lo, hi = jumps.reachable_interval(m)
                rb.append({"asset": cur, **kw,
                           "jump_share_wd": m["jump_share_wd"],
                           "jump_share_we": m["jump_share_we"],
                           "realized_ratio": m["realized_ratio"],
                           "jump_ratio": m["jump_ratio"],
                           "implied_ratio": imp, "bound_lo": lo, "bound_hi": hi,
                           "implied_inside_bound": bool(lo <= imp <= hi),
                           "kappa_star": jumps.required_kappa(m, imp)})

            for c in (2.5, 3.0, 4.0, 5.0):
                for tod in (True, False):
                    add(jumps.regime_means(jumps.decompose(b, c=c, use_tod=tod)),
                        trunc_c=c, tod=tod, step_minutes=config.BAR_MINUTES)
            # Coarser grids at the baseline truncation. Jump detection weakens as
            # the interval grows, so these are a check that the verdict does not
            # depend on the five-minute grid rather than a better measurement.
            for q in (15, 30, 60):
                add(jumps.regime_means(jumps.decompose(b, step_minutes=q)),
                    trunc_c=jumps.TRUNC_C, tod=True, step_minutes=q)
            del b
        rb = pd.DataFrame(rb)
        rb.round(6).to_csv(config.TABLES / "w13_horse_race_robustness.csv",
                           index=False)
        n_in = int(rb["implied_inside_bound"].sum())
        print(f"\nRobustness: the implied ratio is reachable by a jump premium in "
              f"{n_in} of {len(rb)} estimator settings")
        for cur in config.CURRENCIES:
            s = rb[rb["asset"] == cur]
            print(f"  {cur:>6}: {int(s['implied_inside_bound'].sum())}/{len(s)}  "
                  f"jump ratio {s['jump_ratio'].min():.4f}-{s['jump_ratio'].max():.4f}")
        del days

    # -------------------------------------------------------------- the smile
    if not a.skip_smile:
        parts, walds = [], []
        for cur in config.CURRENCIES:
            p, w = smile_test(cur)
            parts.append(p)
            walds.append(w)
        sm = pd.concat(parts, ignore_index=True)
        sm.round(6).to_csv(config.TABLES / "w14_weekend_slope_by_moneyness.csv",
                           index=False)
        wd = pd.DataFrame(walds)
        wd.round(6).to_csv(config.TABLES / "w14b_smile_wald.csv", index=False)

        print("\nImplied weekend ratio across the smile")
        print("=" * 78)
        print(f"  {'asset':>6} {'bucket':>14} {'n':>10} {'slope':>10} "
              f"{'t':>7} {'implied ratio':>15}")
        for _, r in sm.iterrows():
            print(f"  {r['currency']:>6} {r['bucket']:>14} {r['n']:>10,} "
                  f"{r['slope']:>+10.4f} {r['t']:>+7.1f} "
                  f"{r['implied_ratio']:>10.4f} +/-{r['implied_ratio_se']:.4f}")
        print("\n  A jump-risk premium is priced in the wings: under that story")
        print("  the far wing must discount the weekend LESS than the money, so")
        print("  'wing - money' below must be POSITIVE. Under a calendar-time")
        print("  convention the discount is flat across the smile.")
        print(f"\n  {'asset':>6} {'chi2 (equal)':>13} {'p':>7} "
              f"{'wing - money':>14} {'t':>7}")
        for _, r in wd.iterrows():
            print(f"  {r['currency']:>6} {r['chi2_equal']:>13.2f} "
                  f"{r['p_equal']:>7.3f} {r['wing_minus_atm']:>+14.4f} "
                  f"{r['wing_minus_atm_t']:>+7.2f}")

    if race_stages:
        for f in ("w11_jump_decomposition", "w12_risk_horse_race",
                  "w13_horse_race_robustness", "w15_volatility_signature"):
            print(f"-> {config.TABLES / (f + '.csv')}")
    if not a.skip_smile:
        print(f"-> {config.TABLES / 'w14_weekend_slope_by_moneyness.csv'}")
        print(f"-> {config.TABLES / 'w14b_smile_wald.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
