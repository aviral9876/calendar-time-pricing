"""A short entered at a fixed clock time and closed at another, not held to expiry.

Everything in section 6 enters when a trade happens to print and holds to
settlement. That is the right convention for measuring a pricing error, because
settlement is the one exit whose value is not a matter of opinion. It is not how
a desk would run the trade. This script tests the clock version: sell the most
weekend-heavy contract available at a fixed hour on Friday, delta-hedge it in the
perpetual, and buy it back at a fixed hour later -- by default 00:00 UTC on
Sunday, which is the first moment after Saturday has finished.

Two things change, and both cost money.

The exit is now a *trade*, so the position crosses the spread twice instead of
once, and it is marked at whatever implied volatility the market was quoting at
the exit hour rather than at a settlement value. A weekend that stayed quiet but
left the market quoting the next weekend higher can still lose. Where no trade
prints near the exit hour the position is dropped rather than marked at its own
entry volatility, which would guarantee a profit whenever the weekend was calm.

Outputs:

  w38_clock_blotter_{cur}.csv   one row per trade: instrument, both timestamps,
                                both prices and volatilities, the hedge, every
                                fee, and the net
  w39_clock_grid.csv            the same strategy over a grid of entry hours and
                                exit points, all currencies
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

from dbop import (bars, config, costs, funding, greeks, tape, util,
                  weekend)  # noqa: E402

log = logging.getLogger("weekend_clock")

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
MS_YEAR = config.YEAR * DAY_MS

# How far either side of the clock hour a print is accepted as "at" that hour.
# Wide enough that a thin book still fills, narrow enough that the trade is not
# quietly moved to a different session.
MATCH_WINDOW_MIN = 45
REHEDGE_MINUTES = 5
DELTA_BAND = (0.35, 0.65)
MAX_T_DAYS = 7.0

# Exits are named by where they sit relative to the Saturday being traded.
# "sun_00" is the first instant after Saturday ends, which is the exit that
# holds the whole of the quietest day of the week.
EXITS = {"sat_00": 0, "sat_12": 12, "sun_00": 24, "sun_12": 36, "mon_00": 48}


def fridays(ts_min: int, ts_max: int) -> np.ndarray:
    """Friday 00:00 UTC stamps spanned by the sample, in epoch ms."""
    lo = pd.Timestamp(ts_min, unit="ms", tz="UTC").normalize()
    hi = pd.Timestamp(ts_max, unit="ms", tz="UTC").normalize()
    # as_unit("ms") is load-bearing. pd.Timestamp(x, unit="ms") builds a
    # millisecond-resolution stamp, date_range inherits that resolution, and
    # astype("int64") then returns milliseconds rather than the nanoseconds the
    # usual //10**6 rescaling assumes -- which silently puts every Friday in
    # 1970. Pinning the unit makes the conversion mean one thing.
    days = pd.date_range(lo, hi, freq="D", tz="UTC").as_unit("ms")
    return days[days.dayofweek == 4].astype("int64").to_numpy()


class InstIndex:
    """Per-instrument print lookup, used to find the mark at the exit instant.

    This replaces a dictionary of one DataFrame per instrument, and it exists
    for two reasons.

    The first is correctness, and it is the important one. The dictionary used
    to be built from the *entry* frame, which had already been filtered to the
    0.35-0.65 delta band. That made the exit mark conditional on the option
    still being near the money at the exit instant -- a condition on the future.
    Options leave the band when the index moves, and a delta-hedged short loses
    when the index moves, so the requirement quietly deleted the losing
    weekends: the Fridays that survived it had a mean absolute weekend move of
    0.94% against 2.15% across all Fridays, and the Bitcoin result it produced
    was seven times the unconditioned one. The exit index is now built from an
    unbanded frame, and the band applies only to what may be entered.

    The second is memory. The unbanded frame is an order of magnitude larger,
    and slicing it into tens of thousands of small frames runs to ten gigabytes
    -- enough to get the process killed. Contiguous arrays with per-instrument
    offsets hold the same information in a few hundred megabytes.
    """

    __slots__ = ("_pos", "_ts", "_sigma", "_F", "_start", "_end")

    def __init__(self, d: pd.DataFrame, instants: np.ndarray | None = None,
                 window_ms: int | None = None):
        # Select rows and columns in one indexing operation. Doing either half
        # on its own materialises an intermediate the size of the whole unbanded
        # tape -- and the instrument names are Python strings, so that
        # intermediate is what drove the machine into swap and took the run from
        # minutes to hours.
        cols = ["instrument_name", "timestamp", "sigma", "F"]
        if instants is not None and window_ms is not None:
            keep = _window_mask(d["timestamp"].to_numpy(), instants, window_ms)
            log.info("  exit index: %d of %d prints in window (%.1f%%)",
                     int(keep.sum()), len(keep), 100.0 * keep.mean())
            d = d.loc[keep, cols]
        else:
            d = d[cols]
        codes, uniques = pd.factorize(d["instrument_name"], sort=False)
        ts = d["timestamp"].to_numpy(dtype="int64")
        order = np.lexsort((ts, codes))
        codes = codes[order]
        self._ts = ts[order]
        self._sigma = d["sigma"].to_numpy(dtype="float64")[order]
        self._F = d["F"].to_numpy(dtype="float64")[order]
        n = len(uniques)
        self._start = np.searchsorted(codes, np.arange(n), side="left")
        self._end = np.searchsorted(codes, np.arange(n), side="right")
        self._pos = {name: i for i, name in enumerate(uniques)}
        log.info("  exit index: %d prints over %d instruments", len(self._ts), n)

    def __len__(self) -> int:
        return len(self._ts)

    def nearest(self, name: str, stamp: int, window_ms: int) -> dict | None:
        """The closest print on ``name`` within ``window_ms`` of ``stamp``."""
        i = self._pos.get(name)
        if i is None:
            return None
        a, b = self._start[i], self._end[i]
        if a == b:
            return None
        seg = self._ts[a:b]
        j = int(np.searchsorted(seg, stamp))
        best, gap = -1, window_ms + 1
        for k in (j - 1, j):
            if 0 <= k < len(seg):
                g = abs(int(seg[k]) - stamp)
                if g < gap:
                    best, gap = k, g
        if best < 0 or gap > window_ms:
            return None
        return {"timestamp": int(seg[best]),
                "sigma": float(self._sigma[a + best]),
                "F": float(self._F[a + best])}


def _window_mask(ts: np.ndarray, instants: np.ndarray,
                 window_ms: int) -> np.ndarray:
    """Rows within ``window_ms`` of any instant. ``ts`` must be sorted."""
    keep = np.zeros(len(ts), dtype=bool)
    for t in instants:
        lo, hi = np.searchsorted(ts, [t - window_ms, t + window_ms + 1])
        keep[lo:hi] = True
    return keep


def exit_instants(ts_min: int, ts_max: int,
                  offsets_hours=None) -> np.ndarray:
    """Every instant the exit lookup will ever be asked about."""
    if offsets_hours is None:
        offsets_hours = sorted(EXITS.values())
    fri = fridays(ts_min, ts_max)
    return np.sort(np.concatenate(
        [fri + DAY_MS + int(h) * HOUR_MS for h in offsets_hours]))


def _near(d: pd.DataFrame, stamp: int, window_ms: int,
          ts: np.ndarray | None = None) -> pd.DataFrame:
    """Rows whose timestamp lies within ``window_ms`` of ``stamp``.

    ``ts`` is the frame's own timestamp column as a sorted array. Passing it
    turns a full boolean scan into two binary searches, which matters because
    this runs once per Friday per configuration over a tape of several million
    rows.
    """
    lo, hi = stamp - window_ms, stamp + window_ms
    if ts is None:
        return d[(d["timestamp"] >= lo) & (d["timestamp"] <= hi)]
    a, b = np.searchsorted(ts, [lo, hi + 1])
    return d.iloc[a:b]


def hedge_pnl(px: pd.Series, t0: int, t1: int, K: float, cp: float,
              sigma: float, expiry: int, rehedge_minutes: int) -> tuple:
    """Delta-hedge P&L and perpetual fees for a SHORT option over [t0, t1].

    The hedge is set with the Black-76 delta at the *entry* implied volatility
    throughout, which is what a desk running a fixed rule could do without a
    live surface, and is the same convention as weekend_commercial.
    """
    idx = px.index.to_numpy()
    vals = px.to_numpy()

    def price_at(ms):
        pos = np.searchsorted(idx, ms, side="right") - 1
        return vals[np.clip(pos, 0, len(vals) - 1)]

    step = rehedge_minutes * 60_000
    stamps = np.minimum(np.arange(t0, t1 + step, step, dtype="int64"), t1)

    S = price_at(stamps)
    T = np.clip((expiry - stamps) / MS_YEAR, 1e-9, None)
    # A short option carries delta -Delta, so the neutralizing hedge is LONG
    # Delta units of the perpetual. The whole path is one vectorized call: a
    # scalar loop here costs minutes per configuration on the mature books.
    want = greeks.greeks(S, K, T, sigma, cp)["delta"]
    trades = np.diff(want, prepend=0.0)
    cash = -float(np.sum(trades * S))
    fees = float(np.sum(costs.perp_fee_usd(np.abs(trades) * S)))

    S_end = float(price_at(np.int64(t1)))
    return cash + float(want[-1]) * S_end, fees


def _rv_ann(px: pd.Series, t0: int, t1: int) -> float:
    """Annualized realized volatility of the index between two stamps."""
    idx = px.index.to_numpy()
    a, b = np.searchsorted(idx, [t0, t1])
    v = px.to_numpy()[a:b]
    if len(v) < 12:
        return np.nan
    r = np.diff(np.log(v))
    per_year = config.YEAR * 24 * 60 / config.BAR_MINUTES
    return float(np.sqrt(np.mean(r ** 2) * per_year))


def entry_factors(px: pd.Series, fund: pd.Series | None, dvol: pd.Series | None,
                  fri: int, t_in: int, sig_in: float, wknd_frac: float,
                  expiry: int) -> dict:
    """State observable at the entry instant, and nothing after it.

    Every one of these is pre-specified with a sign, because with fewer than two
    hundred trades a search over candidate filters will always find something.
    The list is fixed before it is run and reported whole in section 6.4,
    winners and losers alike.
    """
    # Realized volatility of the week so far: Monday 00:00 UTC to the entry.
    wd_vol = _rv_ann(px, fri - 4 * DAY_MS, t_in)
    fri_move = np.nan
    idx = px.index.to_numpy()
    a, b = np.searchsorted(idx, [fri, t_in])
    if b > a:
        v = px.to_numpy()
        fri_move = 100.0 * (float(v[min(b, len(v) - 1)]) / float(v[a]) - 1.0)

    def _mean_over(sr, lo, hi):
        if sr is None or sr.empty:
            return np.nan
        w = sr.loc[(sr.index >= lo) & (sr.index <= hi)]
        return float(w.mean()) if len(w) else np.nan

    fund_wk = _mean_over(fund, t_in - 7 * DAY_MS, t_in)
    dv_now = _mean_over(dvol, t_in - 6 * HOUR_MS, t_in)
    dv_prev = _mean_over(dvol, t_in - 5 * DAY_MS - 6 * HOUR_MS,
                         t_in - 5 * DAY_MS)
    return {
        "f_iv": sig_in,
        # The cushion of section 5.6, computed the way a desk would see it:
        # what the weekend is quoted at against what the week just realized.
        "f_iv_premium": sig_in / wd_vol if wd_vol and wd_vol > 0 else np.nan,
        "f_wd_vol": wd_vol,
        "f_friday_move_abs": abs(fri_move),
        "f_funding_abs": abs(fund_wk) if fund_wk == fund_wk else np.nan,
        "f_wknd_frac": wknd_frac,
        "f_dvol_chg": (dv_now - dv_prev) if (dv_now == dv_now
                                             and dv_prev == dv_prev) else np.nan,
        "f_T_days": (expiry - t_in) / DAY_MS,
    }


def run_one(d: pd.DataFrame, px: pd.Series, entry_hour: int, exit_key: str,
            half_spread_vol: float, by_inst: "InstIndex",
            rehedge_minutes: int = REHEDGE_MINUTES,
            alive_key: str | None = None,
            match_window_min: int = MATCH_WINDOW_MIN,
            fund: pd.Series | None = None,
            dvol: pd.Series | None = None) -> pd.DataFrame:
    """One blotter for one (entry hour, exit) rule.

    ``alive_key`` fixes which contracts are eligible to the survival requirement
    of a *different* exit. Without it the comparison across exits is confounded:
    a later exit forces a longer-dated and therefore less weekend-heavy
    contract, so the exits differ in what they trade as well as in how long they
    hold it. Setting alive_key to the latest exit in the comparison makes every
    rule pick from the same menu.
    """
    win = match_window_min * 60_000
    exit_offset = EXITS[exit_key]
    rows = []
    n_no_entry = n_no_exit = 0

    ts = d["timestamp"].to_numpy()
    for fri in fridays(int(ts[0]), int(ts[-1])):
        t_in = fri + entry_hour * HOUR_MS
        # The Saturday being traded starts the day after this Friday.
        t_out = fri + DAY_MS + exit_offset * HOUR_MS
        if t_out <= t_in:
            continue
        t_alive = (fri + DAY_MS + EXITS[alive_key] * HOUR_MS
                   if alive_key else t_out)

        cand = _near(d, t_in, win, ts)
        # Only contracts still alive at the exit hour: an option that settles
        # inside the holding window is a different trade with a different payoff.
        cand = cand[cand["expiration_timestamp"] > max(t_out, t_alive) + HOUR_MS]
        if cand.empty:
            n_no_entry += 1
            continue

        # The most weekend-heavy contract on offer, which is the trade the
        # paper's pricing result says is rich.
        cand = cand.assign(
            wknd_frac=weekend.weekend_fraction(
                cand["timestamp"].to_numpy(),
                cand["expiration_timestamp"].to_numpy()))
        pick = cand.loc[cand["wknd_frac"].idxmax()]

        # Vega-weights would need a second Greek pass for a number that barely
        # moves; the closest print to the hour is the honest mark. The index is
        # unbanded, so a contract that has drifted out of the money by the exit
        # is still marked rather than dropped.
        ex = by_inst.nearest(pick["instrument_name"], t_out, win)
        if ex is None:
            n_no_exit += 1
            continue

        K = float(pick["strike"])
        cp = float(pick["cp_sign"])
        expiry = int(pick["expiration_timestamp"])
        sig_in, sig_out = float(pick["sigma"]), float(ex["sigma"])
        F_in, F_out = float(pick["F"]), float(ex["F"])
        T_in = max((expiry - t_in) / MS_YEAR, 1e-9)
        T_out = max((expiry - t_out) / MS_YEAR, 1e-9)

        prem_in = float(greeks.price_usd(F_in, K, T_in, sig_in, cp))
        prem_out = float(greeks.price_usd(F_out, K, T_out, sig_out, cp))
        vega = float(greeks.greeks(F_in, K, T_in, sig_in, cp)["vega_usd"])
        if not np.isfinite(vega) or vega <= 0:
            continue

        hp, perp_fees = hedge_pnl(px, int(pick["timestamp"]), t_out, K, cp,
                                  sig_in, expiry, rehedge_minutes)
        opt_fees = (float(costs.option_fee_usd(F_in, prem_in))
                    + float(costs.option_fee_usd(F_out, prem_out)))
        # Unlike the hold-to-settlement version, this exits by trading, so the
        # spread is crossed on the way out as well as on the way in.
        spread_cost = 2.0 * abs(vega) * half_spread_vol
        fees = perp_fees + opt_fees + spread_cost

        gross = prem_in - prem_out + hp
        fac = entry_factors(px, fund, dvol, fri, int(pick["timestamp"]),
                            sig_in, float(pick["wknd_frac"]), expiry)
        rows.append({
            **fac,
            "entry_ts": pd.Timestamp(int(pick["timestamp"]), unit="ms", tz="UTC"),
            "exit_ts": pd.Timestamp(t_out, unit="ms", tz="UTC"),
            "instrument": pick["instrument_name"],
            "strike": K, "cp": "C" if cp > 0 else "P",
            "expiry": pd.Timestamp(expiry, unit="ms", tz="UTC"),
            "hold_hours": (t_out - int(pick["timestamp"])) / HOUR_MS,
            "wknd_frac": float(pick["wknd_frac"]),
            "index_in": F_in, "index_out": F_out,
            "index_move_pct": 100 * (F_out / F_in - 1),
            "iv_in": sig_in, "iv_out": sig_out, "iv_change": sig_out - sig_in,
            "premium_in": prem_in, "premium_out": prem_out,
            "option_pnl": prem_in - prem_out,
            "hedge_pnl": hp, "perp_fees": perp_fees, "option_fees": opt_fees,
            "spread_cost": spread_cost,
            "vega_usd": vega,
            "gross_usd": gross, "net_usd": gross - fees,
            "gross_per_vega": gross / vega,
            "net_per_vega": (gross - fees) / vega,
        })

    log.info("    %d trades (%d Fridays with no entry, %d with no exit print)",
             len(rows), n_no_entry, n_no_exit)
    return pd.DataFrame(rows)


def summarize(bl: pd.DataFrame, **tags) -> dict:
    if bl.empty:
        return {**tags, "n": 0}
    s = bl["net_per_vega"]
    mu, sd = s.mean(), s.std()
    return {
        **tags, "n": len(s),
        "gross_per_vega": bl["gross_per_vega"].mean(),
        "net_per_vega": mu,
        "t": mu / (sd / np.sqrt(len(s))) if sd > 0 else np.nan,
        # 52 weekends a year, not 252 trading days: this trade is on once a week.
        "sharpe": mu / sd * np.sqrt(52) if sd > 0 else np.nan,
        "hit_rate": (s > 0).mean(),
        "median": s.median(),
        "worst": s.min(),
        "mean_hold_hours": bl["hold_hours"].mean(),
        "mean_iv_change": bl["iv_change"].mean(),
        "cost_per_vega": ((bl["perp_fees"] + bl["option_fees"]
                           + bl["spread_cost"]) / bl["vega_usd"]).mean(),
    }


def paired(blotters: dict[str, pd.DataFrame], cur: str) -> pd.DataFrame:
    """Compare exits on the Fridays where every exit actually traded.

    The unpaired grid is not a clean comparison: whether a print exists near the
    exit hour varies by exit, so each cell is a different sample of Fridays and
    a difference between cells can be a difference between samples. Restricting
    to the intersection costs observations and buys the comparison.
    """
    keys = list(blotters)
    common = None
    for k in keys:
        b = blotters[k]
        if b.empty:
            return pd.DataFrame()
        d = pd.to_datetime(b["entry_ts"]).dt.floor("D")
        common = set(d) if common is None else (common & set(d))
    if not common:
        return pd.DataFrame()

    rows = []
    for k in keys:
        b = blotters[k].copy()
        b["fri"] = pd.to_datetime(b["entry_ts"]).dt.floor("D")
        b = b[b["fri"].isin(common)].drop_duplicates("fri")
        s = b["net_per_vega"]
        mu, sd = s.mean(), s.std()
        rows.append({
            "asset": cur, "exit": k, "n_common": len(s),
            "gross_per_vega": b["gross_per_vega"].mean(),
            "net_per_vega": mu,
            "t": mu / (sd / np.sqrt(len(s))) if sd > 0 and len(s) > 1 else np.nan,
            "hit_rate": (s > 0).mean(),
            "mean_hold_hours": b["hold_hours"].mean(),
            "mean_iv_change": b["iv_change"].mean(),
        })
    return pd.DataFrame(rows)


def _hourly(frame, col: str) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    return pd.Series(frame[col].to_numpy(dtype="float64"),
                     index=frame["timestamp"].to_numpy(dtype="int64")).sort_index()


def conditioners(cur: str) -> tuple[pd.Series | None, pd.Series | None]:
    """Perpetual funding and the exchange's own volatility index, hourly.

    Both are optional: SOL has neither and DVOL only begins in 2021, so a
    missing series has to narrow one factor rather than drop the whole trade.
    """
    try:
        fund = _hourly(funding.load(cur), "interest_8h")
    except (FileNotFoundError, OSError):
        log.info("%s: no funding history", cur)
        fund = None
    try:
        dvol = _hourly(bars.load_dvol(cur), "close")
    except (FileNotFoundError, OSError):
        log.info("%s: no DVOL history", cur)
        dvol = None
    return fund, dvol


def prepare(cur: str, instants_fn=None, window_ms: int | None = None
            ) -> tuple[pd.DataFrame, pd.Series, float, InstIndex]:
    """The entry menu, the hedge path, the crossing cost, and the exit index.

    The delta band belongs to the entry menu alone. Applying it to the exit
    index as well would make the trade conditional on where the option ended
    up, which is why the two frames are built separately here.
    """
    df = tape.load(cur, columns=weekend.LEAN_COLS)
    mark = tape.baseline_filter(df)
    del df
    mark = mark.loc[mark["iv_ok"] & mark["delta"].notna()
                    & (mark["premium_usd"] > 0)].sort_values("timestamp")

    T_days = mark["T"] * config.YEAR
    d = mark.loc[T_days.between(0.1, MAX_T_DAYS)
                 & mark["delta"].abs().between(*DELTA_BAND)].copy()
    d["date"] = util.to_utc_day(pd.to_datetime(d["timestamp"], unit="ms",
                                               utc=True))
    half = costs.summarize_spread(
        costs.effective_spread_iv(d)).get("median_half_spread_volpts", 0.0) / 100.0

    b = bars.load(cur)
    px = pd.Series(b["close"].to_numpy(dtype="float64"),
                   index=b["timestamp"].to_numpy(dtype="int64"))
    px = px[~px.index.duplicated()].sort_index()

    ts = mark["timestamp"].to_numpy()
    instants = (exit_instants if instants_fn is None else instants_fn)(
        int(ts[0]), int(ts[-1]))
    if window_ms is None:
        window_ms = MATCH_WINDOW_MIN * 60_000
    by_inst = InstIndex(mark, instants, window_ms)
    del mark
    return d, px, half, by_inst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currencies", nargs="*", default=list(config.CURRENCIES))
    ap.add_argument("--entry-hour", type=int, default=12)
    ap.add_argument("--exit", default="sun_00", choices=sorted(EXITS))
    ap.add_argument("--rehedge", type=int, default=REHEDGE_MINUTES,
                    help="rebalancing interval for the blotters, in minutes")
    ap.add_argument("--grid", action="store_true",
                    help="also sweep entry hours and exit points")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    config.TABLES.mkdir(parents=True, exist_ok=True)

    grid, pair, ladder, window = [], [], [], []
    for cur in a.currencies:
        log.info("%s: loading tape", cur)
        d, px, half, by_inst = prepare(cur)
        fund, dvol = conditioners(cur)
        log.info("%s: %d candidate trades, half-spread %.4f vol",
                 cur, len(d), half)

        log.info("  %s: entry %02d:00 Friday, exit %s", cur, a.entry_hour, a.exit)
        bl = run_one(d, px, a.entry_hour, a.exit, half, by_inst,
                     rehedge_minutes=a.rehedge, fund=fund, dvol=dvol)
        p = config.TABLES / f"w38_clock_blotter_{cur}.csv"
        bl.to_csv(p, index=False, float_format="%.6g")
        log.info("  -> %s", p)
        grid.append(summarize(bl, asset=cur, entry_hour=a.entry_hour,
                              exit=a.exit))

        # The headline rule at several rebalancing frequencies. Five-minute
        # rehedging costs 0.065 per unit vega over a 35-hour hold, which is more
        # than half the gross edge, so the frequency is not a detail.
        for step in (5, 30, 60, 240):
            b = run_one(d, px, a.entry_hour, a.exit, half, by_inst,
                        rehedge_minutes=step)
            ladder.append(summarize(b, asset=cur, entry_hour=a.entry_hour,
                                    exit=a.exit, rehedge_minutes=step))
            log.info("  %s rehedge %4dm: net %+.4f (t %+.2f, n %d)", cur, step,
                     ladder[-1].get("net_per_vega", float("nan")),
                     ladder[-1].get("t", float("nan")), ladder[-1]["n"])

        # Requiring a print within 45 minutes of Sunday midnight fills only
        # about a fifth of Fridays, and which fifth is not random: a contract
        # that trades at that hour may be one where something is happening.
        # Widening the window is the test of whether that selection drives the
        # result. The window is reported, not hidden, because a stale mark is a
        # different kind of error from a missing one.
        for w in (45, 120, 240, 480):
            b = run_one(d, px, a.entry_hour, a.exit, half, by_inst,
                        rehedge_minutes=a.rehedge, match_window_min=w,
                        fund=fund, dvol=dvol)
            if w == 240:
                b.to_csv(config.TABLES / f"w43_clock_blotter_wide_{cur}.csv",
                         index=False, float_format="%.6g")
            window.append(summarize(b, asset=cur, entry_hour=a.entry_hour,
                                    exit=a.exit, match_window_min=w,
                                    n_fridays=len(fridays(int(d["timestamp"].iloc[0]),
                                                          int(d["timestamp"].iloc[-1])))))
            log.info("  %s window %3dmin: n %d, net %+.4f (t %+.2f)", cur, w,
                     window[-1]["n"], window[-1].get("net_per_vega", float("nan")),
                     window[-1].get("t", float("nan")))

        exits = ("sat_00", "sat_12", "sun_00", "mon_00")
        blotters = {a.exit: bl}
        if a.grid:
            for eh in (0, 6, 12, 18):
                for ex in exits:
                    if (eh, ex) == (a.entry_hour, a.exit):
                        continue
                    log.info("  %s: entry %02d:00, exit %s", cur, eh, ex)
                    # --rehedge used to stop at the headline cell and leave the
                    # grid on the default, so the two could not be compared.
                    b = run_one(d, px, eh, ex, half, by_inst,
                                rehedge_minutes=a.rehedge)
                    grid.append(summarize(b, asset=cur, entry_hour=eh, exit=ex,
                                          rehedge_minutes=a.rehedge))
                    if eh == a.entry_hour:
                        blotters[ex] = b
            log.info("  %s: paired exits on a common contract menu", cur)
            fixed = {e: run_one(d, px, a.entry_hour, e, half, by_inst,
                                rehedge_minutes=a.rehedge,
                                alive_key=exits[-1]) for e in exits}
            pair.append(paired(fixed, cur))
        del d, px, by_inst, fund, dvol

    g = pd.DataFrame(grid)
    p = config.TABLES / "w39_clock_grid.csv"
    g.to_csv(p, index=False)
    log.info("-> %s", p)
    print(g.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    if window:
        wd = pd.DataFrame(window)
        p_wd = config.TABLES / "w42_clock_window.csv"
        wd.to_csv(p_wd, index=False)
        log.info("-> %s", p_wd)
        print()
        print(wd.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    if ladder:
        ld = pd.DataFrame(ladder)
        p_ld = config.TABLES / "w41_clock_rehedge.csv"
        ld.to_csv(p_ld, index=False)
        log.info("-> %s", p_ld)
        print()
        print(ld.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    pair = [x for x in pair if not x.empty]
    if pair:
        pr = pd.concat(pair, ignore_index=True)
        p = config.TABLES / "w40_clock_paired.csv"
        pr.to_csv(p, index=False)
        log.info("-> %s", p)
        print()
        print(pr.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
