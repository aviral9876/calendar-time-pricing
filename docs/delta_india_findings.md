# Delta Exchange India: first results

Written 2026-08-26. Sample: BTC, Feb 2024 – Aug 2026, 670 expiries and 15,057
option contracts recovered by discovery-by-probe, 49,396 hourly candle files
(traded and mark), plus 5-minute perpetual candles from Dec 2023.

## Headline

**The weekend variance premium is not the trade here. A Friday-evening
variance premium is.**

The pre-registered S1 test — short delta-hedged straddles held across the
weekend — earns +0.023/vega net at hourly rehedging (t = 2.04) against a cost
of 0.045/vega, so it fails the pre-registered gate of edge > 2x cost. But the
exit grid shows why, and the answer is not a cost problem:

| Holding segment (entry Fri 16:00 UTC, rehedge 240m) | gross/vega | net/vega |
|---|---:|---:|
| Fri 16:00 → Sat 00:00 (Friday evening) | **+0.0793** | **+0.0544** |
| + Sat 00:00 → Sun 00:00 (all Saturday) | +0.0080 | +0.0005 |
| + Sun 00:00 → Mon 00:00 (all Sunday) | +0.0035 | −0.0085 |

Eight hours of Friday evening produce **the entire premium**. The forty-eight
hours of actual weekend add 1.4% of it gross and lose money net of the extra
hedging. On this venue the weekend is priced approximately correctly; Friday
evening is not.

## Validation before any of this was believed

* Our Black-76 inversion vs the venue's own `mark_iv`, 505 live contracts:
  **corr 0.9998**, median gap 0.00 vol points. (Deribit analogue: 0.9913 vs
  DVOL.)
* Realized weekend/weekday variance ratio from Delta's own perpetual candles:
  **BTC 0.664** (t = −9.6), ETH 0.742 — the French–Roll weekend effect is if
  anything larger here than the 0.737 measured on Deribit.
* Measured live quoted half-spread, ATM 0–2 days: **0.15 vol points**, about a
  third of Deribit's 0.42 (`output/tables/di01_quoted_spread.csv`).

## The two falsification tests that decide it

**1. Is the edge an artifact of pricing entries at traded prices and exits at
marks?** Partly, and the surviving two-thirds is what we report.

| Entry convention | n | gross/vega | net/vega | t |
|---|---:|---:|---:|---:|
| traded candle (optimistic) | 123 | +0.0793 | +0.0544 | +5.55 |
| **mark candle (conservative, reported)** | 130 | +0.0610 | **+0.0358** | **+4.52** |

Everything below uses the conservative convention: entry at mark, plus the
measured spread charged on both legs both ways.

**2. Is it specific to Friday, or just an evening effect?** Specific to Friday,
and the neighbouring days are not merely flat — the weekend days are strongly
negative. Same 16:00 → +8h short straddle, each weekday:

| Entry day | n | gross/vega | net/vega | t |
|---|---:|---:|---:|---:|
| Mon | 123 | +0.0349 | −0.0026 | −0.18 |
| Tue | 91 | +0.0298 | +0.0088 | +0.47 |
| Wed | 104 | +0.0236 | +0.0029 | +0.46 |
| Thu | 107 | +0.0155 | −0.0057 | −0.87 |
| **Fri** | **123** | **+0.0793** | **+0.0544** | **+5.55** |
| Sat | 129 | −0.0114 | −0.0413 | −2.80 |
| Sun | 123 | −0.0451 | −0.0824 | −4.68 |

This is an economically coherent picture rather than a lucky cell. The market
charges roughly flat theta per calendar hour while activity is anything but
flat: Friday evening (the US afternoon into the close) is when
traditional-market flow stops but the option clock has not been discounted
enough, and the weekend is discounted *too much* — which is why shorting
volatility on Saturday and Sunday loses. Note this reverses the Deribit
finding, where weekend options looked cheap relative to the realized
slowdown. On Delta India the weekend is, if anything, over-discounted.

## The candidate strategy

Short the near-ATM straddle on the nearest expiry at **Friday 16:00 UTC**,
delta-hedge in the perpetual every **4 hours**, close at **Saturday 00:00 UTC**.

| Rehedge | n | gross/vega | net/vega | t | Sharpe (ann) | hit | cost/vega | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5m | 130 | +0.0504 | −0.0028 | −0.49 | −0.31 | 0.53 | 0.0532 | −0.265 |
| 60m | 130 | +0.0535 | +0.0238 | +3.33 | +2.11 | 0.70 | 0.0297 | −0.295 |
| **240m** | 130 | +0.0610 | **+0.0358** | **+4.52** | **+2.86** | 0.73 | 0.0252 | −0.319 |
| 480m | 130 | +0.0660 | +0.0421 | +4.42 | +2.80 | 0.78 | 0.0239 | −0.661 |

The sign flips negative at 5-minute rehedging, exactly as on Deribit: this is a
hedging-cost tradeoff, and any live implementation lives or dies on rehedge
discipline.

**Stability.** Out-of-sample is stronger than in-sample, and every year is
positive:

| Split | n | net/vega | t | hit |
|---|---:|---:|---:|---:|
| IS (first half) | 65 | +0.0325 | +2.54 | 0.68 |
| OOS (second half) | 65 | +0.0392 | +4.13 | 0.78 |
| 2024 | 47 | +0.0206 | +1.30 | 0.60 |
| 2025 | 50 | +0.0410 | +3.26 | 0.82 |
| 2026 | 33 | +0.0497 | +5.06 | 0.79 |

**Cost stress.** Survives 4x the measured spread: net +0.0268, t = 3.38.

**Risk.** Worst single Friday −0.319/vega; 5th percentile −0.128; worst
drawdown of the cumulative series 0.556/vega — roughly fifteen average winners.
Short straddles have unbounded tails and the 8-hour window is no protection
against a headline; the engine carries a stop-multiple parameter and position
sizing must be set against a COVID-scale gap, not against this 2.5-year sample.

## Gate scorecard

| Pre-registered gate | Result |
|---|---|
| Original S1 (weekend hold) edge > 2x cost | **FAIL** (0.023 vs 0.091) |
| Revised spec (Friday evening) edge > 2x cost | marginal: 0.0358 vs 0.0504 |
| Sign stable across rehedge ladder ≥ 60m | **PASS** (+0.024, +0.036, +0.042) |
| Positive out of sample | **PASS** (OOS +0.039, t 4.13, stronger than IS) |
| Every year positive | **PASS** |
| Survives 2x spread stress | **PASS** (+0.033, t 4.14) |

The honest summary: the hypothesis we came to test failed, and a different,
better-identified effect turned up in its place. The Friday-evening premium
passes every stability test but sits just under the 2x-cost bar on the
conservative pricing convention (and just over it on the optimistic one), which
puts it in "worth paper-trading" territory, not "worth capital" territory.

## Caveats that bound all of the above

1. **No historical quotes.** Costs use *today's* measured spread applied to a
   2.5-year backtest. If spreads were materially wider in 2024, the early years
   are overstated. Forward ticker collection (Phase 6) is what fixes this, and
   it is the single highest-value next step.
2. **Candle granularity.** Hourly option bars mean entry and exit prices are up
   to an hour stale; the perp hedge is 5-minute. Both push against precision,
   not obviously in our favour.
3. **Selection.** The 16:00/sat_00 cell was inside the pre-registered 48-cell
   grid, but it is the best cell in it. The weekday placebo and the year-by-year
   stability are what make it more than a winning lottery ticket; a Bonferroni
   threshold over 48 cells needs t ≈ 3.2, which it clears.
4. **Liquidity not modelled.** The backtest assumes one straddle fills at the
   quoted spread. It says nothing about capacity, and near-ATM daily-expiry
   books here are thinner than Deribit's.
5. **Not tested live.** No paper trading has been run.

## Next

1. Start the ticker/trade pollers (Phase 6) — real quote history is the binding
   constraint on every cost number above.
2. Replicate on ETH (Phases 2–4 rerun; no new code needed).
3. Investigate the mechanism directly: hour-by-hour realized vs implied variance
   through Friday evening, which would either confirm the flat-theta story or
   replace it.
4. Paper-trade the Friday-evening spec against live quotes for 4+ weeks before
   any capital, per the plan's Phase 5 gate.
