"""Does the market price the whole day-of-week variance profile, or just apply
a crude weekend haircut?

A binary weekend split is too coarse, and pitting a "placebo" day-pair against
the weekend in a two-way race is unreadable, because the day fractions of an
option's life sum to one: any two of them are mechanically collinear. The clean
specification puts the fraction of remaining life falling on each weekday into
the regression at once, omitting one as the reference, so the coefficients trace
out the market's implied variance profile across the week. That profile can then
be compared, day by day, with the realized one.

    sigma^2 = sum_d v_d * f_d,   sum_d f_d = 1

so regressing squared implied vol on the six non-reference fractions gives
v_d - v_ref for each day, with day fixed effects absorbing the level.
"""
from __future__ import annotations

import argparse
import logging
import numpy as np
import pandas as pd

from dbop import config, tape, weekend, bars, util

log = logging.getLogger("weekend_profile")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
REF = 6                      # Sunday is the reference day


def implied_profile(d: pd.DataFrame) -> pd.DataFrame:
    fracs = [f"f_{DAYS[i]}" for i in range(7) if i != REF]
    cols = ["iv2"] + fracs + ["logT", "absdelta"]
    d = d.dropna(subset=cols)
    g = d.groupby("date")[cols]
    dm = (d[cols] - g.transform("mean")).dropna()
    X = np.column_stack([dm[f] for f in fracs]
                        + [dm["logT"], dm["absdelta"], dm["logT"] ** 2])
    y = dm["iv2"].to_numpy()
    XtX = X.T @ X
    beta = np.linalg.solve(XtX, X.T @ y)
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

    rows = []
    for i, f in enumerate(fracs):
        rows.append({"day": f[2:], "coef_vs_ref": beta[i], "se": se[i],
                     "t": beta[i] / se[i]})
    rows.append({"day": DAYS[REF], "coef_vs_ref": 0.0, "se": np.nan,
                 "t": np.nan})
    out = pd.DataFrame(rows).set_index("day").reindex(DAYS)
    out.attrs["n"] = len(dm)
    out.attrs["n_days"] = n_g
    return out


def realized_profile(cur: str) -> pd.Series:
    b = bars.load(cur)
    b = b.assign(ts=pd.to_datetime(b["timestamp"], unit="ms", utc=True))
    b["r"] = np.log(b["close"].astype(float)).diff()
    day = b.groupby(b["ts"].dt.normalize())["r"].apply(
        lambda s: np.nansum(s.to_numpy() ** 2))
    day = day[day > 0] * config.YEAR              # annualized variance
    s = day.groupby(day.index.dayofweek).mean()
    s.index = [DAYS[i] for i in s.index]
    return s.reindex(DAYS)


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
    T = d["T"] * config.YEAR
    d = d.loc[d["iv_ok"] & d["delta"].notna() & T.between(0.25, 14)
              & d["delta"].abs().between(0.30, 0.70)].copy()
    d = weekend.attach(d)
    d["iv2"] = d["sigma"] ** 2
    d["logT"] = np.log(d["T"] * config.YEAR)
    d["absdelta"] = d["delta"].abs()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))

    fr = weekend.all_day_fractions(d["timestamp"].to_numpy(),
                                   d["expiration_timestamp"].to_numpy())
    for i, nm in enumerate(DAYS):
        d[f"f_{nm}"] = fr[:, i]
    del fr

    imp = implied_profile(d)
    real = realized_profile(cur)

    # Put both on the same footing: variance relative to the Sunday reference.
    ref_real = real[DAYS[REF]]
    real_rel = real - ref_real

    print("=" * 78)
    print(f"{cur}: DAY-OF-WEEK VARIANCE PROFILE, IMPLIED vs REALIZED")
    print(f"     (annualized variance relative to {DAYS[REF]}; "
          f"n={imp.attrs['n']:,} over {imp.attrs['n_days']:,} days)")
    print("=" * 78)
    print(f"{'day':>5} {'implied':>10} {'t':>7} {'realized':>10} "
          f"{'imp/real':>9}")
    for nm in DAYS:
        i, r = imp.loc[nm, "coef_vs_ref"], real_rel[nm]
        t = imp.loc[nm, "t"]
        ratio = i / r if abs(r) > 1e-9 else np.nan
        ts = f"{t:+7.2f}" if np.isfinite(t) else "    ref"
        print(f"{nm:>5} {i:+10.4f} {ts} {r:+10.4f} {ratio:9.3f}")

    # How much of the realized spread across the week does the market price?
    imp_spread = imp["coef_vs_ref"].max() - imp["coef_vs_ref"].min()
    real_spread = real_rel.max() - real_rel.min()
    print(f"\n  spread across the week: implied {imp_spread:.4f}, "
          f"realized {real_spread:.4f}")
    print(f"  the market prices {imp_spread/real_spread:.1%} of the realized "
          f"day-of-week variance spread")

    # Regression of implied on realized across the seven days
    x = real_rel.to_numpy(); y = imp["coef_vs_ref"].to_numpy()
    ok = np.isfinite(x) & np.isfinite(y)
    slope, icept = np.polyfit(x[ok], y[ok], 1)
    corr = np.corrcoef(x[ok], y[ok])[0, 1]
    print(f"  implied = {icept:+.4f} + {slope:.3f} * realized   "
          f"(corr {corr:+.3f})")
    print(f"  a fully calibrated market would give slope 1.0")

    out = pd.DataFrame({"implied_vs_ref": imp["coef_vs_ref"],
                        "t": imp["t"], "realized_vs_ref": real_rel})
    out.insert(0, "currency", cur)
    p = config.TABLES / f"w4_dow_profile_{cur}.csv"
    out.to_csv(p)
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
