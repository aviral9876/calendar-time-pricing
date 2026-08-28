"""Figures for the weekend-risk paper."""
from __future__ import annotations

import argparse
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dbop import config, tape, weekend, bars, util

log = logging.getLogger("weekend_figures")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BLUE, RED, GREY = "#1f4e79", "#c0392b", "#888888"
# One colour per underlying. Keyed rather than positional: a two-colour
# alternation drew ETH and SOL identically once a third asset was added.
ASSET_COLOR = {"BTC": "#1f4e79", "ETH": "#c0392b", "SOL": "#1e8449",
               "XRP": "#7d3c98"}


def save(fig, name):
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"{name}.{ext}", dpi=150,
                    bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {name}")


def fig_realized(rvs: dict):
    # One panel per asset. A hard-coded pair of axes silently dropped the third
    # underlying from this figure when SOL was added. Beyond three assets a
    # single row is wider than the page, so wrap into a grid at four.
    n = len(rvs)
    ncol = n if n <= 3 else 2
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(5.5 * ncol, 4 * nrow),
                             sharey=False)
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[n:]:
        ax.set_visible(False)
    for ax, (cur, rv) in zip(axes, rvs.items()):
        g = rv.groupby(rv["date"].dt.dayofweek)["ann_vol"]
        m = g.mean() * 100
        colors = [BLUE if i < 5 else RED for i in m.index]
        ax.bar([DAYS[i] for i in m.index], m.values, color=colors)
        wk = rv.loc[~rv.is_weekend, "ann_vol"].mean() * 100
        ax.axhline(wk, color=GREY, ls="--", lw=1,
                   label=f"weekday mean {wk:.0f}%")
        ax.set_title(f"{cur}: realized volatility by day of week")
        ax.set_ylabel("annualized vol (%)")
        ax.legend(frameon=False, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("The market never closes, yet weekends are quiet", y=1.02)
    save(fig, "w_f1_realized_by_dow")


def fig_gap(w1: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(w1))
    ax.bar(x - 0.18, w1["variance_ratio"], 0.36, color=RED,
           label="realized weekend/weekday variance")
    ax.bar(x + 0.18, w1["implied_ratio"], 0.36, color=BLUE,
           label="implied weekend/weekday variance")
    for i, r in w1.reset_index(drop=True).iterrows():
        ax.annotate("", xy=(i + 0.18, r["implied_ratio"]),
                    xytext=(i - 0.18, r["variance_ratio"]),
                    arrowprops=dict(arrowstyle="->", color="black", lw=1.1))
        ax.text(i, max(r["implied_ratio"], r["variance_ratio"]) + 0.03,
                f"gap {r['gap']:+.3f}", ha="center", fontsize=9)
    ax.axhline(1.0, color=GREY, lw=1, ls=":")
    ax.set_xticks(x); ax.set_xticklabels(w1["currency"])
    ax.set_ylabel("weekend variance / weekday variance")
    ax.set_ylim(0, 1.15)
    # With four assets the dispersion runs the other way from the three-asset
    # draft: realized ratios span 0.073 and implied ones 0.157. The old title
    # ("implied discounts are similar; realized effects are not") described the
    # data before XRP and now inverts it.
    ax.set_title("Realized weekend discounts are alike; the prices are not",
                 fontsize=11)
    # Upper left is the only reliably empty corner: the bars sit near 0.6 and
    # the lower right collides with the rightmost asset.
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f2_implied_vs_realized")


def fig_iv_by_expiry_dow(ivs: dict):
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for cur, s in ivs.items():
        v = (s / s.mean() - 1) * 100
        ax.plot([DAYS[i] for i in v.index], v.values, "o-",
                color=ASSET_COLOR.get(cur, GREY), label=cur, lw=1.8)
    ax.axhline(0, color=GREY, lw=1, ls=":")
    ax.axvspan(4.5, 6.5, color=RED, alpha=0.07)
    ax.set_ylabel("ATM implied vol, % deviation from own mean")
    ax.set_title("Short-dated implied vol by expiry weekday")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f3_iv_by_expiry_dow")


def fig_reference(w1: pd.DataFrame, ref: pd.DataFrame):
    """Realized weekend discount across the traded books and the one asset whose
    own market closes. Reads from the stage outputs rather than the tape, so it
    costs nothing to regenerate."""
    rows = [(r["currency"], r["variance_ratio"], False)
            for _, r in w1.iterrows()]
    rows += [(r["asset"], r["variance_ratio"], True) for _, r in ref.iterrows()]
    rows.sort(key=lambda t: -t[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    # Gold for the reference asset, and never a colour already spent on a traded
    # book: drawing PAXG in ETH's red made the highlighted bar look like a
    # fifth crypto book rather than the contrast the figure exists to draw.
    GOLD = "#b7791f"
    colors = [GOLD if r[2] else ASSET_COLOR.get(r[0], BLUE) for r in rows]
    ax.bar(labels, vals, color=colors, width=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)
    ax.axhline(1.0, color=GREY, lw=1, ls=":")
    ax.text(len(rows) - 0.55, 1.005, "no weekend effect", ha="right",
            va="bottom", fontsize=8, color=GREY)
    ax.set_ylabel("weekend variance / weekday variance")
    ax.set_ylim(0, 1.14)
    ax.set_title("The weekend discount roughly doubles when the underlying's\n"
                 "own market is actually closed", fontsize=11)
    # Annotated in the empty space above the short bar, clear of its own value
    # label, rather than in a legend: with one highlighted category a legend
    # costs more space than it explains.
    ax.annotate("tokenized gold —\nspot market shut\nat weekends",
                xy=(len(rows) - 1, vals[-1] + 0.06),
                xytext=(len(rows) - 1, vals[-1] + 0.40),
                fontsize=8.5, color=GOLD, ha="center", va="bottom",
                arrowprops=dict(arrowstyle="->", color=GOLD, lw=1))
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f5_reference_asset")


def fig_horse_race(race: pd.DataFrame):
    """What a jump-risk premium can and cannot price.

    The bar is the interval of weekend ratios reachable by pricing jump variance
    at any multiple of its physical value: it starts at the realized ratio and
    ends at the jump-variance ratio, which is the limit as the premium grows
    without bound. The diamond is what the market actually quotes. The figure
    exists because that diamond sits outside the bar in every asset, which is
    the whole argument in one picture.
    """
    r = race.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    y = np.arange(len(r))
    for i, row in r.iterrows():
        lo, hi = row["bound_lo"], row["bound_hi"]
        ax.barh(i, hi - lo, left=lo, height=0.38, color="#c8d6e5",
                edgecolor="#5b7ea3", lw=0.8, zorder=2)
        ax.plot([row["realized_ratio"]], [i], "o", color="#5b7ea3", ms=6,
                zorder=3)
        ax.errorbar(row["implied_ratio"], i, xerr=1.96 * row["implied_se"],
                    fmt="D", color=RED, ms=7, capsize=3, lw=1.4, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(r["asset"])
    ax.set_xlabel("weekend variance / weekday variance")
    ax.set_title("No jump-risk premium reaches the price the market quotes",
                 fontsize=11, pad=26)
    handles = [
        plt.Line2D([], [], marker="o", ls="", color="#5b7ea3",
                   label="realized (no premium)"),
        plt.Rectangle((0, 0), 1, 1, fc="#c8d6e5", ec="#5b7ea3",
                      label="reachable by any jump premium"),
        plt.Line2D([], [], marker="D", ls="", color=RED,
                   label="implied, 95% CI"),
    ]
    # Above the axes rather than inside: the four rows leave no corner free that
    # some asset's confidence interval does not already run through.
    ax.legend(handles=handles, frameon=False, fontsize=8.5, ncol=3,
              loc="lower center", bbox_to_anchor=(0.5, 1.0),
              handletextpad=0.5, columnspacing=1.6)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    save(fig, "w_f6_horse_race")


def fig_smile(sm: pd.DataFrame):
    """The weekend discount across the smile.

    Jump risk is priced away from the money, so if the weekend discount were
    jump compensation it would have to weaken toward the wings -- the lines
    would slope up to the left. A discount that is a property of the calendar
    rather than of the tail is flat or steeper there.
    """
    order = list(dict.fromkeys(sm["bucket"]))
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for cur, g in sm.groupby("currency", sort=False):
        g = g.set_index("bucket").reindex(order)
        x = np.arange(len(order))
        ax.errorbar(x, g["implied_ratio"], yerr=1.96 * g["implied_ratio_se"],
                    fmt="o-", color=ASSET_COLOR.get(cur, GREY), label=cur,
                    lw=1.7, ms=5, capsize=3)
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(order)
    ax.set_ylabel("implied weekend / weekday variance")
    ax.set_xlabel("distance from the money  (far wing $\\rightarrow$ at the money)")
    # The prediction being falsified, drawn where it would show: an arrow at the
    # wing end pointing the way a jump premium would move those points. Without
    # it the figure is four rising lines and the reader has to be told twice
    # which direction was expected.
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + 0.16 * (hi - lo))
    top = ax.get_ylim()[1]
    ax.annotate("", xy=(0.10, top - 0.02), xytext=(0.10, top - 0.16),
                arrowprops=dict(arrowstyle="->", color=GREY, lw=1.2))
    ax.text(0.20, top - 0.05, "a jump premium would push\nthe wings this way",
            fontsize=8.5, color=GREY, ha="left", va="top")
    ax.set_title("The wings discount the weekend more, not less", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f7_smile")


def fig_trajectory(tr: pd.DataFrame, win: pd.DataFrame):
    """The implied weekend discount year by year, against the realized one.

    This is the figure that dissolves the apparent split between old and young
    books. The lines start at zero -- a market pricing no weekend effect at all
    -- fall through the realized band around 2022, and end below it. Books
    listed in 2024 have only the last leg of that path in their sample, which is
    the whole of the difference between their pricing errors and Bitcoin's.
    """
    tr = tr[tr["year"] >= 2020]
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    band = win[win["window"] == "full"]["rel_effect"]
    ax.axhspan(band.min(), band.max(), color=GREY, alpha=0.18, zorder=1)
    ax.text(tr["year"].max() + 0.08, band.mean(),
            "realized weekend effect\n(all four books, full sample)",
            fontsize=8, color="#555555", va="center")
    for cur, g in tr.groupby("asset", sort=False):
        g = g.sort_values("year")
        ax.errorbar(g["year"], g["rel_implied"], yerr=1.96 * g["rel_implied_se"],
                    fmt="o-", color=ASSET_COLOR.get(cur, GREY), label=cur,
                    lw=1.8, ms=4.5, capsize=2.5, zorder=3)
    ax.axhline(0, color=GREY, lw=1, ls=":")
    ax.text(2020.05, 0.03, "no weekend discount priced", fontsize=8, color=GREY)
    ax.set_ylabel("implied weekend effect, relative to own variance level")
    ax.set_title("The market has been learning the weekend clock, and has now\n"
                 "gone past it", fontsize=11)
    # Room on the right for the band label, but only real years get a tick:
    # letting matplotlib choose put a tick on a year with no data in it.
    yrs = sorted(tr["year"].unique())
    ax.set_xlim(2019.8, max(yrs) + 1.9)
    ax.set_xticks(yrs)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f8_trajectory")


def fig_wings(amp: pd.DataFrame):
    """How much steeper the wing's weekend slope is than the money's, by
    maturity, against what quoting geometry can produce.

    Same grammar as Figure 6: the shaded band is what a mechanism can reach, the
    marker is what the market does. One is a level of variance, the other is a
    moneyness metric, but the reading is identical -- inside the band the
    behaviour is accounted for, outside it something else is going on.
    """
    a = amp[amp["purged"] & (amp["band"] != "pooled")].copy()
    order = [b for b in ("under 1d", "1-3d", "3-7d", "7-14d")
             if b in set(a["band"])]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    xs, obs, lo, hi, ceil = [], [], [], [], []
    for i, band in enumerate(order):
        s = a[a["band"] == band].dropna(subset=["log_amp", "log_amp_se"])
        if s.empty:
            continue
        w = 1.0 / s["log_amp_se"] ** 2
        m = float((s["log_amp"] * w).sum() / w.sum())
        se = float(np.sqrt(1.0 / w.sum()))
        xs.append(i)
        obs.append(np.exp(m))
        lo.append(np.exp(m - 1.96 * se))
        hi.append(np.exp(m + 1.96 * se))
        ceil.append(float(s["ceiling"].mean()))
    xs = np.asarray(xs, dtype=float)
    ax.fill_between(xs, 1.0, ceil, color="#c8d6e5", zorder=1,
                    label="reachable by the smile's geometry")
    ax.axhline(1.0, color=GREY, lw=1, ls=":")
    ax.plot(xs, ceil, color="#5b7ea3", lw=1.4, ls="--")
    ax.errorbar(xs, obs, yerr=[np.array(obs) - np.array(lo),
                               np.array(hi) - np.array(obs)],
                fmt="D", color=RED, ms=8, capsize=4, lw=1.6, zorder=4,
                label="observed, 95% CI")
    ax.set_xticks(xs)
    ax.set_xticklabels(order)
    ax.set_xlabel("time to expiry")
    ax.set_ylabel("wing weekend slope / at-the-money slope")
    ax.set_yscale("log")
    ax.set_yticks([1.0, 1.5, 2.0, 3.0, 4.0])
    ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.text(xs[-1] + 0.06, 1.0, "smile follows\nthe weekend clock", fontsize=8,
            color=GREY, va="center")
    ax.set_xlim(-0.35, xs[-1] + 1.25)
    # Deliberately not "inside a day they are not": the sub-daily point clears
    # the ceiling by 1.9 standard errors, which is a hint and not a finding.
    ax.set_title("The wings are the smile's clock, not a view on weekend tails",
                 fontsize=11)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "w_f9_wings")


def fig_learning(moments: pd.DataFrame, race: pd.DataFrame,
                 ladder: pd.DataFrame):
    """What the market has been tracking, and why the benchmark missed it.

    Left: the trend in the weekend variance ratio, per year in log points, with
    95% intervals -- as the market quotes it, and as the realized series delivers
    it measured at the centre of the daily variance distribution and at its mean.
    In Bitcoin and Ether the quoted trend sits on top of the centre's and well
    clear of the mean's. In Solana and XRP nothing is estimated precisely enough
    to say anything, and the intervals show it.

    Right: the trend in the ratio of means as the top of each day type is
    trimmed away, which is where the benchmark's flatness comes from. At no trim
    it is the insignificant line section 5.5 read as "the market is drifting away
    from the data". One per cent in -- three weekend days a year -- it is not.
    """
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.0, 4.4))

    imp = race[race["table"] == "implied trend"].set_index("asset")
    series = (("implied", None, BLUE, "o"),
              ("realized, centre", "geometric", RED, "s"),
              ("realized, mean", "arithmetic", GREY, "^"))
    ypos, labels = [], []
    for i, cur in enumerate(config.CURRENCIES):
        base = -i * 4.0
        for j, (lab, moment, col, mk) in enumerate(series):
            if moment is None:
                if cur not in imp.index:
                    continue
                b, se = imp.loc[cur, "trend_per_year"], imp.loc[cur, "trend_se"]
            else:
                r = moments[(moments["asset"] == cur)
                            & (moments["moment"] == moment)]
                if r.empty:
                    continue
                b, se = r["trend_per_year"].iloc[0], r["trend_se"].iloc[0]
            y = base - j
            ax.errorbar(b, y, xerr=1.96 * se, fmt=mk, color=col, ms=5.5,
                        lw=1.6, capsize=3,
                        label=lab if i == 0 else None, zorder=3)
        ypos.append(base - 1)
        labels.append(cur)
    ax.axvline(0, color="#333333", lw=1, ls=":")
    ax.set_yticks(ypos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("trend in the weekend variance ratio, log points per year")
    ax.set_title("The quotes move with the centre of the\n"
                 "distribution, not with its mean", fontsize=10.5)
    # Upper right is the only corner clear of an interval: XRP's mean estimate
    # runs across the bottom of the panel and Bitcoin's sit hard left.
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)

    for cur, g in ladder.groupby("asset", sort=False):
        g = g.sort_values("trim")
        mature = cur in ("BTC", "ETH")
        bx.plot(g["trim"] * 100, g["trend_per_year"], "o-",
                color=ASSET_COLOR.get(cur, GREY), lw=2.0 if mature else 1.2,
                ms=5 if mature else 3.5, alpha=1.0 if mature else 0.45,
                label=cur, zorder=3 if mature else 2)
    bx.axhline(0, color=GREY, lw=1, ls=":")
    bx.set_xscale("symlog", linthresh=1.0)
    bx.set_xticks([0, 1, 2, 5, 10, 25, 50])
    bx.set_xticklabels(["0", "1", "2", "5", "10", "25", "50"])
    bx.set_xlabel("per cent of days trimmed from the top of each day type")
    bx.set_ylabel("trend in the ratio of means, per year")
    bx.set_title("The benchmark's flatness is bought in\n"
                 "the top one per cent of days", fontsize=10.5)
    bx.legend(frameon=False, fontsize=8.5, loc="lower right", ncol=2)
    bx.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    save(fig, "w_f10_learning")


def fig_shortability(daily: dict, beh_yr: pd.DataFrame):
    """Left: cumulative P&L of the short-weekend spread. Right: the edge."""
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.5, 4.6))

    for cur, d in daily.items():
        idx = pd.to_datetime(d.index)
        cum = d["spread_net"].cumsum()
        lw = 2.0 if cur in ("BTC", "ETH") else 1.2
        alpha = 1.0 if cur in ("BTC", "ETH") else 0.55
        ax.plot(idx, cum, color=ASSET_COLOR[cur], lw=lw, alpha=alpha, label=cur)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("cumulative P&L per unit vega")
    ax.set_title("Short weekend / long weekday, net of measured costs")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.grid(alpha=0.25)

    # The edge a seller was paid, against what the weekend then delivered.
    # Mean and median are plotted together because the gap between them IS the
    # finding of section 5.6: the market quotes the centre, the seller pays the
    # mean.
    for cur in ("BTC", "ETH"):
        g = beh_yr[beh_yr["asset"] == cur]
        if g.empty:
            continue
        bx.plot(g["year"], g["median_iv_minus_rv"], "o-", color=ASSET_COLOR[cur],
                lw=1.8, ms=5, label=f"{cur} median")
        bx.plot(g["year"], g["mean_iv_minus_rv"], "s--", color=ASSET_COLOR[cur],
                lw=1.4, ms=4, alpha=0.6, label=f"{cur} mean")
    bx.axhline(0, color="k", lw=0.8)
    bx.set_ylabel("Friday weekend IV $-$ realized weekend vol")
    bx.set_xlabel("year")
    bx.set_title("What the weekend seller was paid, ex post")
    bx.legend(loc="upper right", frameon=False, fontsize=8, ncol=2)
    bx.grid(alpha=0.25)

    fig.tight_layout()
    save(fig, "w_f11_shortability")


def fig_binscatter(d: pd.DataFrame, cur: str):
    cols = ["iv2", "wknd_frac"]
    g = d.groupby("date")[cols]
    dm = (d[cols] - g.transform("mean")).dropna()
    q = pd.qcut(dm["wknd_frac"], 20, duplicates="drop")
    b = dm.groupby(q, observed=True).mean()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.scatter(b["wknd_frac"], b["iv2"], color=BLUE, s=28, zorder=3)
    k = np.polyfit(dm["wknd_frac"], dm["iv2"], 1)
    xs = np.linspace(b["wknd_frac"].min(), b["wknd_frac"].max(), 50)
    ax.plot(xs, np.polyval(k, xs), color=RED, lw=1.6,
            label=f"slope {k[0]:+.3f}")
    ax.axhline(0, color=GREY, lw=0.8, ls=":")
    ax.set_xlabel("weekend fraction of remaining life (demeaned within day)")
    ax.set_ylabel("squared implied vol (demeaned within day)")
    ax.set_title(f"{cur}: contracts trading the same instant, "
                 f"different weekend exposure")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, f"w_f4_binscatter_{cur}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="WARNING")
    # The binscatters and the expiry-weekday panel each reload an option tape
    # and dominate the runtime; everything else reads a stage output in
    # milliseconds. --bars-only redraws just the cheap half.
    ap.add_argument("--bars-only", action="store_true",
                    help="skip the figures that need the option tape")
    a = ap.parse_args()
    logging.basicConfig(level=a.log)

    print("building figures")
    rvs, ivs = {}, {}
    for cur in config.CURRENCIES:
        rv = weekend.realized_by_daytype(bars.load(cur))
        rv["date"] = pd.to_datetime(rv["date"], utc=True)
        rvs[cur] = rv

    fig_realized(rvs)

    # Annualized realized vol by weekday, one row per asset: quoted directly in
    # the paper, and cheap enough to write here rather than rerun the tape for.
    dow = pd.DataFrame({
        cur: rv.groupby(rv["date"].dt.dayofweek)["ann_vol"].mean() * 100
        for cur, rv in rvs.items()}).T
    dow.columns = [DAYS[i] for i in dow.columns]
    dow.round(1).to_csv(config.TABLES / "w6_realized_vol_by_dow.csv",
                        index_label="currency")

    w1 = pd.read_csv(config.TABLES / "w1_weekend_pricing.csv")
    fig_gap(w1)

    ref_path = config.TABLES / "w8_reference_assets.csv"
    if ref_path.exists():
        fig_reference(w1, pd.read_csv(ref_path))
    else:
        print("  (no w8_reference_assets.csv; skipping the reference figure)")

    # The horse-race figures read stage output, so they are skipped rather than
    # fatal when that stage has not been run: the figure script is the one stage
    # people run on its own.
    for name, fn in (("w12_risk_horse_race", fig_horse_race),
                     ("w14_weekend_slope_by_moneyness", fig_smile)):
        p = config.TABLES / f"{name}.csv"
        if p.exists():
            fn(pd.read_csv(p))
        else:
            print(f"  (no {p.name}; skipping)")

    tp, wp = (config.TABLES / "w17_split_trajectory.csv",
              config.TABLES / "w16_split_windows.csv")
    if tp.exists() and wp.exists():
        fig_trajectory(pd.read_csv(tp), pd.read_csv(wp))
    else:
        print("  (no split tables; skipping the trajectory figure)")

    ap = config.TABLES / "w22_wing_amplification.csv"
    if ap.exists():
        fig_wings(pd.read_csv(ap))
    else:
        print("  (no w22_wing_amplification.csv; skipping)")

    mp, rp, lp = (config.TABLES / "w26_trend_by_moment.csv",
                  config.TABLES / "w29_learning_race.csv",
                  config.TABLES / "w28_trimming_ladder.csv")
    if mp.exists() and rp.exists() and lp.exists():
        fig_learning(pd.read_csv(mp), pd.read_csv(rp), pd.read_csv(lp))
    else:
        print("  (no learning tables; skipping the learning figure)")

    byp = config.TABLES / "w35_weekend_behaviour_by_year.csv"
    daily = {}
    for cur in config.CURRENCIES:
        dp = config.TABLES / f"w32_short_daily_{cur}.csv"
        if dp.exists():
            daily[cur] = pd.read_csv(dp, index_col=0)
    if daily and byp.exists():
        fig_shortability(daily, pd.read_csv(byp))
    else:
        print("  (no shortability tables; skipping)")

    if a.bars_only:
        print("done (skipped the tape-backed figures)")
        return 0

    for cur in config.CURRENCIES:
        df = tape.load(cur, columns=weekend.LEAN_COLS)
        d = tape.baseline_filter(df)
        del df
        T = d["T"] * config.YEAR
        d = d.loc[d["iv_ok"] & d["delta"].notna() & T.between(0.25, 14)
                  & d["delta"].abs().between(0.30, 0.70)].copy()
        d = weekend.attach(d)
        d["iv2"] = d["sigma"] ** 2
        d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms",
                                                   utc=True))
        short = d[T.reindex(d.index).between(0.25, 3)]
        ivs[cur] = short.groupby("expiry_dow")["sigma"].mean() * 100
        fig_binscatter(d, cur)
        del d, short

    pd.DataFrame(ivs).round(2).to_csv(
        config.TABLES / "w7_atm_iv_by_expiry_dow.csv", index_label="dow")
    fig_iv_by_expiry_dow(ivs)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
