"""Run the whole weekend pipeline in sequence.

Sequentially, deliberately: each stage loads a multi-million-row tape, and
running them concurrently is what exhausted memory before. Each stage is
skipped if its output already exists unless --force is passed, so a partial run
can be resumed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from dbop import config

ROOT = Path(__file__).resolve().parent.parent

ASSETS = config.CURRENCIES

STAGES = (
    [(f"pricing {c}", ["weekend_academic.py", "--currency", c], None)
     for c in ASSETS]
    # The trading test was previously run by hand, which left §6 outside the
    # one-command reproduction the paper claims. It belongs in the sequence.
    + [(f"trading test {c}", ["weekend_commercial.py", "--currency", c],
        f"w2_weekend_trade_{c}.csv") for c in ASSETS]
    + [(f"robustness {c}", ["weekend_robustness.py", "--currency", c],
        f"w3_robustness_{c}.csv") for c in ASSETS]
    + [(f"dow profile {c}", ["weekend_profile.py", "--currency", c],
        f"w4_dow_profile_{c}.csv") for c in ASSETS]
    + [("convention test", ["weekend_pooled.py"],
        "w5_pooled_convention_test.csv"),
       # Realized-side only, and cheap: bars rather than a tape. Kept out of the
       # per-asset loop above because these assets have no usable option book.
       ("reference assets", ["weekend_reference.py"], "w8_reference_assets.csv"),
       ("weekend tails", ["weekend_tails.py"], "w10_weekend_tails.csv"),
       # Reads w1, so it must follow the pricing stages; the figure stage in
       # turn reads its output, so it must precede that.
       ("risk horse race", ["weekend_riskrace.py"], "w12_risk_horse_race.csv"),
       # Runs off the sample cache the horse race writes, so it must follow it;
       # takes seconds rather than the hour a tape reload would.
       ("vintage vs window", ["weekend_split.py"], "w16_split_windows.csv"),
       ("wing anatomy", ["weekend_wings.py"], "w22_wing_amplification.csv"),
       # Reads the same cached smile samples as the split stage and the 5-minute
       # bars, so it must follow the pricing stages but costs minutes, not
       # hours. Its w31 output feeds the learning figure.
       ("what the market tracks", ["weekend_learning.py"],
        "w26_trend_by_moment.csv"),
       # Runs after the commercial stage because it refits the same spread; the
       # tape load dominates, so it is the slowest stage in the pipeline.
       ("date-wise P&L and weekend behaviour", ["weekend_short.py"],
        "w33_short_by_year.csv"),
       # Sweeps contract selection on top of the same engine; reloads the tape
       # once per currency and is limited to the two mature books.
       ("contract-selection sweep", ["weekend_params.py"],
        "w56_param_sweep.csv"),
       # Reloads the tape a third time and is the slowest stage after backfill;
       # --grid adds the exit and rehedge ladders section 6.3 reports.
       ("fixed-hour entry and exit", ["weekend_clock.py", "--grid"],
        "w39_clock_grid.csv"),
       # Reads the blotters the clock stage writes, so it needs no tape of its
       # own and runs in seconds.
       ("pre-specified entry filters", ["weekend_filters.py", "--wide"],
        "w44_factor_tests.csv"),
       # Reloads the tape once more, and is the only stage that enters on every
       # day of the week rather than only Friday.
       # --hold-ladder runs five holding periods, which is what separates the
       # weekend content of the window from simply holding for longer.
       ("weekend content vs maturity", ["weekend_content.py", "--hold-ladder"],
        "w47_content_regressions.csv"),
       # Recomputes the calendar spread with both legs' costs charged, and
       # prices the maker variant. Produces the paper's Table 7; must follow
       # the trading stage whose construction it corrects.
       ("corrected costing and maker economics", ["weekend_maker.py"],
        "w60_spread_costed.csv"),
       # Moneyness ladder for the companion paper.
       ("moneyness ladder", ["weekend_moneyness.py"], "w52_moneyness_summary.csv"),
       ("figures", ["weekend_figures.py"], None)]
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", default=None, help="substring of a stage name")
    a = ap.parse_args()

    env_python = sys.executable
    failed = []
    for name, cmd, marker in STAGES:
        if a.only and a.only.lower() not in name.lower():
            continue
        if marker and not a.force and (config.TABLES / marker).exists():
            print(f"[skip] {name} ({marker} exists)")
            continue
        print(f"\n{'=' * 70}\n[run ] {name}\n{'=' * 70}", flush=True)
        t0 = time.time()
        r = subprocess.run([env_python, str(ROOT / "scripts" / cmd[0])] + cmd[1:],
                           cwd=ROOT, env={**__import__("os").environ,
                                          "PYTHONPATH": str(ROOT)})
        dt = time.time() - t0
        if r.returncode == 0:
            print(f"[ok  ] {name} in {dt/60:.1f} min", flush=True)
        else:
            print(f"[FAIL] {name} exit {r.returncode} after {dt/60:.1f} min",
                  flush=True)
            failed.append(name)

    print("\n" + "=" * 70)
    print("FAILED:" if failed else "all stages ok")
    for f in failed:
        print("  ", f)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
