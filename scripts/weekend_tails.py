"""Weekend tail risk: is the weekend quieter in scale but fatter in shape?

§7 of the paper asks whether the residual pricing gap has a risk-based reading.
Average realized variance is lower at the weekend, but an option is not priced
off average variance alone: if weekend returns are more prone to jumps once the
volatility difference is removed, options may be rich against realized weekend
variance for a perfectly good reason.

The comparison must therefore be about shape, not scale. Returns are standardized
within each regime by that regime's own standard deviation before the tail
frequencies and skew are computed, so a weekend that is merely quieter registers
as identical here and only a genuine difference in the distribution shows up.

These statistics were computed by hand for an earlier draft and never scripted,
which meant §7 was the one section that could not be regenerated from the repo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

import numpy as np
import pandas as pd

from dbop import bars, config, weekend

log = logging.getLogger("weekend_tails")

# Thresholds in standard deviations. Five is where a Gaussian is already
# negligible (~0.6 bp two-sided) so the counts are all tail; eight separates
# "fat" from "jump" without emptying the sample at these lengths.
CUTOFFS = (5.0, 8.0)


def five_minute_returns(b: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame({"ts": pd.to_datetime(b["ts"], utc=True)})
    d["r"] = np.log(b["close"].astype("float64")).diff()
    d = d.dropna(subset=["r"])
    # A bar spanning a gap in the series is a multi-period return wearing a
    # five-minute label; those are what corrupted an earlier version of this
    # table, so drop anything that does not follow its predecessor by one bar.
    step = pd.Timedelta(minutes=config.BAR_MINUTES)
    d = d[d["ts"].diff() == step]
    d["is_weekend"] = d["ts"].dt.dayofweek >= 5
    return d


def stats(d: pd.DataFrame) -> dict:
    out = {}
    for label, mask in (("weekday", ~d["is_weekend"]), ("weekend", d["is_weekend"])):
        r = d.loc[mask, "r"].to_numpy()
        sd = r.std(ddof=1)
        z = r / sd
        out[f"n_{label}"] = int(len(r))
        out[f"sd_{label}"] = float(sd)
        for c in CUTOFFS:
            out[f"p{c:.0f}_{label}_bp"] = float((np.abs(z) > c).mean() * 1e4)
        out[f"skew_{label}"] = float(pd.Series(z).skew())
    for c in CUTOFFS:
        a, b_ = out[f"p{c:.0f}_weekday_bp"], out[f"p{c:.0f}_weekend_bp"]
        out[f"p{c:.0f}_ratio"] = float(b_ / a) if a > 0 else np.nan
    out["skew_ratio"] = (out["skew_weekend"] / out["skew_weekday"]
                         if out["skew_weekday"] != 0 else np.nan)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    rows = []
    for cur in config.CURRENCIES:
        d = five_minute_returns(bars.load(cur, check=False))
        rows.append({"asset": cur, **stats(d)})
    for name, instrument in config.REFERENCE_ASSETS.items():
        b = bars.fetch_bars(instrument, config.REFERENCE_START[name],
                            dt.datetime.now(dt.timezone.utc).date(),
                            resolution=str(config.BAR_MINUTES))
        rows.append({"asset": name, **stats(five_minute_returns(b))})

    out = pd.DataFrame(rows)
    print("\nStandardized within regime, so these are shape not scale")
    print("=" * 78)
    print(f"  {'asset':>6} {'P(|z|>5) wd->we, bp':>26} "
          f"{'P(|z|>8) wd->we, bp':>26} {'skew wd->we':>22}")
    for _, r in out.iterrows():
        print(f"  {r['asset']:>6} "
              f"{r['p5_weekday_bp']:9.1f} -> {r['p5_weekend_bp']:6.1f} "
              f"(x{r['p5_ratio']:.2f})  "
              f"{r['p8_weekday_bp']:7.1f} -> {r['p8_weekend_bp']:5.1f} "
              f"(x{r['p8_ratio']:.2f})  "
              f"{r['skew_weekday']:+6.2f} -> {r['skew_weekend']:+6.2f}")

    p = config.TABLES / "w10_weekend_tails.csv"
    out.round(6).to_csv(p, index=False)
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
