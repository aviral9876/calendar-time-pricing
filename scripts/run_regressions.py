"""Estimate every specification in the paper and write tables and figures.

    python scripts/run_regressions.py

Assumes scripts/build_all.py has produced the panels.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from dbop import config, figures, panels, surfaces, tables  # noqa: E402
from dbop.econo import iv2sls, panel as panel_econ, ts  # noqa: E402

log = logging.getLogger("run_regressions")


def _load(currency: str):
    try:
        return panels.load_market(currency), panels.load_buckets(currency)
    except FileNotFoundError:
        log.warning("%s: panels not built, skipping", currency)
        return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", choices=list(config.CURRENCIES), default=None)
    ap.add_argument("--gpp-beta", type=float, default=None,
                    help="benchmark elasticity from docs/gpp_calibration.md")
    ap.add_argument("--log", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log.upper()),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    currencies = [args.currency] if args.currency else list(config.CURRENCIES)
    markets, bucket_panels, signing, volumes = [], [], [], []

    for cur in currencies:
        m, b = _load(cur)
        if m is None:
            continue
        markets.append(m)
        bucket_panels.append(b)
        for lst, fname in ((signing, f"{cur}_signing_test.parquet"),
                           (volumes, f"{cur}_volume_summary.parquet")):
            p = config.PANELS / fname
            if p.exists():
                d = pd.read_parquet(p)
                d["currency"] = cur
                lst.append(d)

    if not markets:
        log.error("no panels found; run scripts/build_all.py first")
        return 1

    # ---------------------------------------------------------- descriptives
    if volumes:
        tables.t1_market_structure(volumes)
    if signing:
        tables.t2_inventory_summary(markets, signing)
    tables.t3_expensiveness_summary(markets)

    for cur, m, b in zip(currencies, markets, bucket_panels):
        print(f"\n{'=' * 70}\n{cur}\n{'=' * 70}")

        # ------------------------------------------------ 1. cross-section
        rob = panel_econ.robustness_suite(b)
        tables.save(rob, f"t4_cross_section_{cur}",
                    f"{cur}: bucket expensiveness on lagged dealer inventory")
        print("\n[1] Cross-section (day + bucket FE)")
        print(rob.to_string(index=False))

        sub = panel_econ.by_subsample(b, config.EVENTS)
        tables.save(sub, f"t9_subsamples_{cur}", f"{cur}: subsample stability")
        print("\n[9] Subsamples")
        print(sub.to_string(index=False))

        # ------------------------------------------------ 2. time series
        tsres = {
            "levels, no controls": ts.inventory_on_expensiveness(
                m, use_controls=False),
            "levels, with controls": ts.inventory_on_expensiveness(m),
            "changes": ts.changes_spec(m),
        }
        tables.regression_table(
            {k: v for k, v in tsres.items() if k != "changes"}, "neg_inv",
            f"t5_timeseries_{cur}", f"{cur}: expensiveness on dealer inventory")
        print("\n[2] Time series")
        print(ts.summarize(tsres, "neg_inv").to_string(index=False))
        print(ts.summarize({"changes": tsres["changes"]},
                           "d_inv").to_string(index=False))

        # ------------------------------------ 3. delta-hedged return predictability
        rets = {f"h={h}": ts.inventory_predicts_returns(m, horizon=h)
                for h in (1, 5, 22)}
        tables.regression_table(rets, "dealer_vega_sc", f"t6_dh_returns_{cur}",
                                f"{cur}: forward delta-hedged returns on inventory")
        print("\n[6] Delta-hedged return predictability")
        print(ts.summarize(rets, "dealer_vega_sc").to_string(index=False))

        # ------------------------------------------------ 4. the instrument
        print("\n[7] Funding-cost instrument")
        try:
            fals = iv2sls.falsification_suite(m, b)
            for name, tab in fals.items():
                tables.save(tab, f"t7_{name}_{cur}",
                            f"{cur}: {name.replace('_', ' ')}")
                print(f"\n  -- {name} --")
                print(tab.to_string(index=False))
            if len(fals.get("placebo_buckets", [])):
                figures.f5_placebo_ladder(fals["placebo_buckets"], cur)
        except Exception as exc:
            log.warning("%s: IV stage failed: %s", cur, exc)

        # ------------------------------------------------ figures
        try:
            figures.f1_inventory_vs_expensiveness(m, cur)
            figures.f3_binscatter(b, cur)
            figures.f2_surface_factors(surfaces.load_grid(cur), cur)
        except Exception as exc:
            log.warning("%s: figure generation failed: %s", cur, exc)

        # ---------------------------------- 8. elasticity vs the GPP benchmark
        base = rob[rob["spec"] == "vega, two-way cluster"]
        if len(base) and np.isfinite(base["beta"].iloc[0]):
            beta = float(base["beta"].iloc[0])
            t = float(base["t"].iloc[0])
            se = abs(beta / t) if t else np.nan
            tables.t8_elasticity_comparison(beta, se, int(base["n"].iloc[0]),
                                            args.gpp_beta)

    print(f"\nTables -> {config.TABLES}\nFigures -> {config.FIGURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
