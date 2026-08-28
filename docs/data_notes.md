# Data notes and measurement decisions

Everything here was verified against the live Deribit API in August 2026. Where
a choice was made, the evidence for it is recorded, because several of these
would silently corrupt results rather than crash the pipeline.

## API topology

`history.deribit.com` serves the complete trade archive since platform
inception. `www.deribit.com` serves only a recent window of trades. **The split
is not uniform across endpoints**: `get_funding_rate_history` and
`get_volatility_index_data` return HTTP 400 on the history host and must be
requested from `www`. This is not documented and cost an hour to find.

Public rate limit is roughly 20 req/s; the backfill deliberately runs at 5 to
survive an unattended multi-hour run.

## Final sample

Collected in 165 minutes at 5 requests per second:

| | Days | Trades | First | Last |
|---|---:|---:|---|---|
| BTC | 3,545 | 24,349,954 | 2016-11-29 | 2026-08-13 |
| ETH | 2,703 | 16,207,332 | 2019-03-21 | 2026-08-13 |
| **Total** | | **40,557,286** | | |

## Sample coverage (the binding constraints)

| Series | Starts | Source |
|---|---|---|
| BTC option trades | 2016-11-29 | first trade observed; instruments listed from 2016-07-15 but nothing traded until November |
| ETH option trades | 2019-03-21 | first trade observed |
| Perpetual 5-min bars | 2018-08-14 | perp launch |
| **Perp funding history** | **2019-04-30** | binds the 2SLS sample |
| DVOL index | 2021-03-26 | binds only a control variable |

The funding start date is the real constraint: the instrumental-variables
design cannot run before May 2019. DVOL is used only as a control and as an
external check, so it is treated as optional rather than required — insisting
on it would throw away 2019-2021.

## Trade record fields

Always present: `trade_id`, `trade_seq`, `timestamp`, `instrument_name`,
`price`, `amount`, `direction`, `iv`, `index_price`, `mark_price`,
`tick_direction`.

Present only when applicable, so they must be filled rather than assumed:
`block_trade_id` and `block_trade_leg_count` (~1.3% of trades), `block_rfq_id`
(~0.8%), `combo_id` / `combo_trade_id` (~0.7%), `liquidation` (~0.03%, values
`M`, `T`, `MT` for maker/taker/both).

**`contracts` is not usable historically.** It is entirely NaN in the early
sample and only appears in recent years. `amount`, denominated in units of the
underlying coin, is the authoritative quantity and is what inventory uses.

## Pagination

The endpoint returns at most 1000 trades plus a `has_more` flag. The next page
must start at the **last timestamp seen, not that timestamp plus one
millisecond**: many trades share a millisecond and advancing past it silently
drops them. This re-requests the boundary millisecond, so pages overlap by a
few trades and are deduplicated on `trade_id`. On a verification day, 6,341
rows were fetched for 6,331 unique trades — exactly the expected overlap.

## Instrument metadata anomalies

Four BTC instruments (`BTC-27OCT23-1775-C/P`, `BTC-27OCT23-1825-C/P`) have
metadata expiries that disagree with their names. They were created at 08:10
and expired at 08:20 on 2023-10-26 — a ten-minute exchange listing error, with
ETH-scale strikes on the BTC index — and never traded. They are quarantined to
`data/instruments/BTC_quarantined.parquet` rather than merged away, and any
trade referencing one would fail the join in `tape.attach_instruments`.

Not all options expire at 08:00 UTC: 672 BTC instruments expire at 15:00. Every
time-to-expiry downstream uses the metadata timestamp, never the 08:00
convention, so this is informational only.

## A Series that forgets its index is worse than one that raises

`util.to_utc_day` used to rebuild its result with a fresh `RangeIndex`. Every
call inside `dbop/` appends `.to_numpy()`, so the loss never mattered there. The
weekend scripts assigned the Series directly onto a **filtered** frame, where
labels no longer equal positions — pandas aligned on index, and every row whose
label fell outside the new RangeIndex silently became `NaT`. Those rows then
disappeared from the next `groupby` and `dropna`.

| Sample | Rows the filters selected | Rows the regression saw |
|---|---:|---:|
| BTC pricing | 5,339,133 | **1,206,483** |
| SOL pricing | 189,906 | **55,371** |

Roughly three quarters of every affected sample, dropped with no error, no
warning, and a plausible-looking `n`. Worse than random: the survivors are rows
retained early in the frame, so the subsample is systematically biased toward
the start of the sample period.

The correction changed the paper's headline. BTC's implied weekend variance
ratio went from 0.898 to **0.635** against a realized 0.584 — from "the market
prices a quarter of the weekend effect" to "the market prices about seven
eighths of it." The slope doubled and its t-statistic went from −3.7 to −10.8.

`to_utc_day` now preserves the input index, so both call styles are correct.
`tests/test_util.py` covers the exact failure mode. **The general lesson for
this codebase: a helper that returns a re-indexed Series is a loaded gun, and
the symptom is a fit sample much smaller than the filter output.** If those two
numbers disagree, find out why before reporting anything.

## Scale before comparing slopes across assets

The weekend slope estimates $v^{we}-v^{wd}$ in variance units, so it inherits
the asset's volatility level — SOL's implied weekday variance is 0.81 against
BTC's 0.44. Testing whether raw slopes are equal across assets therefore rejects
on volatility differences, not on weekend pricing. Both implied and realized
quantities are scaled by each asset's own mean variance before any cross-asset
comparison, giving the unit-free $(v^{we}-v^{wd})/\bar v$.

## SOL is a different animal: linear, USDC-grouped, contract size 10

Adding SOL as a third underlying is not a matter of appending to a list. Three
things differ from BTC and ETH, and each one silently corrupts results if
missed:

| | BTC / ETH | SOL |
|---|---|---|
| API currency | `BTC`, `ETH` | **`USDC`** (all USDC books share one feed) |
| Instrument name | `BTC-27DEC24-60000-C` | `SOL_USDC-15AUG26-66-C` |
| Settlement | inverse (coin) | **linear (USDC)** |
| Premium | quoted in coin → USD = price × forward | **already USD → premium = price** |
| Contract size | 1.0 | **10.0** |
| History | 2016-11 / 2019-03 | 2024-02-12 |

`config.API_CURRENCY`, `INSTRUMENT_PREFIX`, `LINEAR` and `CONTRACT_SIZE` carry
these. Two consequences worth stating:

**Pagination cannot be filtered server-side.** SOL trades arrive inside the
shared USDC feed alongside BTC_USDC and ETH_USDC, so `fetch_day_trades`
paginates the whole feed and filters each page by prefix. Filtering after
pagination would break the cursor; filtering the request is not offered.

**The linear premium is the dangerous one.** Applying the inverse convention to
SOL gives `price × forward` — a $0.30 option priced at $19.50, two orders of
magnitude out, with no error raised. `greeks.enrich` takes an explicit `linear`
flag rather than inferring it.

The name parser needed no change: `SOL_USDC-15AUG26-66-C` splits into four
hyphen-separated parts exactly like the inverse names, and the underlying
segment was already ignored. All 51,475 SOL instruments validate against their
parsed names with zero quarantined.

SOL's sample is short (from February 2024) but lands entirely inside the
daily-expiry era — 79% of instruments have two days or less of life, and expiry
weekdays are near-uniform including Saturday and Sunday — so it contributes
usable within-day variation from its first day.

## The tape does not fit in memory twice — load lean columns

`tape.load` returns roughly 40 columns; at 24m BTC rows that is several
gigabytes, and `baseline_filter` needs a second copy to apply its mask. Loading
the full frame and filtering afterwards therefore fails on a 16GB machine, and
fails *intermittently*, depending on what else is running — which is worse than
failing outright, because it looks like a code bug.

Three scripts hit this before it was diagnosed. The fix is to pass a column
subset at load time: `tape.load(cur, columns=weekend.LEAN_COLS)` loads only the
thirteen raw fields needed to price a trade and apply the baseline filter.
`scripts/run_weekend_all.py` additionally runs stages sequentially rather than
concurrently, since three parallel tape loads will exhaust memory however lean
each one is.

The same trap bit `tape.volume_summary`, which used to `.copy()` the whole frame
to produce a dozen summary rows.

## Chart endpoint truncates silently — size chunks by resolution

`get_tradingview_chart_data` returns at most **5,001 bars per request** and does
not report that it truncated: it just returns fewer rows than the window covers.
Measured directly:

| Window at 5-min | Bars expected | Bars returned |
|---|---:|---:|
| 15 days | 4,320 | 4,321 |
| 17 days | 4,896 | 4,897 |
| 20 days | 5,760 | **5,001** |
| 30 days | 8,640 | **5,001** |

The first version of the collector used a flat 30-day chunk, which quietly
dropped the last twelve days of every chunk and left the perpetual return series
about 40% incomplete (1,856 days of bars across a 2,922-day span, with 196 days
below the 200-bar threshold realized volatility needs). `bars.chunk_days_for`
now sizes each window from the resolution, and `bars.build` reports per-day
completeness rather than a bare row count, since a row count looks equally
plausible either way.

The forward-curve anchor uses a dedicated **daily** series
(`bars.build_daily`) rather than aggregating the 5-minute cache: one value per
day by construction cannot be silently thinned.

Effect of the fix on the BTC perpetual series:

| | Bars | Days covered | Days at full coverage |
|---|---:|---:|---:|
| 30-day chunks (truncating) | 488,428 | 1,856 | — |
| Resolution-aware chunks | **841,411** | **2,923** | **99.9%** |

Only two days now fall below 70% coverage. Everything downstream of the return
series — realized volatility, the HAR forecasts, expensiveness, and the
delta-hedged return benchmark — was affected by this, so any result produced
before this fix should be regenerated.

## Forward convention (tested, not assumed)

Deribit computes its reported implied vol against the **spot index**, not
against a futures-implied forward. Verified by recomputing IV from traded
premia both ways on 2019-06-15:

| Maturity | Basis (PCP fwd vs index) | Gap using index | Gap using PCP forward |
|---|---|---|---|
| 5.8d | +1.34% | **0.003** | 6.485 |
| 12.7d | +0.72% | **1.105** | 2.749 |
| 40.7d | +0.50% | **0.484** | 2.177 |
| 103.7d | +1.97% | **1.100** | 1.898 |

(gaps in vol points). **That first test was wrong** — it scaled the coin premium
to USD by the candidate forward as well as using it in Black-76. The USD premium
is always `price_coin * index_price`; only the forward entering Black-76 should
change. Corrected, and with the forward curve built from dated futures, the
picture reverses:

| Date | Basis | Signed error, index | Signed error, futures curve | \|median\|, index | \|median\|, futures curve |
|---|---:|---:|---:|---:|---:|
| 2019-06-15 | +0.71% | +0.00 | −1.16 | 0.60 | 2.21 |
| 2020-11-20 | +0.45% | +1.60 | +0.37 | 2.50 | 0.71 |
| 2021-02-10 | +1.00% | +3.69 | **+0.88** | 6.47 | **2.01** |
| 2021-04-15 | +1.07% | +3.23 | **+0.54** | 6.18 | **1.25** |
| 2022-11-09 | −0.64% | +0.00 | −0.02 | 1.01 | 1.28 |
| 2023-06-01 | +0.15% | +0.33 | −0.02 | 0.58 | 0.15 |
| 2024-01-11 | +0.28% | +0.86 | +0.31 | 2.11 | 0.71 |
| **mean** | | | | **2.78** | **1.19** |

Mean absolute error more than halves, and the systematic positive bias on
contango days largely disappears. Two days worsen slightly, both small-basis
cases where the index was already close. Errors are now largest at the money
(2.5 vol points on 2021-04-15) and smallest in the wings, the opposite of the
pattern under the index convention, and consistent with residual tick noise
rather than a convention error.

The validation suite checks the **signed** median separately for exactly this
reason: a convention error produces a level shift, tick noise does not.

## Inverse-option conventions

Premia are quoted in coin: USD premium = `price * index_price`. Greeks are
returned in USD per contract (contract size = 1.0 coin) so that exposures are
comparable across a sample in which the coin price moved by two orders of
magnitude.

The perpetual hedge ratio is the **premium-adjusted delta**, `delta_bs - price_coin`,
not the Black delta, because an inverse option is hedged with an inverse
perpetual whose own coin value moves with spot.

## Volatility forecast

HAR is estimated on **log** variance, not levels. Crypto realized variance is
so right-skewed that a levels fit is dominated by a handful of crash days and
loses out of sample to a rolling mean (OOS R² = −0.185 at h=30).

The forecast is mapped back to expected *volatility* directly as
`exp(mu/2 + s²/8)`. Correcting to the mean of the variance and then taking a
square root inflates the forecast by roughly the size of the premium being
measured — an 11 vol point bias in early testing.

Estimation uses a rolling 2-year window after a 2-year burn-in, selected on
out-of-sample performance:

| Window | R² h=7 | h=30 | h=60 | h=90 |
|---|---|---|---|---|
| Expanding | +0.156 | +0.077 | −0.090 | −0.249 |
| **756d** | **+0.197** | **+0.266** | **+0.185** | **+0.011** |
| 1095d | +0.169 | +0.124 | −0.007 | −0.167 |
| 1460d | +0.155 | +0.080 | −0.087 | −0.249 |

A residual positive bias in the level of expected vol remains (the sample's
volatility trended down, and a real-time forecaster would have over-predicted).
This is absorbed by the intercept in every time-series specification and by day
fixed effects in the panel, so it cannot bias the demand coefficient; it is
reported rather than tuned away. The two other dependent variables — the
variance risk premium and delta-hedged returns — do not depend on the forecast
at all.

## Sign convention

`direction = +1` means the taker bought, so end-user demand is `+amount` and
the passive counterparty (presumed intermediary) is short `amount`. The
identifying assumption is that the passive side of a maker-taker book is the
intermediary; GPP observed end-user positions directly from OCC open/close
codes. `inventory.validate_signing` probes the assumption by comparing the
mean-reversion half-life of reconstructed inventory against sign-shuffled
placebos.

Baseline demand excludes block trades (negotiated bilaterally off the book, so
neither side is necessarily absorbing flow) and combo legs (reported alongside
their parent, so they would double-count the same risk transfer). Liquidations
are kept — forced flow is still flow a dealer must warehouse — and dropped only
in robustness runs.

## Stale closes bias realized variance, and not equally across day types

A five-minute realized variance is only a variance if the price moves on a
five-minute grid. When it does not, the close repeats, the return records as
exactly zero, and realized variance is biased down. The bias is worse where
trading is thinner, which at these venues means the weekend, so it does *not*
cancel in a weekend/weekday ratio — it manufactures part of the weekend effect.

Share of five-minute returns that are exactly zero, by day type:

| | weekday | weekend |
|---|---:|---:|
| BTC | 2.6% | 4.7% |
| ETH | 2.3% | 3.4% |
| SOL | 6.0% | 12.5% |
| XRP | 17.5% | 28.8% |
| PAXG | 77.7% | 88.3% |

`jumps.signature` recomputes the ratio at 5, 15, 30, 60 and 120 minutes. The
four traded books are flat: none moves by more than 1.33 times the standard
error of its own five-minute estimate across a twenty-four-fold change of
interval, and none drifts monotonically. PAXG does both — 0.345 down to 0.188 —
because it is genuinely stale rather than genuinely quiet at short horizons.

Two consequences worth carrying:

- **The crypto weekend results are not a sampling artefact**, and the signature
  is the check to rerun if a thinner book is ever added. XRP is the one to watch:
  nearly three in ten of its weekend closes repeat.
- **PAXG's numbers are lower bounds on its weekend discount**, since the bias
  runs toward one. Anything computed on its five-minute grid that is *not* a
  variance — the tail frequencies and skew in `weekend_tails.py`, in particular —
  should not be read as a distributional statistic at all, because most of the
  mass sits at exactly zero.

The same staleness breaks the intraday seasonality factor outright: with a
majority of returns at zero, the within-slot median absolute return is zero, the
normalizer is zero, and every truncation threshold comes back NaN. Nothing then
exceeds its threshold, so the jump share is reported as a clean 0.000. That is
the worst kind of failure — a plausible number rather than an error — and
`jumps.tod_factor` now falls back to a flat factor and logs a warning instead.

## A ratio of means of a skewed series is a weak test, and a weak test is not a null

For six months this paper carried the sentence "the market is moving; the thing
it is pricing is not." It was wrong, and the way it was wrong is worth keeping.

The realized weekend effect is a ratio of mean weekend variance to mean weekday
variance. That is the right *estimand* — an option pays off on expected total
variance, so arithmetic means are what it needs — but daily realized variance is
extreme enough that each year's mean is set by a handful of days. Fitting a
trend to seven such ratios returned t = −1.25, and t = −1.25 was read as "no
trend" rather than as "no power". The realized weekend ratio had in fact been
falling for six years at almost exactly the rate the market was pricing.

Three diagnostics catch this, all cheap, and `scripts/weekend_learning.py` runs
all three:

- **Trim a little off the top and refit.** Cutting the top 1% of days from each
  side of the comparison, within each year so the trim carries no weekend
  effect, takes Bitcoin's trend from −0.062 (t = −1.2) to −0.132 (t = −4.9) and
  it barely moves thereafter. If a result lives in the top one per cent of
  observations, say so; if it dies there, that is worth knowing too.
- **Refit at the centre.** The same within-month contrast on `log` variance
  estimates the ratio of geometric means, and has three to four times the
  *t*-statistic on the same days. Where the two moments disagree, the disagreement
  is itself the finding: here it says the weekend's variance distribution is
  pulling apart from its own mean.
- **Walk the sampling interval.** Microstructure noise adds a roughly constant
  amount to every day's measured variance, so it pushes a measured ratio toward
  one and attenuates any trend in it — hardest on the finest grid. Bitcoin's
  arithmetic trend runs −0.062 (t = −1.2) at five minutes and −0.105 (t = −3.3)
  at sixty. Reaching for a finer grid to get more returns costs power on a
  *ratio*, which is the opposite of the intuition.

The general rule: **when a non-rejection is load-bearing, it needs its own
robustness section.** A rejection is checked reflexively here and everywhere; a
failure to reject gets written into the abstract unexamined. In this repo the
same mistake had already been made once in the other direction — `jumps.tod_factor`
returning a plausible 0.000 rather than an error — and it is the same failure
mode: a number that looks like an answer and is really an absence of one.

Note also which way the sampling ladder points, because it is the discriminator
between economics and measurement and it is easy to get backwards. A *real*
trend seen through noise gets **stronger** as the interval coarsens, since
coarsening removes the attenuation. A trend **manufactured** by noise that is
itself shrinking over time — improving weekend liquidity, say — gets **weaker**,
since coarse sampling never saw the noise. `tests/test_learning.py` simulates
both and pins the sign in each direction.

## 3. Look-ahead in the clock trading engine (found 2026-08-26)

**Symptom.** The moneyness ladder of §6.7, which uses its own engine, could not
reproduce §6.3's headline. On the comparable cell it returned −0.011 per unit
vega against §6.3's +0.094.

**Cause.** `weekend_clock.prepare` built the per-instrument index used to find
the *exit* mark from the same frame it drew entries from, and that frame had
already been filtered to `delta.abs().between(0.35, 0.65)`. A trade therefore
entered the blotter only if the option was still inside the delta band at the
exit instant. That is a condition on the future: options leave the band when the
index moves, and a delta-hedged short loses when the index moves.

**Magnitude.** Two selections, both measurable:

| | conditioned | unconditioned |
|---|---:|---:|
| Fridays filled (BTC) | 82 of ~430 | 227 of 496 |
| mean absolute weekend index move | 0.94% | 2.15% |
| net per vega, same 82 Fridays | +0.0935 | +0.0130 |
| same instrument picked | 19 of 82 | — |

Within a Friday the constraint forced a different contract 63 times out of 82,
always one that had stayed still. Mean IV change over the hold was −6.7
volatility points on the conditioned sample against −1.7 unconditioned.

**Fix.** `InstIndex` in `scripts/weekend_clock.py`. The exit index is built from
an unbanded frame; the delta band now constrains only what may be entered. The
index stores contiguous arrays with per-instrument offsets rather than a frame
per instrument, because the unbanded frame is an order of magnitude larger and
the dictionary form ran the machine into swap. Rows and columns are selected in
one indexing operation — the instrument names are Python strings, so any
intermediate the size of the full tape is fatal.

**Affected.** §6.3 (`weekend_clock.py`), §6.4 (`weekend_filters.py`, which runs
on its blotters), §6.5 and §6.6 (`weekend_content.py`, which calls the same
`prepare`). §6.1, §6.2 and everything before §6 use a different path and are
unaffected. §6.7's engine never had the defect.

**Revisions.** Not uniform in direction. §6.3's headline roughly halves and
changes sign at fine rehedging; a discarded Monday-exit finding returns. §6.4
improves markedly — the seller's cushion becomes the only pre-specified factor to
pass in both books. §6.5's weekend coefficients are essentially unchanged; its
"maturity is a precisely estimated zero" claim is withdrawn. §6.6's attribution
improves: the quiet weekend now appears as a positive gamma term rather than an
unexplained residual, and gamma per unit vega replaces volga as the exposure that
separates contracts.

**Test.** `test_a_contract_that_leaves_the_delta_band_is_still_marked_at_the_exit`
in `tests/test_clock.py` fails against the old banded index.

## Differencing two costed positions reverses one side's costs

The fourth and largest bug in this project was two lines long and lived in the
assembly of a strategy, not in any of the code the tests covered.

`weekend_commercial.hedged_pnl_to_expiry` prices a **short** contract: it
receives the premium, walks the delta hedge, settles against the index, and
subtracts fees. That is correct, and it was tested. The spread trade was then
built as

```python
sp_pnl = piv["weekend_heavy"] - piv["weekday_only"]   # both are NET of costs
```

Both pivot values are the net P&L of a short. Negating the second to make it a
long negates its costs too, turning a charge into a credit. An implementable
position that is short one contract and long another pays

    (gross_short - gross_long) - (cost_short + cost_long)

not `(gross_short - cost_short) - (gross_long - cost_long)`. The two differ by
**twice the long leg's cost** — 0.064 per unit vega at daily rehedging and 0.267
at five-minute, against a reported edge of 0.039 and 0.021. The trade had never
been profitable net of costs; the whole of the reported edge, and the subsequent
"inversion", were this term.

Three things about how it hid, all worth generalising:

- **Every leg was individually correct.** Unit tests on the pricer, the fee
  functions and each leg's P&L all passed and would still pass. Only the
  combination was wrong, and nothing tested the combination.
- **The sign of the error flattered the result.** Costs are always positive, so
  the bug could only ever inflate the P&L. A bug that made the trade look worse
  would have been chased down in an afternoon.
- **It survived three earlier bug hunts** — index alignment, bar coverage, and a
  look-ahead in the exit condition — because each of those was found by
  interrogating a number that looked wrong. This number looked right.

The rule: **whenever a strategy's P&L is assembled by differencing two
separately-costed positions, the differencing reverses the sign of one side's
costs.** Cost must be accumulated across legs and subtracted once, never carried
inside per-leg nets that are later combined with mixed signs. `spread_pnl` in
`weekend_commercial.py` is the only sanctioned way to combine legs here, and
`tests/test_spread_costing.py` pins both the identity and the size of the old
error.

The same separation is what made the maker calculation possible at all. Once
costs are decomposed per leg into exchange fees and spread crossing, the maker's
economics are one sign flip on one component — earning the half-spread instead of
paying it — rather than a re-derivation. A costing that hides its components
inside a net cannot answer that question.
