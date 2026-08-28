"""Can the Greeks pick a better contract than "most weekend-heavy"?

The clock trade fixes everything except one choice. Entry is Friday 12:00 UTC,
exit is Sunday 00:00 UTC, rehedging is four-hourly, and the contract is whichever
of the ones trading at that moment has the largest weekend share of its remaining
life. That last step is a guess. It was chosen because the paper's pricing result
says weekend-heavy contracts are rich, not because anything tested it against the
alternatives.

This runs *every* candidate contract on every Friday, not just the chosen one,
and asks what would have been the better pick. Because all candidates trade at
the same instant on the same index under the same weekend, a fixed effect for the
Friday removes everything except the choice itself.

The Greeks are entered per unit vega, because the trade is sized on vega and an
absolute Greek would just be measuring contract size. Signs are pre-specified
from the attribution work:

  gamma/vega   negative -- the short pays for realized movement, and gamma per
               vega is how much it pays per unit of the thing being sold
  theta/vega   positive -- the carry, and the mirror of gamma; the two are close
               to the same statement and are reported together for that reason
  volga/vega   negative -- convexity to a move in implied volatility, and
               implied volatility moves against a weekend short
  vanna/vega   no prior
  charm        no prior -- delta drift over the hold, a hedging-cost effect

Capacity is tracked alongside, because a selection rule that improves the P&L by
moving into contracts nobody trades has not improved anything. The vega actually
traded on each candidate near the entry hour is recorded per trade.

Outputs:

  g1_candidates_{cur}.csv   every candidate on every Friday, with entry Greeks,
                            realized P&L and the vega traded near entry
  g2_within_friday.csv      which Greeks predict the better pick, Friday fixed
                            effects, clustered on the Friday
  g3_rules.csv              incumbent rule against Greek-based alternatives,
                            in sample and out of sample
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
import weekend_content as W  # noqa: E402

from dbop import config, costs, greeks, weekend  # noqa: E402

log = logging.getLogger("weekend_greek_select")

ENTRY_HOUR = 12
EXIT_KEY = "sun_00"
REHEDGE_MINUTES = 240
MATCH_WINDOW_MIN = 45

# Per-vega Greeks, with the sign each is expected to take on the P&L of the
# short. Fixed before looking at the answer.
GREEKS = [
    ("gamma_per_vega", -1, "realized movement paid per unit of vega sold"),
    ("theta_per_vega", +1, "the carry, and gamma's mirror"),
    ("volga_per_vega", -1, "convexity to an IV move, and IV moves against"),
    ("vanna_per_vega", 0, "no prior"),
    ("charm_per_day", 0, "no prior; delta drift is a hedging cost"),
]


def candidates(cur: str, d: pd.DataFrame, px: pd.Series, half: float,
               by_inst: "C.InstIndex") -> pd.DataFrame:
    """Run the trade on every contract available at the entry hour."""
    win = MATCH_WINDOW_MIN * 60_000
    ts = d["timestamp"].to_numpy()
    rows = []
    for fri in C.fridays(int(ts[0]), int(ts[-1])):
        t_in = fri + ENTRY_HOUR * C.HOUR_MS
        t_out = fri + C.DAY_MS + C.EXITS[EXIT_KEY] * C.HOUR_MS
        cand = C._near(d, t_in, win, ts)
        cand = cand[cand["expiration_timestamp"] > t_out + C.HOUR_MS]
        if cand.empty:
            continue
        cand = cand.assign(wknd_frac=weekend.weekend_fraction(
            cand["timestamp"].to_numpy(),
            cand["expiration_timestamp"].to_numpy()))
        # One print per instrument, the closest to the hour, and the vega
        # actually traded on it inside the window -- that is the capacity of
        # this candidate, and it is the number a selection rule can destroy.
        gk = greeks.greeks(cand["F"].to_numpy(),
                           cand["strike"].to_numpy(dtype="float64"),
                           cand["T"].to_numpy(), cand["sigma"].to_numpy(),
                           cand["cp_sign"].to_numpy())
        cand = cand.assign(_vega=gk["vega_usd"])
        traded = cand.groupby("instrument_name")["_vega"].sum()
        cand = cand.assign(_gap=(cand["timestamp"] - t_in).abs())
        picks = cand.sort_values("_gap").groupby("instrument_name",
                                                 sort=False).head(1)

        for _, p in picks.iterrows():
            ex = by_inst.nearest(p["instrument_name"], t_out, win)
            if ex is None:
                continue
            K, cp = float(p["strike"]), float(p["cp_sign"])
            expiry = int(p["expiration_timestamp"])
            sig_in, sig_out = float(p["sigma"]), float(ex["sigma"])
            F_in, F_out = float(p["F"]), float(ex["F"])
            T_in = max((expiry - t_in) / C.MS_YEAR, 1e-9)
            T_out = max((expiry - t_out) / C.MS_YEAR, 1e-9)

            g = greeks.greeks(F_in, K, T_in, sig_in, cp)
            vega = float(g["vega_usd"])
            if not np.isfinite(vega) or vega <= 0:
                continue
            prem_in = float(greeks.price_usd(F_in, K, T_in, sig_in, cp))
            prem_out = float(greeks.price_usd(F_out, K, T_out, sig_out, cp))
            hp, perp_fees = C.hedge_pnl(px, int(p["timestamp"]), t_out, K, cp,
                                        sig_in, expiry, REHEDGE_MINUTES)
            fees = (perp_fees
                    + float(costs.option_fee_usd(F_in, prem_in))
                    + float(costs.option_fee_usd(F_out, prem_out))
                    + 2.0 * abs(vega) * half)
            gross = prem_in - prem_out + hp
            rows.append({
                "fri": pd.Timestamp(fri, unit="ms", tz="UTC").date(),
                "entry_ts": pd.Timestamp(int(p["timestamp"]), unit="ms",
                                         tz="UTC"),
                "instrument": p["instrument_name"],
                "cp": "C" if cp > 0 else "P",
                "strike": K,
                "expiry": pd.Timestamp(expiry, unit="ms", tz="UTC"),
                "T_days": (expiry - t_in) / C.DAY_MS,
                "wknd_frac": float(p["wknd_frac"]),
                "abs_delta": abs(float(p["delta"])),
                "iv_in": sig_in, "iv_out": sig_out,
                "iv_change": sig_out - sig_in,
                "index_move_pct": 100 * (F_out / F_in - 1),
                "vega_usd": vega,
                "gamma_per_vega": float(g["gamma"]) * F_in ** 2 / vega,
                "theta_per_vega": float(g["theta_usd"]) / vega,
                "volga_per_vega": float(g["volga"]) / vega,
                "vanna_per_vega": float(g["vanna"]) * F_in / vega,
                "charm_per_day": float(g["charm_per_day"]),
                "vega_traded_in_window": float(traded.get(
                    p["instrument_name"], np.nan)),
                "net_per_vega": (gross - fees) / vega,
                "gross_per_vega": gross / vega,
            })
    out = pd.DataFrame(rows)
    log.info("  %s: %d candidates over %d Fridays (%.1f per Friday)", cur,
             len(out), out["fri"].nunique() if len(out) else 0,
             len(out) / max(out["fri"].nunique(), 1) if len(out) else 0)
    return out


def within_friday(cand: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Which entry Greek predicts the better contract, holding the Friday fixed."""
    rows = []
    for cur, t in cand.items():
        t = t.copy()
        t["fri"] = t["fri"].astype(str)
        # Only Fridays offering a real choice identify anything.
        t = t[t.groupby("fri")["instrument"].transform("size") >= 2]
        if len(t) < 200:
            continue
        for col, sign, why in GREEKS:
            # Standardised within the Friday so the coefficient reads as the
            # gain from picking one standard deviation along that Greek.
            v = t[col].to_numpy(dtype="float64")
            ok = np.isfinite(v)
            s = t[ok].copy()
            z = W._within(v[ok], pd.factorize(s["fri"])[0])
            sd = z.std()
            s["_z"] = z / sd if sd > 0 else z
            r = W.fit(s.rename(columns={"net_per_vega": "net_per_vega"}),
                      ["_z"], fe="fri", cluster="fri")
            rows.append({"asset": cur, "greek": col, "expected": sign,
                         "beta_per_sd": float(r.beta.iloc[0]),
                         "t": float(r.t.iloc[0]), "n": int(r.n.iloc[0]),
                         "n_fridays": int(r.n_clusters.iloc[0]),
                         "rationale": why})
        # The incumbent criterion, on the same footing.
        v = t["wknd_frac"].to_numpy(dtype="float64")
        z = W._within(v, pd.factorize(t["fri"])[0])
        s = t.copy()
        s["_z"] = z / z.std() if z.std() > 0 else z
        r = W.fit(s, ["_z"], fe="fri", cluster="fri")
        rows.append({"asset": cur, "greek": "wknd_frac (incumbent)",
                     "expected": 1, "beta_per_sd": float(r.beta.iloc[0]),
                     "t": float(r.t.iloc[0]), "n": int(r.n.iloc[0]),
                     "n_fridays": int(r.n_clusters.iloc[0]),
                     "rationale": "weekend share of the life sold"})
    return pd.DataFrame(rows)


def _stats(v: np.ndarray, per_year: float) -> dict:
    if len(v) < 5:
        return {"n": len(v)}
    c = np.cumsum(v)
    dd = float((c - np.maximum.accumulate(c)).min())
    return {
        "n": len(v), "mean": v.mean(),
        "t": v.mean() / (v.std() / np.sqrt(len(v))),
        # Annualised on the frequency the rule actually trades at, not on 52.
        "sharpe": v.mean() / v.std() * np.sqrt(per_year),
        "hit_rate": float((v > 0).mean()),
        "worst": v.min(), "max_dd": dd,
        "dd_over_mean": dd / v.mean() if v.mean() else np.nan,
    }


def rules(cand: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One contract per Friday under each selection criterion."""
    rows = []
    for cur, t in cand.items():
        t = t.copy()
        t["fri"] = t["fri"].astype(str)
        span = (pd.to_datetime(t["fri"]).max()
                - pd.to_datetime(t["fri"]).min()).days / 365.25
        halves = pd.to_datetime(t["fri"]) <= pd.to_datetime(t["fri"]).median()

        CRIT = [("incumbent: max weekend share", "wknd_frac", False)]
        CRIT += [(f"min {c}", c, True) for c, s, _ in GREEKS if s == -1]
        CRIT += [(f"max {c}", c, False) for c, s, _ in GREEKS if s == +1]

        for label, col, ascending in CRIT:
            pick = (t.sort_values(col, ascending=ascending)
                     .groupby("fri", sort=True).head(1)
                     .sort_values("fri"))
            per_year = len(pick) / span
            for win, m in (("full", np.ones(len(pick), bool)),
                           ("first half",
                            (pd.to_datetime(pick["fri"])
                             <= pd.to_datetime(t["fri"]).median()).to_numpy()),
                           ("second half",
                            (pd.to_datetime(pick["fri"])
                             > pd.to_datetime(t["fri"]).median()).to_numpy())):
                v = pick.loc[m, "net_per_vega"].to_numpy()
                rows.append({"asset": cur, "rule": label, "window": win,
                             **_stats(v, per_year),
                             "median_vega_traded":
                                 pick.loc[m, "vega_traded_in_window"].median(),
                             "median_T_days": pick.loc[m, "T_days"].median()})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    cand = {}
    for cur in a.currencies:
        log.info("%s: loading tape", cur)
        d, px, half, by_inst = C.prepare(cur)
        log.info("%s: half-spread %.4f vol", cur, half)
        c = candidates(cur, d, px, half, by_inst)
        if c.empty:
            continue
        cand[cur] = c
        p = config.TABLES / f"g1_candidates_{cur}.csv"
        c.to_csv(p, index=False, float_format="%.6g")
        log.info("  -> %s", p)
        del d, px, by_inst

    w = within_friday(cand)
    w.to_csv(config.TABLES / "g2_within_friday.csv", index=False)
    r = rules(cand)
    r.to_csv(config.TABLES / "g3_rules.csv", index=False)

    pd.set_option("display.width", 250)
    print("\nWhich Greek picks the better contract (within a Friday, per sd):")
    print(w.drop(columns=["rationale"]).to_string(
        index=False, float_format=lambda v: f"{v:,.4f}"))
    print("\nSelection rules, one contract per Friday:")
    print(r.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
