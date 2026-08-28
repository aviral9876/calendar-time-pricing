"""Paper tables.

Each function returns a tidy DataFrame and writes both CSV (for inspection) and
LaTeX (for the draft). Nothing here estimates anything: the econometrics live
in dbop.econo and are called by scripts/run_regressions.py.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)


def save(df: pd.DataFrame, name: str, caption: str = "",
         float_fmt: str = "%.4f") -> pd.DataFrame:
    df.to_csv(config.TABLES / f"{name}.csv", index=False)
    try:
        tex = df.to_latex(index=False, float_format=float_fmt, escape=True,
                          caption=caption or name, label=f"tab:{name}")
        (config.TABLES / f"{name}.tex").write_text(tex, encoding="utf-8")
    except Exception as exc:                       # LaTeX is a nicety, not a gate
        log.warning("latex export failed for %s: %s", name, exc)
    return df


def t1_market_structure(volume_summaries: list[pd.DataFrame]) -> pd.DataFrame:
    """Who trades, how much, and how much of it is off-book."""
    df = pd.concat(volume_summaries, ignore_index=True)
    df = df.sort_values(["currency", "year"])
    out = df[["currency", "year", "n_trades", "volume_coin", "n_instruments",
              "block_share", "combo_share", "liq_share", "taker_buy_share"]]
    return save(out, "t1_market_structure",
                "Deribit option market structure by year")


def t2_inventory_summary(markets: list[pd.DataFrame],
                         signing_tests: list[pd.DataFrame]) -> pd.DataFrame:
    """Dealer inventory descriptives and the sign-inference diagnostic."""
    rows = []
    for m in markets:
        cur = m["currency"].iloc[0]
        for col in ("dealer_vega_sc", "dealer_gamma_sc", "dealer_delta_usd_sc"):
            if col not in m.columns:
                continue
            s = m[col].replace([np.inf, -np.inf], np.nan).dropna()
            if s.empty:
                continue
            rows.append({
                "currency": cur, "measure": col, "n": len(s),
                "mean": s.mean(), "sd": s.std(),
                "p10": s.quantile(0.10), "median": s.median(),
                "p90": s.quantile(0.90),
                "share_dealer_short": float((s < 0).mean()),
                "ar1": float(s.autocorr(1)) if len(s) > 10 else np.nan,
            })
    out = pd.DataFrame(rows)
    save(out, "t2_inventory_summary", "Dealer inventory descriptives")

    sign = pd.concat(signing_tests, ignore_index=True)
    save(sign, "t2b_signing_test",
         "Inventory mean reversion: true signs vs sign-shuffled placebo")
    return out


def t3_expensiveness_summary(markets: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for m in markets:
        cur = m["currency"].iloc[0]
        cands = [c for c in m.columns
                 if c.startswith(("exp_atm_", "vrp_", "dh_ret", "mfiv_"))]
        for c in cands:
            s = m[c].replace([np.inf, -np.inf], np.nan).dropna()
            if len(s) < 30:
                continue
            rows.append({
                "currency": cur, "measure": c, "n": len(s),
                "mean": s.mean(), "sd": s.std(), "median": s.median(),
                "share_positive": float((s > 0).mean()),
            })
    out = pd.DataFrame(rows)
    return save(out, "t3_expensiveness_summary",
                "Expensiveness and premium measures")


def regression_table(results: dict[str, dict], key: str, name: str,
                     caption: str = "") -> pd.DataFrame:
    """Flatten a set of specification results into one comparable table."""
    rows = []
    for label, r in results.items():
        if r is None or "error" in r:
            rows.append({"spec": label, "n": (r or {}).get("n", 0),
                         "beta": np.nan, "t": np.nan, "p": np.nan,
                         "r2": np.nan})
            continue
        params = r.get("params", {})
        tstats = r.get("tstats", {})
        pvals = r.get("pvalues", {})
        rows.append({
            "spec": label,
            "n": r.get("n"),
            "beta": params.get(key, np.nan),
            "t": tstats.get(key, np.nan),
            "p": pvals.get(key, np.nan),
            "r2": r.get("r2", r.get("r2_within", np.nan)),
        })
    return save(pd.DataFrame(rows), name, caption)


def t8_elasticity_comparison(our_beta: float, our_se: float, n: int,
                             gpp_beta: float | None = None) -> pd.DataFrame:
    """Our demand elasticity next to the published equity-option benchmark.

    GPP's coefficient is on a differently scaled demand variable, so the
    comparison is only meaningful after both are expressed per one standard
    deviation of demand relative to market size. The benchmark value must be
    supplied explicitly from docs/gpp_calibration.md rather than hard-coded
    here, so that the derivation stays visible and auditable.
    """
    rows = [{
        "market": "Deribit crypto options (this paper)",
        "beta_per_sd": our_beta,
        "se": our_se,
        "t": our_beta / our_se if our_se else np.nan,
        "n": n,
    }]
    if gpp_beta is not None:
        rows.append({"market": "US equity/index options (GPP 2009)",
                     "beta_per_sd": gpp_beta, "se": np.nan, "t": np.nan,
                     "n": np.nan})
        rows.append({"market": "ratio (crypto / equity)",
                     "beta_per_sd": our_beta / gpp_beta if gpp_beta else np.nan,
                     "se": np.nan, "t": np.nan, "n": np.nan})
    return save(pd.DataFrame(rows), "t8_elasticity_comparison",
                "Demand-pressure elasticity: crypto vs US equity options")
