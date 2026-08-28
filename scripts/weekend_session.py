"""Define the weekend by when traditional markets are shut, not by the calendar.

Everything so far has used the UTC calendar weekend: Saturday 00:00 to Sunday
24:00. That is a convention, and it is probably the wrong one. The reason crypto
is quiet at the weekend is that the information which moves it arrives on a
traditional-finance calendar, and that calendar does not start and stop at UTC
midnight. It stops when the last major venue closes on Friday and restarts when
the first one opens on Monday.

  US equities close   Friday 16:00 America/New_York   21:00 UTC winter, 20:00 summer
  CME futures close   Friday 16:00 America/Chicago    22:00 UTC winter, 21:00 summer
  FX closes           Friday 17:00 America/New_York   22:00 UTC winter, 21:00 summer
  FX reopens          Sunday 17:00 America/New_York   22:00 UTC winter, 21:00 summer
  Tokyo opens         Monday 09:00 Asia/Tokyo         00:00 UTC, no daylight saving

Daylight saving is handled properly rather than assumed away: the US close moves
by a full hour twice a year, and a rule pinned to the wrong hour for half the
sample would be testing something nobody could have traded.

Two things are varied. The **entry and exit instants** move from the UTC clock to
the session clock. And the **selection criterion** moves too: instead of the
share of a contract's life falling on a UTC Saturday or Sunday, the share falling
inside the closed window from Friday's US close to Monday's Tokyo open. If the
mechanism is really about traditional markets being shut, the second should pick
better contracts than the first.

Outputs:

  s1_session_grid.csv     every entry x exit combination, per book
  s2_session_sheet_{cur}.csv   the trade sheet for the best session rule
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import weekend_clock as C  # noqa: E402

from dbop import config, costs, greeks, weekend  # noqa: E402

log = logging.getLogger("weekend_session")

REHEDGE_MINUTES = 240
MATCH_WINDOW_MIN = 45

# (label, timezone, local hour, day offset from the Friday)
ENTRIES = {
    "utc_noon_fri":  (None, 12, 0),                      # the incumbent
    "us_equity_close": ("America/New_York", 16, 0),
    "cme_close":       ("America/Chicago", 16, 0),
    "fx_close":        ("America/New_York", 17, 0),
}
EXITS = {
    "utc_sun_00":  (None, 0, 2),                         # the incumbent
    "fx_open_sun": ("America/New_York", 17, 2),
    "tokyo_open_mon": ("Asia/Tokyo", 9, 3),
}


def instants(fridays_ms: np.ndarray, tz: str | None, hour: int,
             day_offset: int) -> np.ndarray:
    """UTC milliseconds for a local wall-clock time, daylight saving included."""
    days = pd.to_datetime(fridays_ms, unit="ms", utc=True).normalize()
    days = days + pd.Timedelta(days=day_offset)
    if tz is None:
        return (days + pd.Timedelta(hours=hour)).as_unit("ms").astype(
            "int64").to_numpy()
    # Build the local wall clock from the *calendar date*, then attach the zone.
    # Converting a UTC instant into a westward zone and normalising lands on the
    # previous day -- Friday 00:00 UTC is Thursday 19:00 in New York -- which
    # would have entered every US-session trade a day early.
    naive = days.tz_localize(None) + pd.Timedelta(hours=hour)
    local = naive.tz_localize(ZoneInfo(tz))
    return local.tz_convert("UTC").as_unit("ms").astype("int64").to_numpy()


def closed_windows(fridays_ms: np.ndarray) -> np.ndarray:
    """[start, end) of each traditional-market weekend, in UTC ms.

    Friday's US equity close to Monday's Tokyo open. This is the interval the
    session hypothesis says is actually quiet.
    """
    lo = instants(fridays_ms, "America/New_York", 16, 0)
    hi = instants(fridays_ms, "Asia/Tokyo", 9, 3)
    return np.column_stack([lo, hi])


def closed_fraction(start_ms: np.ndarray, expiry_ms: np.ndarray,
                    wins: np.ndarray) -> np.ndarray:
    """Share of [start, expiry) falling inside any closed window."""
    a = np.asarray(start_ms, dtype="int64")
    b = np.asarray(expiry_ms, dtype="int64")
    span = (b - a).astype("float64")
    out = np.zeros(len(a), dtype="float64")
    # Contracts here live at most a week, so only a handful of windows can
    # overlap any one of them; a search rather than a full cross product.
    lo, hi = wins[:, 0], wins[:, 1]
    first = np.searchsorted(hi, a, side="right")
    for i in range(len(a)):
        j = first[i]
        tot = 0
        while j < len(lo) and lo[j] < b[i]:
            tot += max(0, min(b[i], hi[j]) - max(a[i], lo[j]))
            j += 1
        out[i] = tot
    return np.where(span > 0, out / np.where(span > 0, span, 1.0), np.nan)


def run(cur: str, d: pd.DataFrame, px: pd.Series, half: float,
        by_inst: "C.InstIndex", t_ins: np.ndarray, t_outs: np.ndarray,
        wins: np.ndarray, select: str) -> pd.DataFrame:
    """The clock trade on arbitrary entry and exit instants."""
    win = MATCH_WINDOW_MIN * 60_000
    ts = d["timestamp"].to_numpy()
    rows = []
    for t_in, t_out in zip(t_ins, t_outs):
        if t_out <= t_in:
            continue
        cand = C._near(d, int(t_in), win, ts)
        cand = cand[cand["expiration_timestamp"] > t_out + C.HOUR_MS]
        if cand.empty:
            continue
        st = cand["timestamp"].to_numpy()
        ex_ts = cand["expiration_timestamp"].to_numpy()
        cand = cand.assign(
            wknd_frac=weekend.weekend_fraction(st, ex_ts),
            closed_frac=closed_fraction(st, ex_ts, wins))
        pick = cand.loc[cand[select].idxmax()]

        ex = by_inst.nearest(pick["instrument_name"], int(t_out), win)
        if ex is None:
            continue
        K, cp = float(pick["strike"]), float(pick["cp_sign"])
        expiry = int(pick["expiration_timestamp"])
        sig_in, sig_out = float(pick["sigma"]), float(ex["sigma"])
        F_in, F_out = float(pick["F"]), float(ex["F"])
        T_in = max((expiry - t_in) / C.MS_YEAR, 1e-9)
        T_out = max((expiry - t_out) / C.MS_YEAR, 1e-9)

        vega = float(greeks.greeks(F_in, K, T_in, sig_in, cp)["vega_usd"])
        if not np.isfinite(vega) or vega <= 0:
            continue
        prem_in = float(greeks.price_usd(F_in, K, T_in, sig_in, cp))
        prem_out = float(greeks.price_usd(F_out, K, T_out, sig_out, cp))
        hp, perp_fees = C.hedge_pnl(px, int(pick["timestamp"]), int(t_out), K,
                                    cp, sig_in, expiry, REHEDGE_MINUTES)
        fees = (perp_fees + float(costs.option_fee_usd(F_in, prem_in))
                + float(costs.option_fee_usd(F_out, prem_out))
                + 2.0 * abs(vega) * half)
        gross = prem_in - prem_out + hp
        rows.append({
            "entry_ts": pd.Timestamp(int(pick["timestamp"]), unit="ms", tz="UTC"),
            "exit_ts": pd.Timestamp(int(t_out), unit="ms", tz="UTC"),
            "instrument": pick["instrument_name"],
            "cp": "C" if cp > 0 else "P", "strike": K,
            "expiry": pd.Timestamp(expiry, unit="ms", tz="UTC"),
            "hold_hours": (t_out - int(pick["timestamp"])) / C.HOUR_MS,
            "wknd_frac": float(pick["wknd_frac"]),
            "closed_frac": float(pick["closed_frac"]),
            "iv_in": sig_in, "iv_out": sig_out, "iv_change": sig_out - sig_in,
            "index_in": F_in, "index_out": F_out,
            "index_move_pct": 100 * (F_out / F_in - 1),
            "premium_in": prem_in, "premium_out": prem_out,
            "option_pnl": prem_in - prem_out, "hedge_pnl": hp,
            "perp_fees": perp_fees, "vega_usd": vega,
            "gross_usd": gross, "net_usd": gross - fees,
            "gross_per_vega": gross / vega,
            "net_per_vega": (gross - fees) / vega,
        })
    return pd.DataFrame(rows)


def stats(b: pd.DataFrame, span_years: float, **tags) -> dict:
    if len(b) < 5:
        return {**tags, "n": len(b)}
    v = b["net_per_vega"].to_numpy()
    c = np.cumsum(v)
    dd = float((c - np.maximum.accumulate(c)).min())
    per_year = len(v) / span_years
    return {
        **tags, "n": len(v), "per_year": per_year,
        "mean": v.mean(), "t": v.mean() / (v.std() / np.sqrt(len(v))),
        # Annualised on the frequency the rule actually fills at.
        "sharpe": v.mean() / v.std() * np.sqrt(per_year),
        "hit_rate": float((v > 0).mean()),
        "worst": v.min(), "max_dd": dd,
        "mean_hold_hours": b["hold_hours"].mean(),
        "mean_iv_change": b["iv_change"].mean(),
        "mean_net_usd": b["net_usd"].mean(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=["BTC", "ETH"])
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    def all_instants(ts_min: int, ts_max: int) -> np.ndarray:
        fri = C.fridays(ts_min, ts_max)
        got = [instants(fri, *EXITS[k]) for k in EXITS]
        return np.sort(np.concatenate(got))

    grid, best = [], {}
    for cur in a.currencies:
        log.info("%s: loading tape", cur)
        d, px, half, by_inst = C.prepare(cur, all_instants,
                                         MATCH_WINDOW_MIN * 60_000)
        ts = d["timestamp"].to_numpy()
        fri = C.fridays(int(ts[0]), int(ts[-1]))
        wins = closed_windows(fri)
        span = (int(ts[-1]) - int(ts[0])) / (365.25 * C.DAY_MS)

        for ek, ecfg in ENTRIES.items():
            t_ins = instants(fri, *ecfg)
            for xk, xcfg in EXITS.items():
                t_outs = instants(fri, *xcfg)
                for sel in ("wknd_frac", "closed_frac"):
                    b = run(cur, d, px, half, by_inst, t_ins, t_outs, wins, sel)
                    if b.empty:
                        continue
                    grid.append(stats(b, span, asset=cur, entry=ek, exit=xk,
                                      select=sel))
                    best[(cur, ek, xk, sel)] = b
                log.info("  %s %s -> %s done", cur, ek, xk)
        del d, px, by_inst

    g = pd.DataFrame(grid)
    g.to_csv(config.TABLES / "s1_session_grid.csv", index=False)

    pd.set_option("display.width", 260)
    cols = ["asset", "entry", "exit", "select", "n", "per_year", "mean", "t",
            "sharpe", "hit_rate", "mean_hold_hours", "mean_iv_change", "worst"]
    print("\nSession-clock grid (240-minute rehedge):")
    print(g[cols].sort_values(["asset", "mean"], ascending=[True, False])
          .to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

    for cur in a.currencies:
        sub = g[(g.asset == cur) & (g.n >= 50)]
        if sub.empty:
            continue
        top = sub.loc[sub["mean"].idxmax()]
        b = best[(cur, top.entry, top["exit"], top.select)]
        p = config.TABLES / f"s2_session_sheet_{cur}.csv"
        b.to_csv(p, index=False, float_format="%.6g")
        log.info("%s best: %s -> %s on %s, mean %+.4f -> %s", cur, top.entry,
                 top["exit"], top.select, top["mean"], p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
