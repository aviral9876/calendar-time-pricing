"""Validation gate for the Delta India pipeline.

Two checks, mirroring dbop/validate.py on the Deribit side:

1. IV recomputation. For every live near-dated option, invert our Black-76 on
   the venue's mark price (F = venue spot, r = 0, T to 12:00 UTC settlement)
   and compare with the venue's own mark_iv. Gate: correlation > 0.99. This is
   the same check that ties the Deribit surface to DVOL at 0.9913.

2. Quoted spread table. Delta publishes bid_iv/ask_iv; tabulate the half
   spread by |delta| x tenor bucket. This is the cost input the backtest
   charges, so it is written to output/tables/di01_quoted_spread.csv.

Optionally (--coverage) reports stored option-candle coverage once the
backfill has run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dbop import config, costs, greeks
from dbop.venues import delta_india as dx
from dbop.venues import delta_symbols as ds


def iv_recomputation(currency: str, max_t_days: float = 45.0) -> dict:
    tickers = dx.get_tickers("call_options,put_options", currency)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    rows = []
    for t in tickers:
        try:
            p = ds.parse_symbol(t["symbol"])
            mark = float(t["mark_price"])
            venue_iv = float(t["mark_vol"]) if t.get("mark_vol") else \
                float(t["quotes"]["mark_iv"])
            F = float(t["spot_price"])
        except (KeyError, TypeError, ValueError):
            continue
        T = (ds.expiry_ts_ms(p["expiry_date"]) / 1000 - now) / 86400.0 / 365.0
        if T <= 0.25 / 365 or T > max_t_days / 365.0:
            continue
        ours = greeks.implied_vol_scalar(mark, F, p["strike"], T,
                                         p["cp_sign"])
        if np.isfinite(ours):
            rows.append({"symbol": t["symbol"], "venue_iv": venue_iv,
                         "our_iv": ours, "T_days": T * 365.0,
                         "k": np.log(p["strike"] / F)})
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no invertible live options")
    corr = float(df[["venue_iv", "our_iv"]].corr().iloc[0, 1])
    mad = float((df["our_iv"] - df["venue_iv"]).abs().median())
    return {"n": len(df), "corr": corr, "median_abs_diff_volpts": mad * 100,
            "frame": df}


def spread_table(currency: str) -> pd.DataFrame:
    tickers = dx.get_tickers("call_options,put_options", currency)
    df = costs.quoted_spread_table(tickers)
    if df.empty:
        return df
    out = df.groupby(["delta_bucket", "tau_bucket"], observed=True).agg(
        n=("half_spread_vol", "size"),
        half_spread_volpts_med=("half_spread_vol",
                                lambda s: 100 * s.median()),
        half_spread_volpts_p90=("half_spread_vol",
                                lambda s: 100 * s.quantile(0.9)),
    ).reset_index()
    return out


def coverage(currency: str) -> pd.DataFrame:
    from dbop import delta_backfill as db
    disc = db.discovered_symbols(currency)
    h1 = db._h1_dir(currency)
    n_files = len(list(h1.glob("*.parquet")))
    man = db.load_discovery_manifest(currency)
    return pd.DataFrame([{
        "expiries_probed": len(man),
        "contracts_discovered": len(disc),
        "h1_files": n_files,
    }])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--currency", default="BTC", choices=sorted(dx.PERPETUAL))
    p.add_argument("--coverage", action="store_true")
    p.add_argument("--log", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log.upper())

    r = iv_recomputation(args.currency)
    ok = r["corr"] > 0.99
    print(f"IV recomputation ({args.currency}, {r['n']} live contracts): "
          f"corr = {r['corr']:.4f}, median |diff| = "
          f"{r['median_abs_diff_volpts']:.2f} vol pts "
          f"-> {'PASS' if ok else 'FAIL'} (gate: corr > 0.99)")

    sp = spread_table(args.currency)
    if not sp.empty:
        path = config.TABLES / "di01_quoted_spread.csv"
        sp.to_csv(path, index=False)
        print(f"\nquoted half-spread (vol pts), written to {path}:")
        print(sp.to_string(index=False))

    if args.coverage:
        print("\n" + coverage(args.currency).to_string(index=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
