# The Price of Calendar Time in a Market That Never Closes

*Draft. Every figure in the text is reproducible from `scripts/weekend_*.py`.*

> **Data provenance.** All results are computed on verified series: BTC
> 24,349,954 trades, ETH 16,207,332, SOL 695,295, XRP 234,640, with bar coverage
> at 100%, 100%, 99.9% and 99.9%. Three bugs were found and fixed during this
> draft — an index-alignment fault that silently discarded three quarters of
> several regression samples, a truncated Ether bar series that inflated its
> realized variance, and a look-ahead condition in the trading engine of the
> companion paper that made the exit mark conditional on the option still being
> near the money, deleting the weekends on which the index moved. Each
> materially changed the conclusions; the third affects Paper II only. All three
> are documented in `docs/data_notes.md`, with the superseded claims recorded in
> the sections they affected.

---

## Abstract

Equity index variance per calendar hour collapses when the exchange is shut, a
fact established by French and Roll (1986) and since attributed to the arrival
of information during trading hours. That attribution has never been cleanly
testable, because in equity markets closure and the absence of trading are the
same event. Cryptocurrency separates them: Deribit trades continuously, while
the traditional financial system does not.

We show that Bitcoin realized variance is **42% lower on weekends** than on
weekdays despite uninterrupted trading, with Saturday the quietest day of the
week. Because the crypto market itself never closes, this isolates the
information channel from the mechanical effect of an exchange being shut. The
effect is remarkably uniform across four underlyings — 34% to 42% — and roughly
doubles, to 65%, for tokenized gold, which trades continuously on the same venue
while gold's own market is shut all weekend. Turning the traditional calendar up
deepens the weekend; the venue's own hours never change.

We then ask whether options price it. Deribit lists daily expiries on all seven
weekdays — including Saturdays and Sundays, which have no equity analogue — so
the fraction of an option's remaining life falling on a weekend varies across
contracts trading at the same instant. Regressing squared implied volatility on
that fraction with day fixed effects identifies the market's implied weekend
discount from purely within-instant variation.

The market prices most of the effect, but not equally well in each asset:
implied weekend variance ratios of 0.635, 0.645, 0.558 and 0.488 against realized
0.584, 0.607, 0.657 and 0.621. Expressed as a share of each asset's own realized
weekend effect, Bitcoin and Ether price 85.0% and 85.5% of it while Solana and
XRP price 132% and 136% — but no one of those four pricing errors is
individually significant, and the apparent split by vintage largely dissolves
once the books are compared over the same calendar window. What is precisely
estimated is a common time trend: the implied weekend discount has deepened by
0.14 and 0.12 per year since 2020 (t = −12.5 and −10.5), carrying the market
from pricing no weekend discount at all in 2020 to over-discounting today.

**That trend turns out to be a response to a real change in the data, measured
against the wrong moment of it.** The realized weekend ratio compared against
throughout — mean weekend variance over mean weekday variance — appears flat, but
only because a handful of days sets each year's mean: trimming the top one per
cent of days from each day type takes Bitcoin's realized trend from t = −1.2 to
t = −4.9, and at the centre of the distribution the weekend has been getting
quieter at 0.136 log points a year, or about 13%, at t = −7.5. The market's
quotes track that geometric decline and not the arithmetic one, in trends and
in a backward-looking
calibration test alike, and the two become statistically indistinguishable at
the coarse sampling intervals where microstructure noise cannot reach. Since an
option pays off on expected total variance — an arithmetic mean — this is a
systematic error whose size is the widening gap between a weekend's typical
variance and its average one, which is the fat-tail finding below seen from the
other side. A pooled test rejects a strictly uniform
discount across underlyings; it cannot reject proportional calibration either,
but the market's quotes disperse 2.4 times more across assets than realized
weekend risk does, so that non-rejection reflects the test's power rather than
support for calibration.

The differentiation failure is not across assets but *within* the weekend. In
all four books the market prices Saturday as indistinguishable from Sunday, when
Saturday is reliably the quieter of the two — the one place where its ranking of
calendar time is demonstrably wrong rather than merely compressed.

None of this is risk compensation, and we test that rather than assume it. A
premium applied proportionally to calendar time cancels out of a variance ratio,
so only weekend-specific risk can matter — and weekend returns do carry 15% to
28% more mass beyond five standard deviations. Splitting realized variance into
continuous and jump components bounds what a jump premium can price, and every
book's quote falls outside that bound; the two books listed in 2024 quote below
their own realized weekend variance, which no non-negative price of jump risk can
produce. The option surface agrees: the far wings, where jump risk is priced,
discount the weekend **harder** than the money in all four books rather than
more softly. That is the smile's moneyness metric following the weekend clock
only about a third of the way — a second instance of a level adjustment made and
a structural one not.

Finally, the mispricing is measurable and has never been harvestable. A
vega-matched calendar spread that sells weekend-heavy variance and buys weekday
variance earns a *gross* +0.042 per unit vega, and orders the four books exactly
as their measured pricing gaps do — but the venue charges 0.066 to collect it,
leaving **−0.025 (t = −2.09)** net at the cheapest rehedging frequency tested.
The obstacle is the fee schedule, not the market: of that toll, the bid-ask is
0.008 and exchange and hedging fees are 0.058. The gross edge is fading besides,
and the cause is the same moment mismatch. What a Friday seller of weekend
variance is paid, measured against what the weekend then delivers, still looks
positive at the median and has reached zero at the mean — and the mean is what
the seller is paid on. Dropping
the weekday leg does not repair it: the outright short's apparent advantage in
Bitcoin is the variance risk premium, it reverses in Ether, and its own recent
years decay the same way. The companion paper, *The Half-Life of a Pricing
Error*, takes this apart across seven trade constructions and finds nothing that
survives at taker capacity — which is itself the best available evidence that
the residual error is being quoted against rather than traded.

---

## 1. Introduction

Asset prices are far more volatile when exchanges are open than when they are
shut. French and Roll (1986) established the fact for US equities and set out
three candidate explanations: public information arrives disproportionately
during business hours; private information is impounded when informed investors
trade; or trading itself generates pricing errors. Distinguishing among them has
proved difficult for a structural reason. In a conventional market, "the
exchange is closed" and "no one is trading" are the same event, and both
coincide with the hours in which most public information is released. The three
explanations are confounded by construction.

Cryptocurrency markets break that confound. Deribit trades options and
perpetual futures continuously, including weekends, while the traditional
financial system does not. Trading is therefore possible at all times, and any
weekend variance effect cannot be attributed to a venue being shut.

We document three things.

**Weekends are quiet even though the market is open.** Realized variance is 42%
lower on Saturdays and Sundays than on weekdays for Bitcoin, 39% lower for Ether,
38% for XRP and 34% for Solana, with Saturday the quietest day of the week in all
four. Since the crypto venue never closes, this isolates the information channel
from the mechanical effect of closure. The natural interpretation is that much of
what moves crypto prices originates in traditional market hours — macroeconomic
releases, institutional flow, the spot-ETF complex — and the fact that four
assets with different settlement conventions, holder bases and listing histories
inherit the *same* weekly rhythm is what makes that reading hard to avoid. A
fifth asset settles it. PAXG, tokenized gold, trades continuously on the same
venue while gold's own market in London and on COMEX is shut all weekend; its
weekend variance is **65% below weekday**, roughly double the crypto effect. Turn
the traditional calendar up and the weekend deepens, on the same exchange with
the same estimator.

**Options price most of the effect.** Deribit lists daily expiries on all seven
weekdays, so contracts quoted at the same instant differ in how much weekend
calendar time they span: on a Thursday, a Friday expiry covers no weekend while
a Monday expiry covers most of one. Regressing squared implied volatility on
that fraction, with day fixed effects absorbing the volatility level and every
other common shock, identifies the market's implied weekend discount from purely
within-instant variation. Bitcoin's options price 85.0% of Bitcoin's own realized
weekend effect and Ether's 85.5% of Ether's, while Solana's and XRP's price 132%
and 136% of theirs — though none of those four errors is significant on its own,
and §5.5 shows the sign pattern is mostly an artefact of the four books covering
different stretches of calendar time. A pooled test rejects a strictly uniform discount across
underlyings, but it cannot say what replaced it: implied discounts disperse 2.4
times more across assets than realized weekend risk does, and the four realized
effects are bunched too tightly for a proportionality test to have power. This
design has no equity analogue: there are no Saturday expiries when the exchange
is closed.

**The failure is within the weekend, not across assets.** In all four books the
market prices Saturday as statistically indistinguishable from Sunday, when
Saturday is reliably the quieter of the two. Across the rest of the week the
implied day-of-week profile tracks the realized one closely — correlations of
+0.98, +0.88, +0.89 and +0.82 — so the market reads the calendar well everywhere
except here, where it resolves "the weekend" as a single undifferentiated block.
Four independent books make the same mistake in the same place, which is the
signature of a shared convention rather than of a risk premium.

We then take the risk-premium explanation seriously enough to race it. Weekend
returns do carry fatter tails, so there is a weekend-specific risk to charge for
— but decomposing realized variance into continuous and jump parts bounds what a
jump premium can price, and every book's quote falls outside that bound. Two of
the four would need a *negative* price of jump risk, because their quotes sit
below their own realized weekend variance to begin with.

We close by asking whether the residual error is harvestable. It is not, and
the reason is specific: a vega-matched calendar spread isolating the effect earns
+0.042 per unit vega gross and meets 0.066 of measured fees and spread, so it has
never cleared zero at taker cost. The gross edge also falls by roughly three
quarters across the sample, so the error is narrowing as well as being
untradeable — a fading feature of this market rather than a permanent one, and
one that only a fee-advantaged market maker has ever been positioned to collect.

### Related literature

**Trading hours and variance.** French and Roll (1986) is the origin of the
question. Barclay, Litzenberger and Warner (1990) came closest to separating the
mechanisms, using a natural experiment in the opposite direction from ours: when
the Tokyo Stock Exchange opened on Saturdays, weekend variance rose while weekly
variance was unchanged despite higher volume. They varied whether an exchange
was *open* while holding the information environment roughly fixed; we hold the
exchange open always and vary whether the traditional financial system is
running. The two designs bracket the question from opposite sides, and both
point to trading-time rather than calendar-time as the relevant clock.

**Pricing of calendar time in options.** Practitioners have long used
trading-day rather than calendar-day clocks, and the term-structure literature
documents day-of-week and holiday effects in implied volatility. What has been
missing is a market where the clock can be estimated from contracts that differ
only in calendar composition while trading simultaneously. That is what daily
seven-day-a-week expiries provide.

**Crypto derivatives.** A growing literature studies Deribit microstructure and
the inverse-option convention (Alexander and co-authors), and crypto variance
risk premia. We contribute a measurement point that constrains all of it: the
weekend clock is mispriced, so any study using calendar-time maturities on
short-dated crypto options inherits a systematic bias.

**Arbitrage and its decay.** Our closing result speaks to how quickly a young
derivatives market corrects a measurable pricing error. The weekend wedge is
worth +0.042 per unit vega gross over the full sample against 0.066 of measured
cost, so it has never been harvestable by crossing; and roughly three quarters of
the gross return accrues in the first half, with every one of the four books
showing a worse second half than first. §5.5 shows the same thing
from the pricing side: the implied weekend discount deepens by about 0.13 a year,
so the error the trade harvests was closing throughout the sample and has now
changed sign. §5.6 identifies what the deepening is a response to — a real
decline in the *centre* of the realized weekend distribution, tracked at close to
the right speed, in a market whose options nonetheless pay off on its mean. The
mispricing is neither
permanent nor instantly competed away; it erodes over several years, which is the
pace one would expect of a real but modest edge in a venue whose participant base
is professionalizing.

## 2. Institutional setting and data

### 2.1 Why Deribit

Deribit is the dominant venue for crypto options and, critically for this paper,
lists **daily expiries on all seven weekdays**. Across the full instrument
history the expiry-weekday distribution is roughly uniform apart from the
expected Friday concentration:

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---:|---:|---:|---:|---:|---:|---:|
| 42,732 | 43,246 | 43,977 | 44,234 | 80,539 | 44,389 | 43,710 |

Across 342,827 instruments in the four books used here, and the shape holds
within each of them separately: every underlying lists between 12% and 14% of
its instruments on each of the six non-Friday weekdays.

From 2020 onward there is an expiry on essentially every calendar date (365 of
365 in 2021 through 2025). Short-dated contracts are the norm rather than a
curiosity: roughly 80% of instruments listed in 2020–2022 had two days or less
of life, and about 80% throughout have seven days or less.

### 2.2 Sample

The complete public trade history, collected from `history.deribit.com`:

| | Days | Trades | First | Last |
|---|---:|---:|---|---|
| BTC | 3,545 | 24,349,954 | 2016-11-29 | 2026-08-13 |
| ETH | 2,703 | 16,207,332 | 2019-03-21 | 2026-08-13 |
| SOL | 914 | 695,295 | 2024-02-12 | 2026-08-13 |
| XRP | 886 | 234,640 | 2024-03-12 | 2026-08-14 |
| **Total** | | **41,487,221** | | |

Each trade carries the exchange's own implied volatility, the index level, the
aggressor side, and flags for block trades, combinations and liquidations. The
baseline sample excludes block trades and combinations, retains liquidations,
and keeps contracts with |delta| between 0.30 and 0.70 and maturity between 6
hours and 14 days. Realized volatility comes from five-minute perpetual-future
returns over 2,923 Bitcoin days, 2,704 Ether days, 915 Solana days and 887 XRP
days, at 100%, 100%, 99.9% and 99.9% bar completeness respectively.

A fifth asset appears on the realized side only. PAXG is tokenized gold: the
Deribit perpetual trades continuously like every other book here, but the
underlying's price-formation market — London and COMEX — is genuinely shut from
Friday 22:00 to Sunday 22:00 UTC. It therefore turns the paper's mechanism up
rather than merely exhibiting it, and §3 uses it as a dose-response check. It
contributes no pricing estimate: 5,304 of its 5,346 listed options expire on a
Friday, so within a trade day the weekend fraction of a contract's remaining
life is a deterministic function of its maturity and cannot be separated from
the maturity controls that §5.1 requires. Its perpetual covers 618 days from
2024-12-05.

Solana and XRP options are USDC-settled (linear) rather than coin-settled, carry
contract sizes of ten and one thousand rather than one, and are quoted on
separate `SOL_USDC` and `XRP_USDC` instrument families. They therefore require
their own premium and hedging conventions throughout, which is what makes them
genuinely independent observations rather than relabellings of the same book.
XRP strikes are sub-dollar and Deribit encodes their decimal point as a letter
`d` — `XRP_USDC-9MAR24-0d54-C` is a 0.54 strike — while the same expiry also
carries plain integer strikes, so the two forms have to be read off the field
rather than switched on the currency.

One caveat attaches to the two USDC books: no forward curve is used for either,
so their greeks are computed against the index rather than the per-expiry
forward. Deribit does list dated futures on both, but they are close to untraded.
Over the whole sample only three SOL and three XRP contracts produced usable
daily closes, covering the last 127 and 59 days respectively, and the near-dated
ones return no bars at all. A curve fitted to that would introduce a
discontinuity in the final months of each sample and carry stale-close noise
where it did exist, which is worse than the uniform index treatment used
instead. The gap is therefore documented rather than patched.

This does **not** touch the headline regression, whose dependent variable is the
exchange's own implied volatility field and is therefore independent of our
forward. It does slightly perturb the delta used in the moneyness filter and the
vega used to scale the trading test, though the basis is small over the six-hour
to fourteen-day maturities in the sample. The two USDC books' figures should be
read as marginally less precise than Bitcoin's and Ether's for that reason, not
as differently constructed.

Three measurement points, documented in full in `docs/data_notes.md`, matter
enough to state here. Deribit options are inverse (coin-settled) and priced off
the per-expiry forward, not the index, so the forward curve is constructed from
roughly 480 dated futures per currency; using the index instead biases recomputed
implied volatility by up to 12 volatility points at long maturities in contango.
The chart endpoint silently truncates at 5,001 bars, which cost 40% of the return
series before it was caught. And the implied volatilities used here reproduce the
exchange's own field to a median of 0.49 volatility points, with the constructed
30-day at-the-money series correlating 0.9913 with Deribit's published DVOL
index.

## 3. The fact: weekends are quiet in a market that is open

Annualized realized volatility by day of week, from five-minute returns:

| | Mon | Tue | Wed | Thu | Fri | **Sat** | **Sun** |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 59.9 | 58.9 | 61.1 | 60.4 | 59.2 | **42.0** | **46.3** |
| ETH | 77.0 | 75.9 | 79.2 | 77.1 | 75.3 | **56.7** | **62.4** |
| SOL | 89.0 | 85.5 | 83.6 | 82.0 | 87.6 | **60.8** | **68.8** |
| XRP | 86.5 | 80.1 | 76.5 | 76.0 | 84.2 | **58.3** | **63.9** |

Saturday is the quietest day of the week in every asset and Sunday the second
quietest, with no weekday in any row falling below any weekend day. The gap is
large: Bitcoin's Saturday runs 30% below its weekday mean, Ether's 26%, Solana's
29% and XRP's 28%.

In variance terms, across all four underlyings:

| | Weekday days | Weekend days | Weekday variance | Weekend variance | **Ratio** |
|---|---:|---:|---:|---:|---:|
| BTC | 2,089 | 834 | 0.00142 | 0.00083 | **0.584** |
| ETH | 1,932 | 772 | 0.00225 | 0.00137 | **0.607** |
| SOL | 655 | 260 | 0.00238 | 0.00156 | **0.657** |
| XRP | 634 | 253 | 0.00255 | 0.00158 | **0.621** |

**Weekend variance is 34% to 42% below weekday in every asset, and the exchange
is open throughout.** The four ratios agree within seven percentage points
despite the assets differing in settlement convention (Bitcoin and Ether inverse,
Solana and XRP linear), holder base, listing history, and volatility level.

That agreement is the paper's central evidence, and it is a sharper test of the
mechanism than the level of any one ratio. If crypto weekends are quiet because
the *traditional* financial system is closed — no macroeconomic releases, no
institutional flow, no spot-ETF creation and redemption — then every crypto asset
should inherit the same weekly information rhythm regardless of its own
microstructure. If instead weekend quiet reflected asset-specific features such
as retail participation or venue depth, the ratios would diverge. They do not.

An earlier version of this section reported Ether at 0.850 and built an argument
around Bitcoin's supposedly deeper traditional-finance linkages. That figure was
an artefact of a corrupted bar series, and the explanation it invited was
unnecessary: Ether's weekend looks like everyone else's.

![**Figure 1. Realized volatility by day of week.** Annualized volatility from
five-minute perpetual returns. Weekend days in red, the dashed line the weekday
mean. The venue is open on every bar shown.](output/figures/w_f1_realized_by_dow.png){width=100%}

### Turning the mechanism up: an underlying whose market really does close

The four ratios agreeing is consistent with the traditional-calendar explanation,
but it is also consistent with any story that applies uniformly to crypto. The
discriminating test is an asset traded on the same venue, in the same continuous
way, whose own reference market is genuinely shut at the weekend. If the
mechanism is the traditional financial calendar, that asset's weekend should be
much quieter than any crypto asset's; if weekend quiet is something about crypto
market structure, it should look like the others.

PAXG is tokenized gold. Its Deribit perpetual trades continuously, but gold's
price is formed in London and on COMEX, which close from Friday 22:00 to Sunday
22:00 UTC. Over 618 days:

| | Mon | Tue | Wed | Thu | Fri | **Sat** | **Sun** |
|---|---:|---:|---:|---:|---:|---:|---:|
| PAXG | 23.5 | 25.1 | 24.1 | 23.8 | 23.6 | **10.8** | **14.1** |

Its weekend/weekday variance ratio is **0.347** — roughly half the lowest crypto
ratio, and Saturday runs 55% below its weekday mean against 26–30% for the four
crypto books. The effect roughly doubles precisely where the underlying's own
market closes, on the same exchange, in the same continuously traded instrument,
with the same estimator.

That 0.347 is a *lower bound* on the discount, and the reason matters for how it
is read. PAXG's perpetual is thin enough that 88% of its weekend five-minute
closes repeat the previous one, which biases its measured weekend variance
upward toward its weekday variance. Coarsening the sampling interval until most
of that staleness is gone takes the ratio down to 0.246 at hourly returns and
0.188 at two-hourly, against the four crypto books, whose ratios do not move at
all with the interval (§7). The conservative five-minute figure is the one quoted
here and in Figure 2.

![**Figure 2. The weekend discount, four traded books and one reference asset.**
Realized weekend variance divided by realized weekday variance. The four crypto
underlyings sit in a narrow band between 0.58 and 0.66. PAXG, tokenized gold,
trades continuously on the same venue while gold's own market in London and on
COMEX is shut from Friday 22:00 to Sunday 22:00
UTC.](output/figures/w_f5_reference_asset.png){width=85%}

That is the cleanest evidence in the paper that weekend quiet is inherited from
the traditional financial calendar rather than produced by crypto's own
microstructure. It also says something about what the crypto ratios mean: a
weekend that is 38% quieter is what a market looks like when its *information
suppliers* rest, and a weekend 65% quieter is what it looks like when the
price-forming venue itself is bolted shut. Crypto sits in between because it is
continuously traded but informationally tethered.

### The weekly shape, not just the weekend

Realized variance for adjacent day-pairs, relative to the rest of the week:

| Day pair | BTC | ETH | SOL | XRP | PAXG |
|---|---:|---:|---:|---:|---:|
| Sat + Sun | **0.584** | **0.607** | **0.657** | **0.621** | **0.347** |
| Sun + Mon | 0.848 | 0.893 | 1.020 | 1.017 | 0.874 |
| Tue + Wed | 1.143 | 1.226 | 1.045 | 0.962 | 1.312 |
| Thu + Fri | **1.307** | **1.173** | **1.165** | **1.271** | **1.319** |

Two features hold in all five: Saturday–Sunday is by a wide margin the quietest
pair, and Thursday–Friday is among the busiest, running roughly twice weekend
variance. The middle of the week is where the assets stop agreeing — Ether's
Tuesday–Wednesday exceeds its Thursday–Friday, and XRP's falls slightly below
the weekly average — so the shared structure is the weekend trough and the
late-week peak, not a fully common ordering. An earlier version of this section,
written when the sample was three assets, claimed every asset showed the same
ordering; with four it does not, and the weaker statement is the accurate one.
Note that PAXG's midweek is the most pronounced of the five, which is what an
asset whose information arrives only on business days should look like.

This is still a stronger claim than the weekend ratio alone. A single quiet
period could be explained by many things; a trough and peak that recur in four
crypto assets whose only common feature is that they trade against a financial
system running Monday to Friday, and that deepen in the one asset whose own
market observes that week literally, is difficult to attribute to anything else.

## 4. Identification

Write the total variance over an option's life as a time-weighted average of a
weekday and a weekend variance:

$$\sigma^2_{i,t} T_{i,t} = v^{wd}_t (1 - w_{i,t}) T_{i,t} + v^{we}_t\, w_{i,t} T_{i,t}$$

where $w_{i,t}$ is the fraction of contract $i$'s remaining life at time $t$
falling on a Saturday or Sunday. Dividing through,

$$\sigma^2_{i,t} = v^{wd}_t + (v^{we}_t - v^{wd}_t)\, w_{i,t}.$$

The estimating equation is

$$\sigma^2_{i,t} = \gamma_t + \beta\, w_{i,t} + \delta' X_{i,t} + \varepsilon_{i,t}$$

with $\gamma_t$ a day fixed effect and $X$ containing log maturity, its square,
and |delta|. The coefficient $\beta$ estimates $v^{we} - v^{wd}$, and the implied
variance ratio is $(\bar v^{wd} + \beta)/\bar v^{wd}$.

Two features make this credible. First, $\gamma_t$ absorbs the level of
volatility and everything else common to the day, so $\beta$ is identified only
from contracts quoted **at the same instant** that differ in weekend exposure —
on a Thursday, a Friday expiry spans no weekend while a Monday expiry spans most
of one. Second, $w$ is mechanical: it is a property of the calendar and the
expiry date, not of anything the market chooses in response to volatility.

Weekend fraction is computed exactly, in closed form, rather than by counting
whole days. Deribit expiries settle at 08:00 UTC, so almost every contract
covers part-days at both ends, and a whole-day count would misstate $w$ by up to
two thirds of a day on the short contracts that carry most of the identifying
variation. The same construction yields the fraction falling on each of the
seven weekdays, which §5.4 uses.

Standard errors are clustered by day throughout.

The identification is visible directly in the data. Demeaning both squared
implied volatility and weekend fraction within each trading day strips out the
volatility level and every common shock, leaving only the comparison the
regression uses — contracts trading at the same instant that differ in how much
weekend they span:

![**Figure 3. Within-day identification, Bitcoin.** Twenty equal-count bins of
weekend fraction, both axes demeaned within the trading day. The negative slope
is the weekend discount, estimated entirely from contracts quoted
simultaneously.](output/figures/w_f4_binscatter_BTC.png){width=78%}

## 5. Results

### 5.1 The market prices most of the weekend effect, and the residual is not precisely signed

| | slope $\beta$ | se | t | n | implied ratio | realized ratio | gap | (se) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | −0.1612 | 0.0149 | **−10.8** | 5,339,133 | 0.635 | 0.584 | +0.051 | (0.066) |
| ETH | −0.2461 | 0.0277 | **−8.9** | 3,624,938 | 0.645 | 0.607 | +0.038 | (0.067) |
| SOL | −0.3568 | 0.0243 | **−14.7** | 189,906 | 0.558 | 0.657 | −0.099 | (0.102) |
| XRP | −0.5513 | 0.0691 | **−8.0** | 70,128 | 0.488 | 0.621 | −0.133 | (0.123) |

Over 3,413, 2,703, 886 and 885 days respectively, standard errors clustered by
day. The gap's standard error combines the implied slope's with the realized
ratio's own sampling error, which the earlier drafts of this table omitted.

The slope is negative and overwhelmingly significant in all four: **the market
does price weekend calendar time, and prices a large share of it.** Bitcoin
implies a weekend variance ratio of 0.635 against a realized 0.584 — a discount
of 36.5% where the true discount is 41.6% — and Ether 0.645 against 0.607.
Roughly seven eighths of the effect is in the price in both established books.

**The residual gaps are not individually significant, and that constraint binds
everything said about them.** The four t-statistics are +0.78, +0.57, −0.92 and
−1.07. The implied side is estimated to within about three points of variance
ratio, but the realized side is a difference of two means over 834 weekend days
at most, and it is the realized side that dominates the uncertainty. Nothing
below should be read as a measured pricing error in a particular book.

What *is* precisely estimated is the implied discount itself, and the pattern in
it is real: Solana and XRP quote deeper weekend discounts than Bitcoin and Ether
— 44% and 51% against 36.5% and 35.5% — while their realized weekend effects are
if anything the milder ones. Earlier drafts read that as a split by the age of
the book, the two 2024 listings over-discounting and the two mature books
under-discounting. §5.5 takes that reading apart: the sign pattern is mostly an
artefact of the four books being averaged over different stretches of calendar
time, and the underlying fact is a single market-wide trend.

The raw pattern is visible without any regression. Average at-the-money implied
volatility for contracts with three days or less to expiry, by expiry weekday:

| | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 48.8 | 56.7 | 57.8 | 59.5 | 62.4 | 55.7 | **44.6** |
| ETH | 62.6 | 71.1 | 73.6 | 76.3 | 79.7 | 70.9 | **60.1** |
| SOL | 75.5 | 87.9 | 88.1 | 86.7 | 85.3 | 82.1 | **66.3** |
| XRP | 89.0 | 104.0 | 99.9 | 92.7 | 94.5 | 89.6 | **74.5** |

Sunday expiries are the cheapest of the week in all four books and Monday
expiries the second-cheapest in three of them — precisely the two that carry the
most weekend calendar time. The market's ordering is right; its magnitude is not.

![**Figure 4. Short-dated implied volatility by expiry weekday.** Average
at-the-money implied volatility on contracts with three days or less to expiry,
as a percentage deviation from each asset's own mean. The shaded band marks
Saturday and Sunday expiries. All four curves fall into the weekend, and the
Monday trough reflects the weekend calendar time a Monday expiry still
carries.](output/figures/w_f3_iv_by_expiry_dow.png){width=85%}

![**Figure 5. Implied against realized weekend discounts.** Realized
weekend/weekday variance ratio (red) against the ratio implied by option quotes
(blue), with the arrow marking the pricing gap. A ratio of one, the dotted line,
would mean the weekend is priced as an ordinary stretch of
calendar.](output/figures/w_f2_implied_vs_realized.png){width=85%}

### 5.2 The mechanism: how much cross-asset variation reaches prices

The comparison across underlyings is the paper's central piece of evidence:

| | Realized ratio | Implied ratio | Error |
|---|---:|---:|---:|
| BTC | **0.584** | 0.635 | +0.051 |
| ETH | **0.607** | 0.645 | +0.038 |
| SOL | **0.657** | 0.558 | −0.099 |
| XRP | **0.621** | 0.488 | −0.133 |

The realized ratios occupy a band of 0.073; the implied ratios span more than
twice that, 0.157. The market's cross-asset differentiation is therefore not
merely commensurate with the variation it needs to capture — on the face of it,
it is larger. The question is whether the differences across assets are
systematic, which requires a pooled test rather than four separate comparisons.

**A fourth underlying, and what it did not do.** XRP options, listed on Deribit
since March 2024, were added to widen the cross-section. They are USDC-settled
with a contract size of 1,000, so they carry their own premium and hedging
conventions, and they list daily expiries on all seven weekdays from the outset
and therefore contribute the same within-instant variation.

Realized weekend effects, scaled by each asset's own mean daily variance so they
are comparable across volatility levels:

| Asset | Weekend/weekday variance ratio | Scaled realized effect | Weekend days |
|---|---:|---:|---:|
| BTC | 0.584 | −0.4720 | 834 |
| ETH | 0.607 | −0.4427 | 772 |
| XRP | 0.621 | −0.4253 | 253 |
| SOL | 0.657 | −0.3802 | 260 |

XRP landed in the interior. Its realized effect sits between Ether's and
Solana's, so the span across assets is 0.092 with four underlyings exactly as it
was with three, and the cross-sectional dispersion the pooled test needs is no
larger than before. That is a result rather than a disappointment: the previous
draft named a fourth underlying with a materially different weekend profile as
the binding constraint, and the honest finding is that among crypto assets there
may not be one. Four books spanning two settlement conventions, a decade of
listing history and a factor of thirty in trade count all discount their weekend
by between 34% and 42%. §3's PAXG comparison shows what a materially different
profile looks like, and it is not a cryptocurrency.

The consequence for what follows is unchanged and worth stating before the test
rather than after: with four assets whose weekend structures are this similar, a
failure to reject either hypothesis is weak evidence, and only a rejection
carries much information.

Two refinements to the test follow. With four assets, equality and
proportionality become joint restrictions, so both are reported as Wald
statistics on a single fitted model with one weekend slope per asset rather than
as pairwise $t$-tests. And the realized effects are *estimates*, not constants:
XRP's and SOL's each rest on under a third as many weekend days as BTC's. Since implied slopes are
identified from option quotes and realized effects from underlying returns, the
two are independent, and the proportionality test propagates the realized-effect
uncertainty by the delta method,

$$\operatorname{Var}(\hat\beta_i/\hat r_i) = \frac{\operatorname{Var}(\hat\beta_i)}{\hat r_i^{2}} + \frac{\hat\beta_i^{2}\operatorname{Var}(\hat r_i)}{\hat r_i^{4}},$$

rather than treating $\hat r_i$ as known. Omitting the second term would
overstate the test's precision, most severely for the asset with the shortest
realized sample.

A third point matters more than it might appear. The fitted slope estimates
$v^{we}-v^{wd}$ in *variance* units and therefore inherits each asset's
volatility level: Solana's implied weekday variance is 0.81 against Bitcoin's
0.44, so its slope is mechanically larger even if both markets applied an
identical proportional discount. Testing raw slopes would reject a uniform
convention on volatility-level differences alone. Both the implied and realized
quantities are therefore scaled by each asset's own mean variance, making the
slope the unit-free relative weekend effect $(v^{we}-v^{wd})/\bar v$ — the
quantity a quoting convention would hold fixed.

### Result: differentiation without calibration

9,067,876 trades over 6,605 asset-days:

| Asset | Implied slope | se | t | Realized | Implied / realized | se of ratio |
|---|---:|---:|---:|---:|---:|---:|
| BTC | −0.4012 | 0.0373 | −10.74 | −0.4720 | **0.850** | 0.178 |
| ETH | −0.3784 | 0.0421 | −8.99 | −0.4427 | **0.855** | 0.187 |
| SOL | −0.5003 | 0.0345 | −14.50 | −0.3802 | 1.316 | 0.418 |
| XRP | −0.5768 | 0.0671 | −8.60 | −0.4253 | 1.356 | 0.502 |

- **H0a, uniform convention** — implied slopes equal across assets:
  $\chi^2(3) = 10.47$, $p = 0.015$, **rejected**.
- **H0b, calibration** — slopes proportional to realized effects:
  $\chi^2(3) = 1.93$, $p = 0.586$, **not rejected**.

**The market is not applying one flat discount across underlyings.** Beyond that,
the pooled test is close to uninformative, and the fourth asset is what makes
this legible rather than what fixes it.

The reason is visible in the dispersion. Across the four assets the standard
deviation of implied weekend discounts is 0.0919 against 0.0384 for realized
ones — the market's quotes vary **2.4 times more** across assets than the weekend
risk they are pricing does. That is over-differentiation, not calibration, and it
is exactly the pattern the §5.1 gap column showed: the ratios fall into two
groups, 0.850 and 0.855 for Bitcoin and Ether against 1.316 and 1.356 for Solana
and XRP. §5.5 shows that grouping is largely an accident of the windows the four
books are averaged over, so it should be read as the spread it is and not as a
property of new listings.

H0b nonetheless fails to reject, and the reason is worth being explicit about
rather than reporting as support. The realized effects are bunched inside a span
of 0.092, so dividing by them is close to dividing all four slopes by the same
constant; the ratio test is then nearly the equality test, and it survives only
because the delta-method correction for realized-effect uncertainty inflates the
standard errors on the two short samples — 0.418 and 0.502, against 0.178 and
0.187 for the mature books. The gap between the two groups is 0.50 with a
standard error of roughly 0.53. It cannot be resolved at this sample size. A
non-rejection here means the data cannot tell, not that proportionality holds.

So the corrected cross-asset story is neither the flat convention of the first
draft nor the tidy calibration of the second. Options price roughly 85% of the
weekend effect in Bitcoin and Ether and roughly 130% of it in Solana and XRP,
and the pooled test can reject a common discount while lacking the power to
characterise what replaced it. The cross-section is also the wrong dimension in
which to look for the answer: §5.5 finds the movement is over time, not across
assets, and it is estimated there an order of magnitude more sharply.

**A retraction, and a partial reversal of its replacement.** An earlier version
of this section reported implied/realized ratios of 0.85, **2.42** and 1.32, a
cross-asset dispersion ratio of **40%**, and concluded that the market
"transmits only 40% of the cross-asset variation in weekend risk" —
under-differentiating between assets. Ether's 2.42 was an artefact of a corrupted
realized denominator (see the note at the head of this draft); corrected, it is
0.855, essentially Bitcoin's, and the under-differentiation finding does not
survive. The version that replaced it, written on three assets, read the
non-rejection of H0b as positive evidence of proportional calibration and stated
that "every implied/realized ratio is estimated more precisely than its own
magnitude, so unlike a weakly identified test this non-rejection carries
information." With a fourth asset the dispersion ratio is 239% rather than 40%,
and the reading above is the accurate one: the test rejects uniformity and is
too weak to establish what holds instead.

The interesting differentiation failure is not across assets but *within the
weekend* — see the Saturday result in §5.4, which replicates in all four books.

### 5.3 Robustness

| Specification | slope | t | n |
|---|---:|---:|---:|
| baseline | −0.1612 | −10.78 | 5,339,133 |
| maturity ≤ 3 days | −0.1620 | −7.95 | 3,110,034 |
| maturity 3–7 days | −0.1738 | −4.62 | 954,311 |
| maturity 7–14 days | −0.1624 | −0.93 | 1,274,788 |
| \|delta\| ∈ [0.45, 0.55] | −0.1612 | **−14.37** | 1,643,256 |
| excluding 2020 | −0.1687 | −11.07 | 5,016,312 |
| 2016–2020 | −0.0965 | −1.45 | 464,539 |
| 2021–2022 | −0.2015 | −3.84 | 1,273,429 |
| 2023–2024 | −0.1505 | −11.87 | 2,044,696 |
| 2025–2026 | −0.1620 | −9.13 | 1,556,469 |

The estimate is remarkably stable: every specification lands between −0.15 and
−0.20, against a baseline of −0.161. Maturity buckets agree almost exactly
(−0.162, −0.174, −0.162), the tightest at-the-money band reproduces the baseline
to four decimals with the highest precision in the table, and dropping 2020
changes nothing. Only the long-maturity bucket loses significance, which is
expected: weekend coverage barely varies once a contract has two weeks to run,
so there is little left to identify.

The early sample is attenuated but no longer perverse. The 2016–2020 slope is
−0.0965 (t = −1.45) — same sign as everything else, roughly 40% of the
full-sample magnitude, and insignificant. That is exactly the signature of an
era with almost no daily expiries: the share of newly listed instruments with
two days or less of life was 0.5–1.2% in 2018–2019 against 79% in 2020, so
there is little within-day variation in weekend coverage to identify $\beta$.
Estimates from 2021 onward, when the instrument structure supports the design,
are stable and strongly significant.

ETH, SOL and XRP, on the same specifications:

| Specification | ETH slope | t | SOL slope | t | XRP slope | t |
|---|---:|---:|---:|---:|---:|---:|
| baseline | −0.2461 | −8.90 | −0.3568 | −14.66 | −0.5513 | −7.97 |
| maturity ≤ 3 days | −0.2244 | −10.35 | −0.3931 | −9.61 | −0.6080 | −4.99 |
| maturity 3–7 days | −0.3438 | −6.94 | *+1.4129* | *0.69* | −0.6325 | −1.05 |
| maturity 7–14 days | −0.4954 | −1.32 | −0.4546 | −1.12 | −0.1006 | −0.16 |
| \|delta\| ∈ [0.45, 0.55] | −0.2427 | −10.14 | −0.3266 | −13.38 | −0.5128 | −5.45 |
| excluding 2020 | −0.2518 | −8.90 | — | — | — | — |
| 2021–2022 | −0.2954 | −3.48 | — | — | — | — |
| 2023–2024 | −0.2066 | −11.88 | −0.3550 | −10.02 | −0.8761 | −4.70 |
| 2025–2026 | −0.2724 | −15.46 | −0.3599 | −11.46 | −0.4025 | −9.21 |
| early sample | −0.0218 | −0.58 | — | — | — | — |

All three replicate the Bitcoin pattern: negative and strongly significant
throughout, stable across maturity buckets and moneyness bands, and attenuated
toward zero in the earliest window where daily expiries were sparse. The
long-maturity bucket is insignificant for every asset, as it must be when
weekend coverage barely varies.

Three entries deserve flagging rather than burying. Solana's 3–7 day bucket
returns +1.41 with $t = 0.69$ on 35,986 observations — an uninformative estimate
with an enormous standard error, not evidence of a sign flip; it is the one cell
in the table where the sample cannot support the specification. XRP's 3–7 day
and 7–14 day buckets are similarly uninformative, on 12,511 and 17,912 trades.
And Ether's early window (−0.0218, $t = -0.58$) rests on 104,197 trades from a
period with almost no daily expiries.

XRP's two dated windows deserve a second look for a different reason: its slope
falls from −0.876 in 2024 to −0.402 in 2025–2026, more than halving. Solana's is
flat across the same split and Ether's is not falling at all. Whatever is
attenuating XRP's weekend discount is specific to the newest book and moves in
the same direction as its trading-test decay in §6.

**The main sample should therefore begin in 2020.** The full-sample estimates
are, if anything, conservative.

### 5.4 Placebos and the day-of-week profile

A natural falsification is to ask whether implied variance responds to a *fake*
weekend. Entering the true weekend fraction alongside a placebo pair of weekdays
gives:

| Placebo pair | weekend slope | placebo slope | realized variance of the placebo pair |
|---|---:|---:|---:|
| Tue + Wed | −0.1725 (t −11.04) | −0.0246 (t −1.59) | 1.14 |
| Thu + Fri | −0.1418 (t −9.33) | +0.0424 (t +3.18) | 1.31 |
| Sun + Mon | −0.1480 (t −10.69) | −0.0377 (t −3.22) | 0.85 |

The true weekend fraction loads strongly negative in every race, and **each
placebo loads in the direction its own realized variance implies**: Tuesday–
Wednesday sits close to the weekly average (1.14) and is insignificant;
Thursday–Friday is the highest-variance pair (1.31) and loads *positive*;
Sunday–Monday is a low-variance pair (0.85) and loads negative. The market's
implied day structure agrees in sign with the realized day structure in all
three cases.

This is a pass, not a failure. Implied variance does not respond to an
arbitrary label — it responds to genuinely quiet or busy stretches of the
calendar, and the weekend is simply the quietest. Note that the day fractions
of a contract's life sum to one, so any two are mechanically collinear and a
two-way race identifies each coefficient only relative to the omitted
combination; the full profile below is the cleaner statement.

The correct specification estimates the whole profile at once. Writing total
variance as a weighted average across weekdays,

$$\sigma^2_{i,t} = \sum_{d} v_{d,t}\, f_{d,i,t}, \qquad \sum_d f_{d,i,t} = 1,$$

we enter the fraction of remaining life falling on each of six weekdays with the
seventh (Sunday) as reference, again with day fixed effects. The coefficients
trace the market's implied variance profile across the week, directly comparable
with the realized profile computed from five-minute returns. Regressing the
seven implied day effects on the seven realized ones, a fully calibrated market
gives a slope of one; a market applying a fixed convention gives a slope near
zero.

BTC, annualized variance relative to Sunday, 5,339,133 trades over 3,413 days:

| Day | Implied | t | Realized | Implied / realized |
|---|---:|---:|---:|---:|
| Mon | +0.1412 | 5.11 | +0.1718 | 0.82 |
| Tue | +0.1257 | 5.46 | +0.1547 | 0.81 |
| Wed | +0.1885 | 4.69 | +0.2097 | 0.90 |
| Thu | +0.1575 | 5.48 | +0.2175 | 0.72 |
| Fri | +0.2141 | 8.39 | +0.2416 | 0.89 |
| **Sat** | **+0.0042** | **0.14** | **−0.0325** | **−0.13** |
| Sun | ref | — | ref | — |

Every weekday coefficient is individually significant, and the implied profile
tracks the realized one closely: the correlation across the seven days is
**+0.983**, the regression slope **0.763**, and the market prices **78.1%** of
the realized day-of-week variance spread. This is a market that reads the
weekly calendar well.

**The exception is Saturday.** The market prices Saturday as indistinguishable
from Sunday (+0.004, t = 0.14) when Saturday is genuinely the quieter of the two
(−0.033). It resolves "the weekend" as a single block and stops there.

### The result replicates across all four assets

| | BTC | ETH | SOL | XRP |
|---|---:|---:|---:|---:|
| correlation, implied vs realized | **+0.983** | **+0.884** | **+0.890** | **+0.815** |
| slope (1.0 = fully calibrated) | 0.763 | 0.670 | 0.995 | 1.074 |
| share of realized spread priced | 78.1% | 76.9% | 103.1% | 139.2% |

Every asset shows the same thing: the market tracks its weekly variance profile
closely, with correlations between +0.82 and +0.98. The amplitudes, though, order
themselves the same way §5.1's gaps did — Bitcoin and Ether price 77–78% of the
realized weekly spread, Solana and XRP 103% and 139% of it. The newest and
thinnest book overshoots the weekly shape by the widest margin, and the
correlation column falls in the same order, so XRP's profile is both the most
amplified and the most loosely tracked. This is the same ordering seen a third
way rather than independent confirmation of it, and §5.5 shows what generates it:
these amplitudes are also full-sample averages over different windows, and the
window a book covers determines where on a decade-long trend its average sits.

**The Saturday exception replicates in all four.** In every asset the market
prices Saturday as indistinguishable from — or busier than — Sunday, when
Saturday is the quieter of the two:

| | implied Sat effect | realized Sat effect |
|---|---:|---:|
| BTC | +0.004 (t 0.14) | −0.033 |
| ETH | +0.074 (t 2.01) | −0.094 |
| SOL | −0.012 (t −0.18) | −0.075 |
| XRP | +0.158 (t 1.21) | −0.041 |

Four independent books resolve "the weekend" as a single undifferentiated block.
Not one of the four implied Saturday effects is significantly negative, while all
four realized effects are negative. That is the one place in the weekly profile
where the market's ranking is demonstrably wrong rather than merely compressed,
and it is the same place in all four — across two settlement conventions, a
decade of listing history, and a factor of thirty in trade count.

**And it is the one error the listing schedule protects.** The natural response
to a mispricing inside the weekend is to spread it: sell the Saturday-heavy
contract, buy the Sunday-heavy one. Both legs sit inside the weekend, so the
common weekend discount differences out and what is left is exactly the failure
to rank the two days. That trade cannot be put on. Expiries are daily at 08:00
UTC, so which weekday an option's remaining life falls on is fixed entirely by
its entry time and its expiry date; enumerating every hour of the week against
every expiry in the half-day-to-eight-day window gives not a sample of the menu
a desk faces but the whole of it:

| entry day | hours with any Sunday-heavy contract | hours offering **both** legs |
|---|---:|---:|
| Monday–Friday | **0 of 120** | **0 of 120** |
| Saturday | 17 of 24 | 7 of 24 |
| Sunday | 21 of 24 | 6 of 24 |

Thirteen hours out of 168, and a contract counts as tilted here only if its
Saturday and Sunday shares differ by 15% of their sum. Monday through Friday
nothing Sunday-heavy is listed at all: any contract reaching Sunday must pass
through Saturday to get there. The two legs coexist only on Saturday between
07:00 and 13:00 UTC and on Sunday between 15:00 and 20:00 — by which time the
Saturday being sold is already under way or finished.

So the market's one demonstrably wrong ranking of calendar time is also the one
its own contract calendar prevents anyone from arbitraging directly. That is a
more economical account of why this particular error survives than convention or
inventory, and unlike those it needs no quote-level data — it follows from the
expiry schedule alone. It also predicts that the error should be widest where no
offsetting contract exists, which is testable on this tape and left for future
work. The calculation is `weekend_params.sat_sun_availability` and its output is
`w59_sat_sun_availability.csv`.

**A retraction.** An earlier version of this section reported Ether's profile
correlation as +0.406 and concluded that Ether's realized day-of-week structure
was statistically indistinguishable from flat — zero of six days differing from
Sunday — and therefore that Ether was "genuinely the mildest and least
well-identified" of the three assets. That was entirely an artefact of the
corrupted bar series: 89 gap-spanning returns, inflating variance on scattered
days by up to 222x, flattened a real profile into noise. On the corrected series
Ether's realized profile is well defined and looks like the others. The
convenient explanation was wrong, and the anomaly it explained did not exist.

### 5.5 The split by vintage is a split by window

The sign pattern in §5.1's gap column is the most striking thing in the table:
positive in the two books listed before 2020, negative in the two listed in
2024, and the same division recurs in §5.2's ratios, in §5.4's profile
amplitudes and in §6's trading P&L. The natural reading is that a new book
inherits a quoting convention it has not yet recalibrated. There are two other
readings, and the data separates them.

The three candidates are **age** (young books price differently), **period**
(the two groups are measured over different stretches of calendar time) and
**liquidity** (they differ by a factor of thirty in trade count). Period is the
easiest to test, because Bitcoin and Ether are averaged over 2016–2026 while
Solana and XRP exist only from March 2024. Restricting every book to the window
all four share holds the period fixed and lets vintage vary:

| | full sample | 2020 onward | 2022 onward | matched (2024-03-12 →) |
|---|---:|---:|---:|---:|
| BTC | +0.052 | +0.095 | +0.039 | **+0.007** |
| ETH | +0.038 | +0.047 | −0.031 | **−0.073** |
| SOL | −0.094 | −0.094 | −0.094 | **−0.111** |
| XRP | −0.132 | −0.132 | −0.132 | **−0.132** |

**Half the split is gone in matched calendar time**, and what remains is not a
split but a gradient: Bitcoin at zero and the other three negative. Ether, one of
the two "mature" books, over-discounts the weekend in the common window exactly
as the 2024 listings do. Formally, the mature-minus-young contrast in relative
weekend effect falls from +0.206 (t = 1.62) on the full sample to +0.108
(t = 1.22) on the matched window, and a joint test that all four gaps are equal
never rejects — p = 0.45, 0.25 and 0.34 on the full, 2020-onward and matched
windows. Both sides carry their uncertainty here: the implied slopes come from
one stacked regression clustered on asset-day, so the four are jointly
distributed rather than four independent estimates, and the realized effects are
block-bootstrapped over whole weeks resampled *in common* across assets, which
preserves the correlation that makes crypto move together.

The age test cannot be run in the other direction, and the reason is worth
recording rather than working around. Running each book over its own first two
and a half years gives Bitcoin an implied weekend ratio of 2.08 and Ether 0.97 —
a market pricing the weekend as *riskier* than a weekday, which is not a finding
but an unidentified regression. Before 2020 Deribit did not list daily expiries,
so contracts quoted on the same day shared nearly the same weekend exposure. The
within-day standard deviation of the weekend fraction is the identifying
variation itself:

| | 2017 | 2018 | 2019 | 2020 | 2021 | 2023 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 0.044 | 0.066 | 0.083 | 0.171 | 0.170 | 0.177 | 0.179 |
| ETH | — | — | 0.084 | 0.168 | 0.178 | 0.177 | 0.181 |
| SOL | — | — | — | — | — | — | 0.166 |
| XRP | — | — | — | — | — | — | 0.160 |

The identifying variation roughly doubles when daily expiries arrive and is
stable thereafter. The 2024 books have it from listing, so they are not the
disadvantaged ones here — the mature books' own youth is what cannot be measured.

#### What is actually happening

Setting the cross-section aside and looking at each book year by year resolves
it. The implied weekend discount has deepened steadily and enormously since 2020:

![**Figure 8. The market has been learning the weekend clock.** Implied weekend
effect by year, scaled by each asset's own implied variance level so that the
years are comparable, with 95% confidence intervals. The shaded band is the
range of the four books' realized weekend effects over their full samples. The
mature books begin at zero — pricing no weekend effect at all — cross the
realized band in 2022, and end below it. The 2024 listings enter where the
mature books already were.](output/figures/w_f8_trajectory.png){width=85%}

Implied weekend/weekday variance ratio, by year:

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 0.91 | 0.93 | 0.48 | 0.58 | 0.51 | 0.42 | 0.30 |
| ETH | 1.00 | 0.95 | 0.55 | 0.58 | 0.45 | 0.49 | 0.47 |
| SOL | — | — | — | — | 0.60 | 0.53 | 0.58 |
| XRP | — | — | — | — | 0.45 | 0.52 | 0.62 |

In 2020 Bitcoin and Ether priced a weekend variance ratio of 0.91 and 1.00 — that
is, essentially no weekend discount at all — against realized ratios of 0.52 and
0.70 in the same year. By 2026 they price 0.30 and 0.47. Weighting each year by its own precision, the
implied relative weekend effect falls by **0.144 per year in Bitcoin (t = −12.5)
and 0.117 in Ether (t = −10.5)**, while the realized weekend ratio over the same
years, measured as this paper measures it everywhere else — mean weekend variance
over mean weekday variance — has no significant trend at all (t = −1.25 and
−1.09).

That contrast looks like a market walking away from a benchmark standing still,
and an earlier draft read it that way. It is not. The benchmark is a ratio of
two means of a violently right-skewed series, fitted a year at a time, and it
has almost no power: §5.6 shows that trimming the top *one per cent* of days
from each day type turns it into a trend at t = −4.9, and that the market has
been tracking a real decline all along. The trend measured here is the fact.
What it is a response to belongs to the next subsection.

That trend is not a change in the product being quoted. Holding the maturity band
fixed reproduces it: −0.175 per year for Bitcoin and −0.159 for Ether among
contracts with three days or less to expiry (t = −13.4 and −10.8), and negative
in every band tested.

**So the split by vintage is an artefact of averaging over different legs of one
common path.** Bitcoin and Ether's full-sample gaps average in 2020 and 2021,
when the market under-discounted the weekend badly, which pulls their averages
positive. Solana and XRP have only the last leg, by which time the market had
already crossed the realized level and gone past it. In 2024–2026 all four books
quote implied ratios in the same 0.30–0.62 band with no ordering by vintage at
all; XRP, the newest, has been *raising* its ratio, 0.45 to 0.62.

It also explains §6. The spread trade there sells weekend-heavy
variance and profits when the market under-discounts the weekend, which is the
condition that held until roughly 2022 and has not held since. The decaying
profitability §6 measures and the deepening discount measured here are the same
phenomenon seen from two directions.

What survives, and is not explained here, is the residual gradient in the matched
window: Bitcoin at 0.007, Ether at −0.073, Solana at −0.111, XRP at −0.132, in
exact order of trade count. Four assets cannot separate size from listing date —
they are perfectly confounded across this cross-section — and the natural place
to look for a tiebreak, §7's finding that thinly traded far wings discount the
weekend harder than at-the-money contracts of the same book on the same day,
turns out not to be one. That gradient is a property of the moneyness metric the
smile is quoted in rather than of how thinly a contract trades (§7), so it says
nothing about whether a thin *book* prices differently from a thick one. The
residual gradient stays open.

### 5.6 What the market is tracking

The trend just measured is a puzzle only because of the thing it is measured
against. The implied weekend discount has deepened for six years; the realized
weekend ratio, tested as a ratio of mean weekend variance to mean weekday
variance, has a trend of t = −1.25 and −1.09 and was read as flat. A market
walking away from its own benchmark and not stopping when it gets there needs a
cause outside the data — a convention, a hedging cost, a client base that always
sells the weekend — and none of those can be tested on a public trade tape.

The benchmark is the problem. Daily realized variance is violently
right-skewed, and each year's mean is set by a handful of days. Fitting a line
to seven such ratios is an underpowered test, and an underpowered test returning
nothing was read as the data returning nothing.

**Trimming the top one per cent of days reverses the conclusion.** Cutting the
same small share off the top of *each* day type within each year — so the trim
itself carries no weekend effect — and re-estimating the trend in the ratio of
means gives:

| share trimmed | 0% | 1% | 2% | 5% | 10% | 25% | 50% |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | −0.062 (−1.2) | **−0.132 (−4.9)** | −0.125 (−5.3) | −0.126 (−6.6) | −0.135 (−7.1) | −0.160 (−9.6) | −0.186 (−11.2) |
| ETH | −0.037 (−1.0) | **−0.077 (−3.5)** | −0.082 (−3.5) | −0.088 (−4.2) | −0.094 (−6.1) | −0.113 (−8.8) | −0.123 (−11.4) |

Trends are in log points a year with *t*-statistics beside them, estimated with
a fixed effect for every month, so the volatility cycle is absorbed entirely and
a weekend day is only ever compared against weekday days that sit beside it.
One per cent of days is about three weekend days a year. Removing them takes
Bitcoin from a trend that cannot be distinguished from zero to one at t = −4.9,
and the estimate then barely moves as the trim deepens all the way to the
median. Solana and XRP show nothing at any trim, which is the first sign that
whatever this is, it is not universal.

So the flatness of the benchmark is bought entirely in the extreme right tail.
Everywhere else in the distribution the weekend has been getting quieter
relative to the weekday, steadily, for six years.

**At the centre of the distribution the decline is unmistakable.** Estimating
the same monthly within-period contrast on log variance rather than on variance
gives the ratio of geometric means, which is where the centre of a right-skewed
distribution sits:

| | ratio at mid-sample | per year | *t* | 2020 → 2026 |
|---|---:|---:|---:|---|
| BTC arithmetic | 0.494 | −0.062 | −1.19 | 0.606 → 0.402 |
| BTC **geometric** | 0.437 | **−0.136** | **−7.54** | 0.685 → 0.279 |
| ETH arithmetic | 0.564 | −0.037 | −0.97 | 0.637 → 0.499 |
| ETH **geometric** | 0.532 | **−0.098** | **−6.25** | 0.736 → 0.384 |
| SOL geometric | 0.526 | +0.007 | +0.09 | 0.522 → 0.530 |
| XRP geometric | 0.517 | +0.017 | +0.17 | 0.507 → 0.528 |

The typical Bitcoin weekend has gone from carrying 69% of a typical weekday's
variance to 28% of it. The mean has barely moved. Both statements are about
the same days.

![**Figure 10. The market is tracking the centre of the distribution.** Left:
the trend in the weekend variance ratio, in log points a year with 95%
intervals — as the market quotes it, and as the realized series delivers it
measured at the centre of the daily variance distribution and at its mean. In
Bitcoin and Ether the quoted trend sits on the centre's and clear of the mean's;
in Solana and XRP nothing is estimated precisely enough to say anything, and the
intervals show it. Right: the same trend in the ratio of means as the top of
each day type is trimmed away within each year. At no trim it is the flat line
§5.5 read as a market drifting away from its
benchmark.](output/figures/w_f10_learning.png){width=100%}

#### It is not stale prices

A weekend that looks quiet because its prices stopped updating would produce
exactly this pattern and none of the economics: staleness depresses measured
variance on the ordinary days, where moves are small enough to be lost, and
leaves the violent ones alone. It is the one alternative that has to be
eliminated before any of the above is safe, and it is eliminated by the
sampling interval. Microstructure noise is a fine-grid phenomenon; at two-hour
spacing a price that failed to print for five minutes has long since caught up.
Re-estimating the geometric trend at coarser and coarser intervals:

| | 5 min | 15 min | 30 min | 60 min | 120 min |
|---|---:|---:|---:|---:|---:|
| BTC | −0.136 (−7.5) | −0.137 (−6.7) | −0.158 (−7.5) | −0.167 (−7.4) | **−0.193 (−7.8)** |
| ETH | −0.098 (−6.3) | −0.103 (−6.1) | −0.126 (−7.5) | −0.138 (−7.7) | **−0.160 (−7.7)** |

**The trend gets stronger as the interval coarsens, which is the opposite of
what a measurement artefact does.** The pattern it does match is a real trend
seen through noise. Observation error adds roughly the same amount to every
day's measured variance whatever the day type, so it pushes a measured ratio
toward one — and pushes harder the further the truth is from one. As the true
ratio falls, that bias grows with it and flattens the measured trend. Coarsening
the interval removes the noise and the attenuation with it. The levels carry the
same signature: Bitcoin's geometric ratio falls from 0.437 at five minutes to
0.346 at two hours. `tests/test_learning.py` simulates both cases — a real
trend seen through constant noise, and a flat truth seen through *shrinking*
noise, which is what improving weekend liquidity would look like — and confirms
that the ladder separates them, sloping the observed way in the first case and
the opposite way in the second.

The direct evidence agrees. The share of five-minute returns that repeat the
previous price — the diagnostic that condemned PAXG in §7 — has no upward drift
in either mature book, running 5.3%, 0.4%, 2.9%, 7.4%, 1.6%, 2.3%, 2.3% on
Bitcoin weekends from 2020 to 2026 against 3.6%, 0.3%, 1.2%, 2.1%, 0.4%, 0.6%,
0.7% on its weekdays. The weekend is staler than the weekday throughout and no
more so at the end than at the beginning.

The same ladder rescues the arithmetic benchmark too, though less dramatically:
Bitcoin's untrimmed trend goes from −0.062 (t = −1.19) at five minutes to
−0.105 (t = −3.35) at sixty. **Even on its own terms, the paper's original
benchmark is not flat once microstructure noise is taken out of it.** The claim
in §5.5 that "the thing it is pricing is not moving" was wrong, and it was wrong
for two compounding reasons: an estimator with no power, applied to a series
measured on a grid fine enough to attenuate what power it had.

#### Which of the two is the market pricing?

Both realized measures are now falling, so the question is no longer whether the
market is responding to something but which something. Fitting the implied
ratio quarter by quarter and putting it in the same log units:

| | periods | per year | *t* |
|---|---:|---:|---:|
| BTC | 27 | −0.186 | −10.43 |
| ETH | 27 | −0.149 | −10.46 |
| SOL | 10 | −0.186 | −2.38 |
| XRP | 9 | −0.088 | −0.91 |

and differencing against the realized trend at each sampling interval gives the
comparison the whole section has been building toward. Entries are the
*t*-statistic on implied trend minus realized trend, so zero means the market is
moving at exactly the speed of the benchmark:

| | 5 min | 15 min | 30 min | 60 min | 120 min |
|---|---:|---:|---:|---:|---:|
| BTC vs arithmetic | −2.3 | −2.0 | −2.0 | −2.3 | −1.6 |
| BTC vs **geometric** | −2.0 | −1.8 | −1.0 | −0.7 | **+0.2** |
| ETH vs arithmetic | −2.8 | −2.3 | −2.1 | −2.4 | −1.5 |
| ETH vs **geometric** | −2.4 | −2.1 | −1.0 | −0.5 | **+0.4** |

**The implied trend converges on the geometric trend and never on the
arithmetic one.** Against the centre of the distribution the gap closes
monotonically as the noise comes out of the benchmark and vanishes at the
coarsest sampling; against the mean it sits at two standard errors throughout
and closes only where power runs out. Bitcoin's market has been deepening its
weekend discount at 0.186 log points a year while the typical weekend got
quieter at 0.193, and while mean weekend variance fell at 0.105.

A backward-looking level test says the same thing in a different way. Regressing
each quarter's log implied ratio on the *previous* quarter's realized ratio with
asset fixed effects — which is what calibrating to recent history means —
gives a slope of 0.71 on the geometric ratio and 0.27 on the arithmetic one.
Both are attenuated, because both regressors are estimates: correcting each by
its own sampling variance lifts the geometric slope to 1.15 (s.e. 0.22) and the
arithmetic one to 0.48 (s.e. 0.04). The correction is large — reliability is
0.61 on the geometric regressor and 0.57 on the arithmetic one — so the
corrected levels carry more model than the raw ones and only the ranking should
be read off them. The ranking is the same one the trends give: the market's
quotes move roughly one-for-one with where the weekend's variance usually sits,
and about half as much with where its mean sits.

#### The answer, and what it costs the market

The market is not drifting away from the data. It is tracking the data. It is
tracking the statistic a volatility trader would take off a screen — what a
weekend usually looks like — and an option does not pay off on what a weekend
usually looks like. It pays off on expected total variance, which is an
arithmetic mean, and §7 has already established that no proportional risk
premium can move a variance *ratio*, so the distinction between measures does
not rescue the market here.

That is a systematic error, and its size is the distance between the two
statistics. Measured as `log mean − mean log`, which is a scale-free index of
right-tail weight, the weekend's excess over the weekday's runs:

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | −0.23 | −0.00 | +0.08 | +0.19 | +0.16 | +0.14 | +0.31 |
| ETH | −0.07 | −0.14 | +0.07 | +0.10 | +0.08 | +0.17 | +0.27 |

At the start of the sample the weekend's variance distribution was no more
tail-heavy than the weekday's. Since 2022 it has been, and increasingly so. The
weekend has not simply gone quiet; it has become *lumpier* — ordinary weekends
much quieter, rare weekends no less violent. This is §7's fat-tail finding seen
from the other side, and it is the reason the two benchmarks disagree at all: a
market that watches the middle of the distribution will mark the weekend down
faster than the mean falls, by exactly the amount the tail is growing.

Three things follow, and they should be kept separate.

*   **The trend is explained.** It is a response to a real and precisely
    measurable decline, at a rate that matches it. Nothing about convention,
    inventory or hedging cost is needed, and §5.5's appeal to them is withdrawn.

*   **The overshoot is explained, and it is the same fact.** Section 5.1's
    residual gap and §6's decaying trade are both consequences of pricing the
    centre of a distribution whose mean sits above it and is pulling away.

*   **Why market makers use the centre is not explained.** Robust estimation of
    a right-skewed quantity is ordinary practice and defensible on its own
    terms; it is simply the wrong practice for this quantity. Whether it is
    deliberate robustness, a fitted model with a thin-tailed error, or nobody
    looking, the trade tape cannot say.

Two limits on the cross-section, stated rather than buried. Solana and XRP show
no trend on either side, which is consistent, but their standard errors are
three to thirteen times the mature books' and their implied trends rest on nine
or ten quarters; no difference test rejects anything for either, so they neither
confirm the mechanism nor contradict it. And the comparison of trends treats
the option side and the bar side as independent when a volatile week moves both.
The dependence is positive, which makes the reported standard errors
conservative for the null being entertained — that the two trends are equal —
and anti-conservative for the null that they differ.

## 6. The wedge is measurable, and has never been harvestable

The natural objection to a systematic pricing error is that it should be
arbitraged away. Here the answer is more specific and more interesting than
that: the error is real, a trade isolates it cleanly, and the venue's fee
schedule has always cost more than the trade earns. The fact is worth stating in
this paper for two reasons — a P&L that tracks the measured gap is the strongest
available validation of the measurement chain, and the size of the toll bears
directly on how the residual gap of §5.1 should be read. The full treatment —
seven trade constructions, the entry and exit conditions, the Greek attribution,
the maker economics and the commercial arithmetic — is the companion paper, *The
Half-Life of a Pricing Error*, cited here as Paper II.

The trade that isolates the effect is a vega-matched calendar spread: sell the
weekend-heavy contract, buy the weekday-heavy one, delta-hedge both in the
perpetual, hold to settlement. Costs are measured rather than assumed — Deribit's
0.03% option fee capped at 12.5% of premium, 0.05% taker on every perpetual
rebalance, and an effective half-spread of 0.42 volatility points recovered from
the tape by differencing buyer-paid against seller-received implied volatility on
the same instrument-day.

**The gross P&L tracks the pricing gap across all four books.** Bitcoin's spread
earns +0.023 per unit vega gross over 1,231 paired days and Ether's +0.021, while
Solana's is −0.000 and XRP's −0.025. Ordering the four assets by the size of
their measured pricing gap orders them by gross trading P&L as well, without
exception. A gap that did not show up in a hedged position at all would be a gap
one should suspect of being an artefact of the estimator; this one shows up, in
the right order, across two settlement conventions.

**And it has never covered its costs.** At daily rehedging — the cheapest of the
four frequencies tested, and the most favourable — Bitcoin's gross edge of 0.042
per unit vega meets 0.058 of exchange and hedging fees plus 0.008 of spread
crossing, for a net of **−0.025 (t = −2.09)**; Ether is **−0.029**. The signal is
real and it is smaller than the toll. Stripping the construction back to a single
outright short, where the spread arithmetic cannot arise — entered at Friday noon
and closed at the first instant after Saturday ends — earns +0.043 per unit vega
over the full history at hourly rehedging and **−0.001 (t = −0.12) over the last
two years**. Paper II §12 prices the one configuration that does clear zero: a
market maker earning the half-spread on both legs rather than paying it, on a fee
tier discounting option fees by 27%, at roughly +0.022 per unit vega on full-
history data — and about −0.013 over the last twelve months.

**The two findings are consistent, and the second supports the first.** The
quote-side discount measured in §5.5 has gone on deepening throughout a period in
which no crossing strategy ever paid. A desk that prices the weekend clock
correctly improves its marks on inventory it holds anyway — at no crossing cost,
no hedging bill and no capacity limit — and would leave the quoted gap largely
intact while making the error unavailable to anyone who has to cross to reach it.
That is an inference rather than a measurement, and Paper II states it as one.
What can be said from the data here is narrower and sufficient: **the pricing
error this paper documents cannot be harvested by the trade that documents it,
and the obstacle is the fee schedule rather than the market.**

**A correction.** An earlier version of this section reported the spread at
+0.039 per unit vega with a Sharpe of 1.50, and read a subsequent inversion off
the same series. Both figures came from a spread assembled as
`net_weekend − net_weekday`, where each leg is the P&L of a *short* contract with
its costs already subtracted; negating the second leg turned its costs into a
credit, overstating the result by exactly twice the long leg's cost — 0.064 at
daily rehedging against a reported 0.039. The corrected figures are the ones
above. Paper II also reports a look-ahead condition found in its own trading
engine, which had roughly doubled a different headline result. Both are
documented in `docs/data_notes.md`. **Nothing in §§1–5 or §7 of this paper
depends on that engine**, and the gross rank-ordering result above survives the
correction because it never used the net figures.

## 7. Racing the risk-based explanation

Everything so far compares an implied quantity with a realized one, and the
obvious objection is that they are measured under different probability measures.
Options are priced under the risk-neutral measure; realized variance is a
physical-measure quantity. A market that prices the weekend at more than its
realized weekend variance is not necessarily wrong — it may be charging for a
risk that realized variance does not capture. This section prices that risk
explicitly and asks how much of the gap survives.

### What a risk premium would have to look like

Begin with a restriction that eliminates most candidate stories at once. The
headline compares a *ratio* — implied weekend variance over implied weekday
variance, against the same ratio realized — and a risk premium applied
proportionally to all calendar time cancels out of a ratio exactly. If a dealer
marks up every unit of variance by the same factor, weekend and weekday
variance both rise by that factor and the ratio does not move. Verified rather
than asserted: rescaling both regimes by a common factor moves the priced
weekend ratio by at most 2 × 10⁻¹⁶ in these data.

So the aggregate variance risk premium, however large, cannot explain the gap.
Only a premium that loads *differently* on weekend time than on weekday time
can. That is a much narrower target, and there is one natural candidate for it.

### Weekend returns have fatter tails

Standardizing each regime by its own volatility — so the comparison is about
shape, not scale — weekend returns carry consistently fatter tails in all four
assets:

| | P(\|z\| > 5), weekday → weekend | P(\|z\| > 8), weekday → weekend | Skew, weekday → weekend |
|---|---|---|---|
| BTC | 38.4 → **44.2** bp (×1.15) | 10.8 → **11.8** bp (×1.10) | −0.69 → −1.25 (×1.82) |
| ETH | 36.8 → **42.5** bp (×1.15) | 9.2 → **10.3** bp (×1.13) | −1.25 → −1.22 (×0.98) |
| SOL | 25.9 → **31.5** bp (×1.22) | 5.7 → **9.7** bp (×1.70) | −0.18 → −1.47 (×8.0) |
| XRP | 32.6 → **41.7** bp (×1.28) | 8.1 → **10.7** bp (×1.33) | −4.83 → −1.74 (×0.36) |

**The tail excess replicates.** Every asset shows 15–28% more mass beyond five
standard deviations at the weekend and 10–70% more beyond eight, after removing
the volatility difference. Thin weekend liquidity, and the absence of a
traditional market to hedge into, plausibly command a premium that average
realized variance does not capture. That is a genuine weekend-specific risk, of
exactly the kind the previous subsection said the explanation would have to be,
and it is the horse the rest of this section races.

**The skew asymmetry does not replicate, and with a fourth asset it fails in
both directions.** Bitcoin's weekend returns are 1.8 times more negatively skewed
than its weekdays and Solana's eight times; Ether's are identical; XRP's are
*less* skewed at the weekend than on weekdays, its weekday figure of −4.83 being
the most extreme in the table and driven by a handful of crash bars. Two of four
now move the wrong way. The race below therefore runs on tail mass, which is
consistent across all four, and not on skew.

The reference asset needs its own caveat and is excluded from what follows.
PAXG's weekend tail ratio is ×1.01 at five standard deviations and ×1.53 at
eight, with skew moving from +0.25 to −7.18 — but gold reopens at 22:00 on
Sunday, so its reopening gap falls inside the weekend bucket and mechanically
produces both the eight-sigma excess and the skew. Its perpetual is also stale
enough at five-minute sampling that these figures cannot be read as distributional
statistics at all: 78% of its weekday closes and 88% of its weekend closes repeat
the previous one. Reported so it is not mistaken for evidence either way.

*(Statistics recomputed on the corrected bar series and now produced by
`scripts/weekend_tails.py` rather than by hand; an earlier version reported Ether
skew figures of −22.0 and −4.4, which were artefacts of gap-spanning returns.)*

### Pricing weekend jump risk explicitly

Fatter weekend tails are not yet an explanation; they are a quantity that has to
be put a price on. Split realized variance in each regime into a continuous part
and a jump part, and let the risk-neutral measure price jump variance at a
multiple κ ≥ 1 of its physical value. The variance a dealer would charge for a
day of type *g* is then

$$v^*_g(\kappa) = c_g + \kappa\,j_g$$

and the weekend ratio such a dealer would quote is

$$R^*(\kappa) = \frac{c_{we} + \kappa\,j_{we}}{c_{wd} + \kappa\,j_{wd}}.$$

At κ = 1 this is the realized ratio and the comparison is the headline one. As κ
grows the jump terms dominate and $R^*$ converges to the **jump-variance ratio**
$j_{we}/j_{wd}$. Because $R^*$ is monotone in κ, that limit is a *bound*: no jump-risk
premium of any size prices the weekend past it. An implied ratio outside the
interval between the realized ratio and the jump ratio cannot be produced by
jump compensation at all, whatever the premium. Where the implied ratio does lie
inside, inverting $R^*$ gives the premium the market would have to be charging,
which can be judged against what the literature estimates elsewhere.

The split uses truncated realized variance: five-minute returns above three
local standard deviations are jumps, with the local scale taken from the same
day's bipower variation so a quieter weekend is not mechanically classified as
jump-free, and with an intraday seasonality factor estimated separately for each
regime from within-slot medians. Truncation at three standard deviations
misclassifies roughly 0.3% of ordinary returns by construction; that bias applies
to both regimes and so largely cancels in the ratio, and the truncation level is
varied below. The measured jump shares are not that floor: run on a simulated
pure diffusion of the same length and sampling frequency, the same estimator
returns a jump share under 5%, against the 24% to 36% these series produce.

| | jump share, wd | jump share, we | continuous ratio | **jump ratio** | realized | implied |
|---|---|---|---|---|---|---|
| BTC | 0.353 | 0.378 | 0.561 | **0.626** | 0.584 | 0.635 |
| ETH | 0.320 | 0.308 | 0.618 | **0.583** | 0.607 | 0.645 |
| SOL | 0.240 | 0.286 | 0.616 | **0.783** | 0.656 | 0.558 |
| XRP | 0.358 | 0.369 | 0.613 | **0.642** | 0.623 | 0.488 |

Two of the four have a jump ratio above their realized ratio, so for those a
jump premium moves the priced weekend ratio *up*, toward the market's quote in
Bitcoin's case and away from it in Solana's. Ether's jump ratio is *below* its
realized ratio, so for Ether a jump premium moves the priced ratio in the wrong
direction from the start.

### How much of the gap survives

![**Figure 6. What a jump-risk premium can and cannot price.** The bar spans
every weekend ratio reachable by pricing jump variance at any multiple of its
physical value: it starts at the realized ratio and ends at the jump-variance
ratio, the limit as the premium grows without bound. The diamond is the market's
quote with its 95% confidence interval. In all four books the diamond lies
outside the bar, and in Solana and XRP it lies on the opposite side from the
direction a premium moves the price.](output/figures/w_f6_horse_race.png){width=85%}

Residual gap — implied minus what a market pricing jump variance at κ times its
physical value would quote:

| | κ = 1 | κ = 2 | κ = 3 | κ = 5 | κ = 10 | bound (κ → ∞) | reachable? |
|---|---|---|---|---|---|---|---|
| BTC | +0.051 | +0.040 | +0.034 | +0.027 | +0.019 | **+0.009** | no |
| ETH | +0.039 | +0.044 | +0.048 | +0.052 | +0.056 | **+0.039** | no |
| SOL | −0.098 | −0.122 | −0.139 | −0.160 | −0.184 | **−0.098** | no |
| XRP | −0.136 | −0.141 | −0.144 | −0.147 | −0.150 | **−0.136** | no |

**Jump compensation cannot account for the gap in any of the four books, and it
fails in three distinct ways.** Bitcoin is the near miss: a premium does push its
priced weekend ratio toward the quoted one, but the whole path from κ = 1 to the
bound closes only 82% of a gap of 0.051, and it takes an unbounded premium to get
that far. Ether fails on direction — its weekend is *less* jump-intensive than
its weekdays, so every increase in κ widens the gap, from +0.039 at the physical
measure to +0.056 at ten times it. Solana and XRP fail on sign: their quotes sit
*below* their realized ratios, while a jump premium can only push a priced ratio
up. For those two not even κ = 0 works — pricing weekend jump variance at *zero*
still leaves the continuous ratio at 0.616 and 0.613 against quotes of 0.558 and
0.488. Closing their gaps needs a negative price of jump risk, which is to say a
market that pays to hold it.

Sampling uncertainty does not rescue the story either, though it does soften the
verdict for any single asset. Block-bootstrapping whole weeks and redrawing the
implied ratio from its own sampling distribution, the probability that a jump
premium of some size could reach the market's quote is 0.27 for Bitcoin, 0.13 for
Ether, 0.10 for Solana and 0.11 for XRP. No single one of those rejects at
conventional levels. What is decisive is that the failure repeats in four books
and that it requires *opposite-signed* premia in the two pairs: a large positive
price of weekend jump risk in the mature books and a negative one in the books
listed in 2024. No single risk premium does both.

**Robustness.** Across 44 estimator settings — truncation at 2.5, 3, 4 and 5
local standard deviations, with and without the intraday factor, and at 15-, 30-
and 60-minute sampling — the implied ratio is reachable in 8. Five of those are
Bitcoin, and four of the five require jump variance priced at 12 to 55 times its
physical value; equity-index estimates of the jump-variance premium are a small
single-digit multiple. Ether is reachable in one setting of eleven, Solana in
none, XRP in two, both of which need premia of 24 and 136.

### The ordering runs backwards

Risk compensation makes a cross-sectional prediction as well as a level one: the
book whose weekend carries relatively more jump risk should be the one whose
weekend is priced richest against its own realized variance. Sorting the four by
jump ratio gives ETH (0.583), BTC (0.626), XRP (0.642), SOL (0.783), and their
pricing gaps in that order are +0.039, +0.051, −0.136, −0.098. The rank
correlation is −0.60. Four points cannot test an ordering — they can only fail to
support one — but Solana is the sharpest single case: it has by some distance the
most weekend-concentrated jump risk of the four and the market discounts its
weekend the second-hardest.

### The smile test

The realized side has now been asked what a jump premium could do. The option
side can be asked the same question directly, and it gives a sharper answer,
because jump risk is not priced uniformly across an option surface. It is priced
in the wings. An at-the-money option is mostly a bet on diffusive variance; a far
out-of-the-money one pays off almost only in a jump, which is why the smile
exists at all. So if the market's weekend discount is small because it is
withholding a discount as compensation for weekend jump risk, that withholding
has to be concentrated away from the money — the weekend discount must *shrink*
toward the wings. If instead the discount is a property of the calendar, it is a
property of the clock rather than of the tail, and it should be flat across the
smile.

The headline sample is re-run on the full quoted range rather than the
|delta| ∈ [0.30, 0.70] band, in four buckets of distance from the money,
min(|delta|, 1 − |delta|), which puts both wings of the smile together and both
at-the-money sides together. Every coefficient is bucket-specific, so each
bucket carries its own maturity profile — the smile is steeper at short
maturities, and forcing one profile across all four would push that into the
coefficient being compared. Implied weekend/weekday variance ratios:

| | far wing | wing | near | at the money | n |
|---|---|---|---|---|---|
| BTC | **0.528** | 0.609 | 0.639 | 0.630 | 13.6m |
| ETH | **0.542** | 0.615 | 0.645 | 0.639 | 9.2m |
| SOL | **0.452** | 0.647 | 0.558 | 0.560 | 423k |
| XRP | **0.364** | 0.498 | 0.496 | 0.492 | 135k |

![**Figure 7. The weekend discount across the smile.** Implied weekend/weekday
variance ratio by distance from the money, with 95% confidence intervals. Jump
risk is priced in the wings, so weekend jump compensation would raise the
left-hand end of each line. Every line runs the other
way.](output/figures/w_f7_smile.png){width=85%}

**The wings discount the weekend harder, in every book.** The far wing prices
weekend variance 0.10 to 0.13 lower than the money in all four, and the
at-the-money estimates reproduce the headline specification almost exactly
(Bitcoin's 0.630 against 0.635, Ether's 0.639 against 0.645), which is the
consistency check that the widened sample has not changed the object being
measured.

Fitted jointly so that the difference between two buckets carries a covariance,
the far-wing-minus-at-the-money contrast in relative weekend effect is −0.121
(t = −4.15) for Bitcoin, −0.118 (t = −4.95) for Ether, −0.128 (t = −1.04) for
Solana and −0.173 (t = −1.52) for XRP. Equality of the discount across the smile
is rejected outright in the two large books — χ²(3) = 18.4 and 28.4, both
p < 0.001 — and not rejected in the two small ones, where p is 0.125 and 0.483
and the far-wing bucket holds 67,000 and 18,000 trades against Bitcoin's 3.1
million. All four point estimates are negative and of similar size, so what
separates the books here is precision rather than sign.

That is the opposite of the jump-compensation prediction, and it says something
slightly stronger than "no compensation". The part of the surface that pays off
in jumps is where the market marks the weekend down *most* — it prices the
weekend as tail-quieter, not merely as quieter. The realized data says the
reverse: standardized for scale, weekend returns carry 15% to 28% more mass
beyond five standard deviations.

Two caveats. Implied volatilities are noisiest in the far wing, but that is
measurement error in the dependent variable, which widens the confidence
intervals without moving the slope, and those intervals are the ones drawn in
Figure 7. And Solana's ordering is not monotone — its "wing" bucket sits above
its "near" and at-the-money buckets — so the pattern in that book is a far-wing
effect rather than a gradient, which is also why its equality test does not
reject.

What the smile test cannot do is say what the wings are doing instead. It rules
out the premium loading where the risk is, which is the prediction the
risk-based reading makes. The next subsection takes the question up, and the
answer changes what the finding is.

### What the wings are actually doing

A smile is written in a moneyness metric, and the weekend clock moves the
metric. That is the whole of what follows. Write the total variance to expiry as
$V(w)$, falling in the weekend fraction, and the quoted surface as

$$\mathrm{iv}^2(x) = \frac{V}{T}\,G\!\left(x\,/\,V^{(1-\theta)/2}\right)$$

with $x$ log-moneyness and $G$ the smile shape. The one free parameter says what
the market's moneyness metric is pinned to.

At $\theta = 0$ the smile is a function of standardized moneyness. A contract
spanning a weekend carries less variance, so a fixed strike sits further out in
standard deviations and earns a *larger* relative wing markup, which partly
offsets the fall in its level. At fixed delta the relative weekend effect is then
identical at every delta, and there is no wing effect at all.

At $\theta = 1$ the relative smile is pinned to the strike. The markup does not
grow when the clock shortens, so at fixed delta a weekend-heavy contract sits at
a smaller absolute moneyness, collects a smaller markup, and its squared implied
vol falls by more than its level does. The wing effect appears — and its size is
not free. Writing $\eta$ for the smile's elasticity in the wing, the far wing's
relative weekend slope exceeds the at-the-money one by

$$A(\theta) = \frac{1 - \eta(1-\theta)/2}{1 - \eta/2},$$

which is one at $\theta = 0$ and reaches a **ceiling** of $1/(1-\eta/2)$ at
$\theta = 1$. Nothing in the family goes past it. An amplification beyond the
ceiling would not be geometry of any kind and would have to be a belief about
the shape of weekend returns — which §7 has already shown would be the wrong
belief.

We measure $\eta$ inside each trade day and expiry rather than assuming a
functional form, and one detail of that matters. The wing region must be
selected on something the contract's own implied volatility does not enter.
Selecting it on delta looks natural and is wrong: at a given strike only the
*low* implied vols are far enough out to qualify, so the selected sample slopes
upward for a reason that has nothing to do with the smile and $\eta$ comes back
about 0.15 too steep. Standardizing against the expiry's own at-the-money level
instead leaves the selection predetermined. So measured, $\eta$ runs from 0.88 to
1.15, putting the ceiling between 1.79 and 2.35 — well above the 1.5 a quadratic
smile would imply, because real wings are steeper than parabolas.

**Identification, which matters more here than the mechanism.** The design
compares contracts quoted at the same instant with different weekend exposure.
Day fixed effects do not enforce that. Within a trade day the weekend fraction of
a *single* expiry also drifts as the clock advances — a Saturday-expiry contract
is 36% weekend at Friday breakfast and 67% by Friday evening — and none of that
is a comparison between contracts. Splitting the within-day variance of the
weekend fraction into the part from different expiries and the part from the
clock advancing on one:

| | expiries per day | sd of $w$ within a day | between-expiry share |
|---|---:|---:|---:|
| under 1 day | 1.4 – 2.0 | 0.101 – 0.106 | **0.39 – 0.45** |
| 1 – 3 days | 2.0 – 2.5 | 0.111 – 0.130 | **0.89 – 0.92** |
| 3 – 7 days | 1.0 – 1.3 | 0.025 – 0.042 | 0.00 – 0.66 |
| 7 – 14 days | 1.1 | 0.008 – 0.009 | 0.06 |

The 1–3 day band is where the design works: two to two and a half expiries
quoted every day, the most variation in weekend exposure of any band, and nine
tenths of it between contracts. Under a day, most of the variation is the clock
advancing on one contract. Beyond a week there is almost none. Everything below
therefore replaces each trade's weekend fraction with its (day, expiry) mean,
leaving only differences between expiries quoted the same day. That purge
*strengthens* the pooled wing effect rather than weakening it — the intraday
drift was adding noise, not signal.

![**Figure 9. What the smile's geometry can and cannot produce.** The shaded band
is the set of wing amplifications reachable by pinning the relative smile
anywhere between the contract's own standard deviations and its strike: one at
the bottom, the measured ceiling at the top. The diamond is what the market does,
precision-weighted across the four books. Every maturity sits above one and
inside the band, except the sub-daily point, which sits above it without
separating from it.](output/figures/w_f9_wings.png){width=85%}

| | amplification | t vs 1 | ceiling | t vs ceiling | $\theta$ |
|---|---:|---:|---:|---:|---:|
| pooled | 1.298 | +6.29 | 1.979 | −10.18 | 0.30 |
| under 1 day | 3.092 | +4.49 | 1.982 | +1.77 | — |
| 1 – 3 days | 1.102 | +2.19 | 2.137 | −14.92 | 0.09 |
| 3 – 7 days | 1.293 | +2.12 | 2.099 | −4.00 | 0.27 |
| 7 – 14 days | 1.329 | +1.74 | 2.003 | −2.50 | 0.33 |

Precision-weighted across the four books, with the intraday variation purged.

**The wings are geometry.** At every maturity the amplification is above one —
so the market is not putting the weekend into its moneyness metric — and at
every maturity except the sub-daily one it is significantly inside the ceiling,
so no belief about weekend tails is needed to produce it. Inverting gives
$\theta$ around a third, and the four books agree closely on the pooled figure:
0.35, 0.33, 0.44, 0.31. **The market applies the weekend clock in full to the
level of its surface and about a third of the way into the moneyness metric that
defines the smile.** That is the same coarseness §5.4 finds inside the weekend
itself, in a second place: a level adjustment made, a structural one not.

The sub-daily band is the one place that might be something else. Its
amplification of 3.09 sits above its ceiling of 1.98, which no moneyness metric
can produce, and every book contributes the same sign — but the excess is only
1.8 standard errors, and this is also the band with the weakest identification
in the paper. Under a day there are fewer than two expiries on a typical trade
day, and the two are not traded at the same hours: a contract expiring at 08:00
is only quoted before 08:00, so purging the intraday variation removes the
within-expiry part of the problem without removing the between-expiry part. It
is suggestive of the market pricing the weekend as less jump-prone precisely
where an option is nearly a pure jump claim, and it is not more than suggestive.

*(A note on a route that does not work, recorded so it is not tried again.
$\theta$ is also the ratio of two coefficients from a fitted smile — how its
curvature responds to the weekend fraction over how its level does — which needs
no bucketing and looks cleaner. It is not: a real smile is not a parabola, so the
curvature of a quadratic fitted to one is mostly a statement about how wide a
strike range it was fitted over. The correlation between log curvature and log
span is −0.74, the implied $\theta$ swings from −0.27 to −5.43 across quartiles
of span, and the level coefficient changes sign in the widest quartile. The
traded strike range moves with the weekend fraction and no polynomial control in
span repairs it: simply adding or dropping that control flips the sign of the
estimate in all four books, from −0.08 to +0.03 in Bitcoin and from −0.35 to
+0.01 in Solana. `w23_smile_shape.csv` reports it both ways so the gap is on the
record.)*

### Is the realized benchmark itself sound?

One more objection has to be closed before any of this counts, and it is about
measurement rather than about risk. Every realized ratio in the paper is built
from five-minute returns, which is only innocent if prices actually move on a
five-minute grid. When a book is thin the close repeats, the return records as
zero, and realized variance is biased down — by more in the regime where trading
is thinner, which is the weekend. That bias does not cancel in a ratio. It would
push measured weekend variance down and so *manufacture* part of the weekend
effect.

Reading the ratio across sampling intervals is the standard diagnostic, with the
share of unchanged closes as the direct measure of the problem:

| | 5 min | 15 min | 30 min | 60 min | 120 min | drift ÷ s.e. | zero closes at 5 min, wd / we |
|---|---|---|---|---|---|---|---|
| BTC | 0.584 | 0.576 | 0.596 | 0.561 | 0.548 | 0.84 | 2.6% / 4.7% |
| ETH | 0.607 | 0.614 | 0.626 | 0.608 | 0.597 | 0.53 | 2.3% / 3.4% |
| SOL | 0.656 | 0.598 | 0.594 | 0.644 | 0.617 | 0.63 | 6.0% / 12.5% |
| XRP | 0.623 | 0.563 | 0.603 | 0.704 | 0.643 | 1.33 | 17.5% / 28.8% |
| PAXG | 0.345 | 0.311 | 0.287 | 0.246 | 0.188 | 2.17 | 77.7% / 88.3% |

**The crypto results are not a staleness artefact.** Across a twenty-four-fold
change in sampling interval no traded book's ratio moves by more than 1.33 times
the standard error of its own five-minute estimate, and there is no monotone
drift in any of them. XRP is the one to watch — nearly three in ten of its
weekend five-minute closes repeat — and its ratio does wander the most, which is
a reason to read its 0.623 as the noisiest of the four rather than as biased in a
known direction.

**Gold's weekend discount is understated, not overstated.** PAXG is the one
series where staleness clearly bites: its ratio falls monotonically from 0.345 to
0.188 as the interval coarsens and its weekend zero-close share falls from 88% to
31%. The bias runs toward one, so the true discount is *larger* than the 0.347
reported in §3. Read at hourly sampling, where fewer than half its weekend
returns are stale, gold's weekend variance is 25% of its weekday variance against
roughly 60% for crypto — nearer three times the crypto discount than the "roughly
double" §3 claims. The conservative figure is the one kept in the headline.

### Verdict

The risk-based explanation loses the race, and it is worth being precise about
what that does and does not establish. It does not show that weekend jump risk is
unpriced or unimportant; the tail excess is real and replicates in all four
books. What it shows is that no single price of that risk reconciles the
cross-section. A premium large enough to rationalize Bitcoin's rich weekend is
still not large enough, moves Ether's quote the wrong way, and would have to
change sign to touch Solana and XRP. The option side agrees: the compensation is missing
from the part of the surface where jump risk is priced, and the wings mark the
weekend down harder than the money in all four books rather than more softly.
That turns out to be the smile's moneyness metric following the weekend clock
only about a third of the way rather than any statement about tails — a second
instance of a level adjustment made and a structural one not, and one more thing
the risk-based reading does not account for.

Two residuals genuinely remain outside this test. The first is that any risk
story restricted to *within-weekend* differences — a reason Saturday and Sunday
should be priced alike when they are realized differently — is untouched by the
above, and §5.4 is where that has to be argued. The second is the mature/young
split itself, which recurs here as it does everywhere else in the paper: the
required premium is positive in the two books listed before 2020 and negative in
the two listed in 2024. Whatever explains that division is not a property of the
underlying's return distribution, because the return distributions are what this
section measured and they do not divide that way.

## 8. Conclusion

Forty years after French and Roll asked why prices move more when exchanges are
open, a market that never closes gives a cleaner answer than the equity data
could. Variance falls 34% to 42% at the weekend in four separate underlyings with
the venue fully open throughout, and the weekend trough and late-week peak
reproduce in all four. The effect belongs to when information arrives, not to
whether one can trade — and the sharpest confirmation is the fifth asset, where
the venue is identical and the underlying's own market genuinely closes: gold's
weekend discount is roughly double crypto's, on the same exchange with the same
estimator.

The pricing consequence is smaller than we first believed and less tidy than the
version that replaced it. Bitcoin and Ether price roughly 85% of their own
realized weekend effect and Solana and XRP roughly 130% of theirs, though none of
those four errors is significant on its own and the split between the pairs is
mostly an artefact of the windows they cover.
A pooled test rejects a strictly uniform discount across underlyings, and cannot
reject proportionality either — but implied discounts disperse 2.4 times more
across assets than realized weekend risk does, so the second non-rejection is a
statement about power, not a finding. What can be said is that the market
differentiates between underlyings, and differentiates more than the underlying
risk warrants.

Where it is plainly wrong is inside the weekend. All four books price Saturday as
indistinguishable from Sunday when Saturday is reliably the quieter day; not one
of the four implied Saturday effects is significantly negative, and all four
realized effects are. That is the one point in the weekly profile where the
market's *ranking* of calendar time is incorrect rather than merely compressed,
and it is the same point in four markets that share no settlement convention, no
holder base and no listing history. A risk premium would have to be oddly
specific to produce that; a quoting convention that resolves "the weekend" as one
block produces it naturally.

That is an argument by elimination, so we ran the elimination. A premium applied
proportionally to calendar time cancels out of a variance ratio exactly, which
leaves only weekend-specific risk — and there is some: weekend returns carry 15%
to 28% more mass beyond five standard deviations once the volatility difference
is removed. Pricing that jump risk explicitly bounds what it can do, because a
weekend ratio built from a jump premium can never pass the ratio of weekend to
weekday jump variance. Every book's quote lies outside that bound. Bitcoin's
comes closest and still needs an unbounded premium to close 82% of its gap;
Ether's weekend is less jump-intensive than its weekdays, so a premium moves its
quote the wrong way; Solana and XRP quote *below* their own realized weekend
variance, which no non-negative price of jump risk can produce. The ordering
fails too — Solana has the most weekend-concentrated jump risk of the four and
the second-largest weekend discount in its prices. And the option surface agrees
with the returns: the far wings, which are where jump risk is priced, mark the
weekend down harder than the money in all four books rather than more softly.
The market prices the weekend as tail-quieter when it is measurably tail-fatter.

The error has not persisted untouched, and this is where the paper's sharpest
number lives. In 2020 Bitcoin and Ether priced weekend variance ratios of 0.91
and 1.00 — no weekend discount at all — against realized ratios of 0.52 and 0.70.
By 2026 they price 0.30 and 0.47. Weighting each year by its own precision, the
implied weekend discount deepens by 0.144 a year in Bitcoin (t = −12.5) and 0.117
in Ether (t = −10.5). The narrowing §6 measures from the P&L side and the trend
measured from the pricing side are the same fact: a spread trade selling
weekend-heavy variance earns +0.042 per unit vega gross over the full sample,
three quarters of it in the first half, and nothing distinguishable from zero in
the second. It has never covered the 0.066 of fees and spread the venue charges
to collect it, so the narrowing gross signal is the whole of the story on the
trading side — there was no net profit for competition to erode.

**What the market has been deepening its discount *toward* is the answer to why
it has not stopped.** Against the benchmark used everywhere else in this paper —
mean weekend variance over mean weekday variance — nothing in the realized series
moves, and the market looks like it is walking away from its own data. That
benchmark has almost no power: each year's mean is set by a handful of days, and
trimming the top one per cent of days from each day type turns Bitcoin's realized
trend from t = −1.2 into t = −4.9. Measured at the centre of the distribution
instead, the typical weekend has been getting quieter at 0.136 log points a year
(t = −7.5) in Bitcoin and 0.098 (t = −6.3) in Ether — and the implied discount
deepens at 0.186 and 0.149. Those are the same numbers. The market is tracking a real
decline, at close to the right speed, in the statistic a volatility trader reads
off a screen: what a weekend usually looks like.

An option does not pay off on what a weekend usually looks like. It pays off on
expected total variance, an arithmetic mean, and §7 has already shown that no
proportional risk premium can move a variance *ratio* — so the distinction is not
one the risk-neutral measure repairs. The error is therefore not drift but a
moment mismatch, and its size is the distance between a weekend's typical
variance and its average one. That distance has been widening since 2022: the
weekend has not simply gone quiet, it has gone *lumpy*, with ordinary weekends far
quieter and rare weekends no less violent. This is the fat-tail finding of §7
seen from the other side, and it means §5.1's residual gap, §6's decaying trade
and §5.5's deepening trend are three views of one mistake. What the trade tape
cannot say is *why* a desk would calibrate to the centre — deliberate robustness
against a skewed series is ordinary practice, and merely the wrong practice for
this quantity.

That is also what dissolves the paper's most tempting cross-sectional story.
Errors that look like a split between established books and 2024 listings are
four averages taken over four different legs of one common path, and once the
books are compared over the same window the split halves and stops being
significant. The movement in this market is over time, not across assets, and it
is estimated an order of magnitude more sharply there.

That trajectory is the natural close. A market can be sophisticated enough to
know that weekends are quiet, coarse enough to treat the two weekend days as
interchangeable when they are not, competitive enough to grind the residual away
once it is worth money to do so, and diligent enough to re-estimate its weekend
clock year after year against the wrong moment of the right series — all at once.
The errors this paper finds are not failures to look at the data. They are
failures to resolve it: two weekend days collapsed into one block, a smile's
moneyness metric moved a third of the way, a skewed distribution summarized by
its middle. In each case the market makes the level adjustment and misses the
structure underneath it.

Two implications follow. For research, calendar-time maturity conventions
introduce a systematic bias into short-dated crypto option studies, and the
correction is straightforward once the weekend clock is estimated. For practice,
the value of the result lies in quoting and risk systems rather than in a
strategy: a desk that prices the weekend clock correctly quotes better than one
that does not, and needs no arbitrageable alpha for that to pay.

The binding constraint is still cross-sectional, and the fourth underlying is how
we know it may not be relievable. XRP was added precisely to widen the spread of
realized weekend effects; it landed in the interior, leaving the span at 0.092
with four assets exactly where it stood with three. Four crypto books spanning
two settlement conventions, a decade of listing history and a factor of thirty in
trade count all discount their weekend by between 34% and 42%. That uniformity is
itself the mechanism evidence, and it is also the reason the pooled test will not
sharpen: there is no crypto asset whose weekend is materially different to add.

The asset that does have a materially different weekend is PAXG, and it cannot
carry a pricing estimate — 5,304 of its 5,346 listed options expire on a Friday,
so only 11.8% of its within-day variation in weekend exposure survives the
maturity controls, against roughly 39% for Bitcoin and XRP. Widening the priced
cross-section therefore needs an underlying that is both informationally tethered
to a market that closes *and* listed with daily expiries across the week. No such
book exists on Deribit today. Until one does, the cross-asset test is bounded by
the data rather than by the estimator, and the within-weekend result in §5.4 —
which needs no cross-sectional spread at all — is where the paper's sharpest
claim lives.

---

## Appendix: replication of the identifying variation

Figure 3 showed the within-day relationship for Bitcoin. The same picture in the
other three books, on the same axes and the same binning:

![**Figure A1. Within-day identification, Ether.**](output/figures/w_f4_binscatter_ETH.png){width=72%}

![**Figure A2. Within-day identification, Solana.** Solana is USDC-settled and
uses separate premium and hedging conventions throughout, so this is an
independent replication rather than a relabelling.](output/figures/w_f4_binscatter_SOL.png){width=72%}

![**Figure A3. Within-day identification, XRP.** The newest and thinnest of the
four books, on 70,128 trades after filtering against Bitcoin's 5.3
million.](output/figures/w_f4_binscatter_XRP.png){width=72%}

In all four the binned means decline in weekend exposure. The fitted line is a
bivariate OLS on the within-day demeaned data and so does not carry §5.1's
controls for log maturity, its square, and |delta|; it lands close to the
reported coefficient without reproducing it exactly (ETH: −0.227 here against
−0.246 in the regression).

---

## Reproduction

The trading tables (`w32`–`w54`) belong to Paper II and are listed in its own
reproduction table; the scripts live in the same `scripts/` directory.

Everything runs in sequence via:

```bash
python scripts/run_weekend_all.py
```

| Result | Section | Script | Output |
|---|---|---|---|
| Realized and implied ratios | 3, 5.1 | `weekend_academic.py` | `w1_weekend_pricing.csv` |
| Trading test, measured costs | 6 | `weekend_commercial.py` | `w2_weekend_trade_*.csv` |
| Robustness, placebos | 5.3, 5.4 | `weekend_robustness.py` | `w3_robustness_*.csv` |
| Day-of-week profile | 5.4 | `weekend_profile.py` | `w4_dow_profile_*.csv` |
| Convention test | 5.2 | `weekend_pooled.py` | `w5_pooled_convention_test.csv` |
| Reference asset (PAXG) | 3 | `weekend_reference.py` | `w8_*.csv`, `w9_*.csv` |
| Weekend tail risk | 7 | `weekend_tails.py` | `w10_weekend_tails.csv` |
| Risk horse race, smile, signature | 7 | `weekend_riskrace.py` | `w11`–`w15_*.csv` |
| Vintage vs window, time trend | 5.5 | `weekend_split.py` | `w16`–`w21_*.csv` |
| Wing anatomy and the smile clock | 7 | `weekend_wings.py` | `w22`–`w25_*.csv` |
| Which moment the market tracks | 5.6 | `weekend_learning.py` | `w26`–`w31_*.csv` |
| Saturday/Sunday contract availability | 5.4 | `weekend_params.py` | `w59_sat_sun_availability.csv` |
| Figures, day-of-week levels | 3, 5.1 | `weekend_figures.py` | `w_f*.png`, `w6_*.csv`, `w7_*.csv` |

This PDF is built from the same source with:

```bash
python scripts/build_paper.py
```

Assets are generated from `config.CURRENCIES`, so adding an underlying is one
entry rather than a new stage per script. Adding XRP as the fourth book required
exactly that, plus its market conventions — linear settlement, contract size
1,000, the `XRP_USDC` instrument prefix, and the `USDC` umbrella the API groups
it under — and one parser fix, since sub-dollar strikes encode their decimal
point as a letter `d`. Assets carried on the realized side only, such as PAXG,
live in `config.REFERENCE_ASSETS` and never enter the option stages.

Core measurement lives in `dbop/weekend.py` (weekend and weekday fractions,
closed-form and exact), `dbop/jumps.py` (the continuous/jump split, the
reachability bound, and the volatility signature) and `dbop/costs.py` (Deribit
fees, and effective spread recovered from aggressor sides). The two estimators
§5.6 turns on are both in `weekend_learning.py`: a log-link quasi-likelihood for
the ratio of conditional *means*, which is the paper's benchmark fitted
multiplicatively so it can carry a time interaction, and an ordinary within-month
regression on log variance for the ratio of geometric means. Stages run
sequentially by design: each loads a multi-million-row tape, and concurrent runs
exhaust memory.

The smile stage is the exception to the "recompute everything" rule: it caches
its six-column sample to `data/panels/smile_sample_*.parquet`, because loading
and enriching Bitcoin's tape takes half an hour and the specification above went
through several revisions. Delete those files after changing the filter.

Three implementation notes that cost time and are worth not rediscovering, all
documented at length in `docs/data_notes.md`.

**Check that the regression sample matches the filter output.** `util.to_utc_day`
once returned a Series with a fresh index; assigning it onto a filtered frame
aligned on labels and silently turned three quarters of every sample into `NaT`,
which then vanished in the next groupby. Nothing errored, and the surviving
subsample was biased toward the start of the period. It moved BTC's headline
implied ratio from 0.635 to 0.898 — i.e. it manufactured most of the paper's
original claim. The helper now preserves the index and `tests/test_util.py`
covers the failure mode, but the diagnostic worth keeping is the symptom: if the
fit `n` is much smaller than the number of trades passing the filters, find out
why before believing anything.

**Pass `columns=weekend.LEAN_COLS` to `tape.load`.** The full ~40-column frame
needs two copies of a 24m-row table to filter and will not fit; stages also run
sequentially for the same reason.

**`bars.load`'s `ts` column is `datetime64[ms]`, not `[ns]`.** The reflexive
`//10**6` rescaling turns milliseconds into kiloseconds and sends every price
lookup to 1970.

## Open items

Done: introduction and literature review; Solana and XRP added as third and
fourth underlyings, with the pooled convention test, robustness, day-of-week
profile and trading test all rerun on each; PAXG added as a realized-side
reference asset; the day-of-week profiles for all four assets; figures 1–7; the
risk-based horse race of §7, with the jump decomposition, the reachability bound,
the smile test and the volatility signature; and the three corrections
described at the head of this draft, with every number recomputed on verified
series. Ether's gross P&L anomaly resolved with them — it was the corrupted bar
series, not near-zero vega in the denominator.

Three items closed differently from how they were posed. The mature/young split
turned out not to be a property of book vintage at all: half of it disappears
when the four books are compared over a common window, none of the four gaps is
individually significant, and the joint test that they are equal never rejects.
What replaced it is stronger than what it displaced — a decade-long deepening of
the implied weekend discount, estimated at t = −12.5 and −10.5 (§5.5) — and that
in turn led to the paper's one self-correction, in §5.6. The claim that the
realized effect was flat over the same years was an artefact of an underpowered
benchmark, and the deepening is a response to a real decline in the centre of the
realized distribution rather than a drift away from the data. The fourth underlying was
meant to widen the cross-section and did not: XRP's realized weekend effect fell
between Ether's and Solana's, leaving the span unchanged at 0.092. And Solana's
missing forward curve turned out not to be buildable rather than merely unbuilt —
Deribit lists dated futures on the USDC books, but only three SOL and three XRP
contracts have ever produced usable closes, covering the last 127 and 59 days.
Both books therefore keep the index as forward, deliberately (§2.2).

The horse race also closed a question nobody had asked. Checking that the
realized benchmark was not itself a staleness artefact turned up the one place
where it is: PAXG's perpetual repeats 88% of its weekend five-minute closes, and
its weekend variance ratio falls monotonically from 0.345 to 0.188 as the
sampling interval coarsens. The bias runs toward one, so §3's gold result is
conservative rather than wrong, but the *magnitude* quoted there is a lower
bound and should be read as one. The four traded books show no such drift.

A fourth item closed harder than it was posed, and became a paper of its own.
§6 asked whether the wedge was
being competed away and answered with a decayed second half. Charging the spread
correctly (Paper II §4) gives a harder answer: it never cleared zero at all. The
gross edge is +0.042 per unit vega against 0.066 of fees and spread, so the trade
loses in every book at every rehedging frequency, and an earlier reading of it as
profitable-then-inverted came from crediting the long leg's costs instead of
charging them. The mechanism §5.6 identifies is unaffected and still shows in the
gross series — what a Friday seller of weekend variance is paid still looks
positive at the median and has reached zero at the mean. The pricing error the
paper documents is not harvestable by the trade that documents it, and the
binding obstacle is the venue's fee schedule rather than competition.

**A fifth item was not posed at all, and is the paper's second self-correction.**
It falls entirely in Paper II. The trading engine behind its §§6–9 looked for the
exit mark in a frame that had already been narrowed to a 0.35–0.65 delta band, so
the exit was conditional on the option still being near the money — a condition
on the future, since options leave the band when the index moves and a
delta-hedged short loses when the index moves. The Fridays that survived had a
mean absolute weekend index move of 0.94% against 2.15% across all Fridays.
Everything in Paper II from its §6 onward was recomputed on an unbanded exit
index; the revisions are not uniform in direction and are set out there and in
`docs/data_notes.md`. **Nothing in §§1–5 or §7 of this paper uses that engine.**

Remaining, in priority order:

- [ ] **Why does a desk calibrate to the centre of the distribution?** §5.6
      closes the previous version of this item — "why is the market still
      deepening its weekend discount, when nothing in the realized series moves
      with it" — by showing that the premise was false. The realized series does
      move; the benchmark used to test it was a ratio of two means of a series
      whose annual mean is set by a handful of days, and it had no power.
      Measured at the centre of the distribution the weekend has been getting
      quieter at 0.136 and 0.098 log points a year, and the implied discount
      deepens at 0.186 and 0.149: a real decline tracked in the wrong
      moment of it. What remains open is one step further back. Robust
      estimation of a right-skewed quantity is ordinary desk practice, and it is
      simply the wrong practice for a quantity an option integrates rather than
      typifies. Whether it is deliberate, a fitted model with a thin-tailed
      error, or nobody looking, cannot be told from a trade tape — it needs
      quote-level data, or a desk willing to describe its own calibration.
- [ ] **Why has the typical weekend been getting quieter?** New, and raised by
      §5.6 rather than answered there. Bitcoin's weekend has gone from 69% of a
      typical weekday's variance to 28% in six years while its *mean* weekend
      variance held up, so the weekend has become lumpier rather than simply
      calmer. The obvious candidate is that crypto's information increasingly
      arrives on a traditional-finance calendar — macro releases, an equity
      correlation that rose sharply in 2022, spot ETFs from 2024 — all of which
      land on weekdays and none of which touch the rare weekend liquidation
      cascade that keeps the mean up. Testing it needs an equity and
      macro-calendar series this repo does not collect, plus a within-crypto
      proxy such as the share of weekday variance falling in US trading hours.
      Neither Solana nor XRP shows the decline, which is a start on a
      cross-section but not one with the power to carry the test.
- [ ] **The sub-daily wings.** §7 resolves the far-wing effect: it is the
      smile's moneyness metric following the weekend clock only about a third of
      the way, and it needs no belief about weekend tails. The exception is
      contracts expiring within a day, whose amplification of 3.09 sits above
      the geometric ceiling of 1.98 in all four books — by 1.8 standard errors,
      so above it without separating from it, and in the band with the weakest
      identification in the paper. Settling it needs timestamped quotes rather
      than the trade tape, or a venue listing several sub-daily expiries side by
      side.
- [ ] Formal inference on the day-of-week profile correlations, which currently
      rest on seven points per asset with no standard errors. This matters more
      now that the Saturday result is the headline claim.
- [ ] A priced cross-section wide enough to test calibration. It needs an
      underlying informationally tethered to a market that closes *and* listed
      with daily expiries across the week; no such book exists on Deribit today
      (§8).
- [x] Decide whether §6 (tradeability and decay) belongs in the paper or a
      companion note. **Closed: it is a companion paper.** *The Half-Life of a
      Pricing Error* (`paper/decay.md`) carries the seven trade constructions,
      the Greek attribution and the commercial arithmetic; §6 here keeps only
      the validation and the decay, which the pricing argument needs.
- [ ] A reference list. The draft cites informally throughout and has no
      bibliography, and `docs/related_work.md` covers the abandoned
      demand-pressure paper's literature rather than the trading-hours
      literature this paper sits in.
