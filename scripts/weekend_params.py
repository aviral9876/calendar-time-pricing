"""What else can be varied to trade the weekend, and does any of it help?

Sections 6.1 and 6.2 establish that the trade the paper documents has stopped
paying and that removing its hedge does not repair it. Both hold one contract
selection fixed: delta 0.35-0.65, half a day to seven days, one entry per day
per side. This script asks whether the selection itself was the binding choice,
by sweeping the knobs a desk actually has.

Four knobs, in the order they are worth trying:

  1. Entry conditioning (w57). Only trade when the weekend is quoted rich
     against a *predetermined* benchmark -- the trailing realized weekend ratio
     known before the entry. This is the one knob that could restore an edge
     rather than merely relocate it, because section 6.1's diagnosis is that the
     quoted cushion has compressed, not that it has become unpredictable.
  2. Moneyness (w56). Section 7 finds the far wings discount the weekend
     *harder* than the money in all four books. If that is a real structural
     over-discount, the weekend is relatively cheap in the wings and rich at the
     money, and the trade should be selective about where on the smile it sells.
  3. Maturity (w56). Shorter contracts concentrate the weekend, so a two-day
     contract entered on a Friday is almost pure weekend while a seven-day one
     is one part weekend to two parts weekday. More concentration is more signal
     per unit of vega, and also less time for the hedge to drift.
  4. Saturday against Sunday (w58, w59). The weekend paper's section 5.4 finds
     the market prices Saturday as indistinguishable from Sunday when Saturday
     is reliably the quieter -- a mispricing *inside* the weekend, orthogonal to
     whether the weekend as a whole is priced right, and so a candidate to
     outlive the decay that killed the calendar spread. It turns out not to be
     spreadable at all: `sat_sun_availability` shows the expiry schedule offers
     both legs at once in only 13 hours of the week, none of them on a weekday.
     That result is the weekend paper's, not this sweep's, and is quoted there.

Knobs 1-3 overlap the companion trading paper, which tests entry conditioning
against eight pre-specified factors with an out-of-sample split rather than the
in-sample terciles used here; where the two disagree, prefer that one.

Every P&L here comes from the same engine as section 6, so costs are the same
measured ones. The hedge path does not depend on how contracts are bucketed, so
each asset's P&L is simulated once over a wide candidate set and then sliced;
that is what makes a sweep this size affordable.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import weekend_commercial as wc                              # noqa: E402

from dbop import bars, config, costs, greeks, tape, util, weekend   # noqa: E402

log = logging.getLogger("weekend_params")

# Wider than section 6's window on both axes, so every slice below is a subset
# of one simulation rather than a separate one.
DELTA_BAND = (0.10, 0.90)
MIN_T_DAYS, MAX_T_DAYS = 0.5, 8.0
REHEDGE = (60, 1440)

DELTA_CELLS = (("wing", 0.10, 0.25), ("near", 0.25, 0.40),
               ("money", 0.40, 0.60), ("baseline", 0.35, 0.65))
MAT_CELLS = (("<=2d", 0.5, 2.0), ("2-4d", 2.0, 4.0), ("4-8d", 4.0, 8.0),
             ("baseline", 0.5, 7.0))
MIN_PAIRED = 40
# A leg has to be genuinely tilted toward its day, not merely the less-tilted
# of what happened to trade.
TILT_THRESHOLD = 0.15


def wide_entries(cur: str) -> pd.DataFrame:
    """Section 6's candidate set, opened up on delta and maturity."""
    df = tape.load(cur, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    keep = (d["iv_ok"] & d["delta"].notna()
            & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
            & d["delta"].abs().between(*DELTA_BAND)
            & (d["premium_usd"] > 0))
    d = d.loc[keep].copy()
    d = weekend.attach(d)
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
    d["T_days"] = d["T"] * config.YEAR
    d["abs_delta"] = d["delta"].abs()

    fr = weekend.all_day_fractions(d["timestamp"].to_numpy(),
                                   d["expiration_timestamp"].to_numpy())
    d["sat_frac"] = fr[:, 5]
    d["sun_frac"] = fr[:, 6]
    return d


def cell_label(d: pd.DataFrame) -> pd.DataFrame:
    """Tag every trade with the delta and maturity cell it belongs to.

    Cells overlap -- "baseline" spans the others -- so a trade can belong to
    two, and the frame is exploded rather than partitioned.
    """
    out = []
    for dname, dlo, dhi in DELTA_CELLS:
        for mname, mlo, mhi in MAT_CELLS:
            m = (d["abs_delta"].between(dlo, dhi)
                 & d["T_days"].between(mlo, mhi))
            if m.sum() == 0:
                continue
            g = d.loc[m, ["date", "wknd_frac", "timestamp"]].copy()
            g["delta_cell"], g["mat_cell"] = dname, mname
            g["row"] = d.index[m]
            out.append(g)
    return pd.concat(out, ignore_index=True)


def pick_pairs(d: pd.DataFrame, tags: pd.DataFrame) -> pd.DataFrame:
    """One weekend-heavy and one weekday-only entry per day, per cell.

    Buckets are assigned inside each (day, cell) cross-section for the same
    reason section 6 assigns them inside each day: an absolute weekend-coverage
    threshold describes a spread whose two legs rarely exist at the same time.
    """
    keep = []
    for (dc, mc), g in tags.groupby(["delta_cell", "mat_cell"], observed=True):
        q = g.groupby("date")["wknd_frac"]
        lo, hi = q.transform(lambda s: s.quantile(0.25)), q.transform(lambda s: s.quantile(0.75))
        ok = (hi - lo) >= 0.15
        side = np.where(ok & (g["wknd_frac"] >= hi), "weekend_heavy",
                 np.where(ok & (g["wknd_frac"] <= lo), "weekday_only", "mixed"))
        g = g.assign(side=side)
        g = g[g["side"] != "mixed"].sort_values("timestamp")
        keep.append(g.groupby(["date", "side"], observed=True).head(1))
    return pd.concat(keep, ignore_index=True)


def simulate(cur: str, d: pd.DataFrame, rows: np.ndarray,
             step: int) -> pd.DataFrame:
    """Net and gross P&L per unit vega for one set of candidate entries."""
    e = d.loc[rows].copy()
    half_sp = costs.summarize_spread(
        costs.effective_spread_iv(d)).get("median_half_spread_volpts", 0.0) / 100.0

    b = bars.load(cur)
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()

    gross = wc.hedged_pnl_to_expiry(e, px, rehedge_minutes=step,
                                    charge_costs=False)
    net = wc.hedged_pnl_to_expiry(e, px, rehedge_minutes=step,
                                  charge_costs=True, half_spread_vol=half_sp)
    vega = greeks.greeks(e["F"].to_numpy(), e["strike"].to_numpy(dtype="float64"),
                         e["T"].to_numpy(), e["sigma"].to_numpy(),
                         e["cp_sign"].to_numpy())["vega_usd"]
    v = pd.Series(vega, index=e.index).replace(0, np.nan)
    return pd.DataFrame({"net": net / v, "gross": gross / v}, index=e.index)


def _stats(s: pd.Series, label: str = "") -> dict:
    s = s.dropna()
    n = len(s)
    if n < 2:
        return {f"{label}n": n, f"{label}mean": np.nan, f"{label}t": np.nan,
                f"{label}sharpe": np.nan}
    mu, sd = s.mean(), s.std()
    return {f"{label}n": n, f"{label}mean": mu,
            f"{label}t": mu / (sd / np.sqrt(n)),
            f"{label}sharpe": mu / sd * np.sqrt(252) if sd > 0 else np.nan}


def _spread_series(pairs: pd.DataFrame, pnl: pd.DataFrame) -> pd.Series:
    """Weekend-heavy minus weekday-only, per date, for one cell."""
    p = pairs.assign(net=pnl["net"].reindex(pairs["row"]).to_numpy())
    piv = p.pivot_table(index="date", columns="side", values="net")
    if "weekend_heavy" not in piv or "weekday_only" not in piv:
        return pd.Series(dtype="float64")
    piv = piv.dropna()
    return (piv["weekend_heavy"] - piv["weekday_only"]).sort_index()


def sweep(cur: str, d: pd.DataFrame, pairs: pd.DataFrame,
          pnls: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Delta cell x maturity cell x rehedge interval."""
    rows = []
    for step, pnl in pnls.items():
        for (dc, mc), g in pairs.groupby(["delta_cell", "mat_cell"],
                                         observed=True):
            s = _spread_series(g, pnl)
            if len(s) < MIN_PAIRED:
                continue
            idx = pd.to_datetime(s.index)
            recent = s[idx >= idx.max() - pd.Timedelta(days=365)]
            rows.append({"asset": cur, "rehedge_minutes": step,
                         "delta_cell": dc, "mat_cell": mc,
                         **_stats(s), **_stats(recent, "recent_")})
    return pd.DataFrame(rows)


def richness(cur: str, d: pd.DataFrame, pairs: pd.DataFrame,
             pnl: pd.DataFrame, window: int = 90) -> pd.DataFrame:
    """Condition entry on how rich the weekend is quoted, ex ante.

    The signal is the ratio of the day's weekend-heavy implied variance to its
    weekday-only implied variance, divided by a trailing realized weekend
    variance ratio. Both pieces are known before the trade: the quotes are the
    ones being traded on, and the realized ratio is computed on bars that closed
    strictly before the entry day. A value above one says the market is asking
    more for the weekend than the recent past says it is worth.
    """
    base = pairs[(pairs["delta_cell"] == "baseline")
                 & (pairs["mat_cell"] == "baseline")]
    if base.empty:
        return pd.DataFrame()

    e = d.loc[base["row"]].copy()
    e["side"] = base["side"].to_numpy()
    iv = e.pivot_table(index="date", columns="side", values="sigma")
    if "weekend_heavy" not in iv or "weekday_only" not in iv:
        return pd.DataFrame()
    implied = (iv["weekend_heavy"] / iv["weekday_only"]) ** 2

    rv = weekend.realized_by_daytype(bars.load(cur))
    rv["date"] = pd.to_datetime(rv["date"], utc=True)
    rv = rv.set_index("date").sort_index()
    var = rv["ann_vol"] ** 2
    we = var.where(rv["is_weekend"]).rolling(window, min_periods=15).mean()
    wd = var.where(~rv["is_weekend"]).rolling(window, min_periods=30).mean()
    # shift(1): the entry day's own bars have not closed when the trade is put
    # on, so the benchmark must stop at the previous day.
    trailing = (we / wd).shift(1)

    s = _spread_series(base, pnl)
    sig = (implied / trailing.reindex(implied.index)).reindex(s.index)
    good = sig.notna()
    s, sig = s[good], sig[good]
    if len(s) < 4 * MIN_PAIRED:
        return pd.DataFrame()

    rows = []
    idx = pd.to_datetime(s.index)
    recent_mask = idx >= idx.max() - pd.Timedelta(days=365)
    # Terciles of the signal, cut on the full sample: a desk calibrating this
    # live would use an expanding cut, so these are an upper bound on what the
    # filter can do.
    q = sig.rank(pct=True)
    for name, m in (("all", pd.Series(True, index=s.index)),
                    ("rich (top third)", q > 2 / 3),
                    ("middle", (q > 1 / 3) & (q <= 2 / 3)),
                    ("cheap (bottom third)", q <= 1 / 3)):
        rows.append({"asset": cur, "bucket": name,
                     "median_signal": float(sig[m].median()),
                     **_stats(s[m]),
                     **_stats(s[m & pd.Series(recent_mask, index=s.index)],
                              "recent_")})
    return pd.DataFrame(rows)


def sat_sun_availability(entry_hours: int = 24) -> pd.DataFrame:
    """When does the listing schedule offer a Saturday leg and a Sunday leg at once?

    Pure calendar arithmetic -- no tape. Deribit lists daily expiries at 08:00
    UTC, so which weekday a contract's remaining life falls on is fixed by its
    entry time and its expiry date alone. Enumerating every hour of a week
    against every expiry inside the maturity window gives the complete menu a
    desk could ever choose from.

    This is the constraint that decides whether section 5.4's Saturday-versus-
    Sunday mispricing is arbitrageable at all, and it turns out to be binding.
    """
    base = pd.Timestamp("2024-01-01", tz="UTC")            # a Monday
    rows = []
    for d0 in range(7):
        for h in range(entry_hours):
            entry = base + pd.Timedelta(days=d0, hours=h * (24 // entry_hours))
            for k in range(1, 9):
                exp = ((base + pd.Timedelta(days=d0 + k)).normalize()
                       + pd.Timedelta(hours=config.EXPIRY_HOUR_UTC))
                if exp <= entry:
                    continue
                T = (exp - entry).total_seconds() / 86400
                if not (MIN_T_DAYS <= T <= MAX_T_DAYS):
                    continue
                fr = weekend.all_day_fractions(
                    np.array([entry.value // 10**6], dtype="int64"),
                    np.array([exp.value // 10**6], dtype="int64"))[0]
                sat, sun = fr[5], fr[6]
                if sat + sun <= 0.15:
                    continue
                rows.append({"entry_dow": d0, "entry_hour": entry.hour,
                             "expiry_dow": exp.dayofweek, "T_days": T,
                             "sat_frac": sat, "sun_frac": sun,
                             "tilt": (sat - sun) / (sat + sun)})
    w = pd.DataFrame(rows)
    if w.empty:
        return w
    g = w.groupby(["entry_dow", "entry_hour"]).agg(
        n_contracts=("tilt", "size"),
        has_sat=("tilt", lambda s: bool((s >= TILT_THRESHOLD).any())),
        has_sun=("tilt", lambda s: bool((s <= -TILT_THRESHOLD).any())),
        min_tilt=("tilt", "min"), max_tilt=("tilt", "max")).reset_index()
    g["both_legs"] = g["has_sat"] & g["has_sun"]
    return g


def sat_sun_pairs(d: pd.DataFrame) -> pd.DataFrame:
    """Pick one Saturday-heavy and one Sunday-heavy entry per day.

    Selection has to happen before the P&L is simulated: every short-dated
    contract listed on a Friday or Saturday carries some weekend, so an
    unnarrowed candidate set is most of the tape and simulating it costs hours
    for two series per day.
    """
    e = d[(d["sat_frac"] + d["sun_frac"]) > 0.15][
        ["date", "sat_frac", "sun_frac", "timestamp", "abs_delta"]].copy()
    if e.empty:
        return e
    # Stay near the money so the two legs are comparable in vega; the smile is
    # a separate knob, tested in `sweep`.
    e = e[e["abs_delta"].between(0.30, 0.70)]
    if e.empty:
        return e
    e["tilt"] = ((e["sat_frac"] - e["sun_frac"])
                 / (e["sat_frac"] + e["sun_frac"]))
    # Absolute thresholds, not within-day quantiles. A quantile cut always
    # produces two sides, even on the four days a week when no Sunday-heavy
    # contract exists at all -- it then labels a perfectly balanced weekend
    # contract "sun_heavy" and the spread silently becomes pure-Saturday
    # against whole-weekend. See `sat_sun_availability`.
    e["side"] = np.where(e["tilt"] >= TILT_THRESHOLD, "sat_heavy",
                  np.where(e["tilt"] <= -TILT_THRESHOLD, "sun_heavy", "mixed"))
    e = e[e["side"] != "mixed"].sort_values("timestamp")
    return e.groupby(["date", "side"], observed=True).head(1)


def sat_vs_sun(cur: str, first: pd.DataFrame, pnl_rows: pd.DataFrame,
               step: int) -> pd.DataFrame:
    """Sell the Saturday-heavy contract, buy the Sunday-heavy one.

    Section 5.4 finds the market prices the two days alike while Saturday is
    reliably quieter, so a spread that is short Saturday and long Sunday should
    earn even where the weekend as a whole is fairly priced. Both legs sit
    inside the weekend, so the common weekend discount differences out and what
    is left is the market's failure to rank the two days.
    """
    if first.empty:
        return pd.DataFrame()
    pnl = pnl_rows.reindex(first.index)
    p = first.assign(net=pnl["net"].to_numpy())
    piv = p.pivot_table(index="date", columns="side", values="net")
    if "sat_heavy" not in piv or "sun_heavy" not in piv:
        return pd.DataFrame()
    piv = piv.dropna()
    if len(piv) < MIN_PAIRED:
        return pd.DataFrame()
    s = (piv["sat_heavy"] - piv["sun_heavy"]).sort_index()
    idx = pd.to_datetime(s.index)
    recent = s[idx >= idx.max() - pd.Timedelta(days=365)]
    return pd.DataFrame([{
        "asset": cur, "rehedge_minutes": step,
        "median_sat_tilt": float(first[first.side == "sat_heavy"]["tilt"].median()),
        "median_sun_tilt": float(first[first.side == "sun_heavy"]["tilt"].median()),
        **_stats(s), **_stats(recent, "recent_")}])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    sweeps, riches, sats = [], [], []
    for cur in a.currencies:
        log.info("%s: building wide candidate set", cur)
        d = wide_entries(cur)
        tags = cell_label(d)
        pairs = pick_pairs(d, tags)
        ss = sat_sun_pairs(d)
        rows = np.union1d(pairs["row"].unique(),
                          ss.index.to_numpy() if not ss.empty else np.array([], dtype="int64"))
        log.info("%s: %d candidate entries over %d days",
                 cur, len(rows), d["date"].nunique())

        pnls = {}
        for step in REHEDGE:
            log.info("%s: simulating at %d-minute rehedging", cur, step)
            pnls[step] = simulate(cur, d, rows, step)

        sweeps.append(sweep(cur, d, pairs, pnls))
        riches.append(richness(cur, d, pairs, pnls[REHEDGE[-1]]))
        for step in REHEDGE:
            sats.append(sat_vs_sun(cur, ss, pnls[step], step))
        del d, tags, pairs, ss, pnls

    for frames, name in ((sweeps, "w56_param_sweep"),
                         (riches, "w57_richness_filter"),
                         (sats, "w58_sat_vs_sun")):
        frames = [f for f in frames if not f.empty]
        if not frames:
            log.warning("%s: nothing to write", name)
            continue
        out = pd.concat(frames, ignore_index=True)
        p = config.TABLES / f"{name}.csv"
        out.to_csv(p, index=False)
        log.info("-> %s", p)
        print(f"\n=== {name} ===")
        print(out.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
