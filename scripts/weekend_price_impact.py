"""What the weekend variance discount does to option *prices*.

The rest of the study is written in variance: the market quotes weekend calendar
time at roughly 0.5-0.65 of the weekday rate, and the argument is about whether
that ratio matches the realized one. A ratio of variances is the right object
for the economics and the wrong one for a trading desk, which pays premium, not
variance. This script does the translation, and it is not the trivial one the
question invites -- "volatility is lower, so by Black-Scholes the price is
lower" is right in direction and wrong in size, because three things sit between
the variance ratio and the premium:

1.  Only part of a contract's life is weekend. The variance ratio applies to the
    weekend hours alone, so what reaches the price is the ratio diluted by the
    contract's weekend fraction. A quarterly option is barely touched; a Friday
    daily expiring Monday is almost entirely exposed.

2.  Price responds to volatility, not variance, so the square root halves the
    effect in logs before anything else happens.

3.  Price is not linear in volatility away from the money. The elasticity
    sigma * vega / C is about one at the money and rises steeply into the wings,
    so the same proportional cut in volatility takes a far larger share of a
    wing premium than of an at-the-money one -- and the wings are exactly where
    section 7 finds the market applying a *deeper* weekend discount to begin
    with. The two amplifications compound.

Three questions, three answers:

  A. How much cheaper is a weekend-heavy contract than an otherwise identical
     contract quoted at the same instant with no weekend in it? This is the
     cross-sectional comparison the headline regression identifies, expressed in
     premium rather than in variance.

  B. How much of that is wrong? Repricing at the *realized* weekend ratio rather
     than the quoted one gives the pricing gap in premium terms. The weekday leg
     of the comparison carries whatever variance risk premium the market charges
     and it cancels, because both legs are built from the same contract-level
     weekday variance.

  C. What does a contract lose over a weekend? The cross-section is what a
     market maker quotes; the decay is what a position actually earns. These are
     different numbers and the second is the one that pays theta.

Nothing here feeds the working paper. Outputs land in output/tables/p*.csv and
the write-up in paper/price_impact.md.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
from scipy import stats

from dbop import config, greeks, weekend

log = logging.getLogger("weekend_price_impact")

# Same smile buckets as section 7, so the wing story lines up row for row.
ATM_BINS = (0.02, 0.10, 0.20, 0.35, 0.50)
ATM_LABELS = ("far wing", "wing", "near", "at the money")

# Maturity bands. The sample is short-dated by construction (0.25 to 14 days),
# which is where the weekend fraction actually varies; a quarterly contract is
# 2/7 weekend whatever day it is quoted on and the clock cancels out of it.
BANDS = ((0.25, 1.0, "under 1d"), (1.0, 3.0, "1-3d"),
         (3.0, 7.0, "3-7d"), (7.0, 14.0, "7-14d"))


# ----------------------------------------------------------------- the ratios
def ratios() -> pd.DataFrame:
    """Implied and realized weekend variance ratios, from the headline table."""
    d = pd.read_csv(config.TABLES / "w1_weekend_pricing.csv")
    return d.set_index("currency")[["implied_ratio", "variance_ratio",
                                    "v_weekday_implied", "gap"]]


def weekday_variance() -> dict[str, float]:
    """Fitted weekday variance rate per book, for the illustrative tables.

    Nothing measured depends on its level -- every percentage in the stylized
    map and the decay table is a ratio in which it cancels -- but taking it from
    the headline regression rather than rounding it by hand keeps the
    illustrative volatilities equal to the ones the paper reports.
    """
    return {k: float(v) for k, v in ratios()["v_weekday_implied"].items()}


def bucket_ratios() -> pd.Series:
    """Implied ratio by distance from the money, from the smile test."""
    d = pd.read_csv(config.TABLES / "w14_weekend_slope_by_moneyness.csv")
    return d.set_index(["currency", "bucket"])["implied_ratio"]


def year_ratios() -> pd.DataFrame:
    """Per-year implied and realized ratios, from the vintage trajectory.

    The pooled figures hold the clock fixed at its full-sample value, so the
    year-to-year movement in a pooled-clock table is contract mix and nothing
    else. Section 5.5 measures the clock itself deepening by about 0.14 a year,
    which is the larger part of the story and is only visible if each year is
    repriced against its own estimate. The early years are kept and flagged
    rather than dropped: identification is thin before 2021 -- Deribit had no
    daily expiries -- and an implied ratio above one there is mostly noise, but
    it is noise around a real fact, which is that the market began the sample
    pricing no weekend discount at all.
    """
    d = pd.read_csv(config.TABLES / "w17_split_trajectory.csv")
    d = d.rename(columns={"asset": "currency"})
    d["usable"] = d["implied_ratio_se"] < 0.5
    return d.set_index(["currency", "year"])[
        ["implied_ratio", "implied_ratio_se", "realized_ratio", "usable"]]


def damp(w, ratio) -> np.ndarray:
    """Effective-time factor: the variance of a contract with weekend fraction w.

    Total variance to expiry is v_wd * T * (1 - (1 - R) w), so this is the
    factor multiplying the weekday variance rate. It is also the ratio of
    effective time to calendar time, which is the more useful reading of it.
    """
    return 1.0 - (1.0 - np.asarray(ratio, dtype="float64")) * np.asarray(
        w, dtype="float64")


def elasticity(F, K, T, sigma, cp) -> np.ndarray:
    """d log C / d log sigma = sigma * vega / C.

    One at the money and rising into the wings. This is the multiplier that
    turns a proportional volatility change into a proportional price change to
    first order; the tables report the exact repricing beside it, and the two
    part company exactly where the elasticity is large.
    """
    F = np.asarray(F, dtype="float64")
    K = np.asarray(K, dtype="float64")
    T = np.asarray(T, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    vega = F * stats.norm.pdf(d1) * np.sqrt(T)
    c = greeks.price_usd(F, K, T, sigma, cp)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(c > 0, sigma * vega / c, np.nan)


# -------------------------------------------------------- A. the stylized map
def stylized(cur: str, R: float, R_real: float) -> pd.DataFrame:
    """The map from weekend fraction to premium, at the fitted weekday vol.

    Moneyness is set in standard deviations of the contract's own weekday
    variance so a row means the same thing at every maturity, and the weekend
    fractions are the ones the calendar actually produces: zero for a contract
    listed and expiring inside the working week, 2/7 for a long-dated one, 2/3
    for a Friday 08:00 expiring Monday 08:00, one for a Saturday daily.
    """
    sig_wd = np.sqrt(weekday_variance()[cur])
    rows = []
    for T_days in (1.0, 3.0, 7.0, 30.0):
        T = T_days / config.YEAR
        for w in (0.0, 2 / 7, 0.5, 2 / 3, 1.0):
            f = float(damp(w, R))
            sig = sig_wd * np.sqrt(f)
            sig_fair = sig_wd * np.sqrt(float(damp(w, R_real)))
            for z, lab in ((0.0, "at the money"), (1.0, "1 sd out"),
                           (2.0, "2 sd out")):
                # The strike is fixed in standard deviations of the *weekday*
                # contract, so both legs are the same instrument and only the
                # clock differs between them.
                K = float(np.exp(z * sig_wd * np.sqrt(T)))
                c_wd = float(greeks.price_usd(1.0, K, T, sig_wd, 1.0))
                c_we = float(greeks.price_usd(1.0, K, T, sig, 1.0))
                c_fair = float(greeks.price_usd(1.0, K, T, sig_fair, 1.0))
                el = float(elasticity(1.0, K, T, sig_wd, 1.0))
                rows.append({
                    "currency": cur, "T_days": T_days, "wknd_frac": w,
                    "moneyness": lab, "eff_time_frac": f,
                    "vol_weekday": float(sig_wd), "vol_weekend": float(sig),
                    "vol_cut_pct": float(sig / sig_wd - 1) * 100,
                    "vol_cut_points": float(sig - sig_wd) * 100,
                    "elasticity": el,
                    "prem_weekday_pct_fwd": c_wd * 100,
                    "prem_weekend_pct_fwd": c_we * 100,
                    "price_cut_pct": (c_we / c_wd - 1) * 100 if c_wd > 0 else np.nan,
                    "price_cut_firstorder_pct": el * (sig / sig_wd - 1) * 100,
                    "price_gap_pct": (c_we / c_fair - 1) * 100 if c_fair > 0 else np.nan,
                })
    return pd.DataFrame(rows)


# ------------------------------------------------------------- B. on the tape
def load(cur: str, extra: tuple[str, ...] = ()) -> pd.DataFrame:
    """The traded sample.

    Every price here is computed as a fraction of the forward, which is all the
    repricing needs; the trade's own forward is carried so those fractions can
    be turned into dollars at the level that actually prevailed when the trade
    printed, rather than at a daily close.
    """
    d = pd.read_parquet(config.PANELS / f"smile_sample_{cur}.parquet",
                        columns=["iv2", "logT", "atmness", "is_call", "logm",
                                 "wknd_frac", "size", "date", "F"]
                                + list(extra))
    d["date"] = pd.to_datetime(d["date"], utc=True)
    d["T_days"] = np.exp(d["logT"].to_numpy())
    d["bucket"] = pd.cut(d["atmness"], ATM_BINS, labels=list(ATM_LABELS),
                         right=False)
    band = pd.Series(pd.NA, index=d.index, dtype="object")
    for lo, hi, lab in BANDS:
        band[(d["T_days"] >= lo) & (d["T_days"] < hi)] = lab
    d["band"] = band
    return d


def reprice(d: pd.DataFrame, R, R_real) -> pd.DataFrame:
    """Three prices per trade: as quoted, with the clock off, at realized.

    All three are the same contract -- same strike, same expiry, same instant,
    same forward -- and differ only in the volatility the clock implies. The
    contract's own quoted variance supplies the weekday rate, so the level of
    the surface, the variance risk premium inside it, and every strike- and
    maturity-specific quirk are held fixed and cancel from the comparison.

    The effect columns are computed on the out-of-the-money leg at each strike
    rather than on whichever leg happened to trade. Put-call parity makes the
    forward-intrinsic part of an in-the-money premium insensitive to volatility,
    so the *dollar* effect is identical either way, but the percentage is not:
    dividing a real dollar effect by a premium that is nine tenths intrinsic
    reports a small number about a large one. Time value is the part of the
    premium that volatility prices, so it is the denominator. The premium
    actually paid on the traded leg is carried alongside for context.
    """
    T = d["T_days"].to_numpy() / config.YEAR
    K = np.exp(d["logm"].to_numpy())
    cp = np.where(d["is_call"].to_numpy() > 0, 1.0, -1.0)
    sig_q = np.sqrt(d["iv2"].to_numpy())
    w = d["wknd_frac"].to_numpy()

    f = damp(w, R)
    sig_flat = sig_q / np.sqrt(f)                    # the clock switched off
    sig_fair = sig_flat * np.sqrt(damp(w, R_real))   # the clock set to realized

    # The out-of-the-money leg at this strike: a call above the forward, a put
    # below it. Its premium is pure time value.
    otm = np.where(K >= 1.0, 1.0, -1.0)
    c_q = greeks.price_usd(1.0, K, T, sig_q, otm)
    c_flat = greeks.price_usd(1.0, K, T, sig_flat, otm)
    c_fair = greeks.price_usd(1.0, K, T, sig_fair, otm)
    c_paid = greeks.price_usd(1.0, K, T, sig_q, cp)

    out = pd.DataFrame(index=d.index)
    out["eff_time_frac"] = f
    out["vol_cut_pct"] = (sig_q / sig_flat - 1.0) * 100
    out["vol_cut_points"] = (sig_q - sig_flat) * 100
    out["elasticity"] = elasticity(1.0, K, T, sig_flat, otm)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["price_cut_pct"] = np.where(c_flat > 0, c_q / c_flat - 1.0,
                                        np.nan) * 100
        out["price_gap_pct"] = np.where(c_fair > 0, c_q / c_fair - 1.0,
                                        np.nan) * 100
    # Dollars of premium. `amount` is in units of the base coin for every option
    # book on this venue, inverse and linear alike, so premium-as-a-fraction-of-
    # forward, times the forward, times the amount is USD under both
    # conventions and no contract multiplier enters.
    notional = d["size"].to_numpy() * d["F"].to_numpy()
    out["tv_usd"] = c_q * notional
    out["tv_flat_usd"] = c_flat * notional
    out["tv_fair_usd"] = c_fair * notional
    out["prem_paid_usd"] = c_paid * notional
    return out


def summarize(d: pd.DataFrame, r: pd.DataFrame, keys: list[str],
              cur: str) -> pd.DataFrame:
    """Premium-weighted averages of the per-contract effects.

    Weighted by premium rather than by contract count: the question is what the
    discount does to the money that changes hands, and a book whose trades are
    mostly one-lot far wings would otherwise be described by its least valuable
    contracts. The weight is the counterfactual premium, so the weighting scheme
    itself does not respond to the effect being measured.
    """
    g = pd.concat([d[keys + ["wknd_frac"]], r], axis=1)
    g = g[np.isfinite(g["price_cut_pct"]) & np.isfinite(g["price_gap_pct"])
          & (g["tv_flat_usd"] > 0) & np.isfinite(g["tv_usd"])
          & np.isfinite(g["prem_paid_usd"])]
    rows = []
    for k, sub in g.groupby(keys, observed=True, dropna=True):
        wt = sub["tv_flat_usd"].to_numpy()
        key = k if isinstance(k, tuple) else (k,)
        rows.append({
            "currency": cur,
            **{c: v for c, v in zip(keys, key)},
            "n": len(sub),
            "wknd_frac_mean": float(np.average(sub["wknd_frac"], weights=wt)),
            "eff_time_frac": float(np.average(sub["eff_time_frac"], weights=wt)),
            "vol_cut_pct": float(np.average(sub["vol_cut_pct"], weights=wt)),
            "vol_cut_points": float(np.average(sub["vol_cut_points"],
                                               weights=wt)),
            "elasticity": float(np.average(sub["elasticity"], weights=wt)),
            # The aggregate cut is the ratio of the two premium totals, which is
            # what a book-level P&L shows; the weighted mean of the per-trade
            # percentages sits beside it because the two differ whenever the
            # effect covaries with contract value.
            "price_cut_pct": float(sub["tv_usd"].sum()
                                   / sub["tv_flat_usd"].sum() - 1) * 100,
            "price_cut_pct_mean": float(np.average(sub["price_cut_pct"],
                                                   weights=wt)),
            "price_gap_pct": float(sub["tv_usd"].sum()
                                   / sub["tv_fair_usd"].sum() - 1) * 100,
            "tv_usd_m": float(sub["tv_usd"].sum()) / 1e6,
            "tv_flat_usd_m": float(sub["tv_flat_usd"].sum()) / 1e6,
            "tv_fair_usd_m": float(sub["tv_fair_usd"].sum()) / 1e6,
            # What the discount is worth in dollars: the premium the clock
            # removes, and the part of that which realized variance does not
            # justify. Signed so that a positive discount_usd_m is money the
            # weekend clock takes off the price.
            "discount_usd_m": float(sub["tv_flat_usd"].sum()
                                    - sub["tv_usd"].sum()) / 1e6,
            "gap_usd_m": float(sub["tv_usd"].sum()
                               - sub["tv_fair_usd"].sum()) / 1e6,
            "prem_paid_usd_m": float(sub["prem_paid_usd"].sum()) / 1e6,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------- C. the decay
def decay(cur: str, R: float) -> pd.DataFrame:
    """What a contract loses from Friday 08:00 to Monday 08:00.

    The cross-section says what a weekend-heavy contract is quoted at. It does
    not say what a position earns, because a position also moves through the
    weekend: three calendar days pass and only about two effective days do. The
    two numbers are different, and this is the one that pays theta.

    Priced at the money on both dates with the strike fixed at Friday's forward
    and the underlying unchanged, so the whole difference is the clock. The
    weekend fraction on each date is the exact one the calendar produces.
    """
    fri = pd.Timestamp("2025-01-03 08:00", tz="UTC")   # a Friday, at the cut
    mon = fri + pd.Timedelta(days=3)
    sig_wd = np.sqrt(weekday_variance()[cur])
    rows = []
    for T_days in (4.0, 5.0, 7.0, 10.0, 14.0, 30.0, 60.0):
        exp = fri + pd.Timedelta(days=T_days)
        ms = lambda t: np.array([t.value // 10 ** 6], dtype="int64")
        w_f = float(weekend.weekend_fraction(ms(fri), ms(exp))[0])
        w_m = float(weekend.weekend_fraction(ms(mon), ms(exp))[0])
        Tf, Tm = T_days / config.YEAR, (T_days - 3.0) / config.YEAR
        # Flat calendar: the same volatility on both dates, only the clock runs.
        c_f0 = float(greeks.price_usd(1.0, 1.0, Tf, sig_wd, 1.0))
        c_m0 = float(greeks.price_usd(1.0, 1.0, Tm, sig_wd, 1.0))
        # Weekend clock: the volatility is itself rescaled by the weekend
        # content of the remaining life, which falls as the weekend is spent.
        c_f1 = float(greeks.price_usd(1.0, 1.0, Tf,
                                      sig_wd * np.sqrt(float(damp(w_f, R))), 1.0))
        c_m1 = float(greeks.price_usd(1.0, 1.0, Tm,
                                      sig_wd * np.sqrt(float(damp(w_m, R))), 1.0))
        rows.append({
            "currency": cur, "T_days_friday": T_days,
            "wknd_frac_friday": w_f, "wknd_frac_monday": w_m,
            "eff_days_friday": T_days * float(damp(w_f, R)),
            "eff_days_monday": (T_days - 3.0) * float(damp(w_m, R)),
            "decay_flat_pct": (c_m0 / c_f0 - 1) * 100,
            "decay_clock_pct": (c_m1 / c_f1 - 1) * 100,
            "premium_saved_pct": (c_m1 / c_f1 - c_m0 / c_f0) * 100,
            "friday_markdown_pct": (np.sqrt(float(damp(w_f, R))) - 1) * 100,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- figure
def figure(sty: pd.DataFrame, own: pd.DataFrame):
    """Two panels: the map, and what the market has actually been doing with it.

    Left is arithmetic -- the premium a Bitcoin contract loses as its life fills
    with weekend, at three distances from the money, on the full-sample clock.
    Right is measurement: each year's traded book repriced against that year's
    own estimated clock, so the deepening documented in section 5.5 shows up as
    a premium effect that has roughly tripled and a pricing gap that has crossed
    from rich to cheap.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 140, "savefig.dpi": 200, "font.size": 9,
                         "axes.grid": True, "grid.alpha": 0.25,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.autolayout": True})

    fig, (a, b) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    d = sty[(sty["currency"] == "BTC") & (sty["T_days"] == 3.0)]
    for lab, mk in (("at the money", "o"), ("1 sd out", "s"), ("2 sd out", "^")):
        g = d[d["moneyness"] == lab].sort_values("wknd_frac")
        a.plot(g["wknd_frac"], g["price_cut_pct"], marker=mk, lw=1.2, ms=4,
               label=lab)
    a.axvline(2 / 3, color="k", lw=0.6, ls=":")
    a.text(2 / 3, -2, "  Friday daily,\n  expires Monday", fontsize=7,
           va="top")
    a.axhline(0, color="k", lw=0.5)
    a.set_xlabel("fraction of the contract's life falling on a weekend")
    a.set_ylabel("premium vs the same contract with no weekend (%)")
    a.set_title("What the clock takes off a 3-day Bitcoin option", fontsize=9)
    a.legend(frameon=False, fontsize=8, loc="lower left")

    for cur, col in (("BTC", "#1f77b4"), ("ETH", "#d62728")):
        g = own[(own["currency"] == cur) & own["usable"]].sort_values("year")
        b.plot(g["year"], g["price_cut_pct"], marker="o", ms=4, lw=1.2,
               color=col, label=f"{cur}: discount applied")
        b.plot(g["year"], g["price_gap_pct"], marker="s", ms=4, lw=1.2,
               ls="--", color=col, label=f"{cur}: unjustified by realized")
    b.axhline(0, color="k", lw=0.5)
    b.set_xlabel("year, each repriced on its own estimated clock")
    b.set_ylabel("% of time value traded")
    b.set_title("The discount has deepened; the gap has changed sign",
                fontsize=9)
    b.legend(frameon=False, fontsize=7.5, loc="lower left")

    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"p_f1_price_impact.{ext}",
                    bbox_inches="tight")
    plt.close(fig)
    log.info("wrote figure p_f1_price_impact")


# --------------------------------------------------------------------- driver
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--currency", default=None,
                    help="restrict to one book (default: all four)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    curs = [a.currency] if a.currency else list(config.CURRENCIES)
    rat, brat = ratios(), bucket_ratios()

    sty = pd.concat([stylized(c, float(rat.loc[c, "implied_ratio"]),
                              float(rat.loc[c, "variance_ratio"]))
                     for c in curs], ignore_index=True)
    sty.to_csv(config.TABLES / "p1_price_impact_stylized.csv", index=False)

    dec = pd.concat([decay(c, float(rat.loc[c, "implied_ratio"]))
                     for c in curs], ignore_index=True)
    dec.to_csv(config.TABLES / "p4_weekend_decay.csv", index=False)

    yr = year_ratios()
    by_bucket, by_band, pooled, wing = [], [], [], []
    by_year, own_clock = [], []
    for c in curs:
        log.info("pricing %s", c)
        d = load(c)
        R = float(rat.loc[c, "implied_ratio"])
        R_real = float(rat.loc[c, "variance_ratio"])
        r = reprice(d, np.full(len(d), R), np.full(len(d), R_real))
        d["_all"] = "all"
        d["year"] = d["date"].dt.year
        by_bucket.append(summarize(d, r, ["bucket"], c))
        by_band.append(summarize(d, r, ["band"], c))
        pooled.append(summarize(d, r, ["_all"], c))
        # By year, because none of these dollar totals is an annual figure:
        # volume grew by orders of magnitude across the sample and the quoted
        # clock itself deepened every year, so a per-year average of the total
        # would describe no year in the sample.
        by_year.append(summarize(d, r, ["year"], c))
        del r

        # The wing variant: each bucket repriced against the ratio the market
        # actually quotes there rather than against the pooled one. This is the
        # smile test of section 7 carried into premium -- the far wings run on a
        # deeper clock *and* are the most elastic to it.
        Rb = d["bucket"].map(
            {b: float(brat.loc[(c, b)]) for b in ATM_LABELS}
        ).astype("float64").to_numpy()
        keep = np.isfinite(Rb)
        dk = d.loc[keep]
        wing.append(summarize(dk, reprice(dk, Rb[keep],
                                          np.full(len(dk), R_real)),
                              ["bucket"], c))
        del dk

        # Each year against its own clock, quoted and realized alike.
        y = yr.loc[c].reindex(d["year"].to_numpy())
        keep = y["implied_ratio"].notna().to_numpy() & y["realized_ratio"].notna().to_numpy()
        dy = d.loc[keep]
        oc = summarize(dy, reprice(dy, y["implied_ratio"].to_numpy()[keep],
                                   y["realized_ratio"].to_numpy()[keep]),
                       ["year"], c)
        oc = oc.merge(yr.loc[c].reset_index()[
            ["year", "implied_ratio", "implied_ratio_se", "realized_ratio",
             "usable"]], on="year", how="left")
        own_clock.append(oc)
        del d, dy

    pd.concat(by_bucket, ignore_index=True).to_csv(
        config.TABLES / "p2_price_impact_by_moneyness.csv", index=False)
    pd.concat(by_band, ignore_index=True).to_csv(
        config.TABLES / "p3_price_impact_by_maturity.csv", index=False)
    pd.concat(wing, ignore_index=True).to_csv(
        config.TABLES / "p5_price_impact_wing_clock.csv", index=False)
    pd.concat(by_year, ignore_index=True).to_csv(
        config.TABLES / "p7_price_impact_by_year.csv", index=False)
    pd.concat(own_clock, ignore_index=True).to_csv(
        config.TABLES / "p8_price_impact_own_clock.csv", index=False)
    pool = pd.concat(pooled, ignore_index=True)
    pool.to_csv(config.TABLES / "p6_price_impact_pooled.csv", index=False)
    if not a.currency:
        figure(sty, pd.concat(own_clock, ignore_index=True))

    print("\n=== pooled, premium-weighted ===")
    print(pool[["currency", "wknd_frac_mean", "vol_cut_pct", "elasticity",
                "price_cut_pct", "price_gap_pct", "tv_usd_m", "discount_usd_m",
                "gap_usd_m"]]
          .to_string(index=False, float_format=lambda x: f"{x:8.3f}"))
    for f in ("p1_price_impact_stylized", "p2_price_impact_by_moneyness",
              "p3_price_impact_by_maturity", "p4_weekend_decay",
              "p5_price_impact_wing_clock", "p6_price_impact_pooled",
              "p7_price_impact_by_year", "p8_price_impact_own_clock"):
        print(f"-> {config.TABLES / (f + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
