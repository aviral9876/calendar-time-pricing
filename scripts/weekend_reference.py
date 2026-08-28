"""Realized weekend profile for assets whose reference market actually closes.

The four traded underlyings all sit in a narrow band -- realized weekend/weekday
variance ratios of 0.58 to 0.66 -- which is itself the mechanism evidence but
leaves the cross-section with almost no spread to work with. The obvious way to
widen it is an underlying whose *reference* market is shut at the weekend rather
than merely quiet.

Tokenized gold is that asset. PAXG tracks spot gold, which trades in London and
on COMEX from Sunday 22:00 to Friday 22:00 UTC, while the PAXG perpetual on
Deribit trades continuously exactly like the crypto books. So the venue is open
and the underlying's price-formation market is closed -- the same separation the
paper exploits, but with the traditional-market channel turned up rather than
merely present.

This stage is realized-side only, and deliberately so: PAXG's Deribit options
expire almost exclusively on Fridays, so no within-day variation in weekend
exposure survives the maturity controls. It contributes a variance profile, not
a priced slope, and the paper reports it as such.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from dbop import bars, config, weekend

log = logging.getLogger("weekend_reference")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def profile(name: str, instrument: str, start) -> tuple[pd.Series, dict]:
    b = bars.fetch_bars(instrument, start,
                        pd.Timestamp.now("UTC").date(), resolution="5")
    if b.empty:
        raise RuntimeError(f"{name}: no bars for {instrument}")
    rv = weekend.realized_by_daytype(b)
    dow = rv.groupby(rv["date"].dt.dayofweek)["ann_vol"].mean() * 100
    dow.index = [DAYS[i] for i in dow.index]
    stats = weekend.weekend_variance_ratio(rv)
    stats["n_days"] = int(len(rv))
    stats["first"] = str(rv["date"].min().date())
    stats["last"] = str(rv["date"].max().date())
    return dow, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="WARNING")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    dows, rows = {}, []
    for name, instrument in config.REFERENCE_ASSETS.items():
        dow, st = profile(name, instrument, config.REFERENCE_START[name])
        dows[name] = dow
        rows.append({"asset": name, "instrument": instrument, **st})
        print(f"\n{name} ({instrument}), {st['n_days']} days "
              f"{st['first']}..{st['last']}")
        print("  annualized vol by weekday (%):")
        print("   ", dow.round(1).to_dict())
        print(f"  weekend/weekday variance ratio: {st['variance_ratio']:.3f} "
              f"({st['n_weekend']} weekend days, {st['n_weekday']} weekday)")
        # The realized effect scaled by the asset's own mean variance, so it is
        # directly comparable with the scaled effects in the pooled test.
        vbar = (st["var_weekday"] * st["n_weekday"]
                + st["var_weekend"] * st["n_weekend"]) / st["n_days"]
        print(f"  scaled realized effect: {st['diff'] / vbar:+.4f}")
        rows[-1]["scaled_effect"] = st["diff"] / vbar

    out = pd.DataFrame(rows)
    p = config.TABLES / "w8_reference_assets.csv"
    out.to_csv(p, index=False)
    d = pd.DataFrame(dows).T
    pd.DataFrame(d).round(1).to_csv(config.TABLES / "w9_reference_vol_by_dow.csv",
                                    index_label="asset")
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
