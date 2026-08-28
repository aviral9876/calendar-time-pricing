# What the Weekend Clock Does to Option Prices

*A companion note to* The Price of Calendar Time in a Market That Never Closes.
*Nothing here is used in that paper; it translates its results into premium.
Reproducible from `scripts/weekend_price_impact.py` and
`scripts/weekend_price_observed.py`; tables land in `output/tables/p*.csv` and
`o*.csv`, the figure in `output/figures/p_f1_price_impact.*`.*

---

## The question

The paper is written in variance. It says that Deribit quotes weekend calendar
time at roughly half to two thirds of the weekday rate, and argues about whether
that ratio matches the one realized returns actually deliver. Variance is the
right object for the economics and the wrong one for anyone who pays for
options. The natural follow-up is the mechanical one: **volatility is lower over
a weekend, so by Black-Scholes the price must be lower — by how much?**

The direction is right and the size is not obvious, because three things sit
between a variance ratio and a premium, and they push in different directions.

1. **Dilution.** The ratio applies to weekend *hours*, not to contracts. What
   reaches a price is the ratio weighted by the share of that contract's
   remaining life falling on Saturday and Sunday. Across every short-dated trade
   in the sample that share averages 0.216, so the typical contract sees about a
   fifth of the raw effect. A quarterly option is 2/7 weekend whatever day it is
   quoted on, and the clock washes out of it entirely.

2. **The square root.** Price responds to volatility; the clock is stated in
   variance. Half the effect is gone before anything else happens.

3. **Convexity.** Price is close to linear in volatility at the money and is
   not linear at all away from it. The elasticity `sigma * vega / C` is 1.22 in
   the at-the-money bucket and 4.30 in the far wing, so the same proportional
   cut in volatility takes three and a half times as large a share of a wing
   premium. And the wings are where the paper's §7 finds the market applying a
   *deeper* clock to begin with, so the two amplifications compound.

The short answer: the weekend clock removes **7.0% of the time value** of the
average short-dated Bitcoin option, **4.9% at the money and 17.2% in the far
wing**; on a Friday daily expiring Monday it removes **13.0% at the money and
62% two standard deviations out**. Over the sample that is **$910m of premium
across the four books**, of which about **$117m** is more than realized weekend
variance justifies — a figure that has changed sign since 2022 and is not
statistically distinguishable from zero book by book.

---

## 1. The arithmetic

Write `w` for the fraction of a contract's remaining life falling on a weekend
and `R` for the weekend variance ratio the market quotes. Total variance to
expiry is

    V = v_wd · T · (1 − (1 − R)·w)

so the contract's implied volatility is the weekday rate scaled by the square
root of an **effective-time factor** `f = 1 − (1−R)w`. That factor is the whole
story: it is the ratio of effective time to calendar time, and it is what the
option is really being sold.

Everything below compares one contract against **itself with the clock switched
off**: same strike, same expiry, same instant, same forward, volatility raised
from the quoted level to that level divided by the square root of `f`. That
comparison is deliberate. It is exactly the
within-instant contrast the headline regression identifies, and because both
legs are built from the same contract-level weekday variance, the level of the
surface — and with it whatever variance risk premium the market is charging —
cancels out of every number reported here.

**Two conventions worth stating.** Percentages are quoted on *time value*, that
is, on the out-of-the-money leg at each strike. By put-call parity the
forward-intrinsic part of an in-the-money premium carries no volatility, so the
dollar effect of a change in the clock is identical whichever leg you price,
while the percentage is not: dividing a real dollar effect by a premium that is
nine tenths intrinsic reports a small number about a large one. Second, premia
are reconstructed from the exchange's own implied volatility through Black-76
rather than read off the traded price. Section 7 checks that reconstruction
against the premia that were actually paid and against volatilities inverted
from them, and nothing in the note turns on it.

### In volatility points

The blunt version, at each book's fitted weekday rate:

| book | weekday IV | Friday daily → Monday (w = ⅔) | all-weekend contract (w = 1) |
|---|---|---|---|
| BTC | 66.5 | 57.8 (−8.6 pts) | 53.0 (−13.5 pts) |
| ETH | 83.3 | 72.8 (−10.5 pts) | 66.9 (−16.4 pts) |
| SOL | 89.9 | 75.5 (−14.4 pts) | 67.2 (−22.7 pts) |
| XRP | 103.7 | 84.2 (−19.6 pts) | 72.4 (−31.3 pts) |

A market maker who ignored the weekend and quoted one flat surface would be
offering Friday's three-day Bitcoin contract nearly nine volatility points too
rich, and XRP's nearly twenty.

### In premium

`p1_price_impact_stylized.csv`, Bitcoin, three days to expiry, at the
full-sample quoted clock `R = 0.635`:

| weekend fraction | effective time | IV | ATM | 1 sd out | 2 sd out |
|---|---|---|---|---|---|
| 0 (Tue → Fri) | 3.00 d | 66.5 | — | — | — |
| 2/7 (long-dated) | 2.69 d | 62.9 | −5.4% | −15.2% | −30.5% |
| 1/2 | 2.45 d | 60.1 | −9.6% | −26.4% | −49.7% |
| 2/3 (Fri → Mon) | 2.27 d | 57.8 | −13.0% | −35.1% | −62.4% |
| 1 (Saturday daily) | 1.91 d | 53.0 | −20.3% | −52.1% | −81.7% |

Concretely: Bitcoin at $100,000, a three-day at-the-money call listed Friday at
08:00 and expiring Monday at 08:00 is worth **$2,090**. The identical contract
with no weekend in it is worth **$2,403**. The weekend takes $313, or 13%, off
the price — and takes 62% off the same contract struck two standard deviations
away.

That last row is worth pausing on, because it is where the naive version of the
question breaks down. "Vega times the change in volatility" would price that
2-sd Saturday contract at **−129%** of its own premium. The exact repricing is
−81.7%. Convexity is not a correction here; it is most of the answer, which is
why every number in this note is an exact repricing rather than a greek
multiplication.

---

## 2. On the tape

The stylized map assumes a contract. `p2`–`p3` reprice every trade that clears
the headline filter — 13.6m Bitcoin trades, 9.2m Ether, 0.42m Solana, 0.14m XRP,
all with 0.25 to 14 days to run — at that trade's own quoted volatility, its own
strike, its own maturity and its own weekend fraction. Averages are weighted by
the counterfactual premium, so a book is described by the money that changes
hands in it rather than by its cheapest contracts, and the weight does not
respond to the effect being measured.

**Pooled (`p6`):**

| book | mean w | IV cut | elasticity | premium cut | time value traded | premium removed |
|---|---|---|---|---|---|---|
| BTC | 0.216 | −4.10% | 1.77 | **−7.03%** | $8,178m | $618m |
| ETH | 0.216 | −3.98% | 1.77 | **−6.86%** | $3,836m | $283m |
| SOL | 0.218 | −5.05% | 1.70 | **−8.29%** | $67m | $6.0m |
| XRP | 0.215 | −5.86% | 1.64 | **−9.36%** | $25m | $2.6m |

The dilution step dominates: a raw variance ratio of 0.635 becomes a 4.1%
volatility cut once weighted by how much weekend the traded book actually
carries. Convexity then puts roughly three quarters of it back, and the premium
effect lands at 7%. The ordering across books follows the quoted ratios
directly — XRP discounts the weekend hardest and pays for it with the largest
premium effect.

**By distance from the money (`p2`, Bitcoin):**

| bucket | mean w | IV cut | elasticity | premium cut | time value |
|---|---|---|---|---|---|
| at the money | 0.212 | −4.02% | 1.22 | −4.86% | $4,455m |
| near | 0.216 | −4.09% | 1.91 | −7.57% | $2,451m |
| wing | 0.223 | −4.23% | 2.86 | −11.29% | $921m |
| far wing | 0.242 | −4.62% | 4.30 | **−17.22%** | $347m |

The volatility cut is nearly flat across the smile — this column holds the clock
at the pooled estimate — and the premium cut rises three and a half fold. That
is convexity alone, before any of §7's wing result is allowed in. The other
three books give the same picture: far-wing premium cuts of 16.4% (ETH), 19.4%
(SOL) and 23.1% (XRP).

**By maturity (`p3`):** the effect is essentially flat in maturity within the
sample — Bitcoin runs −6.9%, −7.3%, −5.6%, −7.6% across the sub-daily, 1–3 day,
3–7 day and 7–14 day bands — because what varies is not the clock but the
weekend content of each band, and the 3–7 day band happens to average the least
weekend (w = 0.171) of the four. The sample stops at 14 days; past a few weeks
the weekend fraction converges on 2/7 for every contract and the cross-sectional
effect disappears by construction.

---

## 3. The wings pay for it twice

§7 finds that the far wings apply a *deeper* weekend clock than the money —
Bitcoin's far-wing implied ratio is 0.528 against 0.630 at the money — and reads
that as the smile's moneyness metric following the clock about a third of the
way rather than as a view on weekend tails. In premium terms that structural
finding compounds with the convexity above. Repricing each bucket against the
ratio the market actually quotes there (`p5`, Bitcoin):

| bucket | IV cut | elasticity | premium cut | gap vs realized |
|---|---|---|---|---|
| at the money | −4.09% | 1.22 | −4.93% | +0.68% |
| near | −4.05% | 1.91 | −7.49% | +1.28% |
| wing | −4.59% | 2.85 | −12.13% | +0.89% |
| far wing | −6.52% | 4.22 | **−22.65%** | **−3.12%** |

Nearly a quarter of a far-wing Bitcoin option's time value is the weekend clock.
And the sign of the pricing gap is not the same across the smile: the money is
quoted slightly rich against realized weekend variance while the far wing is
quoted **cheap** by 3.1% — Bitcoin's far wing over-discounts the weekend enough
to cross the realized level even though the book as a whole does not. Ether is
the same shape (−3.5% in the far wing, +0.48% at the money); Solana and XRP,
which over-discount everywhere, reach −10.4% and −13.7% in their far wings.

---

## 4. What of it is wrong

Setting the clock to each asset's *realized* weekend ratio instead of its quoted
one prices the paper's headline gap in premium. This is the number a trader
would care about, and it is small:

| book | quoted R | realized R | gap in premium | dollars |
|---|---|---|---|---|
| BTC | 0.635 | 0.584 | **+1.09%** | +$88m |
| ETH | 0.645 | 0.607 | **+0.82%** | +$31m |
| SOL | 0.558 | 0.657 | **−2.02%** | −$1.4m |
| XRP | 0.488 | 0.621 | **−2.68%** | −$0.7m |

Positive means the weekend-heavy contract is rich relative to a weekday
contract quoted at the same instant. Bitcoin and Ether under-discount and their
weekend contracts are about one percent of time value too expensive; Solana and
XRP over-discount and theirs are two to three percent too cheap.

Two cautions, both inherited from the paper and neither optional. First, none of
these four gaps is individually significant (§5.1): the variance ratios carry
standard errors that straddle the realized values, so the dollar figures above
are point estimates of quantities that cannot be signed asset by asset. Second,
the comparison is to *realized* variance, and §7 spends a whole section
establishing that no non-negative price of jump risk closes it — which is what
licenses calling it a gap rather than a premium. Absent that section these
numbers would be a description, not an error.

---

## 5. It has roughly tripled, and it has changed sign

The tables above hold the clock at its full-sample value, so year-to-year
movement in them is contract mix and nothing else. §5.5 measures the clock
*itself* deepening by about 0.14 a year in Bitcoin and 0.12 in Ether. Repricing
each year's traded book against that year's own estimated ratio (`p8`) is where
the price story actually lives:

| year | BTC quoted R | premium cut | gap | premium removed | gap $ |
|---|---|---|---|---|---|
| 2019 | 1.57 | +8.99% | +12.2% | −$6m | +$8m |
| 2020 | 0.906 | −1.67% | +7.60% | $5m | +$23m |
| 2021 | 0.931 | −1.30% | +4.80% | $23m | +$82m |
| 2022 | 0.477 | −10.03% | −0.54% | $93m | −$5m |
| 2023 | 0.580 | −8.05% | +3.92% | $58m | +$25m |
| 2024 | 0.506 | −9.19% | +2.68% | $187m | +$48m |
| 2025 | 0.424 | −11.97% | +0.85% | $257m | +$16m |
| 2026\* | 0.296 | **−16.77%** | **−6.48%** | $153m | −$53m |

\*2026 runs to mid-August.

Through 2021 the market applied essentially no weekend discount: Bitcoin's
estimated ratio runs 1.57, 0.91, 0.93 across 2019–21, so weekend-heavy contracts
were quoted *richer* than weekday ones in 2019 and within a percent and a half
of them in 2020 and 2021. By 2026 the weekend clock is removing a sixth of the
time value of every short-dated Bitcoin option traded. Ether tracks it: +11.3%
in 2019, −11.4% in 2026.

The gap column is the part that matters for whether anyone is wrong. It starts
at +12% of time value — the market charging for weekend variance that never
arrived, which is the mispricing §6's calendar spread was harvesting — falls
through zero around 2022, and is now **negative in both mature books**. The
trade that made money for most of this sample is, on 2026 quotes, pointing the
other way. That is the same fact §6 records as decaying profitability, seen in
premium rather than in Sharpe ratios, and it is the reason the paper's open
items lead with *why the market is still deepening a discount it has already
overshot*.

![**The weekend clock in premium.** Left: what a three-day Bitcoin option loses
as its life fills with weekend, at three distances from the money, on the
full-sample quoted clock. Right: each year's traded book repriced against that
year's own estimated clock — the solid lines are the discount the market
applies, the dashed lines the part of it realized weekend variance does not
justify.](output/figures/p_f1_price_impact.png){width=100%}

---

## 6. What a position earns across a weekend

Everything above is a cross-section: what a contract is quoted at relative to
another contract at the same instant. A position also moves *through* the
weekend, and that is a different number. Three calendar days pass from Friday
08:00 to Monday 08:00 and only about two effective days do, so a long option
decays more slowly than the calendar says (`p4`, Bitcoin, at the money):

| maturity on Friday | decay, flat calendar | decay, weekend clock | premium saved |
|---|---|---|---|
| 4 days | −50.0% | −44.7% | **+5.3 pts** |
| 5 days | −36.7% | −31.6% | +5.2 pts |
| 7 days | −24.4% | −20.1% | +4.3 pts |
| 10 days | −16.3% | −14.3% | +2.0 pts |
| 14 days | −11.3% | −9.5% | +1.9 pts |
| 30 days | −5.1% | −4.4% | +0.8 pts |
| 60 days | −2.5% | −2.1% | +0.4 pts |

A long weekly straddle carried over the weekend keeps four percentage points of
premium a flat-calendar theta model would have written off, and the effect dies
away with maturity because a long contract's weekend fraction barely moves over
one weekend. The mirror image is the Friday markdown: a seven-day Bitcoin
contract quoted Friday morning already carries a 5.4% volatility markdown for
the weekend ahead, which is what the buyer is paying to avoid and the seller has
already given up.

These two views are consistent and easy to confuse. The weekend is cheap to buy
*and* cheap to hold; what it is not is free, and the cross-sectional discount is
precisely the compensation for the slower decay.

---

## 7. The same numbers, on premia that were actually paid

Everything above is built from premia reconstructed through Black-76 from the
exchange's implied volatility. The fair objection is that a pricing effect
stated in reconstructed prices is partly a statement about the pricer. The tape
carries the traded premium itself, so the objection can be answered rather than
conceded. Four checks, in increasing order of how little each assumes
(`o1`–`o5`, from `scripts/weekend_price_observed.py`).

**The reconstruction is a change of units.** Every trade's observed premium
against the Black-76 price at the exchange's own volatility, judged on time
value:

| book | trades | median error | within 1% | within 5% | Σ recon ÷ Σ observed | at the tick |
|---|---|---|---|---|---|---|
| BTC | 13,590,752 | −0.02% | 43.0% | 90.9% | **0.9983** | 17.7% |
| ETH | 9,217,106 | −0.03% | 47.9% | 92.4% | **0.9996** | 13.6% |
| SOL | 422,919 | −0.00% | 96.0% | 99.5% | **1.0000** | 0% |
| XRP | 135,445 | −0.00% | 96.7% | 99.5% | **1.0000** | 0% |

The aggregates — which is what the dollar tables rest on — are right to within
two parts in a thousand. The per-trade dispersion on the inverse books is the
premium tick: Bitcoin quotes in increments of 0.0005 BTC, so a cheap option's
price is coarsely quantized and no continuous formula can match it within one
percent. That shows up as a wide error distribution and no bias. Fewer than one
trade in a thousand prints below forward intrinsic; they are counted, not
dropped.

**The dollar figures, restated on observed money.** Time value is directly
observable — premium paid less forward intrinsic, both known per trade — so the
base can be actual money with no pricer in it. Only the counterfactual leg stays
modelled, and it has to: the contract with the weekend taken out of it does not
exist to be observed.

| book | time value traded, observed | reconstructed | premium removed, observed | reconstructed | gap, observed |
|---|---|---|---|---|---|
| BTC | $8,194m | $8,178m | **$620m** | $618m | +$88.3m |
| ETH | $3,839m | $3,836m | **$283m** | $283m | +$31.2m |
| SOL | $66.8m | $66.8m | **$6.03m** | $6.03m | −$1.37m |
| XRP | $25.2m | $25.2m | **$2.59m** | $2.59m | −$0.69m |

Nothing moves. The pooled Bitcoin premium cut is −7.032% on observed time value
against −7.029% reconstructed.

**The effect itself, with no pricer in the outcome.** Regressing log observed
time value on the weekend fraction inside a cell of trades that printed on the
same day, at the same strike to within two percent, in the same maturity decile,
measures the premium discount straight off traded prices. Running the identical
regression on the reconstructed series and estimating the difference directly —
by regressing the log ratio of the two, so the difference carries its own
day-clustered standard error — is the test:

| book | bucket | observed | reconstructed | difference | s.e. |
|---|---|---|---|---|---|
| BTC | all | −0.6560 | −0.6537 | −0.0023 | 0.0024 |
| BTC | at the money | −0.5476 | −0.5457 | −0.0019 | 0.0012 |
| BTC | far wing | −0.5444 | −0.5434 | −0.0010 | 0.0072 |
| ETH | all | −0.5683 | −0.5682 | −0.0001 | 0.0010 |
| SOL | all | −0.4833 | −0.4854 | +0.0021 | 0.0027 |
| XRP | all | −0.4895 | −0.4927 | +0.0032 | 0.0038 |

Across all sixty rows of `o4` — three specifications, five buckets, four books —
the largest divergence anywhere is 0.005 on a coefficient of −0.42, and only
three rows reach two standard errors. Traded prices and reconstructed prices
carry the same weekend effect.

**Volatilities inverted from the traded premia.** On a subsample stratified by
year, Brent inversion of the observed price, owing the exchange's volatility
field nothing:

| book | n | exchange IV | inverted IV | median gap | premium cut, exchange IV | inverted |
|---|---|---|---|---|---|---|
| BTC | 39,975 | 77.22 | 77.41 | +0.001 pts | −6.879% | **−6.874%** |
| ETH | 31,990 | 82.35 | 82.40 | +0.000 pts | −6.723% | **−6.715%** |
| SOL | 12,000 | 83.45 | 83.45 | +0.000 pts | −8.150% | **−8.150%** |
| XRP | 12,000 | 93.30 | 93.31 | +0.001 pts | −9.020% | **−9.021%** |

The whole calculation run on volatilities recovered from traded prices lands
within a hundredth of a percentage point of the same calculation on the
exchange's field.

**One thing this exercise does *not* license.** `o4` also carries the local
derivative the pricer implies, `−elasticity·(1−R)/2f`, and in the wings it sits
well away from the measured coefficient — Bitcoin's far wing is −0.54 measured
against −1.22 predicted. That gap is the estimator's, not the market's: a
regression linear in the weekend fraction recovers a chord, log premium is
strongly convex in that fraction away from the money, and on a simulated book
generated by the pricer itself the same gap appears with nothing to explain it.
`tests/test_price_observed.py` pins that, which is why the comparison quoted
above is observed against reconstructed rather than observed against a
linearization.

## 8. What this note does not establish

- **The counterfactual leg is modelled and always will be.** Section 7 puts the
  base on observed money and shows the effect measures the same either way, but
  "the same contract with no weekend in it" is something the tape supplies only
  across contracts, never for one contract against itself. It is a
  cross-sectional comparison, not a forecast: switching the clock off book-wide
  would move the level of the surface too, and nothing here estimates that.
- **The dollar totals cover the filtered short-dated sample only** — trades
  between 0.25 and 14 days with usable volatility and delta between 0.02 and
  0.98. They are not Deribit's option revenue and they are not annual figures;
  volume grew by orders of magnitude across the sample.
- **No standard errors on the price effects.** Each is a deterministic function
  of an estimated ratio, so its uncertainty is that ratio's uncertainty, carried
  through a nonlinear map. The gap figures in §4 above inherit the paper's own
  finding that no single asset's gap is individually significant.

## Reproduction

```bash
python scripts/weekend_price_impact.py
python scripts/weekend_price_observed.py
```

The first reads the headline pricing table, the smile-by-moneyness table, the
vintage trajectory and the cached smile samples in `data/panels/`, and writes
`p1`–`p8` and `p_f1` in about 70 seconds. The second writes `o1`–`o5` and takes around twenty minutes, most of it
the Bitcoin regressions.

The smile-sample cache now carries the traded premium, the trade-time forward
and the strike alongside the volatility; a cache written before those columns
existed is rebuilt from the tape automatically, with a warning, the first time
any of these scripts loads it.

Tests: `tests/test_price_impact.py` (12) pins the identities — the effect
vanishes when `w = 0` or `R = 1`, the repricing returns the planted weekday
volatility, the dollar effect is invariant to which leg of a strike is priced
while the percentage is not, and the first-order vega approximation agrees with
the exact repricing only where it is entitled to.
`tests/test_price_observed.py` (10) builds a book whose premia were generated by
a known clock and checks that the reconstruction returns exact, that the
inverse and linear premium conventions are handled apart, that the
observed-versus-reconstructed difference is zero there and non-zero when a real
divergence is planted, and that the local-derivative comparison fails in the
wings on the pricer's own prices — the reason it is reported and not relied on.
