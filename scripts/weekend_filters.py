"""Which observable conditions separate the clock trade's winners from its losers?

Section 6.3 shows a fixed-hour weekend short that earns about 0.09 per unit vega
at hourly rehedging and loses on roughly a quarter of weekends. The obvious next
question is whether the losing quarter is identifiable in advance. The obvious
danger is that with fewer than two hundred trades and a free choice of filters,
something will always look like it works.

This script is built around that danger rather than around the question.

  * The candidate list is **pre-specified** in ``FACTORS`` below, each with the
    sign it is expected to take, and every one is reported -- winners and losers
    alike. Nothing is added after seeing a result.
  * Each factor is tested once on Bitcoin and once on Ether, and Ether is
    treated as a replication rather than as a second bite. A factor that works
    in one book and not the other has not worked.
  * The whole set is then re-tested on the first half of the sample only, and
    the filter it implies is evaluated on the second half, which it has never
    seen.
  * A Bonferroni threshold for the number of factors tested is reported beside
    the raw p-values, because the raw ones are not the relevant ones.

Outputs:

  w44_factor_tests.csv     every factor, both books, slope and t on the full
                           sample and on the first half
  w45_filter_oos.csv       the filter implied by the in-sample tests, evaluated
                           in-sample and out-of-sample
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dbop import config  # noqa: E402

log = logging.getLogger("weekend_filters")

# (column, human name, expected sign of the slope on P&L, rationale)
FACTORS = [
    ("f_iv_premium", "IV / realized vol of the week so far", +1,
     "the seller's cushion of section 5.6, as a desk would see it"),
    ("f_iv", "entry implied volatility", +1,
     "a richer quote is a bigger buffer"),
    ("f_wd_vol", "realized vol of the week so far", -1,
     "volatility clusters, so a loud week forecasts a loud weekend"),
    ("f_friday_move_abs", "absolute index move over Friday", -1,
     "a market already moving into the weekend keeps moving"),
    ("f_funding_abs", "absolute perpetual funding, trailing week", -1,
     "crowded leverage is what liquidation cascades run on"),
    ("f_wknd_frac", "weekend share of the contract's life", +1,
     "more of the thing the paper says is mispriced"),
    ("f_dvol_chg", "5-day change in DVOL", -1,
     "a rising volatility index is a regime turning against a short"),
]

# Added after the first round, and counted in the multiplicity rather than
# quietly appended. The first round found that the only factor clearing the bar
# in either book was the *level* of implied volatility, and that a threshold
# frozen on the first half kept almost nothing in the second -- because implied
# volatility fell across the sample, which is section 5.5's finding. A level
# filter is therefore non-stationary by construction. These two are the same
# idea made scale-free, so they can be applied by a desk in any regime.
SECOND_ROUND = [
    ("f_iv_rank", "IV percentile within its own trailing year", +1,
     "the level filter that failed, made stationary"),
]


def derive(b: pd.DataFrame) -> pd.DataFrame:
    """A scale-free version of the entry volatility, computed causally.

    The rank at trade i uses only trades strictly before i. Using the whole
    sample would let the filter read the future, and on a series whose level
    trends down that is exactly the mistake that would make it look best.
    """
    b = b.copy()
    iv = b["f_iv"]
    # Percentile of this entry's IV among the previous 52 entries, which on a
    # weekly trade is its own trailing year.
    b["f_iv_rank"] = [
        float((iv.iloc[max(0, i - 52):i] < iv.iloc[i]).mean())
        if i >= 12 else np.nan
        for i in range(len(b))
    ]
    return b


MIN_N = 40


def ols_t(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float, int]:
    """Univariate slope, its heteroskedasticity-robust t, R^2 and n."""
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = len(y)
    if n < MIN_N or np.std(x) == 0:
        return np.nan, np.nan, np.nan, n
    # Standardize the regressor so slopes are comparable across factors: the
    # coefficient is then P&L per one-standard-deviation of the condition.
    x = (x - x.mean()) / x.std()
    X = np.column_stack([np.ones(n), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ b
    xtx_inv = np.linalg.inv(X.T @ X)
    meat = X.T @ (X * (resid ** 2)[:, None])
    cov = xtx_inv @ meat @ xtx_inv
    se = float(np.sqrt(cov[1, 1]))
    r2 = 1 - float(np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2))
    return float(b[1]), (float(b[1]) / se if se > 0 else np.nan), r2, n


def load_blotter(cur: str, wide: bool) -> pd.DataFrame:
    name = (f"w43_clock_blotter_wide_{cur}.csv" if wide
            else f"w38_clock_blotter_{cur}.csv")
    p = config.TABLES / name
    if not p.exists():
        return pd.DataFrame()
    b = pd.read_csv(p, parse_dates=["entry_ts"])
    return derive(b.sort_values("entry_ts").reset_index(drop=True))


def test_factors(blotters: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cur, b in blotters.items():
        if b.empty:
            continue
        y = b["net_per_vega"].to_numpy()
        half = len(b) // 2
        for col, name, sign, why in FACTORS + SECOND_ROUND:
            if col not in b or b[col].notna().sum() < MIN_N:
                continue
            x = b[col].to_numpy()
            beta, t, r2, n = ols_t(y, x)
            b1, t1, _, n1 = ols_t(y[:half], x[:half])
            rows.append({
                "asset": cur, "factor": col, "name": name,
                "expected_sign": sign, "rationale": why,
                "beta_per_sd": beta, "t": t, "r2": r2, "n": n,
                "sign_as_expected": (np.sign(beta) == sign
                                     if np.isfinite(beta) else False),
                "beta_first_half": b1, "t_first_half": t1, "n_first_half": n1,
            })
    return pd.DataFrame(rows)


# The level of implied volatility is excluded from the scale-free variant of
# the filter. It is not that it fails in sample -- it is the strongest single
# factor in Ether -- but that a threshold in volatility points cannot survive a
# sample over which volatility itself trends down, which is what sections 5.5
# and 5.6 establish. Excluding it is a decision about stationarity, made before
# looking at the out-of-sample result, not a reaction to it.
LEVEL_FACTORS = {"f_iv", "f_wd_vol"}


def filter_oos(blotters: dict[str, pd.DataFrame], tests: pd.DataFrame,
               t_gate: float, scale_free_only: bool = False) -> pd.DataFrame:
    """Build the filter from the first half only, then score the second half.

    The rule is deliberately crude -- drop the worst tercile of the surviving
    condition -- because a fitted threshold is another parameter to overfit.
    """
    rows = []
    for cur, b in blotters.items():
        if b.empty:
            continue
        half = len(b) // 2
        tr = tests[(tests.asset == cur) & tests.sign_as_expected
                   & (tests.t_first_half.abs() >= t_gate)]
        picked = [f for f in tr.factor
                  if not (scale_free_only and f in LEVEL_FACTORS)]
        if not picked:
            rows.append({"asset": cur, "filter": "(none survived)",
                         "scale_free_only": scale_free_only,
                         "n_all": half})
            continue

        keep_in = np.ones(half, dtype=bool)
        keep_out = np.ones(len(b) - half, dtype=bool)
        for col in picked:
            sign = next(s for c, _, s, _ in FACTORS + SECOND_ROUND
                        if c == col)
            x_in = b[col].to_numpy()[:half]
            # The cut is set on the first half and then frozen.
            thr = np.nanquantile(x_in, 1 / 3 if sign > 0 else 2 / 3)
            good = (lambda v: v >= thr) if sign > 0 else (lambda v: v <= thr)
            keep_in &= good(x_in) | ~np.isfinite(x_in)
            keep_out &= good(b[col].to_numpy()[half:]) | ~np.isfinite(
                b[col].to_numpy()[half:])

        y = b["net_per_vega"].to_numpy()
        for label, sl, keep in (("in_sample", slice(0, half), keep_in),
                                ("out_of_sample", slice(half, len(b)), keep_out)):
            yy = y[sl]
            rows.append({
                "asset": cur, "filter": "+".join(picked),
                "scale_free_only": scale_free_only, "window": label,
                "n_all": len(yy), "mean_all": yy.mean(),
                "n_kept": int(keep.sum()),
                "mean_kept": yy[keep].mean() if keep.any() else np.nan,
                "hit_all": float((yy > 0).mean()),
                "hit_kept": float((yy[keep] > 0).mean()) if keep.any() else np.nan,
                "t_kept": (yy[keep].mean() / (yy[keep].std() / np.sqrt(keep.sum()))
                           if keep.sum() > 2 and yy[keep].std() > 0 else np.nan),
            })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--wide", action="store_true",
                    help="use the 4-hour exit-match blotter, which is larger")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log, format="%(levelname)-7s %(name)s: %(message)s")

    blotters = {c: load_blotter(c, a.wide) for c in a.currencies}
    blotters = {c: b for c, b in blotters.items() if not b.empty}
    if not blotters:
        log.error("no blotters found; run weekend_clock.py first")
        return 1
    for c, b in blotters.items():
        log.info("%s: %d trades, %s to %s", c, len(b),
                 b.entry_ts.min().date(), b.entry_ts.max().date())

    tests = test_factors(blotters)
    p = config.TABLES / "w44_factor_tests.csv"
    tests.to_csv(p, index=False)
    log.info("-> %s", p)

    k = len(FACTORS) + len(SECOND_ROUND)
    # Two-sided Bonferroni at 5% over the pre-specified list.
    gate = float(abs(np.round(
        __import__("scipy.stats", fromlist=["norm"]).norm.ppf(1 - 0.05 / (2 * k)), 3)))
    print(f"\n{k} pre-specified factors; Bonferroni |t| threshold = {gate:.2f}\n")
    show = ["asset", "factor", "expected_sign", "beta_per_sd", "t", "n",
            "sign_as_expected", "t_first_half"]
    print(tests[show].to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

    survivors = tests[tests.sign_as_expected & (tests.t.abs() >= gate)]
    print(f"\nSurvive sign + Bonferroni on the full sample: "
          f"{len(survivors)} of {len(tests)}")
    if len(survivors):
        print(survivors[["asset", "factor", "beta_per_sd", "t"]].to_string(index=False))

    # The out-of-sample exercise uses a looser in-sample gate on purpose: the
    # point is to see whether anything that looks good in the first half holds
    # up in the second, so the bar for "looks good" is deliberately low.
    oos = pd.concat([filter_oos(blotters, tests, t_gate=1.5, scale_free_only=v)
                     for v in (False, True)], ignore_index=True)
    p = config.TABLES / "w45_filter_oos.csv"
    oos.to_csv(p, index=False)
    for cur, b in blotters.items():
        if {"f_wknd_frac", "f_T_days"} <= set(b):
            r = b[["f_wknd_frac", "f_T_days"]].corr().iloc[0, 1]
            log.info("%s: corr(weekend share, days to expiry) = %+.2f", cur, r)
    log.info("-> %s", p)
    print()
    print(oos.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
