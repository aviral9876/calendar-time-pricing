# dbop — demand-based option pricing on Deribit

Research code for *"Demand-Based Option Pricing Without a Clearinghouse"*:
testing Gârleanu–Pedersen–Poteshman (2009) inventory pricing on crypto options,
where end-user demand has the opposite sign to US index options.

Everything is built from Deribit's free public API. No credentials, no vendor
data.

## Quick start

```bash
pip install -e .
```

Collect the data (hours; resumable, safe to interrupt and rerun):

```bash
python scripts/run_backfill.py --all
```

Build every constructed dataset (offline, under an hour):

```bash
python scripts/build_all.py
```

Estimate everything and write tables and figures:

```bash
python scripts/run_regressions.py
```

## What each stage does

| Stage | Module | Output |
|---|---|---|
| Trade tape | `backfill.py` | `data/trades/options/{CUR}/{CUR}-YYYY-MM-DD.parquet` |
| Instrument metadata | `instruments.py` | strike, expiry, type; quarantines exchange listing errors |
| Forward curve | `forwards.py` | interpolated from ~480 dated futures per currency |
| Funding, bars, DVOL | `funding.py`, `bars.py` | perp carry cost and the underlying return series |
| Open interest | `oi.py` | snapshots, and the reconciliation test |
| Greeks | `greeks.py` | Black-76 on the forward, inverse-option conventions |
| Inventory | `inventory.py` | signed flow, reconstructed positions, daily revaluation |
| Surfaces | `surfaces.py` | daily IV surface on a fixed (delta, maturity) grid |
| Vol forecast | `rv.py` | out-of-sample log-HAR |
| Expensiveness | `expensiveness.py` | IV − E[RV], BKM variance risk premium, delta-hedged returns |
| Econometrics | `econo/` | cross-section, time series, funding instrument |

Set `DBOP_DATA` to keep the multi-gigabyte tape off the code drive.

## Three things that are easy to get wrong

Recorded in full, with the evidence, in [`docs/data_notes.md`](docs/data_notes.md):

1. **Deribit prices options off the per-expiry forward, not the index.** Trade
   records carry only `index_price`, so using it as the forward biases
   recomputed implied vol by up to +12 vol points at long maturities in
   contango. The forward curve is built from dated futures.
2. **The chart endpoint truncates at 5,001 bars and says nothing.** A flat
   30-day chunk at 5-minute resolution silently loses twelve days out of every
   thirty.
3. **`contracts` is unusable historically** — NaN for most of the sample.
   `amount` is the authoritative quantity.

## Testing

```bash
python -m pytest tests/ -q
```

Unit tests cover the pricer (parity, numerical derivatives, inversion
round-trips), the forward curve, and the position-reconstruction identities.
Data-dependent checks live in `validate.py` and run at the end of
`build_all.py`: backfill completeness, day-file invariants, implied-vol
recomputation against the exchange's own field, the surface against DVOL,
volatility spikes on known event dates, and HAR out-of-sample performance.

## Documentation

- [`docs/related_work.md`](docs/related_work.md) — positioning, what is already
  published, and the threats to identification
- [`docs/data_notes.md`](docs/data_notes.md) — API topology, sample coverage,
  and every measurement decision with its evidence
- [`docs/preliminary_findings.md`](docs/preliminary_findings.md) — results so far
- [`paper/main.md`](paper/main.md) — section plan
