"""Paper figures.

Deliberately plain: one idea per panel, no styling that would not survive a
journal's production process.
"""
from __future__ import annotations

import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

log = logging.getLogger(__name__)

plt.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 200, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.autolayout": True,
})


def _save(fig, name: str):
    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    log.info("wrote figure %s", name)


def f1_inventory_vs_expensiveness(market: pd.DataFrame, currency: str,
                                  inv: str = "dealer_vega_sc",
                                  exp: str = "exp_atm_30"):
    """The money plot: dealer vega inventory against option expensiveness."""
    d = market.dropna(subset=[inv, exp]).copy()
    if d.empty:
        log.warning("f1: nothing to plot for %s", currency)
        return
    d["date"] = pd.to_datetime(d["date"])

    fig, ax1 = plt.subplots(figsize=(9, 4))
    ax1.plot(d["date"], -d[inv], lw=0.9, color="#1f77b4",
             label="dealer vega inventory (negated)")
    ax1.set_ylabel("$-$dealer vega inventory (scaled)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.axhline(0, color="k", lw=0.5)

    ax2 = ax1.twinx()
    ax2.plot(d["date"], d[exp] * 100, lw=0.9, color="#d62728",
             label="expensiveness (vol pts)")
    ax2.set_ylabel("ATM 30d IV $-$ E[RV] (vol pts)", color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    ax2.grid(False)

    for name, day in config.EVENTS.items():
        ts = pd.Timestamp(day, tz="UTC")
        if d["date"].min() <= ts <= d["date"].max():
            ax1.axvline(ts, color="gray", ls=":", lw=0.8)

    ax1.set_title(f"{currency}: dealer inventory and option expensiveness")
    _save(fig, f"f1_inventory_expensiveness_{currency}")


def f2_surface_factors(grid: pd.DataFrame, currency: str):
    """Level, skew and curvature through the sample."""
    d = grid.copy()
    d["date"] = pd.to_datetime(d["date"])
    panels = [("atm_30", "ATM 30d implied vol"),
              ("rr25_30", "25$\\Delta$ risk reversal"),
              ("bf25_30", "25$\\Delta$ butterfly")]
    panels = [(c, t) for c, t in panels if c in d.columns and d[c].notna().any()]
    if not panels:
        return

    fig, axes = plt.subplots(len(panels), 1, figsize=(9, 2.2 * len(panels)),
                             sharex=True)
    axes = np.atleast_1d(axes)
    for ax, (c, title) in zip(axes, panels):
        ax.plot(d["date"], d[c] * 100, lw=0.8)
        ax.set_ylabel("vol pts")
        ax.set_title(title, fontsize=9)
        ax.axhline(0, color="k", lw=0.5)
        for _, day in config.EVENTS.items():
            ts = pd.Timestamp(day, tz="UTC")
            if d["date"].min() <= ts <= d["date"].max():
                ax.axvline(ts, color="gray", ls=":", lw=0.7)
    fig.suptitle(f"{currency}: implied volatility surface factors", y=1.01)
    _save(fig, f"f2_surface_factors_{currency}")


def f3_binscatter(buckets: pd.DataFrame, currency: str,
                  x: str = "dealer_vega_sc_lag", y: str = "exp_bucket",
                  nbins: int = 20):
    """Binscatter of expensiveness on demand, after removing day and bucket
    means — the visual counterpart of the fixed-effects regression."""
    d = buckets[[x, y, "date", "bucket"]].replace([np.inf, -np.inf],
                                                  np.nan).dropna()
    if len(d) < 200:
        log.warning("f3: too few observations for %s", currency)
        return
    # Two-way demeaning, so the picture shows the same variation the panel
    # regression uses.
    for col in (x, y):
        d[col] = (d[col] - d.groupby("date")[col].transform("mean")
                  - d.groupby("bucket")[col].transform("mean")
                  + d[col].mean())

    d["bin"] = pd.qcut(d[x], nbins, duplicates="drop")
    g = d.groupby("bin", observed=True).agg(xm=(x, "mean"), ym=(y, "mean"),
                                            n=(y, "size")).reset_index()

    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.scatter(-g["xm"], g["ym"] * 100, s=18, color="#1f77b4")
    b = np.polyfit(-g["xm"], g["ym"] * 100, 1)
    xs = np.linspace((-g["xm"]).min(), (-g["xm"]).max(), 50)
    ax.plot(xs, np.polyval(b, xs), color="#d62728", lw=1.2,
            label=f"slope = {b[0]:.2f}")
    ax.set_xlabel("$-$dealer vega inventory (demeaned)")
    ax.set_ylabel("expensiveness (vol pts, demeaned)")
    ax.set_title(f"{currency}: cross-sectional demand pressure")
    ax.legend(frameon=False)
    _save(fig, f"f3_binscatter_{currency}")


def f5_placebo_ladder(placebo: pd.DataFrame, currency: str):
    """Funding-shock coefficient by bucket, ordered by how delta-exposed the
    bucket is. The channel should weaken toward the low-delta end."""
    d = placebo.dropna(subset=["beta_shock"]).sort_values("mean_abs_delta")
    if d.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    y = np.arange(len(d))
    se = d["beta_shock"] / d["t_shock"].replace(0, np.nan)
    ax.errorbar(d["beta_shock"], y, xerr=1.96 * se.abs(), fmt="o", ms=4,
                lw=1, capsize=2)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{b} ($|\\Delta|${a:.2f}, {t:.0f}d)"
                        for b, a, t in zip(d["bucket"], d["mean_abs_delta"],
                                           d["mean_tau"])], fontsize=7)
    ax.set_xlabel("funding-shock coefficient")
    ax.set_title(f"{currency}: placebo ladder across buckets")
    _save(fig, f"f5_placebo_ladder_{currency}")
