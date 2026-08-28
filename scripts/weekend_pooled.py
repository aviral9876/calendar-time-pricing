"""Formal test of the 'uniform convention' claim, across N underlyings.

The mechanism argument is that the market applies roughly the same weekend
discount to every asset, while the realized weekend effects differ. With two
assets that cannot be settled: the pooled test rejects neither equality of the
implied slopes nor proportionality to the realized effects. Each additional
underlying adds a point to a relationship otherwise identified by two.

Two hypotheses, tested jointly across all assets:

    H0a  implied weekend slopes are EQUAL across assets        (convention)
    H0b  implied slopes are PROPORTIONAL to realized effects   (calibration)

A market pricing by convention fails to reject H0a and rejects H0b; a market
calibrating per asset does the reverse. Both are Wald tests on the same fitted
model, so they are directly comparable.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import bars, config, tape, util, weekend

log = logging.getLogger("weekend_pooled")
MAX_T_DAYS, MIN_T_DAYS = 14, 0.25
DELTA_BAND = (0.30, 0.70)


def _scale_note() -> None:
    """Why the dependent variable is scaled before pooling.

    The fitted slope estimates v_we - v_wd in *variance* units, so it inherits
    the asset's volatility level: SOL's implied weekday variance is 0.81 against
    BTC's 0.44, and its slope is correspondingly larger even if both markets
    apply an identical proportional weekend discount. Testing equality of raw
    slopes would therefore reject a uniform convention on vol-level differences
    alone, which is not the question.

    Dividing each asset's squared implied vol by its own mean makes the slope
    the *relative* weekend effect, (v_we - v_wd)/v_bar, which is the quantity a
    quoting convention would hold fixed and the quantity comparable with the
    realized weekend ratio.
    """


def prep(cur: str, start_year: int | None) -> pd.DataFrame:
    df = tape.load(cur, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T = d["T"] * config.YEAR
    d = d.loc[d["iv_ok"] & d["delta"].notna()
              & T.between(MIN_T_DAYS, MAX_T_DAYS)
              & d["delta"].abs().between(*DELTA_BAND)].copy()
    d = weekend.attach(d)
    d["iv2"] = d["sigma"] ** 2
    d["logT"] = np.log(d["T"] * config.YEAR)
    d["absdelta"] = d["delta"].abs()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
    if start_year:
        d = d[d["date"].dt.year >= start_year]
    d["cur"] = cur
    # Scale to the asset's own mean implied variance so the fitted slope is the
    # relative weekend effect and is comparable across assets. See _scale_note.
    d["iv2_scaled"] = d["iv2"] / d["iv2"].mean()
    return d[["date", "cur", "iv2", "iv2_scaled", "wknd_frac", "logT",
              "absdelta"]]


def pooled_fit(d: pd.DataFrame, assets: list[str]) -> dict:
    """Within (asset x day) fit with one weekend slope per asset.

    Every asset gets its own slope rather than a base plus interactions, so the
    restrictions below are stated directly on the coefficients of interest and
    the covariance matrix needs no reassembly.
    """
    d = d.dropna().copy()
    slope_cols = []
    for a in assets:
        col = f"w_{a}"
        d[col] = d["wknd_frac"] * (d["cur"] == a)
        slope_cols.append(col)
    cols = ["iv2_scaled"] + slope_cols + ["logT", "absdelta"]

    key = d["cur"] + "|" + d["date"].astype(str)
    dm = d[cols] - d[cols].groupby(key).transform("mean")
    dm = dm.dropna()
    X = np.column_stack([dm[c] for c in slope_cols]
                        + [dm["logT"], dm["absdelta"], dm["logT"] ** 2])
    y = dm["iv2_scaled"].to_numpy()
    XtX = X.T @ X
    beta = np.linalg.solve(XtX, X.T @ y)
    resid = y - X @ beta

    g = key.loc[dm.index].to_numpy()
    order = np.argsort(g)
    Xo, ro, go = X[order], resid[order], g[order]
    _, starts = np.unique(go, return_index=True)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for a_, b_ in zip(starts, list(starts[1:]) + [len(Xo)]):
        s = Xo[a_:b_].T @ ro[a_:b_]
        meat += np.outer(s, s)
    inv = np.linalg.inv(XtX)
    n_g = len(starts)
    cov = inv @ meat @ inv * (n_g / max(n_g - 1, 1))
    k = len(assets)
    return {"beta": beta[:k], "cov": cov[:k, :k], "se": np.sqrt(np.diag(cov))[:k],
            "n": int(len(dm)), "n_groups": n_g, "assets": assets}


def wald(beta: np.ndarray, cov: np.ndarray, R: np.ndarray,
         r: np.ndarray) -> tuple[float, int, float]:
    """Test R beta = r. Returns (stat, df, p)."""
    d = R @ beta - r
    V = R @ cov @ R.T
    stat = float(d @ np.linalg.solve(V, d))
    df = R.shape[0]
    return stat, df, float(1 - stats.chi2.cdf(stat, df))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2020)
    ap.add_argument("--assets", default=None,
                    help="comma-separated; default all with a cached tape")
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    wanted = ([x.strip() for x in a.assets.split(",")] if a.assets
              else list(config.CURRENCIES))
    assets, frames = [], []
    for c in wanted:
        try:
            f = prep(c, a.from_year)
        except FileNotFoundError:
            log.warning("%s: no cached tape, skipping", c)
            continue
        if f.empty:
            log.warning("%s: no usable trades after filters, skipping", c)
            continue
        assets.append(c)
        frames.append(f)
    if len(assets) < 2:
        print("need at least two assets")
        return 1

    d = pd.concat(frames, ignore_index=True)
    del frames
    print(f"pooled sample from {a.from_year}: {len(d):,} trades, "
          f"{len(assets)} assets")
    print(d.groupby("cur").size().to_string())

    r = pooled_fit(d, assets)
    beta, cov, se = r["beta"], r["cov"], r["se"]

    # Realized weekend effect per asset, scaled by that asset's own mean daily
    # variance so it is directly comparable with the scaled implied slope:
    # both are now (v_we - v_wd) / v_bar, a unit-free weekend discount. Its
    # standard error is carried through, because H0b uses these as scaling
    # constants and SOL's rests on a quarter as many weekend days as BTC's.
    realized, realized_se = {}, {}
    for c in assets:
        rv = weekend.realized_by_daytype(bars.load(c))
        w = weekend.weekend_variance_ratio(rv)
        vbar = float(rv["rv_daily"].mean())
        realized[c] = w["diff"] / vbar
        realized_se[c] = w["se_diff"] / vbar

    print("\n" + "=" * 74)
    print("POOLED FIT (asset x day fixed effects, clustered by asset-day)")
    print("  slopes are RELATIVE weekend effects, (v_we - v_wd)/v_bar, so they")
    print("  are comparable across assets with different volatility levels")
    print("=" * 74)
    print(f"  {'asset':>6} {'implied slope':>14} {'se':>9} {'t':>7} "
          f"{'realized':>10} {'imp/real':>9}")
    for i, c in enumerate(assets):
        ratio = beta[i] / realized[c] if abs(realized[c]) > 1e-12 else np.nan
        print(f"  {c:>6} {beta[i]:+14.4f} {se[i]:9.4f} {beta[i]/se[i]:+7.2f} "
              f"{realized[c]:+10.4f} {ratio:9.3f}")
    print(f"  n = {r['n']:,} over {r['n_groups']:,} asset-days")

    k = len(assets)
    # H0a: all implied slopes equal. Contrast each asset against the first.
    R = np.zeros((k - 1, k))
    for i in range(k - 1):
        R[i, 0], R[i, i + 1] = 1.0, -1.0
    stat, df, p = wald(beta, cov, R, np.zeros(k - 1))
    print("\n  H0a: implied slopes EQUAL across assets  (pricing by convention)")
    print(f"       chi2({df}) = {stat:.2f}, p = {p:.4f} -> "
          f"{'REJECT' if p < 0.05 else 'CANNOT REJECT'} at 5%")

    # H0b: slopes proportional to realized effects, i.e. the ratios
    # g_i = beta_i / real_i are equal for all i.
    #
    # The realized effects are estimates, not constants. Implied slopes come
    # from option quotes and realized effects from underlying returns, so the
    # two are independent and the delta method gives
    #     Var(g_i) = Var(beta_i)/real_i^2 + beta_i^2 Var(real_i)/real_i^4
    # with off-diagonal terms inherited from Cov(beta_i, beta_j) alone. Ignoring
    # the second term would overstate the precision of this test, most for the
    # asset with the shortest realized sample.
    scale = np.array([realized[c] for c in assets])
    scale_se = np.array([realized_se[c] for c in assets])
    if np.all(np.abs(scale) > 1e-12):
        g = beta / scale
        J = np.diag(1.0 / scale)
        cov_g = J @ cov @ J.T
        cov_g += np.diag((beta ** 2) * (scale_se ** 2) / (scale ** 4))
        Rb = np.zeros((k - 1, k))
        for i in range(k - 1):
            Rb[i, 0], Rb[i, i + 1] = 1.0, -1.0
        statb, dfb, pb = wald(g, cov_g, Rb, np.zeros(k - 1))
        print("\n  H0b: slopes PROPORTIONAL to realized effects  (calibration)")
        print("       implied/realized ratio per asset, with realized-effect "
              "uncertainty propagated:")
        for i, c in enumerate(assets):
            print(f"         {c:>5} {g[i]:+8.4f} (se {np.sqrt(cov_g[i, i]):.4f})")
        print(f"       chi2({dfb}) = {statb:.2f}, p = {pb:.4f} -> "
              f"{'REJECT' if pb < 0.05 else 'CANNOT REJECT'} at 5%")
    else:
        statb = dfb = pb = np.nan

    # How much of the cross-asset variation in weekend risk reaches prices?
    # This is the economically interesting quantity and does not depend on
    # either restriction being rejected.
    sd_imp = float(np.std(beta, ddof=1))
    sd_real = float(np.std(scale, ddof=1))
    shrink = sd_imp / sd_real if sd_real > 0 else np.nan
    print(f"\n  cross-asset dispersion: implied sd {sd_imp:.4f}, "
          f"realized sd {sd_real:.4f}")
    print(f"  the market transmits {shrink:.0%} of the cross-asset variation "
          f"in weekend risk")

    # A failure to reject is only informative if the test could have rejected.
    # ETH's realized weekend effect is small, so dividing by it inflates both
    # its ratio and that ratio's standard error; H0b can be near-powerless
    # while still "passing".
    ratios = beta / scale
    ratio_se = np.sqrt(np.diag(cov_g)) if np.all(np.abs(scale) > 1e-12) else None
    weak = (ratio_se is not None
            and np.any(ratio_se > np.abs(ratios)))
    print("\n  interpretation:")
    if p >= 0.05 and pb < 0.05:
        print("    convention: slopes indistinguishable across assets and")
        print("    inconsistent with tracking realized weekend risk.")
    elif p < 0.05 and pb >= 0.05 and not weak:
        print("    calibration: slopes differ across assets in proportion to")
        print("    realized weekend effects.")
    elif p < 0.05 and pb >= 0.05 and weak:
        print("    PARTIAL DIFFERENTIATION. Equality is rejected, so the")
        print("    market is not applying one flat discount. But H0b is not")
        print("    rejected only because at least one implied/realized ratio")
        print("    is estimated with a standard error exceeding its own")
        print("    magnitude, so proportionality is not established either.")
        print("    The dispersion ratio above is the informative number.")
    elif p >= 0.05 and pb >= 0.05:
        print("    INCONCLUSIVE: neither restriction is rejected. The data")
        print("    cannot separate the hypotheses at this precision.")
    else:
        print("    both restrictions rejected: the market neither applies a")
        print("    uniform discount nor calibrates proportionally.")
    out_extra = {"sd_implied": sd_imp, "sd_realized": sd_real,
                 "dispersion_ratio": shrink}

    out = pd.DataFrame({
        "asset": assets, "implied_slope": beta, "se": se,
        "t": beta / se, "realized_effect": [realized[c] for c in assets],
    })
    out["from_year"] = a.from_year
    out["n"] = r["n"]
    out["chi2_equal"] = stat
    out["p_equal"] = p
    out["chi2_proportional"] = statb
    out["p_proportional"] = pb
    for k_, v_ in out_extra.items():
        out[k_] = v_
    p_out = config.TABLES / "w5_pooled_convention_test.csv"
    out.to_csv(p_out, index=False)
    print(f"\n-> {p_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
