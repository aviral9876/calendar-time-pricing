"""Academic path: is weekend variance priced, and by how much?

Identification is within-day. Total variance over an option's life is

    sigma^2 = v_wd + (v_we - v_wd) * w

where w is the fraction of remaining life falling on a Saturday or Sunday. With
date fixed effects the slope on w is identified purely from contracts trading at
the same instant that differ in weekend coverage, so the level of volatility,
the state of the market, and anything else common to the day drop out. Deribit's
daily expiries on all seven weekdays are what make that variation exist.
"""
from __future__ import annotations

import argparse
import logging
import numpy as np
import pandas as pd

from dbop import config, tape, weekend, bars, util

log = logging.getLogger("weekend_academic")

MAX_T_DAYS = 14          # weekend coverage barely varies beyond this
MIN_T_DAYS = 0.25
DELTA_BAND = (0.30, 0.70)


def load_sample(currency: str) -> pd.DataFrame:
    df = tape.load(currency, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    keep = (d["iv_ok"] & d["delta"].notna()
            & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
            & d["delta"].abs().between(*DELTA_BAND))
    d = d.loc[keep].copy()
    d = weekend.attach(d)
    d["T_days"] = d["T"] * config.YEAR
    d["iv2"] = d["sigma"] ** 2
    d["logT"] = np.log(d["T_days"])
    d["absdelta"] = d["delta"].abs()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
    return d.dropna(subset=["iv2", "wknd_frac", "logT", "absdelta"])


def within_day_fit(d: pd.DataFrame) -> dict:
    """Regress squared IV on weekend fraction with day fixed effects.

    Demeaning by day is equivalent to day dummies and far cheaper at this size.
    Controls enter demeaned too, so the slope is identified off contracts quoted
    the same day.
    """
    cols = ["iv2", "wknd_frac", "logT", "absdelta"]
    g = d.groupby("date")[cols]
    dm = d[cols] - g.transform("mean")
    dm = dm.dropna()
    X = np.column_stack([dm["wknd_frac"], dm["logT"], dm["absdelta"],
                         dm["logT"] ** 2])
    y = dm["iv2"].to_numpy()
    XtX = X.T @ X
    beta = np.linalg.solve(XtX, X.T @ y)
    resid = y - X @ beta

    # Cluster by day: contracts quoted on the same day share shocks.
    days = d.loc[dm.index, "date"].to_numpy()
    order = np.argsort(days)
    Xo, ro = X[order], resid[order]
    _, starts = np.unique(days[order], return_index=True)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for a, b in zip(starts, list(starts[1:]) + [len(Xo)]):
        Xg, rg = Xo[a:b], ro[a:b]
        s = Xg.T @ rg
        meat += np.outer(s, s)
    XtX_inv = np.linalg.inv(XtX)
    n_g = len(starts)
    cov = XtX_inv @ meat @ XtX_inv * (n_g / max(n_g - 1, 1))
    se = np.sqrt(np.diag(cov))

    # The day fixed effects absorb the intercept, so recover the weekday
    # variance level as the mean fitted value at w = 0.
    base = float((d.loc[dm.index, "iv2"]
                  - beta[0] * d.loc[dm.index, "wknd_frac"]).mean())
    return {
        "n": int(len(dm)), "n_days": int(n_g),
        "slope": float(beta[0]), "se": float(se[0]),
        "t": float(beta[0] / se[0]),
        "v_weekday_implied": base,
        "implied_ratio": float((base + beta[0]) / base) if base > 0 else np.nan,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", default=None)
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    currencies = [a.currency] if a.currency else list(config.CURRENCIES)
    rows = []
    for cur in currencies:
        print("=" * 78)
        print(f"{cur}")
        print("=" * 78)

        rv = weekend.realized_by_daytype(bars.load(cur))
        real = weekend.weekend_variance_ratio(rv)
        print(f"\nRealized (daily RV, {real['n_weekday']} weekday / "
              f"{real['n_weekend']} weekend days)")
        print(f"  weekday variance {real['var_weekday']:.6f}   "
              f"weekend variance {real['var_weekend']:.6f}")
        print(f"  variance ratio   {real['variance_ratio']:.4f}   "
              f"(vol ratio {real['vol_ratio']:.4f})")

        d = load_sample(cur)
        print(f"\nImplied sample: {len(d):,} trades, {d.date.nunique():,} days, "
              f"{d.T_days.min():.2f}-{d.T_days.max():.1f}d to expiry")
        print(f"  weekend fraction: mean {d.wknd_frac.mean():.3f}, "
              f"sd {d.wknd_frac.std():.3f}, "
              f"10-90pct {d.wknd_frac.quantile(.1):.3f}-{d.wknd_frac.quantile(.9):.3f}")

        fit = within_day_fit(d)
        print(f"\nWithin-day fit of squared IV on weekend fraction")
        print(f"  slope (v_we - v_wd)  {fit['slope']:+.6f}  "
              f"(se {fit['se']:.6f}, t {fit['t']:+.1f})")
        print(f"  implied v_weekday    {fit['v_weekday_implied']:.6f}")
        print(f"  IMPLIED ratio        {fit['implied_ratio']:.4f}")
        print(f"  REALIZED ratio       {real['variance_ratio']:.4f}")
        gap = fit["implied_ratio"] - real["variance_ratio"]
        print(f"  gap                  {gap:+.4f}   "
              f"({'options OVERprice weekends' if gap > 0 else 'options UNDERprice weekends'})")
        print(f"\n  n = {fit['n']:,} trades over {fit['n_days']:,} days, "
              f"SEs clustered by day")

        rows.append({"currency": cur, **real, **fit, "gap": gap})
        del d

    out = pd.DataFrame(rows)
    config.TABLES.mkdir(parents=True, exist_ok=True)
    path = config.TABLES / "w1_weekend_pricing.csv"
    # Merge with whatever is already there so a single-currency run refreshes
    # its own row instead of discarding the other one -- otherwise the figures
    # silently plot half the evidence.
    if path.exists():
        prev = pd.read_csv(path)
        out = (pd.concat([prev[~prev["currency"].isin(out["currency"])], out],
                         ignore_index=True)
                 .sort_values("currency"))
    out.to_csv(path, index=False)
    print(f"\n-> {path}  ({', '.join(out['currency'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
