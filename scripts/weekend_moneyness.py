"""The Friday-to-Saturday-midnight short, run across the moneyness ladder.

Everything in §6.3 to §6.6 was run on contracts within a 0.35-0.65 delta band --
the most liquid part of the surface, and the part where vega is largest. This
runs the same rule across the whole ladder: deep in the money, in the money, at
the money, out of the money and deep out of the money.

The rule is fixed and is the one §6.3 settled on: enter Friday 12:00 UTC, exit
00:00 UTC on Sunday, which is the first instant after Saturday has finished,
rehedging hourly.

Two design decisions do the work.

*Maturity is controlled in the regression, not in the sampling.* §6.5 showed
that weekend content and maturity move together unless something pins one of
them. The first version of this script pinned them by hand -- one expiry per
Friday, every bucket on that series -- and the wings starved: 266 Bitcoin and 63
Ether trades in total. So every contract tradeable at the entry instant is kept,
and maturity is held down by a Friday fixed effect plus each contract's own
maturity and weekend share. The moneyness comparison is then made within a
single instant, against contracts whose maturity is measured rather than
matched. ``--one-expiry`` restores the hand-matched design as a robustness
check.

*In the money and out of the money are not independent.* A delta-hedged short
call and a delta-hedged short put struck at the same price are, by put-call
parity, the same position: the difference between them is linear in the forward
and is exactly what the hedge removes. So the ITM and OTM buckets are two views
of the same strikes, and the analysis reports them separately because they are
asked for, while testing that they agree.

Outputs:

  w51_moneyness_sheet_{cur}.csv   the trade sheet: every trade, every field
  w52_moneyness_summary.csv       P&L, hit rate and attribution by bucket
  w53_moneyness_volume.csv        traded volume, notional, vega and effective
                                  spread by bucket
  w54_moneyness_regressions.csv   moneyness within a Friday, maturity controlled
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

from dbop import config, costs, greeks, tape, util, weekend  # noqa: E402

log = logging.getLogger("weekend_moneyness")

ENTRY_HOUR = 12
EXIT_KEY = "sun_00"
REHEDGE_MINUTES = 60
MATCH_WINDOW_MIN = 240
MIN_T_DAYS = 0.6
MAX_T_DAYS = 14.0

# Buckets on the absolute Black delta of the contract actually traded. The
# repo's usual `atmness` measure folds the two wings together on purpose; here
# they are kept apart because the question is about them.
BUCKETS = (
    ("deep ITM", 0.85, 1.00, 0.92),
    ("ITM", 0.65, 0.85, 0.75),
    ("ATM", 0.35, 0.65, 0.50),
    ("OTM", 0.15, 0.35, 0.25),
    ("deep OTM", 0.02, 0.15, 0.08),
)
BUCKET_ORDER = [b[0] for b in BUCKETS]


def label(delta_abs: np.ndarray) -> np.ndarray:
    out = np.full(len(delta_abs), "", dtype=object)
    for name, lo, hi, _ in BUCKETS:
        out[(delta_abs >= lo) & (delta_abs < hi)] = name
    return out


def prepare(cur: str):
    """Like weekend_clock.prepare, but without the near-the-money delta band."""
    df = tape.load(cur, columns=weekend.LEAN_COLS)
    d = tape.baseline_filter(df)
    del df
    T_days = d["T"] * config.YEAR
    d = d.loc[d["iv_ok"] & d["delta"].notna()
              & T_days.between(MIN_T_DAYS, MAX_T_DAYS)
              & d["delta"].abs().between(0.02, 1.0)
              & (d["premium_usd"] > 0)].copy()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms",
                                               utc=True))
    d["abs_delta"] = d["delta"].abs()
    d["bucket"] = label(d["abs_delta"].to_numpy())
    d = d[d["bucket"] != ""]
    d = d.sort_values("timestamp")
    return d


def exit_index(d: pd.DataFrame) -> dict:
    """Per-instrument prints, but only near the instants the rule ever looks at.

    The exit lookup wants a frame per instrument. Building that over the whole
    tape is what killed the first attempt at this run: dropping the delta band
    multiplies the instrument count, and a dictionary of twelve million rows cut
    into tens of thousands of small frames ran the machine to ten gigabytes and
    was killed before it wrote anything.

    The rule only ever reads prints within the match window of Friday noon or of
    the exit instant, so everything else is dropped before the split. That is a
    reduction of roughly fifty to one and changes no result.
    """
    ts = d["timestamp"].to_numpy()
    win = MATCH_WINDOW_MIN * 60_000
    keep = np.zeros(len(ts), dtype=bool)
    for fri in C.fridays(int(ts[0]), int(ts[-1])):
        for t in (fri + ENTRY_HOUR * C.HOUR_MS,
                  fri + C.DAY_MS + C.EXITS[EXIT_KEY] * C.HOUR_MS):
            lo, hi = np.searchsorted(ts, [t - win, t + win])
            keep[lo:hi] = True
    near = d.loc[keep, ["instrument_name", "timestamp", "sigma", "F"]]
    log.info("  exit index: %d of %d prints kept (%.1f%%)", len(near), len(d),
             100.0 * len(near) / max(len(d), 1))
    return {n: g for n, g in near.groupby("instrument_name", sort=False)}


def spread_by_bucket(d: pd.DataFrame) -> pd.DataFrame:
    """Effective half-spread per bucket, recovered from the aggressor sides.

    Deep wings quote much wider than the money, and since the trade crosses
    twice this is the number that decides whether a bucket is tradeable at all.
    """
    sp = costs.effective_spread_iv(d)
    if sp.empty:
        return pd.DataFrame()
    key = d[["instrument_name", "date", "bucket"]].drop_duplicates()
    on = [c for c in ("instrument_name", "date") if c in sp.columns]
    if not on:
        return pd.DataFrame()
    m = sp.merge(key, on=on, how="left")
    if "half_spread_vol" not in m.columns:
        return pd.DataFrame()
    # costs.effective_spread_iv returns the half-spread in the same decimal
    # units as sigma; the rest of this module works in volatility points, so
    # the conversion happens here once and the column name says so.
    g = m.assign(volpts=m["half_spread_vol"] * 100.0).groupby("bucket")["volpts"]
    return pd.DataFrame({"median_half_spread_volpts": g.median(),
                         "n_instrument_days": g.size()}).reset_index()


def volume(d: pd.DataFrame, cur: str) -> pd.DataFrame:
    """What actually trades in each bucket, over the whole tape and on Fridays."""
    d = d.copy()
    g = greeks.greeks(d["F"].to_numpy(), d["strike"].to_numpy(dtype="float64"),
                      d["T"].to_numpy(), d["sigma"].to_numpy(),
                      d["cp_sign"].to_numpy())
    d["vega_usd"] = g["vega_usd"]
    d["notional_usd"] = d["amount"] * d["F"]
    dow = pd.to_datetime(d["date"]).dt.dayofweek
    hour = pd.to_datetime(d["timestamp"], unit="ms", utc=True).dt.hour
    fri_window = (dow == 4) & hour.between(ENTRY_HOUR - 2, ENTRY_HOUR + 2)

    rows = []
    for name, mask in (("all", pd.Series(True, index=d.index)),
                       ("friday_noon", fri_window)):
        s = d[mask]
        tot_n, tot_v = len(s), s["vega_usd"].sum()
        for b in BUCKET_ORDER:
            g2 = s[s["bucket"] == b]
            rows.append({
                "asset": cur, "window": name, "bucket": b,
                "n_trades": len(g2),
                "share_of_trades": len(g2) / tot_n if tot_n else np.nan,
                "contracts": g2["amount"].sum(),
                "notional_usd": g2["notional_usd"].sum(),
                "vega_usd": g2["vega_usd"].sum(),
                "share_of_vega": (g2["vega_usd"].sum() / tot_v
                                  if tot_v else np.nan),
                "median_vega_per_trade": g2["vega_usd"].median(),
                "median_premium_usd": g2["premium_usd"].median(),
            })
    return pd.DataFrame(rows)


def sheet(cur: str, d: pd.DataFrame, px: pd.Series, by_inst: dict,
          half_by_bucket: dict, one_expiry: bool = False) -> pd.DataFrame:
    """Every contract tradeable at Friday noon and markable at the exit.

    An earlier version took one contract per bucket on a single common expiry.
    That is the tightest possible control for maturity, and it starved the
    wings: requiring five buckets to print on one series *and* to print again
    near Sunday midnight left 266 Bitcoin and 63 Ether trades, which is not
    enough to say anything about a wing.

    The design here keeps every contract and controls maturity in the
    regression instead -- a Friday fixed effect plus the contract's own maturity
    and weekend share, so the moneyness comparison is made within a single
    instant against contracts of measured maturity. ``one_expiry`` restores the
    old behaviour as a robustness check.
    """
    win = MATCH_WINDOW_MIN * 60_000
    ts = d["timestamp"].to_numpy()
    rows = []
    n_fri = n_used = 0

    for fri in C.fridays(int(ts[0]), int(ts[-1])):
        n_fri += 1
        t_in = fri + ENTRY_HOUR * C.HOUR_MS
        t_out = fri + C.DAY_MS + C.EXITS[EXIT_KEY] * C.HOUR_MS
        cand = C._near(d, t_in, win, ts)
        cand = cand[cand["expiration_timestamp"] > t_out + C.HOUR_MS]
        if cand.empty:
            continue

        # One expiry for the whole ladder: the most weekend-heavy series still
        # alive at the exit. Fixing it is what makes the buckets comparable.
        wf = weekend.weekend_fraction(cand["timestamp"].to_numpy(),
                                      cand["expiration_timestamp"].to_numpy())
        cand = cand.assign(wknd_frac=wf)
        expiry = int(cand.loc[cand["wknd_frac"].idxmax(),
                              "expiration_timestamp"])
        series = cand[cand["expiration_timestamp"] == expiry] if one_expiry else cand
        used = False

        # One trade per instrument: the print closest to the entry hour.
        series = series.assign(
            _gap=(series["timestamp"] - t_in).abs()
        ).sort_values("_gap").groupby("instrument_name", sort=False).head(1)

        for _, pick in series.iterrows():
            name = pick["bucket"]

            nxt = by_inst.get(pick["instrument_name"])
            if nxt is None:
                continue
            ex = C._near(nxt, t_out, win, nxt["timestamp"].to_numpy())
            if ex.empty:
                continue
            ex = ex.iloc[(ex["timestamp"] - t_out).abs().argsort().iloc[0]]

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
            half = half_by_bucket.get(name, half_by_bucket.get("ATM", 0.0))
            opt_fees = (float(costs.option_fee_usd(F_in, prem_in))
                        + float(costs.option_fee_usd(F_out, prem_out)))
            spread_cost = 2.0 * abs(vega) * half
            fees = perp_fees + opt_fees + spread_cost
            gross = prem_in - prem_out + hp

            dF, dsig = F_out - F_in, sig_out - sig_in
            dt_days = (t_out - int(pick["timestamp"])) / C.DAY_MS
            att = {
                "term_gamma": -0.5 * float(g["gamma"]) * dF ** 2 / vega,
                "term_theta": -float(g["theta_usd"]) * dt_days / vega,
                "term_vega": -dsig,
                "term_volga": -0.5 * float(g["volga"]) * dsig ** 2 / vega,
                "term_vanna": -float(g["vanna"]) * dF * dsig / vega,
            }

            used = True
            rows.append({
                "entry_ts": pd.Timestamp(int(pick["timestamp"]), unit="ms",
                                         tz="UTC"),
                "exit_ts": pd.Timestamp(t_out, unit="ms", tz="UTC"),
                "bucket": name,
                "instrument": pick["instrument_name"],
                "cp": "C" if cp > 0 else "P",
                "strike": K,
                "expiry": pd.Timestamp(expiry, unit="ms", tz="UTC"),
                "T_days": (expiry - t_in) / C.DAY_MS,
                "wknd_frac": float(pick["wknd_frac"]),
                "abs_delta": float(pick["abs_delta"]),
                "log_moneyness": float(np.log(K / F_in)),
                "index_in": F_in, "index_out": F_out,
                "index_move_pct": 100 * (F_out / F_in - 1),
                "iv_in": sig_in, "iv_out": sig_out, "iv_change": dsig,
                "premium_in": prem_in, "premium_out": prem_out,
                "option_pnl": prem_in - prem_out,
                "hedge_pnl": hp,
                "vega_usd": vega,
                "gamma_per_vega": float(g["gamma"]) * F_in ** 2 / vega,
                "volga_per_vega": float(g["volga"]) / vega,
                "vanna_per_vega": float(g["vanna"]) * F_in / vega,
                "perp_fees": perp_fees, "option_fees": opt_fees,
                "half_spread_volpts": half * 100,
                "spread_cost": spread_cost, "total_cost": fees,
                **att,
                "gross_usd": gross, "net_usd": gross - fees,
                "gross_per_vega": gross / vega,
                "net_per_vega": (gross - fees) / vega,
                "cost_per_vega": fees / vega,
            })
        n_used += int(used)

    log.info("  %s: %d trades over %d of %d Fridays", cur, len(rows), n_used,
             n_fri)
    return pd.DataFrame(rows)


def summarize(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cur, s in sheets.items():
        for b in BUCKET_ORDER:
            g = s[s["bucket"] == b]
            if len(g) < 10:
                rows.append({"asset": cur, "bucket": b, "n": len(g)})
                continue
            v = g["net_per_vega"]
            rows.append({
                "asset": cur, "bucket": b, "n": len(g),
                "gross_per_vega": g["gross_per_vega"].mean(),
                "net_per_vega": v.mean(),
                "median_net": v.median(),
                "t": v.mean() / (v.std() / np.sqrt(len(v))),
                "hit_rate": float((v > 0).mean()),
                "cost_per_vega": g["cost_per_vega"].mean(),
                "half_spread_volpts": g["half_spread_volpts"].mean(),
                "median_vega_usd": g["vega_usd"].median(),
                "net_usd_per_contract": g["net_usd"].mean(),
                "mean_iv_change": g["iv_change"].mean(),
                "call_share": float((g["cp"] == "C").mean()),
                **{k: g[k].mean() for k in ("term_gamma", "term_theta",
                                            "term_vega", "term_volga",
                                            "term_vanna")},
            })
    return pd.DataFrame(rows)


def regressions(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Is the bucket ordering moneyness, or is it maturity wearing a costume?

    Every specification here is estimated within a Friday, so a bucket is only
    ever compared against contracts that were tradeable at the same instant, on
    the same index, under the same weekend. ATM is the omitted category, so each
    coefficient reads as "this bucket, against the money, that afternoon".
    """
    import weekend_content as W

    rows = []
    for cur, s0 in sheets.items():
        if len(s0) < 200:
            log.info("%s: only %d trades, skipping regressions", cur, len(s0))
            continue
        t = s0.copy()
        t["fri"] = t["entry_ts"].dt.tz_localize(None).dt.date.astype(str)
        t["d_from_atm"] = (t["abs_delta"] - 0.5).abs()
        for b in BUCKET_ORDER:
            if b == "ATM":
                continue
            t[_slug(b)] = (t["bucket"] == b).astype(float)

        dummies = [_slug(b) for b in BUCKET_ORDER if b != "ATM"]
        specs = [
            ("A. buckets, pooled", dummies, None),
            ("B. + Friday fixed effect", dummies, "fri"),
            ("C. + maturity and weekend share",
             dummies + ["T_days", "wknd_frac"], "fri"),
            ("D. distance from the money",
             ["d_from_atm", "T_days", "wknd_frac"], "fri"),
            ("E. + volga and gamma",
             ["d_from_atm", "T_days", "wknd_frac", "volga_per_vega",
              "gamma_per_vega"], "fri"),
        ]
        for label, cols, fe in specs:
            r = W.fit(t, cols, fe, "fri")
            r.insert(0, "spec", label)
            r.insert(0, "asset", cur)
            rows.append(r)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _slug(bucket: str) -> str:
    return "b_" + bucket.replace(" ", "_").lower()


def parity_check(s: pd.DataFrame) -> pd.DataFrame:
    """A delta-hedged call and put on the same strike should behave alike.

    ITM and OTM are the same strikes seen from opposite sides, so if the two
    buckets disagree the disagreement is about which contract trades, not about
    the risk being held.
    """
    rows = []
    for b in BUCKET_ORDER:
        g = s[s["bucket"] == b]
        for cp in ("C", "P"):
            h = g[g["cp"] == cp]
            if len(h) < 10:
                continue
            v = h["net_per_vega"]
            rows.append({"bucket": b, "cp": cp, "n": len(v),
                         "net_per_vega": v.mean(),
                         "t": v.mean() / (v.std() / np.sqrt(len(v)))})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--one-expiry", action="store_true",
                    help="force every bucket onto one common expiry")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    sheets, vols, spreads = {}, [], []
    for cur in a.currencies:
        log.info("%s: loading tape", cur)
        d = prepare(cur)
        log.info("%s: %d candidate trades", cur, len(d))
        by_inst = exit_index(d)

        vol = volume(d, cur)
        vols.append(vol)

        sp = spread_by_bucket(d)
        # The effective-spread estimator needs both aggressor sides on the same
        # instrument-day. The wings rarely provide that, and where they do not
        # it returns noise -- including negative half-spreads, which are not a
        # spread. Those buckets fall back to the pooled figure rather than
        # being charged a cost that cannot be right, and the substitution is
        # recorded rather than hidden.
        half, pooled = {}, 0.0
        if not sp.empty:
            sp["asset"] = cur
            ok = ((sp["median_half_spread_volpts"] > 0)
                  & (sp["n_instrument_days"] >= 30))
            pooled = float(sp.loc[ok, "median_half_spread_volpts"].median()
                           if ok.any() else 0.0)
            sp["usable"] = ok
            sp["applied_volpts"] = np.where(
                ok, sp["median_half_spread_volpts"], pooled)
            spreads.append(sp)
            half = dict(zip(sp["bucket"], sp["applied_volpts"] / 100.0))
            for b in sp.loc[~ok, "bucket"]:
                log.info("  %s: %s half-spread unusable, using pooled %.2f "
                         "vol pts", cur, b, pooled)
        log.info("  half-spread applied by bucket (vol pts): %s",
                 {k: round(v * 100, 2) for k, v in half.items()})

        from dbop import bars
        b = bars.load(cur)
        px = pd.Series(b["close"].to_numpy(dtype="float64"),
                       index=b["timestamp"].to_numpy(dtype="int64"))
        px = px[~px.index.duplicated()].sort_index()

        s = sheet(cur, d, px, by_inst, half, one_expiry=a.one_expiry)
        if s.empty:
            continue
        sheets[cur] = s
        p = config.TABLES / f"w51_moneyness_sheet_{cur}.csv"
        s.to_csv(p, index=False, float_format="%.6g")
        log.info("  -> %s", p)
        print(f"\nput-call parity check, {cur}:")
        print(parity_check(s).to_string(index=False,
                                        float_format=lambda x: f"{x:,.4f}"))
        del d, by_inst, px

    summ = summarize(sheets)
    p = config.TABLES / "w52_moneyness_summary.csv"
    summ.to_csv(p, index=False)
    log.info("-> %s", p)

    vol = pd.concat(vols, ignore_index=True)
    if spreads:
        vol = vol.merge(pd.concat(spreads, ignore_index=True),
                        on=["asset", "bucket"], how="left")
    p = config.TABLES / "w53_moneyness_volume.csv"
    vol.to_csv(p, index=False)
    log.info("-> %s", p)

    reg = regressions(sheets)
    if not reg.empty:
        p = config.TABLES / "w54_moneyness_regressions.csv"
        reg.to_csv(p, index=False)
        log.info("-> %s", p)
        print()
        print(reg.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    print()
    print(summ.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print()
    print(vol[vol.window == "all"].to_string(
        index=False, float_format=lambda x: f"{x:,.4g}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
