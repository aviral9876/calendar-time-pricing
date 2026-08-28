"""Robustness and placebos for the weekend pricing result.

The headline slope has to survive the obvious referee questions: is it a
maturity artefact, does it hold outside the volatile early years, and — most
importantly — does implied variance respond to a *fake* weekend? If a placebo
pair of weekdays loads as strongly as Saturday and Sunday, the specification is
picking up something about calendar structure rather than about weekends.
"""
from __future__ import annotations

import argparse
import logging
import numpy as np
import pandas as pd

from dbop import config, tape, weekend, bars, util

log = logging.getLogger("weekend_robustness")

MAX_T_DAYS = 14
MIN_T_DAYS = 0.25
DELTA_BAND = (0.30, 0.70)


def day_fraction(all_fracs: np.ndarray, days: tuple[int, ...]) -> np.ndarray:
    """Fraction of remaining life on the given weekdays (0=Mon), from the
    precomputed (n, 7) matrix. Walking the hourly grid once per day-group ran
    out of memory on the ETH tape; `weekend.all_day_fractions` does it in a
    single pass and everything here is a column sum of that."""
    return all_fracs[:, list(days)].sum(axis=1)


def fit(d: pd.DataFrame, regressors: list[str]) -> dict:
    """Within-day OLS of squared IV on the given regressors, day-clustered SEs."""
    cols = ["iv2"] + regressors + ["logT", "absdelta"]
    d = d.dropna(subset=cols)
    if len(d) < 500:
        return {}
    g = d.groupby("date")[cols]
    dm = (d[cols] - g.transform("mean")).dropna()
    X = np.column_stack([dm[r] for r in regressors]
                        + [dm["logT"], dm["absdelta"], dm["logT"] ** 2])
    y = dm["iv2"].to_numpy()
    XtX = X.T @ X
    try:
        beta = np.linalg.solve(XtX, X.T @ y)
    except np.linalg.LinAlgError:
        return {}
    resid = y - X @ beta
    days = d.loc[dm.index, "date"].to_numpy()
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
    se = np.sqrt(np.diag(cov))
    out = {"n": int(len(dm)), "n_days": int(n_g)}
    for i, r in enumerate(regressors):
        out[f"b_{r}"] = float(beta[i])
        out[f"t_{r}"] = float(beta[i] / se[i])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", default="BTC")
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)
    cur = a.currency

    df = tape.load(cur, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    d = d.loc[d["iv_ok"] & d["delta"].notna()
              & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
              & d["delta"].abs().between(*DELTA_BAND)].copy()
    d = weekend.attach(d)
    d["T_days"] = d["T"] * config.YEAR
    d["iv2"] = d["sigma"] ** 2
    d["logT"] = np.log(d["T_days"])
    d["absdelta"] = d["delta"].abs()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
    d["year"] = d["date"].dt.year

    fr = weekend.all_day_fractions(d["timestamp"].to_numpy(),
                                   d["expiration_timestamp"].to_numpy())
    d["placebo_tuewed"] = day_fraction(fr, (1, 2))
    d["placebo_thufri"] = day_fraction(fr, (3, 4))
    d["sunmon_frac"] = day_fraction(fr, (6, 0))
    del fr

    print("=" * 84)
    print(f"{cur}: ROBUSTNESS OF THE WEEKEND SLOPE (squared IV, within-day)")
    print("=" * 84)

    rows = []
    base = fit(d, ["wknd_frac"])
    print(f"\n{'specification':>34} {'slope':>10} {'t':>7} {'n':>10} {'days':>6}")

    def show(label, r, key="wknd_frac"):
        if not r:
            print(f"{label:>34} {'--':>10}"); return
        print(f"{label:>34} {r[f'b_{key}']:+10.4f} {r[f't_{key}']:+7.2f} "
              f"{r['n']:10,d} {r['n_days']:6,d}")
        rows.append({"spec": label, "slope": r[f"b_{key}"], "t": r[f"t_{key}"],
                     "n": r["n"], "n_days": r["n_days"]})

    show("baseline", base)

    # Maturity slices
    for lo, hi, nm in ((0.25, 3, "T <= 3d"), (3, 7, "3-7d"), (7, 14, "7-14d")):
        show(nm, fit(d[d.T_days.between(lo, hi)], ["wknd_frac"]))

    # Periods
    for lo, hi, nm in ((2016, 2020, "2016-2020"), (2021, 2022, "2021-2022"),
                       (2023, 2024, "2023-2024"), (2025, 2027, "2025-2026")):
        show(nm, fit(d[d.year.between(lo, hi)], ["wknd_frac"]))
    show("ex-2020 (covid)", fit(d[d.year != 2020], ["wknd_frac"]))

    # Tighter ATM band
    show("|delta| in 0.45-0.55",
         fit(d[d.absdelta.between(0.45, 0.55)], ["wknd_frac"]))

    print("\n" + "=" * 84)
    print("PLACEBO: does implied variance respond to FAKE weekends?")
    print("=" * 84)
    print("  Horse race -- true weekend and a placebo pair entered together.")
    for pl in ("placebo_tuewed", "placebo_thufri", "sunmon_frac"):
        r = fit(d, ["wknd_frac", pl])
        if not r:
            continue
        print(f"\n  vs {pl}:")
        print(f"    weekend  {r['b_wknd_frac']:+.4f} (t {r['t_wknd_frac']:+.2f})")
        print(f"    {pl:14s} {r[f'b_{pl}']:+.4f} (t {r[f't_{pl}']:+.2f})")
        rows.append({"spec": f"horse race vs {pl}", "slope": r["b_wknd_frac"],
                     "t": r["t_wknd_frac"], "n": r["n"], "n_days": r["n_days"],
                     "placebo_slope": r[f"b_{pl}"], "placebo_t": r[f"t_{pl}"]})

    print("\n" + "=" * 84)
    print("REALIZED variance by the same day groupings (is the placebo real?)")
    print("=" * 84)
    rv = bars.load(cur)
    rv = rv.assign(ts=pd.to_datetime(rv["timestamp"], unit="ms", utc=True))
    rv["r"] = np.log(rv["close"].astype(float)).diff()
    day = rv.groupby(rv["ts"].dt.normalize())["r"].apply(lambda s: np.nansum(s**2))
    day = day[day > 0]
    dd = pd.DataFrame({"rv": day}); dd["dow"] = dd.index.dayofweek
    allmean = dd["rv"].mean()
    for nm, days in (("Sat+Sun", (5, 6)), ("Tue+Wed", (1, 2)),
                     ("Thu+Fri", (3, 4)), ("Sun+Mon", (6, 0))):
        sub = dd[dd.dow.isin(days)]["rv"].mean()
        oth = dd[~dd.dow.isin(days)]["rv"].mean()
        print(f"  {nm:9s} variance ratio vs other days: {sub/oth:.4f}")

    out = pd.DataFrame(rows)
    out.insert(0, "currency", cur)
    p = config.TABLES / f"w3_robustness_{cur}.csv"
    out.to_csv(p, index=False)
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
