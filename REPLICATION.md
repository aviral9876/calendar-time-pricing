# Replication package

**The Price of Calendar Time in a Market That Never Closes**

This package reproduces every table, figure and in-text number in the paper from
raw source data. There is no licensed or proprietary data: everything is
collected from Deribit's free public API, which requires no account, no key and
no agreement. A replicator with an internet connection can rebuild the entire
paper from nothing.

---

## 1. What you need

| | |
|---|---|
| Python | 3.11 or later (developed on 3.12.10) |
| OS | Platform-independent; developed on Windows 11, CI on Linux |
| Disk | ~3 GB for the raw trade tape and bars |
| Memory | 16 GB recommended (the Bitcoin tape is the constraint) |
| Network | Required for the collection stage only |

Install:

```bash
pip install -e .
```

Dependencies are pinned by lower bound in `pyproject.toml`: numpy, pandas,
scipy, pyarrow, requests, statsmodels, linearmodels, matplotlib. The test suite
additionally needs pytest.

## 2. Running it

Three commands, in order. Stages are resumable and safe to interrupt.

```bash
python scripts/run_backfill.py --all      # collect (6-9 h per currency, network)
python scripts/run_weekend_all.py         # estimate everything (2-4 h, offline)
python scripts/build_paper.py --src paper/weekend_ms.md   # typeset
```

**Expected runtime.** The collection stage is dominated by Deribit's rate limit
(5 requests/second, self-imposed) and takes one overnight run per currency; it
is the only stage that touches the network, and it is resumable, so an
interrupted run continues where it stopped. The estimation stage reloads the
option tape several times and is dominated by that I/O rather than by
computation. Total wall-clock from nothing to typeset paper is roughly 24 hours,
almost all of it collection.

**Verifying without re-collecting.** If `data/` is already populated,
`run_weekend_all.py` alone reproduces every number. Each stage declares the
output file it must produce and the runner fails loudly if it does not appear,
so a partial run cannot silently produce a stale paper.

## 3. Where each exhibit comes from

Every table and figure in the paper maps to one script and one output file.
Output tables are CSV under `output/tables/`; figures are PNG and PDF under
`output/figures/`.

### Tables

| Paper | Content | Script | Output |
|---|---|---|---|
| Table 1 | Realized volatility by weekday; weekend variance ratios | `weekend_figures.py`, `weekend_academic.py` | `w6_realized_vol_by_dow.csv`, `w1_weekend_pricing.csv` |
| Table 2 | Implied and realized weekend variance ratios | `weekend_academic.py` | `w1_weekend_pricing.csv` |
| Table 3 | Saturday against Sunday, implied and realized | `weekend_profile.py` | `w4_dow_profile_{CUR}.csv` |
| Table 4 | Implied weekend ratio by year | `weekend_split.py` | `w17_split_trajectory.csv` |
| Table 5 | Weekend trend by moment of the realized distribution | `weekend_learning.py` | `w26_trend_by_moment.csv` |
| Table 6 | Residual gap under a jump-risk premium | `weekend_riskrace.py` | `w12_risk_horse_race.csv` |
| Table 7 | The spread, gross and net of measured costs | `weekend_maker.py` | `w60_spread_costed.csv`, `w61_fee_split.csv` |

### Figures

| Paper | Content | Script | Output |
|---|---|---|---|
| Figure 1 | Realized volatility by day of week | `weekend_figures.py` | `w_f1_realized_by_dow` |
| Figure 2 | Implied against realized weekend ratios | `weekend_figures.py` | `w_f2_implied_vs_realized` |
| Figure 3 | What the market tracks | `weekend_figures.py` | `w_f10_learning` |
| Figure 4 | The horse race | `weekend_figures.py` | `w_f6_horse_race` |

### In-text numbers

| Claim | Section | Script | Output |
|---|---|---|---|
| PAXG weekend ratio 0.347; staleness ladder | 3 | `weekend_reference.py` | `w8_reference_assets.csv`, `w9_reference_vol_by_dow.csv` |
| Pooled convention test; 2.4x dispersion | 5.1 | `weekend_pooled.py` | `w5_pooled_convention_test.csv` |
| Day-of-week profile correlations | 5.2 | `weekend_profile.py` | `w4_dow_profile_{CUR}.csv` |
| Saturday/Sunday contract availability (13 of 168 hours) | 5.2 | `weekend_params.py` | `w59_sat_sun_availability.csv` |
| Trimming and sampling ladders | 5.3 | `weekend_learning.py` | `w27_sampling_ladder.csv`, `w28_trimming_ladder.csv` |
| Tail-weight wedge (log mean − mean log) | 5.3 | `weekend_learning.py` | `w30_tail_wedge.csv` |
| Backward-looking calibration regression | 5.3 | `weekend_learning.py` | `w29_learning_race.csv` |
| Weekend tail mass, 15–28% beyond 5σ | 6 | `weekend_tails.py` | `w10_weekend_tails.csv` |
| Jump decomposition; 44-setting robustness | 6 | `weekend_riskrace.py` | `w11_jump_decomposition.csv`, `w13_horse_race_robustness.csv` |
| Wing vs at-the-money weekend discount | 6 | `weekend_wings.py` | `w22_wing_amplification.csv`, `w23_smile_shape.csv` |
| Gross P&L rank ordering across four books | 7 | `weekend_commercial.py` | `w2_weekend_trade_{CUR}.csv` |

`{CUR}` ranges over BTC, ETH, SOL, XRP.

## 4. Data

### Provenance

All raw data comes from Deribit's public history API at `history.deribit.com`,
documented at <https://docs.deribit.com>. No authentication is required. The
endpoints used are:

| Endpoint | What it provides |
|---|---|
| `public/get_last_trades_by_currency_and_time` | Complete trade history: timestamp, instrument, price, size, aggressor side, exchange implied volatility, index level, block/combo/liquidation flags |
| `public/get_instruments` (expired and active) | Strike, expiry, option type, contract size |
| `public/get_tradingview_chart_data` | Five-minute index and perpetual bars |
| `public/get_funding_rate_history` | Perpetual funding |

### Why the raw data is not deposited

The collected tape is approximately 2.8 GB across 41.5 million option trades,
which exceeds practical deposit limits. Because the source is public, free and
permanent, the collection code is a complete substitute: `run_backfill.py`
rebuilds it byte-for-byte given the same date range. Each collected day is
written with a manifest row recording trade count, request count and completion
status, so a replicator can verify coverage without re-downloading.

Should the journal prefer a deposited snapshot, the constructed intermediates
that every result depends on — daily realized variance by day type, and the
per-instrument-day implied volatility panel — total under 200 MB and can be
supplied instead.

### Integrity checks built into the pipeline

The collection and construction stages assert rather than assume:

- no duplicate `trade_id`; `trade_seq` strictly increasing within an instrument
- parsed instrument names cross-validated against exchange metadata (strike,
  expiry, type); any mismatch is a hard error, not a warning
- bar coverage checked at load and refused below a threshold — this guard was
  added after a corrupted bar series produced 89 gap-spanning returns that
  inflated scattered days' variance by up to 222x
- returns spanning a feed gap are dropped, not winsorized
- realized-variance stages refuse a day-type cell with insufficient coverage

Bar completeness in the delivered sample is 100%, 100%, 99.9% and 99.9% for BTC,
ETH, SOL and XRP.

## 5. Tests

```bash
python -m pytest tests/ -q
```

238 tests, roughly 40 seconds. These are not smoke tests. Each estimator is
checked against simulated data with a planted answer, so a test failure means a
number in the paper would be wrong:

| File | What it pins |
|---|---|
| `test_weekend.py` | Weekend-fraction arithmetic in closed form, against hand-computed cases |
| `test_greeks.py` | Black-76 pricer identities; implied-volatility round-trip to 1e-8 |
| `test_jumps.py` | Jump/continuous split recovers a planted jump share; returns a share under 5% on a pure diffusion |
| `test_learning.py` | Arithmetic and geometric estimators each recover their own estimand and neither recovers the other's; the sampling ladder points the right way for a real trend and the opposite way for one manufactured by shrinking noise |
| `test_params.py` | Contract-selection slicing; the entry-conditioning benchmark excludes the entry day (a look-ahead trap) |
| `test_spread_costing.py` | A spread pays both legs' costs; pins the size of a previously undetected error |
| `test_smile.py`, `test_wings.py` | Moneyness-bucket estimators and the joint smile contrast |

## 6. Corrections made during development

Four errors were found and fixed while this paper was written. All are recorded
in `docs/data_notes.md` with the superseded numbers. Three affected results in
the paper and one affected only the companion paper. They are listed here rather
than buried because the fixes are themselves part of what the code guards
against:

1. **Index alignment** in the trading engine — a millisecond/kilosecond rescaling
   that resolved every price lookup to 1970.
2. **Bar coverage** — a corrupted series whose gaps sent hedging paths through
   price jumps that never occurred; now guarded in `bars.load`.
3. **An underpowered realized benchmark** read as a null (§5.3). This is a
   methodological correction rather than a bug, and the paper states it as one.
4. **Spread costing** — a strategy P&L assembled by differencing two
   separately-costed short positions, which reversed the sign of one leg's costs.
   The general rule and the regression test are in `docs/data_notes.md` and
   `tests/test_spread_costing.py`.

## 7. Directory layout

```
dbop/            library: API client, instrument parsing, greeks, bars,
                 realized variance, weekend arithmetic, cost model
scripts/         one stage per file; run_weekend_all.py sequences them
tests/           pytest suite, 238 tests
data/            collected and constructed data (not in version control)
output/tables/   every CSV the paper cites
output/figures/  PNG and PDF
paper/           weekend_ms.md is the submitted manuscript
docs/            data_notes.md records every correction and its diagnosis
```

## 8. Contact and disclosure

### AsCollected project page

Management Science requires an AsCollected project page at submission, recording
which author did what and which data were used. Its URL must be disclosed in the
submission system and is repeated here so a replicator can find it from the code.

> **AsCollected project page:** `<<PASTE URL HERE BEFORE SUBMITTING>>`

Create it at <https://ascollected.org>. For this project the page should record:

| Field | What applies here |
|---|---|
| Data source | Deribit public history API, `history.deribit.com` — no authentication, no licence, no vendor agreement |
| Collection | Automated, by `scripts/run_backfill.py`; date range and per-day manifest in `data/manifest/` |
| Data type | Observational market data; no human subjects, no experiment, no survey |
| Third-party data | None |
| Author contributions | To be completed by the author(s) |

### Funding and competing interests

> **To be confirmed by the author before submission.** The statements below are
> placeholders reflecting no known funding or position, and must be verified
> rather than inherited from this file.

- Funding: none known.
- Positions in the assets studied (BTC, ETH, SOL, XRP, PAXG) or any financial
  interest in Deribit: none known.
- Proprietary or confidential data: none used. This one is verifiable from the
  code — every input comes from the public endpoints listed in §4.
