"""Separating weekend content from maturity by varying when the trade is entered.

Section 6.4 found that the weekend share of a contract's remaining life predicted
the clock trade's P&L, and then found that the finding was empty: with entry
pinned to Friday noon, weekend share is a deterministic decreasing function of
maturity -- the correlation was exactly -1.00 -- and only two maturities were
ever on offer. The regression could not tell "more weekend" from "less time".

Breaking that requires the identification the paper already uses for pricing.
Deribit lists daily expiries, so at any single instant the contracts on offer
have weekend shares that are *not* monotone in maturity: from a Wednesday, the
contract expiring Thursday carries no weekend, the one expiring Monday carries a
large share, and the one expiring the following Friday carries a smaller share
again on a longer life. Entering on every day of the week rather than only
Friday adds a second source of variation, because the same maturity then carries
different weekend content depending on the day it is bought.

Two specifications, and they answer different halves of the question.

  A. **Within-instant.** Every contract traded at the same entry instant, with a
     fixed effect for that instant. Market conditions, volatility level and
     everything else common to the moment are absorbed, so the weekend share and
     the maturity are identified purely from the cross-section of contracts
     available simultaneously. This is the specification that separates the two,
     and it is the paper's identification applied to P&L rather than to quotes.

  B. **Across-instant.** The weekend content of the *holding window* rather than
     of the contract's life, which a within-instant fit cannot see because it is
     constant across contracts bought at the same moment. Identified from the
     entry day of week, controlling for the contract's own weekend share and
     maturity.

Outputs:

  w46_content_trades_{cur}.csv   every trade, with both weekend measures
  w47_content_regressions.csv    both specifications, both books
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

import weekend_clock as C  # noqa: E402

from dbop import config, costs, greeks, weekend  # noqa: E402

log = logging.getLogger("weekend_content")

ENTRY_HOUR = 12
HOLD_HOURS = 36
HOLD_LADDER = (12, 24, 36, 48, 72)
MIN_T_DAYS = 0.6
MAX_T_DAYS = 14.0
MATCH_WINDOW_MIN = 120
REHEDGE_MINUTES = 60
DELTA_BAND = (0.35, 0.65)


def all_days(ts_min: int, ts_max: int) -> np.ndarray:
    lo = pd.Timestamp(ts_min, unit="ms", tz="UTC").normalize()
    hi = pd.Timestamp(ts_max, unit="ms", tz="UTC").normalize()
    days = pd.date_range(lo, hi, freq="D", tz="UTC").as_unit("ms")
    return days.astype("int64").to_numpy()


def _content_instants(ts_min: int, ts_max: int) -> np.ndarray:
    """Every instant this script's exit lookup will be asked about."""
    days = all_days(ts_min, ts_max)
    return np.sort(np.concatenate(
        [days + (ENTRY_HOUR + int(h)) * C.HOUR_MS for h in HOLD_LADDER]))


def build(cur: str, d: pd.DataFrame, px: pd.Series, half_spread_vol: float,
          by_inst: "C.InstIndex", hold_hours: int = HOLD_HOURS) -> pd.DataFrame:
    """One short per (entry instant, expiry), across every day of the week."""
    win = MATCH_WINDOW_MIN * 60_000
    hold_ms = hold_hours * C.HOUR_MS
    ts = d["timestamp"].to_numpy()
    rows = []

    for day in all_days(int(ts[0]), int(ts[-1])):
        t_in = day + ENTRY_HOUR * C.HOUR_MS
        t_out = t_in + hold_ms
        cand = C._near(d, t_in, win, ts)
        if cand.empty:
            continue
        T_days = (cand["expiration_timestamp"].to_numpy() - t_in) / C.DAY_MS
        cand = cand[(T_days >= MIN_T_DAYS) & (T_days <= MAX_T_DAYS)
                    & (cand["expiration_timestamp"].to_numpy()
                       > t_out + C.HOUR_MS)]
        if cand.empty:
            continue

        # One contract per expiry, the closest to at-the-money, so that the
        # delta of the position is held roughly fixed across maturities and
        # cannot stand in for either regressor.
        cand = cand.assign(_atm=(cand["delta"].abs() - 0.5).abs())
        picks = cand.sort_values("_atm").groupby("expiration_timestamp",
                                                 sort=False).head(1)

        for _, pick in picks.iterrows():
            ex = by_inst.nearest(pick["instrument_name"], t_out, win)
            if ex is None:
                continue

            K = float(pick["strike"])
            cp = float(pick["cp_sign"])
            expiry = int(pick["expiration_timestamp"])
            sig_in, sig_out = float(pick["sigma"]), float(ex["sigma"])
            F_in, F_out = float(pick["F"]), float(ex["F"])
            T_in = max((expiry - t_in) / C.MS_YEAR, 1e-9)
            T_out = max((expiry - t_out) / C.MS_YEAR, 1e-9)

            prem_in = float(greeks.price_usd(F_in, K, T_in, sig_in, cp))
            prem_out = float(greeks.price_usd(F_out, K, T_out, sig_out, cp))
            g = greeks.greeks(F_in, K, T_in, sig_in, cp)
            vega = float(g["vega_usd"])
            if not np.isfinite(vega) or vega <= 0:
                continue

            hp, perp_fees = C.hedge_pnl(px, int(pick["timestamp"]), t_out, K,
                                        cp, sig_in, expiry, REHEDGE_MINUTES)
            fees = (perp_fees
                    + float(costs.option_fee_usd(F_in, prem_in))
                    + float(costs.option_fee_usd(F_out, prem_out))
                    + 2.0 * abs(vega) * half_spread_vol)
            gross = prem_in - prem_out + hp

            # A second-order attribution of the hedged short's P&L, in the
            # entry Greeks and the terminal moves. It is an approximation --
            # the true gamma cost is a path integral, not a function of the
            # endpoint -- so the residual is carried explicitly rather than
            # assumed away.
            dF = F_out - F_in
            dsig = sig_out - sig_in
            dt_days = (t_out - int(pick["timestamp"])) / C.DAY_MS
            att = {
                "term_gamma": -0.5 * float(g["gamma"]) * dF ** 2 / vega,
                "term_theta": -float(g["theta_usd"]) * dt_days / vega,
                # Per unit vega the first-order volatility term is just the
                # move in implied volatility, with the sign a short pays.
                "term_vega": -dsig,
                "term_volga": -0.5 * float(g["volga"]) * dsig ** 2 / vega,
                "term_vanna": -float(g["vanna"]) * dF * dsig / vega,
            }

            rows.append({
                "entry_ts": pd.Timestamp(t_in, unit="ms", tz="UTC"),
                "hold_hours": hold_hours,
                "entry_dow": pd.Timestamp(t_in, unit="ms", tz="UTC").dayofweek,
                "instrument": pick["instrument_name"],
                "expiry": pd.Timestamp(expiry, unit="ms", tz="UTC"),
                "T_days": (expiry - t_in) / C.DAY_MS,
                # What the option is priced on: the weekend share of the life
                # it has left to run.
                "wknd_life": float(weekend.weekend_fraction(
                    np.array([t_in]), np.array([expiry]))[0]),
                # What the position actually lives through.
                "wknd_hold": float(weekend.weekend_fraction(
                    np.array([t_in]), np.array([t_out]))[0]),
                "abs_delta": abs(float(pick["delta"])),
                "iv_in": sig_in, "iv_out": sig_out,
                "d_index": dF, "d_iv": dsig,
                "vega_usd": vega,
                # Scaled per unit vega so they are comparable across contracts,
                # which is the same normalization the P&L uses.
                "gamma_per_vega": float(g["gamma"]) * F_in ** 2 / vega,
                "theta_per_vega": float(g["theta_usd"]) / vega,
                "volga_per_vega": float(g["volga"]) / vega,
                "vanna_per_vega": float(g["vanna"]) * F_in / vega,
                "charm_per_day": float(g["charm_per_day"]),
                **att,
                "attributed": sum(att.values()),
                "gross_per_vega": gross / vega,
                "net_per_vega": (gross - fees) / vega,
                "residual": gross / vega - sum(att.values()),
            })

    out = pd.DataFrame(rows)
    log.info("  %s: %d trades on %d entry instants", cur, len(out),
             out["entry_ts"].nunique() if len(out) else 0)
    return out


def _within(v: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """Subtract the group mean, absorbing a fixed effect without dummies."""
    s = np.bincount(codes, weights=v, minlength=codes.max() + 1)
    n = np.bincount(codes, minlength=codes.max() + 1)
    return v - (s / n)[codes]


def fit(t: pd.DataFrame, cols: list[str], fe: str | None,
        cluster: str) -> pd.DataFrame:
    """OLS with an optional absorbed fixed effect and clustered standard errors."""
    y = t["net_per_vega"].to_numpy(dtype="float64")
    X = t[cols].to_numpy(dtype="float64")
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X, t = y[ok], X[ok], t[ok]

    if fe is None:
        X = np.column_stack([np.ones(len(y)), X])
        names = ["const"] + cols
        n_fe = 1
    else:
        codes = pd.factorize(t[fe])[0]
        y = _within(y, codes)
        X = np.column_stack([_within(X[:, j], codes) for j in range(X.shape[1])])
        names = cols
        n_fe = int(codes.max()) + 1

    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ y)
    resid = y - X @ b
    bread = np.linalg.inv(XtX)
    cl = pd.factorize(t[cluster])[0]
    G = int(cl.max()) + 1
    agg = np.zeros((G, X.shape[1]))
    np.add.at(agg, cl, X * resid[:, None])
    # Small-sample correction for the clusters and for the absorbed effects.
    dof = (G / max(G - 1, 1)) * ((len(y) - 1) / max(len(y) - X.shape[1] - n_fe, 1))
    cov = bread @ (agg.T @ agg) @ bread * dof
    se = np.sqrt(np.diag(cov))
    return pd.DataFrame({"term": names, "beta": b, "se": se, "t": b / se,
                         "n": len(y), "n_clusters": G})


def regressions(trades: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cur, t in trades.items():
        if len(t) < 200:
            log.info("%s: only %d trades, skipping", cur, len(t))
            continue
        t = t.copy()
        naive = t["entry_ts"].dt.tz_localize(None)
        t["week"] = naive.dt.to_period("W").astype(str)
        t["month"] = naive.dt.to_period("M").astype(str)

        # A. Within-instant: weekend content against maturity, identified only
        # from contracts trading side by side.
        a = fit(t, ["wknd_life", "T_days"], fe="entry_ts", cluster="week")
        a["spec"] = "A. within entry instant"

        # A'. The same with the delta added, in case the ATM pick leaves a
        # residual moneyness tilt correlated with maturity.
        a2 = fit(t, ["wknd_life", "T_days", "abs_delta"], fe="entry_ts",
                 cluster="week")
        a2["spec"] = "A2. + moneyness"

        # B. Across instants: the weekend content of the holding window, which
        # a within-instant fit absorbs entirely.
        b = fit(t, ["wknd_hold", "wknd_life", "T_days"], fe="month",
                cluster="week")
        b["spec"] = "B. within month"

        # C. The mechanism. If holding through a weekend costs money, the
        # reason should be visible in the contract's own quote: as the weekend
        # is consumed the life that remains is more weekday, so the implied
        # volatility per unit of remaining time has to re-rate upward, and a
        # short pays that on the mark.
        div = t.drop(columns=["net_per_vega"]).assign(
            net_per_vega=t["iv_out"] - t["iv_in"])
        c = fit(div, ["wknd_hold", "wknd_life", "T_days"], fe="month",
                cluster="week")
        c["spec"] = "C. change in the contract IV"

        # D. The holding period varies too, so the weekend content of the
        # window is no longer pinned to the entry day and can be separated from
        # simply holding for longer.
        specs = [(a, None), (a2, None), (b, None), (c, None)]
        if t["hold_hours"].nunique() > 1:
            dd = fit(t, ["wknd_life", "wknd_hold", "T_days", "hold_hours"],
                     fe="month", cluster="week")
            dd["spec"] = "D. + holding period"
            specs.append((dd, None))

            # E. Where in the P&L the weekend effect lives. The same regressors
            # run on each attribution term: if section 6.5's mechanism is right
            # the weekend-held coefficient should sit almost entirely in the
            # volatility terms and not in gamma.
            for term in ("term_gamma", "term_theta", "term_vega",
                         "term_volga", "term_vanna", "residual"):
                e = fit(t.drop(columns=["net_per_vega"]).assign(
                            net_per_vega=t[term]),
                        ["wknd_life", "wknd_hold", "T_days", "hold_hours"],
                        fe="month", cluster="week")
                e["spec"] = f"E. {term}"
                specs.append((e, None))

            # F. Do the Greeks themselves add anything beyond the two weekend
            # measures? Priced per unit vega so the scale is comparable.
            f6 = fit(t, ["wknd_life", "wknd_hold", "hold_hours",
                         "gamma_per_vega", "volga_per_vega", "vanna_per_vega"],
                     fe="month", cluster="week")
            f6["spec"] = "F. + entry greeks"
            specs.append((f6, None))

        for f, _ in specs:
            f["asset"] = cur
            rows.append(f)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def by_hold(trades: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The trade at each holding period, split by whether it spans a weekend.

    Holding longer earns more theta in absolute terms, so the levels are not
    comparable across rows; the contrast within each row is.
    """
    rows = []
    for cur, t in trades.items():
        for hh, g in t.groupby("hold_hours"):
            for lab, m in (("no weekend", g["wknd_hold"] <= 0.02),
                           ("spans a weekend", g["wknd_hold"] >= 0.30)):
                v = g.loc[m, "net_per_vega"]
                if len(v) < 30:
                    continue
                rows.append({
                    "asset": cur, "hold_hours": int(hh), "window": lab,
                    "n": len(v), "net_per_vega": v.mean(),
                    "t": v.mean() / (v.std() / np.sqrt(len(v))),
                    "hit_rate": float((v > 0).mean()),
                    "mean_d_iv": g.loc[m, "d_iv"].mean(),
                    "mean_wknd_life": g.loc[m, "wknd_life"].mean(),
                })
    return pd.DataFrame(rows)


def best_cell(trades: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The combination the regression implies, now that both axes vary.

    Section 6.5 could only reach "high weekend content, no weekend held" from a
    Thursday, on about a hundred trades. With the holding period free it is
    reachable from several days, which is the point of running the ladder.
    """
    rows = []
    for cur, t in trades.items():
        hi = t["wknd_life"] >= t["wknd_life"].quantile(0.5)
        for lab, m in (
                ("high content, no weekend held", hi & (t["wknd_hold"] <= 0.02)),
                ("high content, weekend held", hi & (t["wknd_hold"] >= 0.30)),
                ("low content, no weekend held", ~hi & (t["wknd_hold"] <= 0.02)),
                ("low content, weekend held", ~hi & (t["wknd_hold"] >= 0.30))):
            v = t.loc[m, "net_per_vega"]
            if len(v) < 30:
                rows.append({"asset": cur, "cell": lab, "n": int(m.sum())})
                continue
            rows.append({
                "asset": cur, "cell": lab, "n": len(v),
                "net_per_vega": v.mean(),
                "t": v.mean() / (v.std() / np.sqrt(len(v))),
                "hit_rate": float((v > 0).mean()),
                "mean_hold_hours": t.loc[m, "hold_hours"].mean(),
                "mean_wknd_life": t.loc[m, "wknd_life"].mean(),
            })
    return pd.DataFrame(rows)


def by_dow(trades: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The same trade entered on each day of the week.

    With the hold fixed at 36 hours, the entry day is what moves the weekend
    content of the holding window, so this is the regression's second
    coefficient shown without a model.
    """
    rows = []
    for cur, t in trades.items():
        for dow, g in t.groupby("entry_dow"):
            v = g["net_per_vega"]
            rows.append({
                "asset": cur, "entry_day": DOW[int(dow)], "n": len(v),
                "net_per_vega": v.mean(),
                "t": (v.mean() / (v.std() / np.sqrt(len(v)))
                      if len(v) > 2 and v.std() > 0 else np.nan),
                "hit_rate": float((v > 0).mean()),
                "mean_wknd_life": g["wknd_life"].mean(),
                "mean_wknd_hold": g["wknd_hold"].mean(),
                "mean_iv_change": (g["iv_out"] - g["iv_in"]).mean(),
            })
    return pd.DataFrame(rows)


def collinearity(t: pd.DataFrame) -> dict:
    """How far the design actually broke the -1.00 correlation of section 6.4."""
    out = {"raw_corr": float(t["wknd_life"].corr(t["T_days"]))}
    codes = pd.factorize(t["entry_ts"])[0]
    a = _within(t["wknd_life"].to_numpy(dtype="float64"), codes)
    b = _within(t["T_days"].to_numpy(dtype="float64"), codes)
    out["within_instant_corr"] = float(np.corrcoef(a, b)[0, 1])
    out["n_entry_instants"] = int(codes.max()) + 1
    out["expiries_per_instant"] = float(
        t.groupby("entry_ts")["expiry"].nunique().mean())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--hold-hours", type=int, default=HOLD_HOURS)
    ap.add_argument("--hold-ladder", action="store_true",
                    help="run every holding period in HOLD_LADDER")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    trades = {}
    for cur in a.currencies:
        log.info("%s: loading tape", cur)
        # The exits this script asks about are not the clock's: entries land
        # on every day at noon and the ladder holds for up to three days.
        d, px, half, by_inst = C.prepare(
            cur, _content_instants, MATCH_WINDOW_MIN * 60_000)
        holds = HOLD_LADDER if a.hold_ladder else (a.hold_hours,)
        t = pd.concat([build(cur, d, px, half, by_inst, hh) for hh in holds],
                      ignore_index=True)
        if t.empty:
            continue
        trades[cur] = t
        p = config.TABLES / f"w46_content_trades_{cur}.csv"
        t.to_csv(p, index=False, float_format="%.6g")
        log.info("  -> %s", p)
        c = collinearity(t)
        log.info("  %s: corr(weekend share, maturity) raw %+.2f, "
                 "within instant %+.2f; %.1f expiries per instant",
                 cur, c["raw_corr"], c["within_instant_corr"],
                 c["expiries_per_instant"])
        del d, px, by_inst

    reg = regressions(trades)
    if reg.empty:
        log.error("no regressions produced")
        return 1
    p = config.TABLES / "w47_content_regressions.csv"
    reg.to_csv(p, index=False)
    log.info("-> %s", p)

    hold = by_hold(trades)
    if not hold.empty:
        p_hold = config.TABLES / "w49_content_by_hold.csv"
        hold.to_csv(p_hold, index=False)
        log.info("-> %s", p_hold)
        print()
        print(hold.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    cells = best_cell(trades)
    if not cells.empty:
        p_cell = config.TABLES / "w50_content_cells.csv"
        cells.to_csv(p_cell, index=False)
        log.info("-> %s", p_cell)
        print()
        print(cells.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    dow = by_dow(trades)
    p_dow = config.TABLES / "w48_content_by_entry_day.csv"
    dow.to_csv(p_dow, index=False)
    log.info("-> %s", p_dow)
    print()
    print(dow.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print()
    print(reg[["asset", "spec", "term", "beta", "se", "t", "n",
               "n_clusters"]].to_string(index=False,
                                        float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
