# The Half-Life of a Pricing Error: Trading the Crypto Weekend, 2017–2026

*Draft. Companion to* **The Price of Calendar Time in a Market That Never Closes**
*(Paper I), which establishes the pricing error this paper tries to harvest.
Every figure in the text is reproducible from* `scripts/weekend_*.py`.

> **Data provenance.** All results are computed on verified series: BTC
> 24,349,954 trades, ETH 16,207,332, SOL 695,295, XRP 234,640, with bar coverage
> at 100%, 100%, 99.9% and 99.9%. Three bugs were found and fixed during this
> draft, one of them in this paper's own trading engine — a look-ahead condition
> that made the exit mark conditional on the option still being near the money,
> deleting the weekends on which the index moved and roughly doubling the
> headline result. All three are documented in `docs/data_notes.md`, with the
> superseded claims recorded in the sections they affected.
>
> **A fourth bug, found after that list was written, is the reason this draft
> exists in its present form.** The vega-matched spread was constructed as
> `net_weekend − net_weekday`. Both stored legs are the P&L of a *short*
> contract and the engine always subtracts costs, so negating the second leg
> turned its costs into a credit. An implementable position that is short one
> contract and long another pays the costs of both. The reported edge was
> overstated by exactly twice the long leg's cost — 0.064 per unit vega at daily
> rehedging and 0.267 at five-minute, against a reported edge of 0.039 and
> 0.021. **The spread was never profitable net of costs. It has not decayed; it
> was never there.** Every P&L number below is the corrected one, the
> superseded figures are stated where they stood, and §12 is new.

---

## Abstract

Paper I documents a persistent pricing error in Deribit's crypto options: the
market prices the weekend as though it were an ordinary stretch of trading time,
when Saturday realizes about a third of a weekday's variance, and the implied
discount has been deepening for a decade. This paper asks the natural follow-up.
**Can it be harvested, and if it once could, what happened?**

The answer is a null, and a sharper one than an earlier draft of this paper
claimed. The vega-matched calendar spread that isolates the error has a *gross*
edge of +0.042 per unit vega in both mature books, which tracks the pricing gap
across all four underlyings with the right sign and the right rank. It has never
covered its costs. Charging both legs — as an implementable position must, and
as an earlier version of this paper did not — leaves **−0.025 (t = −2.09) in
Bitcoin and −0.029 (t = −1.82) in Ether over the full history**, at the cheapest
rehedging frequency available. Stripping the trade back to a single outright
short, where no such construction is possible, earns +0.043 per unit vega over
the full history and **−0.001 (t = −0.12) over the last two years.**

Along the way the paper measures the anatomy of the trade rather than merely its
sign. Selling weekend content pays (+0.127 per unit of weekend share in the life
sold) and holding through the weekend costs (−0.080 per unit of the window),
because implied volatility mechanically re-rates upward as weekend-heavy
remaining life becomes weekday-heavy and a short pays that on the mark. A
second-order attribution locates the entire cost in the vega term and finds the
quiet weekend arriving, as it should, as a *credit* in the gamma term. Of eight
pre-specified conditioning variables only one survives — the ratio of the entry
quote to the volatility the week has already realized — and it raises the
out-of-sample hit rate by sixteen and fourteen points without rescuing a losing
period. Across the moneyness ladder there is nowhere better to run the trade than
at the money, and the in-the-money side cannot be traded at size at all.

The commercial conclusion is unambiguous and negative, and the correction
sharpens rather than softens it. Because the binding constraint is cost rather
than signal, the paper prices the one configuration in which the trade could
work: a market maker, who earns the effective half-spread instead of paying it
on both legs. That is worth four half-spreads, and it closes two thirds of the
gap without crossing zero — **−0.008 in Bitcoin and −0.004 in Ether**. Splitting
the residual shows why: of 0.058 per unit vega in fees, **exchange option fees
are 0.030 and perpetual hedging is 0.028**. A maker on a fee tier that discounts
option fees by 27% in Bitcoin or 12% in Ether clears zero on full-history data
at roughly +0.022. **Over the last twelve months even that configuration loses
0.013.** The pricing error in Paper I is real and is not going away; no
construction available on this venue has ever monetised it net of costs, and the
fee schedule is the reason.

## 1. Introduction

The natural objection to a systematic pricing error is that it should be
arbitraged away. This paper is an attempt to do exactly that, reported in full
including the parts that failed, and its interest is in the shape of the failure
rather than in the failure itself.

Three things make the exercise worth reporting rather than filing. First, the
decay is *measurable*: the same trade, on the same construction, run date by
date across nine years, goes from a Sharpe above one to an inversion, and the
date at which it turns is informative about when the market started pricing the
weekend properly. Second, a trading P&L is the strongest available validation of
a measurement chain — a pricing gap that cannot be shorted at all is a gap that
might be an artefact of the estimator, and Paper I's gap could be shorted,
profitably, for years. Third, the anatomy of the trade turns out to identify the
mechanism more sharply than the quotes do: the P&L separates selling weekend
content from living through the weekend, which the quote-side regressions in
Paper I cannot.

The paper also reports two of its own errors, because the corrections change
conclusions rather than decimal places. One is a look-ahead condition in the
trading engine described in the provenance note above. The other is a discarded
finding that returned once that condition was removed. Both are flagged where
they occur.

## 2. The trade, and how its costs are measured

The natural objection to a systematic pricing error is that it should be
arbitraged away. Here it partly has been.

The trade that isolates the effect is a vega-matched calendar spread: sell the
weekend-heavy contract, buy the weekday-heavy one, delta-hedge both in the
perpetual, hold to settlement. Buckets are assigned within each day's own
cross-section — an absolute threshold makes the legs nearly mutually exclusive,
since Fridays offer weekend-heavy contracts and Tuesdays offer weekday-only
ones, so a fixed cutoff describes a spread that could rarely be put on.

Costs are measured rather than assumed. Deribit charges 0.03% of the underlying
on options, capped at 12.5% of premium, plus 0.05% taker on the perpetual hedge
at every rebalance. The effective half-spread, recovered from the tape by
differencing buyer-paid against seller-received implied volatility on the same
instrument-day, is **0.42 volatility points**.

Bitcoin, 1,231 paired days, per unit of vega:

| Rehedge interval | Level (gross) | Level (net) | Spread (net) | t | Sharpe |
|---|---:|---:|---:|---:|---:|
| 5 minutes | +0.0445 | −0.0896 | +0.0209 | 3.83 | 1.73 |
| 1 hour | +0.0539 | −0.0038 | +0.0160 | 2.51 | 1.13 |
| 8 hours | +0.0614 | +0.0244 | +0.0288 | 3.19 | 1.44 |
| daily | +0.0583 | +0.0251 | **+0.0391** | **3.33** | **1.50** |

Two readings, and the second is the finding.

**The level column validates the engine.** A short delta-hedged option book earns
a positive premium gross at every frequency, as the variance-risk-premium
literature requires. It turns negative net only under five-minute rebalancing,
where perpetual taker fees are paid some two thousand times over a seven-day
contract and cost 0.134 per unit vega — more than the premium is worth. That is
a statement about an unrealistic hedging rule, not about the market.

**The spread trade is profitable at every frequency**, and most profitable where
hedging is cheapest: at daily rebalancing it earns 0.039 per unit vega net of
measured fees and spread, $t = 3.33$, annualized Sharpe **1.50**.

## 3. The P&L tracks the pricing gap in all four assets

The trade sells weekend-heavy variance, so it should profit where weekends are
priced rich and lose where they are priced cheap. Comparing against Paper I §5.1's gaps,
at five-minute rehedging — the setting the cross-asset stage runs at, and the
most conservative of the four in the table above because it pays the most
perpetual fees:

| Asset | Pricing gap | Spread P&L, **gross** | Paired days |
|---|---:|---:|---:|
| BTC | **+0.051** | **+0.0226** | 1,231 |
| ETH | **+0.038** | **+0.0212** | 1,213 |
| SOL | **−0.099** | −0.0004 | 377 |
| XRP | **−0.133** | −0.0254 | 284 |

This test is stated on gross P&L, and deliberately. Costs are a property of the
venue's fee schedule, not of the weekend, so a validation of the *measurement*
should not be routed through them; §4 charges them in full and the answer there
is negative in every book. Read gross, every sign matches and the estimates are
**rank-ordered perfectly**: sorting the four books by their implied-versus-
realized pricing gap sorts them by gross trading profit, from Bitcoin's +0.051
and +0.0226 down to XRP's −0.133 and −0.0254. The ordering is carried by point
estimates rather than four independent rejections — but the ordering itself is
the prediction, and it holds without exception.

An earlier version of this table reported *net* P&L of +0.0209, +0.0151, −0.0103
and −0.0291, and read the rank ordering off those. Those figures credited the
long leg's costs rather than charging them; the ranking happened to survive the
correction because the bias is a similar size in every book, but the levels did
not, and none of the four is positive net of costs at this rehedging frequency.

This is the paper's strongest internal check. The two legs differ in maturity as
well as weekend coverage, so a mechanical bias — short-dated contracts
systematically out-earning longer-dated ones — would generate same-signed
profits in every asset regardless of its pricing gap. Instead the sign, and now
the rank, tracks the gap across four independent books with two different
settlement conventions. **Implied-volatility gaps measured from quotes translate
into realized trading profits with the correct sign and the correct order**,
which validates the measurement chain far better than a single profitable
backtest.

Note also that Ether's gross level is now positive (+0.0295 per unit vega), as
the variance risk premium requires. An earlier version of this section reported
it at −0.176 and treated the anomaly as an open puzzle; it was the corrupted bar
series, whose gaps sent the hedging path through price jumps that never
occurred. That diagnosis is what led to the bar-coverage guard now in
`bars.load`.

### 3.1 The edge is being competed away, in every book

Splitting each sample in half:

| Asset | First half | t | Second half | t |
|---|---:|---:|---:|---:|
| BTC | +0.0343 | 3.80 | +0.0076 | 1.24 |
| ETH | +0.0465 | 3.19 | **−0.0162** | **−2.20** |
| SOL | +0.0018 | 0.09 | −0.0224 | −1.69 |
| XRP | −0.0128 | −0.42 | **−0.0454** | **−2.87** |

Bitcoin's edge has roughly quartered and lost significance. Ether's has
*reversed* — significantly negative in the second half. Every one of the four
books has a second half worse than its first, and the two that are significant
in the second half are both significantly negative.

That decay is the more interesting result, and it replicates in all four. It is
a statement about the *gross* signal narrowing, not about a profit being
competed away — §4 shows there was never a net profit to compete away — and on
that reading it still qualifies every full-sample pricing estimate in Paper I §5:
they average over a period during which the weekend error was shrinking, so the
*current* mispricing is smaller than the pooled figures suggest. What the
narrowing cannot be is evidence of arbitrage capital entering this trade, since
the trade did not pay. Someone is quoting against the error; they are not doing
it by crossing the spread.

The two young books deserve a caveat rather than the same reading. Solana and
XRP were listed in 2024, so their "first half" begins where Bitcoin's second half
is already well advanced; their decline is a decline within a late window, not a
replication of the same multi-year arc. What the four rows share is a direction,
not a common clock.

**A note on two earlier versions of this section.** Before the index-alignment
bug was found, this analysis reported the trade as unprofitable and
*undetectable* — a per-trade dispersion of 5.0 per unit vega against an implied
edge of 0.031 — which invited a limits-to-arbitrage reading. Corrected, the
dispersion is 0.19. Then, before the bar-coverage bug was found, it reported
Ether's spread at −0.164 and presented that as confirming a sign prediction
derived from Ether's corrupted gap of −0.205. Both the prediction and the test
used corrupted inputs, and the apparent agreement — 4.2× observed against 4.0×
predicted — was two errors cancelling. The table above is the version computed
on verified data.

## 4. The spread never covered its costs

The half-sample split above ends on a direction rather than a level, and a
direction is not enough to answer the question a desk would ask: is the trade on
today? Charged correctly, the answer is that it was never on. Walking the
rehedging interval out to the frequency where costs are lowest, and reporting
gross alongside net so the two can be told apart:

| BTC | 5 min | 60 min | 8 hours | daily |
|---|---:|---:|---:|---:|
| gross | +0.0226 | +0.0192 | +0.0311 | **+0.0418** |
| fees, both legs | 0.2599 | 0.1071 | 0.0658 | **0.0579** |
| spread crossing, both legs | 0.0083 | 0.0083 | 0.0083 | 0.0083 |
| **taker net** | **−0.2457** | **−0.0962** | **−0.0430** | **−0.0245** |
| *as previously reported* | *+0.0209* | *+0.0160* | *+0.0288* | *+0.0391* |

Ether is the same shape: gross +0.0418 at daily rehedging against 0.0581 of fees
and 0.0127 of spread, for a net of **−0.0289**. Solana and XRP have negative
gross to begin with and are worse at every rung.

**The signal is real and smaller than the toll.** Bitcoin's gross edge of 0.042
per unit vega is a genuine measurement of weekend richness — it is what §3's
rank ordering rests on — but the venue charges 0.066 to collect it. Nothing
about the weekend changed; the arithmetic was wrong. Every superseded figure is
shown in italics above.

The rest of this section is retained because the *time profile* is unaffected:
the bias is a near-constant per-day charge, so it shifts the level of every
subsequent table without changing its slope. Refitting date by date, with
five-minute rehedging and the previous costing, and reading it by calendar year:

| | BTC | ETH | SOL | XRP |
|---|---:|---:|---:|---:|
| 2020 | +0.0192 (+0.9) | +0.0993 (+2.0) | | |
| 2021 | +0.0596 (+2.8) | +0.0617 (+2.3) | | |
| 2022 | +0.0414 (+3.0) | +0.0404 (+2.3) | | |
| 2023 | +0.0172 (+1.8) | −0.0064 (−0.6) | | |
| 2024 | +0.0212 (+1.8) | −0.0177 (−1.6) | +0.0151 (+0.6) | +0.0026 (+0.1) |
| 2025 | +0.0117 (+1.1) | −0.0101 (−0.6) | −0.0294 (−1.7) | −0.0367 (−1.6) |
| 2026 | **−0.0367 (−3.1)** | **−0.0456 (−3.4)** | −0.0094 (−0.5) | **−0.0485 (−2.2)** |
| last 12m | **−0.0188 (−2.2)** | **−0.0301 (−2.7)** | −0.0127 (−0.8) | **−0.0393 (−2.4)** |
| last 6m | **−0.0428 (−3.3)** | **−0.0549 (−3.7)** | −0.0311 (−1.5) | **−0.0636 (−2.9)** |
| full | +0.0209 (+3.8) | +0.0151 (+1.8) | −0.0103 (−0.8) | −0.0291 (−1.7) |

Mean P&L per unit vega with *t*-statistics beside it. **The trade has gone from
decayed to inverted.** Over the last twelve months it loses money in all four
books and does so significantly in three; over the last six it loses in all four
at −0.04 to −0.06 per unit vega, against a full-sample Bitcoin edge of +0.021.
The hit rate falls with it, from 63% in Bitcoin's best year to 40% over the last
six months. Selling the weekend against the weekday is now a losing trade at
every horizon short enough to describe current conditions.

This is not a tail accident. Bitcoin's median day over the last twelve months is
−0.008 and Ether's is −0.010, so the centre of the P&L distribution has crossed
zero on its own; removing the five worst days from each still leaves −0.011 and
−0.019. The tails make the loss worse — the distribution is left-skewed, at
−0.29 in Bitcoin and −0.63 in Ether, and Bitcoin's five worst days all fall in
February and March 2026 — but they are not what put it below zero.

Figure 11 shows the cumulative path. Ether's equity curve peaks in late 2022 and
has given back a third of its gains; Bitcoin's runs to a high in early 2025 and
turns over. Solana and XRP never establish a positive stretch at all.

All of this is measured at the five-minute rehedging used elsewhere here. §5 walks that
interval out and finds the inversion does not survive to daily rebalancing —
not because the sign flips, but because discrete-hedging error more than doubles
the series' standard deviation and swamps an effect this size. The claim is
therefore that the trade has inverted *at a rehedging frequency fine enough to
see it*, which is the frequency this paper's bar data supports and the one at
which the full-sample edge was established in the first place.

**The reason is the same one Paper I §5.6 identified, seen from the seller's side.**
Comparing the implied volatility at which Friday's weekend-covering contracts
actually traded against what the weekend then delivered:

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC median | +0.081 | +0.169 | +0.154 | +0.094 | +0.125 | +0.065 | +0.035 |
| BTC **mean** | +0.037 | +0.080 | +0.129 | +0.086 | +0.104 | +0.052 | **+0.006** |
| ETH median | +0.149 | +0.161 | +0.138 | +0.071 | +0.086 | +0.094 | +0.067 |
| ETH **mean** | +0.046 | +0.080 | +0.090 | +0.053 | +0.069 | +0.041 | **+0.015** |

In annualized volatility units. The seller's cushion has compressed by an order
of magnitude in Bitcoin since 2022, and the mean is now within a rounding error
of zero while the median is still visibly positive. That gap between the two
columns is the whole story: a desk reading a screen sees a weekend still quoted
above what weekends usually deliver and concludes the sale is on, while the
quantity it is actually paid on — the mean — has already gone. Add two crossings
of a 0.42-vol-point spread and the transaction costs of a hedged position, and
what is left is negative.

So the market's deepening discount and the disappearance of the trade are two
readings of one fact. The discount had somewhere to go because the weekend's
typical variance really was falling; the trade stopped working because the
weekend's *mean* variance stopped falling with it. Whoever is still shorting
weekend variance on a screen-read edge has been paying for the difference since
roughly the start of 2025.

![**Figure 11. The trade has inverted, and the seller's cushion is gone.**
Left: cumulative P&L per unit vega of the vega-matched spread that sells the
weekend-heavy contract and buys the weekday-only one, net of measured exchange
fees, perpetual rehedging costs and two crossings of the 0.42-vol-point
effective spread. Bitcoin and Ether in bold; Solana and XRP, listed in 2024,
faded. Right: the implied volatility at which Friday's weekend-covering
contracts traded, minus the volatility the weekend then realized, by year.
Median (solid) against mean (dashed): the gap between them is the moment
mismatch of Paper I §5.6, and the mean reaching zero is what ends the
trade.](../output/figures/w_f11_shortability.png)

## 5. Dropping the weekday leg

The weekday leg exists to difference out everything that is not the weekend, and
it is fair to ask what it costs. Selling weekend-heavy contracts outright and
skipping the hedge is simpler, ties up less margin, and pays one spread instead
of two. The answer is that it changes the trade into a different trade, and the
change has to be measured at a rehedge frequency where the comparison is even
possible.

**At five-minute rehedging the outright short cannot be evaluated at all.** It
loses 0.079 per unit vega in Bitcoin and 0.102 in Ether, but 0.135 and 0.143 of
that is perpetual taker fees. The two legs of the spread carry similar vega and
therefore similar rebalancing costs, so the fee drag largely differences out;
standing alone, the weekend leg pays all of it. That is a fact about the
rebalancing rule, not about weekends. Walking the interval out:

| | 5 min | 60 min | 8 hours | daily |
|---|---:|---:|---:|---:|
| BTC fee drag | 0.135 | 0.059 | 0.038 | 0.034 |
| BTC outright, net | −0.079 (−16.5) | +0.004 (+0.7) | +0.039 (+4.8) | **+0.045 (+4.5)** |
| BTC spread, net | +0.021 (+3.8) | +0.016 (+2.5) | +0.029 (+3.2) | +0.039 (+3.3) |
| ETH outright, net | −0.102 (−16.0) | −0.017 (−2.3) | +0.011 (+1.0) | +0.010 (+0.7) |
| ETH spread, net | +0.015 (+1.8) | +0.012 (+1.4) | +0.013 (+1.1) | +0.038 (+2.4) |

Full sample, per unit vega, *t*-statistics beside. Daily rebalancing is the only
rung at which an outright short is a real proposition, so it is the one to read.

**There the outright looks better in Bitcoin and worse in Ether**, which is the
tell. Bitcoin's outright earns +0.045 at an annualized Sharpe of 2.03 against the
spread's +0.039 at 1.50; Ether's earns +0.010 at 0.33 against the spread's +0.038
at 1.10. A weekend effect would not reverse between two books that both price the
weekend the same way. A variance risk premium would, and does: Bitcoin's outright
gross level is +0.079 and Ether's is +0.047, and Solana's is +0.000 — Solana has
essentially no variance premium in this sample, and its outright short is
negative at every rung, in every year.

So the extra return in Bitcoin is not weekend alpha. It is the variance risk
premium, which the weekday leg was never there to capture and which a *weekday*
short would have earned just as well. **Removing the hedge does not sharpen the
weekend bet; it buries it inside a much larger short-volatility position.** The
correlation between the two series is 0.57 in Bitcoin and 0.61 in Ether, so most
of what the outright does day to day is something else entirely.

The risk is worse in the way that matters for a short-volatility book. Ether's
outright draws down 21.3 per unit vega at its worst against the spread's 9.5, and
its worst sixty-day stretch is −8.5 against −7.4. Bitcoin's are comparable in
this sample — 6.9 against 6.7 — but Bitcoin is the book whose realized weekend
tail has grown least, and Paper I §5.6 shows that tail growing in both.

**And it does not rescue the trade.** By year, at daily rehedging:

| | BTC | ETH | SOL | XRP |
|---|---:|---:|---:|---:|
| 2021 | +0.125 (+3.2) | +0.091 (+1.8) | | |
| 2022 | +0.094 (+3.3) | +0.040 (+1.0) | | |
| 2023 | +0.039 (+1.8) | +0.007 (+0.3) | | |
| 2024 | +0.023 (+1.2) | +0.001 (+0.0) | +0.007 (+0.1) | −0.111 (−1.1) |
| 2025 | −0.011 (−0.6) | −0.051 (−1.4) | −0.080 (−1.6) | −0.019 (−0.3) |
| 2026 | −0.013 (−0.7) | −0.032 (−1.2) | −0.020 (−0.4) | +0.039 (+1.1) |
| last 12m | −0.017 (−1.1) | −0.023 (−0.9) | −0.033 (−0.8) | +0.042 (+1.3) |

The same arc as §4: strong through 2022, decayed by 2024, negative in three of
four books over the last twelve months. The outright version is noisier — none of
the recent estimates is individually significant — so it fails to reject rather
than confirming, but it certainly does not point the other way. Dropping the
weekday leg trades a small measurable edge that has gone for a large unmeasurable
one that has also gone.

**A caveat this ladder forces on §4.** The recent inversion of the spread is
measured at five-minute rehedging, and it does not survive to the coarse end of
the ladder: Bitcoin's last-twelve-month spread runs −0.019 (t = −2.2) at five
minutes, −0.019 (t = −2.0) at an hour, −0.010 at eight hours and +0.004 at daily.
That is a power loss rather than a sign reversal — the standard deviation of the
same series rises from 0.125 to 0.312 as discrete-hedging error takes over, so
the daily estimate's standard error is 0.022 and every point estimate in the row
sits inside one of them. It is the same reason §6 hedges at five minutes in the
first place. But it should be stated plainly: **the inversion is established at
fine rehedging and is not independently significant at coarse rehedging**, and a
desk that rebalances daily would not have been able to detect it.

## 6. Trading the clock instead of the contract

Everything above enters when a trade happens to print and holds to settlement.
Settlement is the right exit for measuring a pricing error, because it is the one
valuation that is not a matter of opinion, but it is not how a desk would run the
position. The clock version sells the most weekend-heavy contract available at a
fixed hour on Friday and buys it back at a fixed hour later, marked at whatever
the market was quoting then. Two things get worse — the spread is crossed twice
instead of once, and the exit mark is an opinion — and one thing gets better: the
hold is thirty-five hours rather than a week, so far less is paid to hedge it.

**A correction to an earlier version of this section.** The first implementation
looked for the exit mark in the same frame it drew entries from, and that frame
had already been narrowed to the 0.35–0.65 delta band. The exit mark was
therefore conditional on the option still being near the money when the position
was closed — a condition on the future. Options leave the band when the index
moves, and a delta-hedged short loses when the index moves, so the requirement
deleted losing weekends: the Fridays that survived it had a mean absolute
weekend index move of 0.94% against 2.15% across all Fridays, and within the
surviving Fridays it forced a different contract on 63 of 82 occasions, always
the one that had stayed still. It doubled the reported result. The exit index is
now built from an unbanded frame — the delta band constrains what may be
*entered*, nothing more — and the numbers below are the corrected ones. The
figures in the previous draft (+0.094 and +0.095 at hourly rehedging) should be
read as roughly twice their true size. The bug was visible in the earlier draft's
own limitations paragraph, which noted that only 82 of some 430 Fridays filled
and that "which fifth fills is not random"; the fill is now 227 of 496 in Bitcoin
and 158 of 386 in Ether.

Entering at 12:00 UTC on Friday and closing at 00:00 UTC on Sunday, which is the
first instant after Saturday has finished:

| rehedge | BTC net | *t* | hit | ETH net | *t* | hit | cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 min | −0.036 | −3.40 | 43% | −0.057 | −3.79 | 37% | 0.102 / 0.126 |
| 30 min | +0.020 | 1.76 | 58% | +0.018 | 1.17 | 61% | 0.060 / 0.073 |
| 60 min | **+0.043** | **3.91** | 64% | **+0.038** | **2.40** | 63% | 0.051 / 0.063 |
| 4 hours | +0.069 | 5.26 | 69% | +0.074 | 4.22 | 70% | 0.041 / 0.051 |

Per unit vega, 227 Bitcoin and 158 Ether trades. **At the five-minute rehedging
§6 uses, the trade loses in both books**: perpetual fees alone take more than the
position earns. Five minutes is the right frequency for a seven-day hold whose
discrete-hedging error would otherwise swamp the signal; it is the wrong
frequency for a thirty-five hour one, where there is far less gamma risk to hedge
away and the same fee schedule applies. At hourly rebalancing both books clear,
by four and two and a half standard errors.

Unlike the previous draft, gross P&L is no longer flat across the rungs — it runs
+0.066 to +0.110 in Bitcoin as rehedging coarsens. That is the discrete-hedging
error of §5 reappearing, and it is visible now precisely because the moving
weekends are back in the sample: on a quiet path the rehedge frequency barely
matters, and the earlier version had kept only quiet paths.

This remains the most profitable version of the weekend trade in the paper, and
the reason is not a better view. It is a shorter hold over the specific stretch
that Paper I §3 shows is quietest, paying for a hedge over thirty-five hours instead of
seven days. But it is now a trade whose sign depends on the hedging frequency,
which is a much weaker claim than the one this section previously made.

**Is the frequency dependence about the weekend, or about not hedging?** A short
option hedged coarsely profits when the path mean-reverts, because it avoids
buying high and selling low between rebalances. Quiet weekends mean-revert, so
the ladder above could be harvesting weekend mean reversion rather than the
weekend variance mispricing — a different trade with a different risk. The test
is to run the same ladder on an exit that holds *no* weekend, on a common
contract menu:

| rehedge | BTC gross, no weekend | BTC gross, holds Saturday | ETH gross, no weekend | ETH gross, holds Saturday |
|---|---:|---:|---:|---:|
| 5 min | +0.015 | +0.066 | +0.018 | +0.069 |
| 30 min | +0.019 | +0.080 | +0.026 | +0.091 |
| 60 min | +0.026 | +0.094 | +0.027 | +0.101 |
| 4 hours | +0.030 | +0.110 | +0.032 | +0.125 |
| **gain from coarsening** | **+0.015** | **+0.044** | **+0.013** | **+0.056** |

Both answers are partly true, and the split is informative. Coarsening helps the
weekend-free exit too, by about 0.014 in both books — that is the generic
mean-reversion effect, and it is real. But it helps the weekend-holding exit
three to four times as much, and **at every rehedging frequency, including the
finest, the exit that holds a Saturday earns four to five times the gross of the
one that does not.** The weekend effect exists independently of how often the
hedge is rebalanced; coarsening amplifies it rather than creating it, which is
what one would expect if the weekend path is the calmer one. The no-weekend exit
never turns positive net of costs at any frequency, reaching only −0.009. What
makes this trade profitable at all is the Saturday.

**Which midnight matters.** Closing at 00:00 UTC on *Saturday* — the start of
Saturday rather than the end — holds no weekend at all, only Friday afternoon.
At five-minute rehedging it runs −0.049 (t = −5.60) in Bitcoin and −0.060
(t = −5.25) in Ether, against −0.036 and −0.057 for the Sunday-midnight exit.
Both lose at that frequency, so this comparison is now about which loses less,
and the ordering is weak.

**A pattern that was discarded, and now returns.** The previous draft found that
extending the exit to Monday 00:00 looked much worse, called it an artefact of
contract selection, and reported it as discarded. Under the corrected exit index
it survives the control that killed it. Restricting every exit to contracts that
live to the latest of them, so all four trade from the same menu on the same
Fridays, Bitcoin runs −0.024, −0.006, −0.028 and **−0.068** (t = −5.37) across
the Saturday-start, Saturday-noon, Sunday-start and Monday-start exits on 86
common Fridays, and Ether −0.037, −0.021, −0.034 and **−0.092** (t = −5.28) on
50. The Monday exit is the worst by a wide margin on a menu that holds the
instrument fixed. What separates it is not the realized path but the mark:
implied volatility falls 1.3 volatility points over the hold to Sunday midnight
and *rises* 6.2 points over the hold to Monday. That is the re-rating mechanism
of §8 — as weekend-heavy remaining life becomes weekday-heavy, the quote goes
up, and the short pays for it — showing up in the P&L of a trade that was never
designed to test it. **Holding a weekend short into Monday gives back more than
the weekend earned.**

**Two limits.** Requiring a print within forty-five minutes of Sunday midnight
still fills fewer than half the Fridays, and which half fills is not random — a
contract trading at that hour may be one where something is happening. Widening
the window to four and eight hours raises the Bitcoin sample to 244 and 266 and
moves the five-minute result from −0.036 to +0.004 and +0.017, so the window
matters and the direction of the selection is now measurable rather than assumed.
And this is an outright short with no weekday leg, so by §5 it collects some
variance risk premium as well as any weekend effect; its level is not a clean
estimate of the weekend error. Solana and XRP fill seven and four Fridays and are
reported only to record that their books cannot support a fixed-hour rule at all.

## 7. Can the losing weekends be identified in advance?

The clock trade of §6 loses on roughly a third of weekends. A desk would want
to know which third. With 244 Bitcoin trades and a free choice of conditioning
variables, however, something will always appear to work, so the exercise is only
worth running under discipline: eight candidate factors fixed in advance with the
sign each is expected to take, every one reported, Ether treated as a replication
rather than a second attempt, a Bonferroni threshold for eight tests
(|t| ≥ 2.73), and a filter built on the first half of the sample and evaluated on
the second.

| factor | expected | BTC β/sd | *t* | ETH β/sd | *t* |
|---|---|---:|---:|---:|---:|
| IV over realized vol of the week so far | + | +0.032 | **3.71** | +0.042 | **3.05** |
| IV percentile in its own trailing year | + | +0.024 | 2.24 | +0.026 | 1.80 |
| entry implied volatility, level | + | +0.017 | 1.28 | +0.026 | 1.37 |
| weekend share of the contract's life | + | +0.013 | 1.34 | +0.025 | 0.83 |
| 5-day change in DVOL | − | +0.016 | 0.60 | +0.028 | 0.50 |
| absolute index move over Friday | − | −0.002 | −0.20 | −0.020 | −1.20 |
| realized vol of the week so far | − | −0.005 | −0.35 | +0.008 | 0.36 |
| absolute perpetual funding, trailing week | − | −0.001 | −0.05 | −0.007 | −0.38 |

Slopes are P&L per unit vega per standard deviation of the condition, with
heteroskedasticity-robust *t*. **Exactly one factor survives its sign and the
Bonferroni threshold, and it does so in both books: the seller's cushion of
Paper I §5.6** — the entry quote divided by the volatility the week has actually
realized so far. It is +0.032 (t = 3.71) in Bitcoin and +0.042 (t = 3.05) in
Ether, and it holds its sign and significance on the first half of each sample
alone (t = 3.32 and 2.14). Everything else fails, though only the DVOL change
fails with the wrong sign in both books, and it is estimated on the shortest
sample here.

**This reverses the previous draft, and the reason is instructive.** Under the
biased exit index of §6 the cushion was the *weakest* thing tested (t = −1.26
in Bitcoin) and perpetual funding was wrong-signed in both books. That is what a
sample with the losing weekends deleted from it looks like: a factor whose job is
to predict losses has nothing left to predict, and the residual variation it fits
is noise. Restoring the moving weekends restored the variation, and the most
theoretically motivated candidate on the list is the one that came back.

**One factor remains a trap, even though it no longer looks impressive.** The
level of implied volatility is insignificant in both books here (t = 1.28 and
1.37), but it would still be the wrong thing to build a threshold on: implied
volatility falls across the sample, which is Paper I §5.5's finding, so a rule
denominated in volatility points is fitted to a level that does not persist. The
percentile version in the table is the same idea made scale-free, and the
out-of-sample filter below uses only scale-free factors for that reason.

**One factor is maturity in disguise.** With entry fixed at Friday noon, the
weekend share of a contract's remaining life is a deterministic decreasing
function of its maturity — the correlation is −1.00 — and the available
maturities take two values, about 1.7 days and about 6.8. The factor is
therefore not measuring weekend content at all at this entry point; it is saying
that the short-dated contract pays more. §8 takes this apart by varying the
entry day, and finds that the weekend share was not simply standing in for
maturity: maturity carries its own effect, but the weekend measures keep their
size beside it, and what a Friday-noon entry cannot separate is two weekend
effects of opposite sign.

**The filter, built on the first half and applied unseen to the second.** Scale-
free factors only, which selects the cushion plus the weekend share in Bitcoin
and the cushion alone in Ether:

| | trades | mean | hit rate | *t* |
|---|---:|---:|---:|---:|
| BTC, all | 122 | +0.002 | 51.6% | |
| BTC, filtered | 34 | **+0.037** | **67.7%** | 1.82 |
| ETH, all | 84 | −0.035 | 44.1% | |
| ETH, filtered | 24 | **−0.028** | **58.3%** | −0.74 |

**On the question as posed the answer is now a qualified yes, where the previous
draft's answer was no.** The filter raises the hit rate by sixteen points in
Bitcoin and fourteen in Ether, out of sample, on weekends it has never seen —
the previous draft found no hit-rate improvement at all, again because the
sample it was fitted to had few losses in it to screen out. It is genuinely
identifying weekends the trade should be skipped on.

Two things keep this qualified rather than clean. Bitcoin's filtered mean is
+0.037 on 34 trades with t = 1.82, which is suggestive and not significant at
conventional levels. And Ether's out-of-sample half loses money outright, at
−0.035 per unit vega across all trades; the filter improves it to −0.028 and
lifts the hit rate, but improving a losing period is not the same as making it
profitable. The honest summary is that the cushion carries real information
about which weekends to skip, that it survives a pre-specified test and a
split-half in both books, and that it is not large enough to rescue a period in
which the underlying trade does not work.

## 8. Weekend content against maturity, separated

§7 could not tell the two apart. With entry pinned to Friday noon the weekend
share of a contract's remaining life is a deterministic decreasing function of
its maturity — the correlation was exactly −1.00 — and only two maturities were
ever available, so "sell more weekend" and "sell less time" were the same
instruction.

Breaking that needs the identification Paper I §4 already uses for quotes, applied to
P&L. Deribit lists daily expiries, so weekend share is *not* monotone in
maturity within a single instant: from a Wednesday, the contract expiring
Thursday carries no weekend, the one expiring Monday carries a large share, and
the one expiring the following Friday carries a smaller share again on a longer
life. Entering on **every day of the week** rather than only Friday adds the
second source of variation, because the same maturity then carries different
weekend content depending on the day it is bought.

The design: enter at 12:00 UTC on every calendar day, sell the at-the-money
contract at each available expiry between 0.6 and 14 days, hold a fixed
thirty-six hours, rehedge hourly, mark out against a traded print. Holding the
horizon fixed matters — it means the entry day alone moves the weekend content
of the holding window. That gives 4,635 Bitcoin and 3,771 Ether trades, and it
takes the raw correlation between weekend share and maturity from −1.00 to
**−0.08** and **−0.10**.

Two quantities now separate, and they turn out to have **opposite signs**:

| | weekend share of *life sold* | weekend share of *window held* | maturity, days |
|---|---:|---:|---:|
| BTC | **+0.127** (6.51) | **−0.080** (−6.57) | +0.010 (3.21) |
| ETH | **+0.153** (6.11) | **−0.112** (−6.53) | +0.016 (4.68) |

Net P&L per unit vega, month fixed effects, standard errors clustered by week.
What §7 read as a maturity confound was two weekend effects of opposite sign,
which a Friday-noon entry forces to move together and therefore cannot
distinguish. Maturity does carry an effect of its own — a day is worth about one
P&L point — but it is an order of magnitude smaller than either weekend
coefficient and does not account for them.

*   **Selling weekend content pays.** A contract whose remaining life is
    weekend-heavy is priced richly relative to what it delivers, and shorting it
    earns +0.127 per unit of weekend share. This is Paper I §5.1's pricing gap showing up
    as realized P&L, now with maturity held fixed.
*   **Living through the weekend costs.** Every unit of weekend inside the
    holding window costs 0.080. Holding a short across a Saturday loses money
    even though the Saturday is quiet.

The second is the surprise, and the contract's own quote explains it. Regressing
the change in the contract's implied volatility over the hold on the same
variables:

| | weekend share of window held | weekend share of life sold | maturity |
|---|---:|---:|---:|
| BTC | **+0.219** (17.22) | −0.226 (−11.46) | −0.039 (−13.51) |
| ETH | **+0.255** (16.10) | −0.231 (−8.86) | −0.044 (−13.13) |

**As the weekend is consumed, the life that remains becomes weekday-heavy, so
implied volatility per unit of remaining time has to re-rate upward — and a
short pays that on the mark.** Holds containing no weekend see implied
volatility rise by 0.036 on average; holds that are weekend-heavy see it rise by
0.057, half again as much. The quiet Saturday is real and the gamma saving is
real — §9 measures it directly — but the re-rating is larger.

Entry day makes the same point without a model, since with the horizon fixed it
is entry day that moves the holding window:

| entry, 12:00 UTC | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | −0.024 | −0.039 | −0.037 | −0.012 | **+0.011** | **−0.053** | −0.065 |
| ETH | −0.069 | −0.061 | −0.047 | −0.018 | −0.002 | **−0.087** | −0.074 |
| weekend in window | 0.00 | 0.00 | 0.00 | 0.00 | 0.67 | 1.00 | 0.33 |
| weekend in life sold | 0.00 | 0.00 | 0.05 | 0.30 | 0.51 | 0.51 | 0.17 |

Saturday entry — a thirty-six hour hold that is entirely weekend — is the worst
day in both books and by a wide margin, winning on 28% of trades against 54% for
a Friday entry. Friday is the best day in both, and the only positive cell
anywhere in the table.

**What this implies, and where the raw cells refuse to cooperate.** The two
coefficients point in opposite directions, so the combination they favour is to
sell weekend content without living through it: short a weekend-heavy contract
and be out before the Saturday. Thursday entry is the closest a fixed
thirty-six-hour horizon allows — weekend share of life 0.30, weekend share of
window 0.00 — and it is the best of the four weekday entries, at −0.012 and
−0.018, but it is not positive and it is not better than Friday, which does hold
the weekend. **The regression separates the two effects; the entry-day table
cannot, because entry day moves both at once along with the maturities on
offer.** The previous draft read this table as confirming the combination, on a
sample a third the size in which the Thursday cell happened to be positive. It
should not have been read that way, and the honest statement is that the
implication rests on the coefficients alone. Testing the combination properly
means letting the holding period vary as well as the entry day; §9 does that,
and both coefficients survive with the horizon controlled.

**The within-instant fit is reported and is not the evidence.** Absorbing a
fixed effect for the entry instant and identifying purely from contracts trading
side by side gives +0.032 (t = 1.09) in Bitcoin and −0.038 (t = −0.62) in Ether
for weekend share, with maturity likewise indistinguishable from zero. That is a
non-rejection from a weak design rather than a contradiction: only 1.7 and 1.8
distinct expiries clear the filters at the average instant, so within an instant
the two regressors are still 80% and 82% collinear and the standard errors are
two to three times those of the month-fixed-effect fit. Paper I §5.6's lesson applies to
this paper's own tables as much as to the market's: **an underpowered
non-rejection is not a null.** The separation above rests on the across-instant
variation, where maturity is controlled directly and carries a coefficient far
too small to explain either weekend term.

## 9. Varying the holding period, and which Greek the weekend arrives through

§8 held the horizon fixed at thirty-six hours, which meant the entry day alone
moved the weekend content of the window and only a Thursday could deliver
weekend-rich content without weekend-rich holding. Freeing the horizon — twelve,
twenty-four, thirty-six, forty-eight and seventy-two hours, each entered on
every day of the week at every available expiry — gives 21,438 Bitcoin and
17,938 Ether trades and separates a third thing: simply holding for longer.

| | weekend share of life sold | weekend share of window held | holding hours | maturity, days |
|---|---:|---:|---:|---:|
| BTC | **+0.060** (6.54) | **−0.035** (−6.47) | +0.0002 (1.76) | **+0.0065** (4.74) |
| ETH | **+0.078** (6.24) | **−0.053** (−6.44) | +0.0001 (0.94) | **+0.0096** (5.87) |

Month fixed effects, clustered by week. **Both weekend coefficients survive with
their signs and gain significance**, and the structure §8 identified is intact:
selling weekend content pays, living through the weekend costs.

Two things differ from §8's fixed-horizon fit, and both are corrections rather
than refinements. **Maturity is not zero here.** A day of extra maturity is worth
+0.0065 in Bitcoin and +0.0096 in Ether, at five and six standard errors — over
the ladder's interquartile range of maturities that is a real effect, and §8's
"precisely estimated zero" does not survive the larger sample. What survives is
the weaker and more important claim: maturity does not *account for* the weekend
coefficients, which keep their size and significance beside it. **And the horizon
itself does almost nothing** once maturity is in the regression — the holding-hours
coefficient is insignificant in both books, where the previous draft attributed a
small positive to theta. That role has passed to maturity, which is where it
belonged.

Splitting each horizon by whether its window spans a weekend:

| hold | BTC no weekend | BTC spans one | ETH no weekend | ETH spans one |
|---|---:|---:|---:|---:|
| 12h | −0.048 (−14.5) | **−0.057 (−19.2)** | −0.063 (−14.5) | **−0.082 (−17.3)** |
| 24h | −0.030 (−6.9) | −0.021 (−7.2) | −0.038 (−8.4) | −0.033 (−8.6) |
| 36h | −0.029 (−5.0) | −0.037 (−10.6) | −0.054 (−8.6) | −0.057 (−10.9) |
| 48h | −0.037 (−4.4) | −0.019 (−4.8) | −0.047 (−5.8) | −0.044 (−8.6) |
| 72h | −0.000 (−0.0) | −0.031 (−5.2) | −0.033 (−2.6) | −0.035 (−6.3) |

Every cell now loses, which is what the corrected sample looks like once the
moving weekends are back in it, so the levels carry no message. The contrast
does. **A twelve-hour hold that spans a weekend is *entirely* weekend, and it is
the worst cell in both books by a wide margin — winning on 25% and 24% of
trades against 40% and 39% for the twelve-hour hold that spans none.** Beyond
twelve hours the raw contrast becomes unreliable and at 24h and 48h it reverses,
because the spanning trades also carry far more weekend content in the life they
sell — 0.39 against 0.06 at twenty-four hours — and that pays. Only the
regression, which prices the two separately, can hold them apart; the raw split
cannot, and this is a case where the cell table is the weaker evidence.

#### Which Greek the weekend arrives through

The P&L of a delta-hedged short decomposes, to second order in the entry Greeks
and the terminal moves, into a gamma term, a theta term, and the three
volatility terms — vega, volga and vanna — plus a residual that carries the path
dependence the endpoint approximation cannot see. Running the same regression on
each term separately locates the effect. Coefficients on the weekend share of
the window held:

| term | BTC | ETH |
|---|---:|---:|
| **gamma** | **+0.0324 (3.61)** | +0.0144 (1.04) |
| theta | −0.0034 (−3.83) | −0.0026 (−2.08) |
| **vega** | **−0.0829 (−17.58)** | **−0.1057 (−15.77)** |
| volga | −0.0000 (−1.25) | −0.0001 (−1.37) |
| vanna | −0.0001 (−0.12) | −0.0003 (−0.29) |
| residual (path) | +0.0201 (1.92) | +0.0427 (2.73) |

**The entire cost of holding through a weekend is still the vega term**, and it
is if anything larger than the previous draft reported. Volga and vanna remain
economically invisible. The terms sum to −0.034 and −0.052, which reconciles
with the −0.035 and −0.053 of the headline regression.

**But gamma is no longer nothing, and that is the correction.** The previous
draft reported a gamma coefficient indistinguishable from zero and put the whole
quiet-weekend credit into an unexplained residual. With the moving weekends
restored to the sample, the credit appears where theory says it should: the
gamma term itself is **positive**, at +0.032 and three and a half standard
errors in Bitcoin. Holding a delta-hedged short through a weekend saves gamma
cost, because the weekend is quiet — which is the finding this entire paper is
about, now visible in the Greek that is supposed to carry it. The residual
shrinks accordingly, from +0.036 to +0.020, and in Bitcoin it is no longer
significant at conventional levels. A large systematic residual was a sign the
decomposition was missing something; it was, and what it was missing was the
weekends where the index moved.

Adding the entry Greeks to the headline regression asks whether the weekend
measures are proxying for risk exposure. They are not — both coefficients
strengthen — but the answer to *which* Greek matters has reversed:

| | weekend life | weekend held | gamma/vega | volga/vega | vanna/vega |
|---|---:|---:|---:|---:|---:|
| BTC | +0.072 (7.96) | −0.030 (−5.45) | **−0.019 (−12.49)** | +0.001 (0.75) | −0.000 (−0.12) |
| ETH | +0.084 (6.92) | −0.041 (−5.27) | **−0.023 (−9.79)** | −0.004 (−2.46) | −0.001 (−0.88) |

Greek coefficients are shown per standard deviation of the exposure, which is
the only way they are readable: gamma per unit vega has a standard deviation of
315 in Bitcoin and 250 in Ether, so its raw coefficient of −0.00006 is a large
effect wearing a small number. **Gamma per unit vega is the exposure that
matters**, at twelve and ten standard errors and about two P&L points per
standard deviation — comparable to the weekend-held coefficient itself. Volga,
which the previous draft identified as the only Greek with independent signal,
is insignificant in Bitcoin and worth −0.004 per standard deviation in Ether;
statistically present there, economically nothing. The reversal has the same
cause as everything else in this section: gamma exposure only pays off
differently across contracts when the index actually moves, and the earlier
sample had removed the occasions when it did.

#### What this says about entry and exit

*   **Entry: choose weekend content, and avoid gamma per unit vega.** The
    weekend share of the life being sold is worth +0.060 to +0.084 per unit.
    Among contracts of equal weekend content, the ones with least gamma per unit
    vega are preferable — which in practice means longer-dated, consistent with
    the positive maturity coefficient in the same regression.
*   **Exit: before the weekend is consumed, not after.** The cost is not the
    weekend's realized movement — that is in the gamma term, and it is a
    *credit*. The cost is the mechanical re-rating of implied volatility as
    weekend-heavy remaining life turns into weekday-heavy remaining life, and it
    is paid on the mark whether or not anything happens. §6's corrected exit
    ladder makes the same point from the other side: holding into Monday, when
    the re-rating is complete, is the worst of the four exits by a wide margin.
*   **Or hedge the re-rating instead of avoiding it.** A long position in a
    weekday-heavy contract of similar vega gains when implied volatility
    re-rates upward, which is what the calendar spread of §2 is, and it is a
    reading of why the spread's Sharpe survived costs that the outright short's
    did not. This is an interpretation the decomposition suggests, not one it
    tests: the spread was never run through this attribution.

**Two limits.** The horizons overlap — a Monday 48-hour trade and a Tuesday
24-hour trade cover some of the same hours — so the effective number of
independent observations is well below the nominal count; the week clustering
absorbs some of this but not all of it. And the attribution uses entry Greeks
with terminal moves, so everything path-dependent lands in the residual by
construction. The residual is smaller than it was and no longer significant in
Bitcoin, which is a better sign for the decomposition than the previous draft's
large one, but it remains a reported column rather than a discarded one.

## 10. The same rule across the moneyness ladder

Everything from §6 to §9 ran on contracts within a 0.35–0.65 delta band — the
most liquid part of the surface and the part where vega is largest. The obvious
question is whether the trade is better somewhere else on the ladder: deep in the
money, in the money, at the money, out of the money, deep out of the money. The
rule is held fixed at the one §6 settled on — enter Friday 12:00 UTC, exit
00:00 UTC on Sunday, rehedge hourly — and only the strike moves.

**The design controls maturity in the regression, not in the sampling.** An
earlier version pinned maturity by hand, requiring all five buckets to print on
one common expiry and to print again near the exit. That is the tightest possible
control and it starved the wings: 266 Bitcoin and 63 Ether trades in total, with
Ether's deep-in-the-money bucket at *one*. The version reported here keeps every
contract tradeable at the entry instant and controls maturity with a Friday fixed
effect plus each contract's own maturity and weekend share, so a bucket is only
ever compared against contracts that were tradeable at the same instant, on the
same index, under the same weekend. That gives 18,794 Bitcoin and 14,576 Ether
trades across 479 of 496 Fridays.

#### What actually trades

Before asking what each bucket pays, it is worth asking what size each bucket
can absorb. Over the whole tape:

| | BTC trades | share | share of vega | notional | median premium |
|---|---:|---:|---:|---:|---:|
| deep ITM | 235,583 | 1.9% | **0.8%** | \$9.4bn | \$3,910 |
| ITM | 496,214 | 4.0% | 4.3% | \$23bn | \$1,727 |
| ATM | 3,836,460 | 31.0% | **43.6%** | \$235bn | \$841 |
| OTM | 3,893,315 | 31.4% | 35.3% | \$291bn | \$348 |
| deep OTM | 3,929,695 | 31.7% | 16.0% | \$289bn | \$81 |

Ether's shares are within a percentage point of these throughout. **The two
in-the-money buckets together are 6% of trades and 5% of vega.** That is not a
quirk of this sample; it is what an options market does. A trader wanting
in-the-money exposure buys the out-of-the-money option on the other side of the
same strike, which by put-call parity is the same delta-hedged position and is
cheaper to cross. The deep-in-the-money bucket is therefore a bucket in name
only, and the analysis below treats it as unmeasurable rather than as a result.

Effective half-spreads, recovered from the aggressor sides, price that
illiquidity: 0.33 volatility points at the money in Bitcoin against 0.45 deep out
of the money and 0.65 deep in the money, and 0.51 against 0.62 and 1.15 in Ether.
**Since the clock trade crosses twice, the wings pay roughly 1.4 times the
at-the-money cost before anything else happens.**

#### What each bucket pays

| | BTC *n* | net/vega | *t* | hit | cost | ΔIV, vol pts |
|---|---:|---:|---:|---:|---:|---:|
| deep ITM | 290 | −0.111 | −1.78 | 37% | 0.092 | +5.9 |
| ITM | 1,055 | −0.040 | −3.96 | 42% | 0.037 | +2.1 |
| **ATM** | 5,350 | **−0.012** | −6.29 | 45% | 0.028 | +0.0 |
| OTM | 5,586 | −0.020 | −13.39 | 40% | 0.029 | +0.9 |
| deep OTM | 6,513 | −0.045 | −16.28 | 31% | 0.041 | +3.3 |

Ether traces the same shape one notch lower throughout: −0.022 at the money,
−0.028 out of the money, −0.063 deep out of the money. **Every bucket loses on
this contract menu**, which is not a contradiction of §6 — that section
selects the single most weekend-heavy contract each Friday, while this one keeps
everything out to fourteen days, and the maturity coefficient below is positive.
The levels are not the point. The shape is: **at the money is the best place to
run this trade and both wings are worse, monotonically in distance from the
money.**

The last column says why, and it is the mechanism of §8 sorted by strike. The
weekend re-rating of implied volatility is almost invisible at the money, at
four hundredths of a volatility point, and reaches **3.3 points deep out of the
money**. A short pays that on the mark. The wings are where the smile moves when
the weekend is consumed.

#### Within a Friday, with maturity controlled

| relative to ATM | BTC β | *t* | ETH β | *t* |
|---|---:|---:|---:|---:|
| deep ITM | −0.046 | −0.66 | −0.582 | −1.88 |
| ITM | −0.007 | −0.85 | −0.011 | −0.94 |
| OTM | **−0.009** | **−4.19** | **−0.010** | **−3.36** |
| deep OTM | **−0.027** | **−3.92** | **−0.032** | **−3.33** |
| maturity, days | +0.0013 | 2.58 | +0.0024 | 2.09 |
| weekend share of life | +0.031 | 1.22 | +0.045 | 0.95 |

Friday fixed effects, clustered on the Friday. The out-of-the-money penalty
survives the tightest control available and replicates across books. As a single
continuous statement, distance from the money is worth **−0.086 (t = −3.66)** in
Bitcoin and **−0.183 (t = −3.23)** in Ether per unit of |Δ − 0.5|.

**A limit that cannot be resolved with this data.** §9 found gamma per unit
vega to be the exposure that separates contracts, and volga to be the one whose
sign the weekend mechanism predicts. Both are functions of moneyness: the
correlation between distance from the money and volga per unit vega is **+0.81**
in both books. Adding volga and gamma to the regression duly kills the moneyness
coefficient — Bitcoin −0.024 (t = −0.61), Ether +0.611 (t = 1.12) — but volga
and gamma are not significant either once moneyness is beside them. **The three
cannot be separated here, and the honest statement is that the wing penalty and
the wing convexity are the same fact seen twice, not that one explains the
other.**

#### Put-call parity, which is the test that matters

A delta-hedged short call and a delta-hedged short put struck at the same price
are the same position: what differs between them is linear in the forward and is
exactly what the hedge removes. So the in-the-money and out-of-the-money buckets
are two views of the same strikes, and if calls and puts disagree within a
bucket, the disagreement is about which contract prints, not about the risk being
held.

| | BTC calls | BTC puts | ETH calls | ETH puts |
|---|---:|---:|---:|---:|
| deep ITM | **−0.204** (−3.02) | **+0.031** (0.26) | **−0.111** (−0.88) | **−1.579** (−3.61) |
| ITM | −0.050 (−4.30) | −0.026 (−1.39) | −0.068 (−5.49) | −0.066 (−3.80) |
| ATM | −0.015 (−6.02) | −0.008 (−2.87) | −0.025 (−8.88) | −0.019 (−5.67) |
| OTM | −0.018 (−9.86) | −0.021 (−9.21) | −0.023 (−9.37) | −0.034 (−11.90) |
| deep OTM | −0.041 (−12.61) | −0.050 (−11.04) | −0.044 (−17.30) | −0.081 (−12.25)|

**Parity holds everywhere it can be measured and fails exactly where the volume
table says it must.** In the at-the-money, out-of-the-money and deep
out-of-the-money buckets calls and puts agree to within a percentage point or
two of vega — different contracts, same risk, same answer, which is a
non-trivial internal check on the whole engine. In the deep-in-the-money bucket
they disagree by 0.23 in Bitcoin and 1.47 in Ether, on 115 and 105 put
observations against a bucket that is 0.8% of market vega. **That bucket is
noise, and its headline −0.111 and −0.740 should not be quoted as findings.**

#### Verdict on the ladder

**There is no better place on the ladder to run this trade.** The at-the-money
bucket is where the vega is, where the crossing cost is lowest, where the
weekend re-rating is smallest, and where the P&L is least bad; every step away
from it costs both in spread and in re-rating, and the two wings are penalised
alike once the position is delta-hedged, exactly as parity requires. The
in-the-money side cannot be traded at size at all — 5% of vega, the widest
spreads on the board, and calls and puts that do not agree. Trade sheets for
every trade in both books are saved in `w51_moneyness_sheet_{cur}.csv`.

## 11. What it is worth

Per-vega figures are the right unit for comparing trades and the wrong unit for
deciding whether to run one. This section converts.

**Per contract.** At the median vega of the contracts the §6 rule actually
selects — \$859 in Bitcoin and \$55 in Ether — the full-history edge of +0.043
and +0.038 per unit vega is:

| | median vega | edge/vega | **per contract** | trades/yr |
|---|---:|---:|---:|---:|
| BTC | \$859 | +0.043 | **+\$37** | ~27 |
| ETH | \$55 | +0.038 | **+\$2** | ~22 |

**Capacity.** The Friday-noon window — every print within two hours of the entry
hour, across the whole tape — carries \$538m of at-the-money vega in Bitcoin over
496 Fridays, or about **\$1.1m of vega per Friday**. A participant taking a
realistic 5–10% of that flow without moving the market against themselves is
working \$55–110k of vega per weekend, which at +0.043 is \$2,400–4,700 a
weekend, or of the order of **\$60,000–120,000 a year gross** across roughly
twenty-seven tradeable weekends. That is before staff, data, colocation, the
funding paid on the perpetual hedge, and the operational risk of a position that
must be delta-hedged hourly through a weekend.

**And the recent record is flat.** The full-history figure is an average over a
sample in which the first half worked and the second did not. Year by year, on
the broad near-the-money menu at hourly rehedging:

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| BTC | −0.023 | −0.009 | +0.025 | +0.004 | −0.017 | **−0.044** |
| ETH | −0.026 | −0.036 | −0.016 | −0.009 | −0.001 | **−0.041** |

Pooled over 2025–26 that is **−0.028 (t = −10.1)** in Bitcoin, winning on 29% of
weekends in 2026. The narrower rule of §6 — one most-weekend-heavy contract per
Friday rather than the whole near-the-money menu — holds up considerably better
and still converges on nothing: **−0.001 (t = −0.12)** in Bitcoin and **+0.007
(t = 0.32)** in Ether over the same two years.

**A trade whose expected value is indistinguishable from zero, whose capacity is
six figures, and whose worst historical weekend costs 0.72 per unit vega, is not
a business.** It is a measurement. Note that the figures in this section are for
the outright clock trade of §6, which is a single short leg and so is unaffected
by the costing correction; the calendar spread, charged correctly, does not
reach this section's arithmetic at all because it never clears zero. §12 prices
the one configuration that does.

## 12. The only configuration that clears zero

Sections 3 to 11 establish that the signal is real and that no *taker*
construction covers its costs. Since the binding constraint turns out to be the
toll rather than the edge, the question worth asking last is what it would take
to stop paying the toll. There is one answer available on this venue: quote
rather than cross.

A market maker running the same position differs from a taker in exactly one
term. The effective half-spread — recovered from the tape by differencing
buyer-paid against seller-received implied volatility on the same
instrument-day, 0.42 volatility points in Bitcoin and 0.63 in Ether — is paid by
the taker on both legs and *earned* by the maker on both. The swing is four
half-spreads. Everything else is identical: the same contracts, the same delta
hedge, the same exchange fees, the same weekend.

| daily rehedging, per unit vega | BTC | ETH |
|---|---:|---:|
| gross spread | +0.0418 | +0.0418 |
| exchange option fees, both legs | −0.0297 | −0.0295 |
| perpetual hedging fees, both legs | −0.0282 | −0.0286 |
| spread crossing, both legs | −0.0083 | −0.0127 |
| **taker net** | **−0.0245** | **−0.0289** |
| **maker net** (earns the spread rather than paying it) | **−0.0079** | **−0.0036** |

**Making markets closes two thirds of the gap and does not cross zero.** That is
the single most useful number in this paper for anyone deciding whether to build
something here, and it is worth being precise about why. The bid-ask was never
what killed this trade. Of the 0.066 a Bitcoin taker pays, the spread is 0.008;
the other 0.058 is fees, and fees fall on the maker exactly as they fall on the
taker.

**So the decision reduces to the fee schedule.** Splitting that 0.058 — by
zeroing each fee function in turn and re-walking the same hedge path, rather
than re-deriving the arithmetic — gives 0.030 of exchange option fees and 0.028
of perpetual hedging. Only the first is negotiable. A maker paying no option fee
at all would earn:

| | BTC | ETH |
|---|---:|---:|
| maker, standard fees | −0.0079 | −0.0036 |
| **maker, zero option fee** | **+0.0218** | **+0.0259** |
| option-fee discount needed to break even | **27%** | **12%** |

Those are the first positive net figures in this paper. A desk quoting both legs
passively, hedging daily, and paying 27% less than the standard option fee in
Bitcoin — 12% in Ether — would have made money on this trade across the full
history, at roughly +0.022 per unit vega. Deribit's published schedule does tier
by volume, so this is not a hypothetical threshold; it is a threshold a large
enough participant could actually be on.

**And it does not survive the recent period.** Over the last twelve months the
maker version earns −0.043 in both mature books, and adding back the entire
option fee still leaves about −0.013. The configuration that clears zero clears
it on history, in a window during which §3.1 shows the gross signal was already
narrowing. There is no twelve-month window at the end of this sample in which
any construction tested here — taker or maker, spread or outright, at any
rehedging frequency, on any part of the smile — makes money.

Three caveats bound how far this can be pushed, and they run in both directions.

*   **Passive fills are assumed, not modelled.** A maker quoting both legs does
    not get filled on demand; they get filled when someone crosses, which is
    disproportionately when the crosser is right. That adverse selection is a
    real cost this calculation omits entirely, and it can only make the maker
    number worse. The trade tape carries the aggressor side, so it is
    measurable; it is not measured here.

*   **The half-spread is an average.** It is estimated per instrument-day from
    both-sided flow, so it describes the contracts that trade both ways, which
    are the liquid ones. A maker's realised capture on a thin weekend-heavy
    contract could be wider or could be zero.

*   **A maker has inventory a taker does not.** The calculation prices one
    round-trip in isolation. A real book warehouses vega between fills, and
    Paper I §5.6 shows the weekend's variance distribution has been getting more
    tail-heavy since 2022 — which is precisely the risk a warehousing maker
    carries and this arithmetic ignores.

The honest summary is that this paper has found the one configuration in which
the trade is not obviously dead, and that configuration is dead over the last
year, rests on an assumption about fills it does not test, and would need a fee
tier to have worked even on history. **That is not a business. It is a
well-measured reason to stop looking.**

## 13. Conclusion

This paper set out to harvest the pricing error documented in Paper I and did
not succeed. What it found instead is worth separating into three claims of
descending confidence.

**The error has never been harvestable by crossing, and the gross signal is
fading besides.** The calendar spread's gross edge of +0.042 per unit vega is
real and tracks the pricing gap across four books in the right order, but the
venue charges 0.066 to collect it; an earlier version of this paper reported a
Sharpe of 1.5 and an inversion, both artefacts of a spread that credited its long
leg's costs instead of charging them. The outright clock short, which admits no
such error, earns +0.043 over the full history and nothing over the last two
years. So there are two facts, not one: costs have always exceeded the edge, and
the edge has been shrinking anyway.

**The mechanism is now well identified, and it is a re-rating rather than a
realized-variance effect.** Selling weekend content pays; holding through the
weekend costs; the two have opposite signs and a Friday-noon entry cannot tell
them apart. What makes the second true is that implied volatility per unit of
remaining time must rise as the weekend is consumed, and the short pays that on
the mark whether or not anything happens. The second-order attribution puts the
entire weekend cost in the vega term, and finds the quiet weekend itself arriving
as a *credit* in the gamma term — the paper's central fact showing up in the
Greek that should carry it. §9 is the strongest part of this paper and it is the
part with no trading implication at all.

**The residual pricing error is probably being quoted against rather than
traded, and §12 now puts a number on how far that gets anyone.** A maker earns
the half-spread on both legs instead of paying it, which is worth 0.017 per unit
vega in Bitcoin and 0.025 in Ether and still leaves the position short of zero at
standard fees. Only a fee tier discounting option fees by 27% and 12%
respectively turns it positive, at +0.022, and only on full-history data — the
last twelve months lose about 0.013 even then. A desk that prices the weekend
clock correctly still improves its marks on inventory it holds anyway, at no
crossing cost and no capacity limit, and that remains the most likely reason the
quote-side gap Paper I measures survives. But the maker arithmetic here also
omits adverse selection entirely, which can only make it worse.

**What this leaves for someone else.** The trade is dead at taker capacity and
marginal at maker capacity, but the measurement is not, and the asymmetry is the
point: an error that survives in quotes while being unharvestable by crossing is
the equilibrium a market maker would produce, not the one an inefficient market
would. The next measurement is the one §12 names and does not make — adverse
selection on passive fills, which the aggressor side of this tape can support and
which would settle whether the maker configuration is genuinely marginal or
merely appears so because the cost of being filled has been left out.

**A closing note on the correction.** This draft's headline result reversed
because of a two-line construction error that no test caught, since each leg was
individually right and only their combination was wrong. The check that would
have found it is the one now in `tests/test_spread_costing.py`: costs add across
the legs of a spread, they do not cancel. It is worth stating as a rule rather
than a fix — **whenever a strategy's P&L is assembled by differencing two
separately-costed positions, the differencing silently reverses the sign of one
side's costs.** The engine was correct throughout; the assembly was not.

## Reproduction

Every table in this paper is regenerated by the scripts below, in order. The
measurement chain they depend on is Paper I's; see its reproduction table.

| What | § | Script | Tables |
|---|---|---|---|
| Spread P&L, date by date | 3, 4 | `weekend_short.py` | `w32`–`w35_*.csv` |
| Outright short, rehedge ladder | 5 | `weekend_short.py` | `w36`–`w37_*.csv` |
| Corrected costing, maker economics | 4, 12 | `weekend_maker.py` | `w60`–`w61_*.csv` |
| Fixed-hour entry and exit | 6 | `weekend_clock.py --grid` | `w38`–`w43_*.csv` |
| Rehedge ladder by exit | 6 | `weekend_rehedge_exits.py` | `w41b_*.csv` |
| Entry filters, pre-specified | 7 | `weekend_filters.py --wide` | `w44`–`w45_*.csv` |
| Weekend content vs maturity | 8 | `weekend_content.py` | `w46`–`w48_*.csv` |
| Hold ladder, Greek attribution | 9 | `weekend_content.py --hold-ladder` | `w49`–`w50_*.csv` |
| Moneyness ladder, volume, sheets | 10 | `weekend_moneyness.py` | `w51`–`w54_*.csv` |

Trade sheets for every trade in §10 are saved per currency in
`w51_moneyness_sheet_{cur}.csv`, one row per trade with both timestamps, both
marks, the hedge P&L, every fee component and the second-order attribution.

## Open items

- [ ] **When exactly did the trade die, and against what?** The year-by-year
      path in §11 shows the turn but not its cause. The candidates —  the
      arrival of systematic market makers, the 2024 spot ETFs, the growth of
      weekend perpetual liquidity — are all datable, and the P&L series is long
      enough to support a break test that this draft does not run.
- [ ] **Is the quote-side error being maintained by the same desks that killed
      the trade?** §12's central inference is untested. It needs quote-level
      data or maker-taker identifiers, neither of which the public trade tape
      carries.
- [ ] **Separate the wing penalty from wing convexity.** §10 finds distance from
      the money costs −0.086 and −0.183, and cannot tell that apart from volga
      per unit vega, with which it correlates at +0.81. A cross-section with
      independent variation in the two — a wider maturity span, or a venue with
      a different smile — would settle it.
- [ ] **The overlapping-horizon problem in §9.** A Monday 48-hour trade and a
      Tuesday 24-hour trade share hours, so the effective number of independent
      observations is well below the nominal count. Week clustering absorbs some
      of this and not all of it; a block bootstrap over non-overlapping windows
      would bound it.
- [ ] A reference list. The draft cites informally throughout and has no
      bibliography.
