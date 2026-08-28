# Making our elasticity comparable to GPP's

The paper's headline is a magnitude comparison: is the demand-pressure
elasticity larger in a market where intermediation is less constrained? That
number is only meaningful if both sides are expressed in the same units, and
they are not natively. This file records the derivation so it stays auditable
rather than buried in a script.

**This document contains a method, not yet the numbers.** The GPP coefficients
and summary statistics must be read off the published paper and entered below,
with page and table references. Do not let anyone — including a language model —
fill these in from memory; the whole point of the comparison is that the
benchmark is verifiable.

## The problem

The two studies scale demand differently.

- **GPP (2009)** measure end-user demand as net non-market-maker open interest
  in contracts, and regress option expensiveness (implied vol minus a measure of
  expected volatility) on it. Their coefficient is therefore *vol points per
  contract of net demand*, in a market whose size is fixed by the units of that
  era's CBOE open interest.
- **This paper** measures demand in vega-USD and scales it by trailing market
  size, so the coefficient is *vol points per unit of normalized vega demand*.

A raw coefficient comparison would mostly reflect that BTC options are quoted on
a coin-denominated contract worth tens of thousands of dollars while an SPX
contract is worth a few hundred thousand, and that the two markets differ in
size by orders of magnitude. That comparison would be meaningless.

## The common unit

Express both as **the change in expensiveness, in volatility points, associated
with a one-standard-deviation move in net end-user demand measured relative to
the size of the market**.

For each market:

```
elasticity = beta * sd(D) / scale
```

where `beta` is the estimated coefficient, `sd(D)` the standard deviation of the
demand variable in that regression's own units, and `scale` the market-size
normalizer used to put demand on a comparable footing (aggregate open interest
in the same risk units).

Because our specification already normalizes demand before estimation, our
elasticity is `beta_ours * sd(D_normalized)`, read directly off
`output/tables/t4_cross_section_BTC.csv` and the demand series in
`data/panels/BTC_buckets.parquet`.

For GPP the rescaling has to be done by hand from published statistics.

## What to extract from GPP (2009), RFS 22(10), 4259–4299

Fill in, with exact table and page references:

| Quantity | Symbol | Value | Source (table, page) |
|---|---|---|---|
| Demand-pressure coefficient, index options | `beta_gpp_index` | | |
| Demand-pressure coefficient, equity options | `beta_gpp_equity` | | |
| Standard deviation of net end-user demand | `sd_D_gpp` | | |
| Mean open interest (same units as demand) | `OI_gpp` | | |
| Units of the dependent variable | | vol points? decimals? | |
| Sample period and frequency | | | |

Two traps:

1. **Dependent-variable units.** If GPP's expensiveness is in decimal
   volatility (0.01 = one vol point) and ours is too, no adjustment is needed —
   but confirm rather than assume, and confirm the same for ours by checking
   `exp_bucket` against `atm_30` in the panel.
2. **Which coefficient.** GPP report several specifications. Use the one whose
   dependent variable is closest to ours (expensiveness in levels, not
   delta-hedged returns) and say explicitly in the paper which one was chosen.

## Reporting

`tables.t8_elasticity_comparison` takes the benchmark as an argument rather than
hard-coding it, precisely so the derivation lives here:

```bash
python scripts/run_regressions.py --gpp-beta <value from the table above>
```

The output reports our elasticity with a bootstrapped confidence interval, the
benchmark, and their ratio.

## How to state the result honestly

The comparison is across markets, eras, underlyings, and measurement schemes.
Even done carefully it is an order-of-magnitude statement, not a precise
estimate, and the paper should say so in the same sentence that reports it. The
subsample estimates carry more weight than the pooled ratio: if the elasticity
compresses monotonically as institutional capital enters the crypto market
(post-2021, post-ETF), that is evidence about the *mechanism* — intermediation
capacity — rather than about a single cross-market number, and it is internal to
one market, so it does not depend on the rescaling above at all.

Present the within-crypto time variation as the primary magnitude evidence and
the GPP ratio as the headline framing, not the other way round.
