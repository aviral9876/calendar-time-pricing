"""Is the clock trade's coarse-rehedge profit about the weekend, or about not hedging?

Section 6.3's P&L rises monotonically as rehedging coarsens: gross +0.066 at five
minutes to +0.110 at four hours. Coarse hedging is profitable on a mean-reverting
path, and quiet weekends mean-revert, so the gain may be harvesting weekend mean
reversion rather than the weekend variance mispricing.

The test: run the same rehedge ladder on an exit that holds *no* weekend
(Saturday 00:00, i.e. Friday afternoon only) and on one that holds a weekend
(Sunday 00:00), on a common contract menu. If coarsening helps both equally, the
gain is not about the weekend.
"""
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import weekend_clock as C  # noqa: E402

from dbop import config  # noqa: E402

logging.basicConfig(level="INFO",
                    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")

LADDER = (5, 30, 60, 240)
EXITS = ("sat_00", "sun_00")

rows = []
for cur in ("BTC", "ETH"):
    d, px, half, by_inst = C.prepare(cur)
    for ex in EXITS:
        for r in LADDER:
            # alive_key pins the contract menu so the two exits trade the same
            # instruments; otherwise a later exit forces a longer-dated contract.
            b = C.run_one(d, px, 12, ex, half, by_inst, rehedge_minutes=r,
                          alive_key="sun_00")
            s = C.summarize(b, asset=cur, exit=ex, rehedge=r)
            rows.append(s)
    del d, px, by_inst

t = pd.DataFrame(rows)
cols = ["asset", "exit", "rehedge", "n", "gross_per_vega", "net_per_vega", "t",
        "hit_rate"]
t = t[[c for c in cols if c in t.columns]]
p = config.TABLES / "w41b_rehedge_by_exit.csv"
t.to_csv(p, index=False)
print(f"-> {p}")
print(t.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

print("\ngain from coarsening 5min -> 240min, per exit:")
for cur in ("BTC", "ETH"):
    for ex in EXITS:
        g = t[(t.asset == cur) & (t["exit"] == ex)].set_index("rehedge")
        if 5 in g.index and 240 in g.index:
            print(f"  {cur} {ex}: gross {g.loc[5,'gross_per_vega']:+.4f} -> "
                  f"{g.loc[240,'gross_per_vega']:+.4f}  "
                  f"(delta {g.loc[240,'gross_per_vega']-g.loc[5,'gross_per_vega']:+.4f})")
