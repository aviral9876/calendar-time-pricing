# Closure or Information? Weekend Variance and Option Prices in a Market That Never Closes

---

## Abstract

Asset prices are far more volatile when exchanges are open than when they are
shut. Distinguishing information arrival from the mechanical effect of closure
has never been possible in equity markets, where "the exchange is closed" and
"no one is trading" are the same event. Cryptocurrency separates them: Deribit
trades continuously while the traditional financial system does not. We show
that Bitcoin realized variance is 42% lower on weekends despite uninterrupted
trading, with Saturday the quietest day of the week, and that the effect is
near-identical across four underlyings with different settlement conventions
(34%–42%). It roughly doubles, to 65%, for tokenized gold, which trades on the
same venue while gold's own market is shut all weekend. Because Deribit lists
daily expiries on all seven weekdays, contracts quoted at the same instant
differ in how much weekend calendar time they span, which identifies the
market's implied weekend discount from purely within-instant variation. The
market prices roughly seven eighths of the effect in the mature books. Its one
demonstrable failure is *within* the weekend: all four books price Saturday as
indistinguishable from Sunday when Saturday is reliably quieter — and the venue's
own expiry schedule makes that error unarbitrageable, offering both sides of the
offsetting spread in 13 hours of the week and none of them on a weekday.

**Keywords:** calendar time; realized variance; option pricing; market
microstructure; cryptocurrency derivatives

---

## 1. Introduction

French and Roll (1986) established that US equity variance per calendar hour
collapses when the exchange is shut, and set out three candidate explanations:
public information arrives disproportionately during business hours; private
information is impounded when informed investors trade; or trading itself
generates pricing errors. Distinguishing among them has proved difficult for a
structural reason. In a conventional market, closure and the absence of trading
are the same event, and both coincide with the hours in which most public
information is released. The three explanations are confounded by construction.

Cryptocurrency markets break that confound. Deribit trades options and perpetual
futures continuously, including weekends, while the traditional financial system
does not. Trading is possible at all times, so any weekend variance effect cannot
be attributed to a venue being shut.

**Weekends are quiet even though the market is open.** Realized variance is 42%
lower on Saturdays and Sundays than on weekdays for Bitcoin, 39% for Ether, 38%
for XRP and 34% for Solana, with Saturday the quietest day in all four. The
natural reading is that much of what moves crypto prices originates in
traditional market hours — macroeconomic releases, institutional flow, the
spot-ETF complex — and the fact that four assets with different settlement
conventions, holder bases and listing histories inherit the *same* weekly rhythm
is what makes that reading hard to avoid. A fifth asset sharpens it. PAXG,
tokenized gold, trades continuously on the same venue while gold's own market in
London and on COMEX is shut all weekend; its weekend variance is **65% below
weekday**, roughly double the crypto effect. Turn the traditional calendar up and
the weekend deepens, on the same exchange with the same estimator.

**Options price most of the effect.** Deribit lists daily expiries on all seven
weekdays, so contracts quoted at the same instant differ in how much weekend
calendar time they span: on a Thursday, a Friday expiry covers no weekend while a
Monday expiry covers most of one. Regressing squared implied volatility on that
fraction, with day fixed effects absorbing the volatility level and every other
common shock, identifies the implied weekend discount from within-instant
variation alone. This design has no equity analogue — there are no Saturday
expiries when the exchange is closed. Bitcoin's options price 85.0% of Bitcoin's
own realized weekend effect and Ether's 85.5% of Ether's. None of the four
residual pricing errors is individually significant, and we do not build on them.

**The failure is within the weekend, not across assets.** In all four books the
market prices Saturday as statistically indistinguishable from Sunday, when
Saturday is reliably the quieter of the two. Across the rest of the week the
implied day-of-week profile tracks the realized one closely — correlations of
+0.98, +0.88, +0.89 and +0.82 — so the market reads the calendar well everywhere
except here, where it resolves "the weekend" as a single undifferentiated block.
Four independent books make the same mistake in the same place.

We then show why that particular error survives, and the answer is a property of
the contract calendar rather than of beliefs. The trade that would correct it —
sell the Saturday-heavy contract, buy the Sunday-heavy one — requires both to
exist at the same moment. Enumerating every hour of the week against every
listed expiry, they coexist in **13 hours out of 168, none of them on a weekday**.
Monday through Friday no Sunday-heavy contract is listed at all, because any
contract reaching Sunday must pass through Saturday first. The market's one
demonstrably wrong ranking of calendar time is the one its own expiry schedule
prevents anyone from arbitraging.

Two further results bound the interpretation. Weekend returns do carry fatter
tails, so there is a weekend-specific risk to charge for — but decomposing
realized variance into continuous and jump components bounds what a jump premium
can price, and every book's quote falls outside that bound; two of the four would
need a *negative* price of jump risk, since their quotes sit below their own
realized weekend variance. And the residual error is not harvestable: a
vega-matched calendar spread isolating it earns +0.042 per unit vega gross
against 0.066 of measured fees and spread, so it has never cleared zero at taker
cost.

**Contribution.** The paper's design point is that a single venue supplies both
halves of the test. The realized side compares weekend to weekday variance on an
exchange that never closes, so closure is held fixed while the information
environment varies; the reference asset raises the dose by holding the venue
fixed while shutting the underlying's own market. The implied side compares
contracts quoted in the same book at the same instant that differ only in how much
weekend they span, which is possible because expiries are listed on all seven
weekdays. Neither comparison is available in equity or listed-futures markets,
where closure, non-trading and the news calendar move together and where no
contract can expire while the exchange is shut.

What that buys is a measurement of how a derivatives market prices a known,
mechanical, repeating feature of calendar time — and, because the same venue
supplies the realized benchmark, a measurement of how well. The answer is
"substantially, but at the wrong resolution and against the wrong moment," and
both failures are identified rather than inferred.

### Related literature

French and Roll (1986) is the origin of the question, and Oldfield and Rogalski
(1980) had already framed returns as accruing over trading and non-trading
periods that need not share a clock. Barclay, Litzenberger and Warner (1990) came
closest to separating the mechanisms, using a natural
experiment in the opposite direction from ours: when the Tokyo Stock Exchange
opened on Saturdays, weekend variance rose while weekly variance was unchanged
despite higher volume. They varied whether an exchange was *open* while holding
the information environment roughly fixed; we hold the exchange open always and
vary whether the traditional financial system is running. The two designs
bracket the question from opposite sides, and both point to trading time rather
than calendar time as the relevant clock.

On the option side, practitioners have long used trading-day rather than
calendar-day clocks, and the academic treatment of weekend and holiday effects in
implied volatility is thin relative to its practical importance. Our contribution
is a venue where the clock convention is identified from within-instant variation
rather than assumed.

Three further literatures bear on the interpretation. Whether the residual gap is
compensation rather than error is a variance-risk-premium question in the sense
of Carr and Wu (2009), and §6 answers it in the negative for this particular
quantity. Whether it instead reflects order flow rather than beliefs is the
demand-pressure question of Gârleanu, Pedersen and Poteshman (2009) and Bollen and
Whaley (2004); we cannot address it, because the trade tape carries the aggressor
side but not the dealer's inventory, and we say so rather than infer. And the
crypto option market has its own measurement literature — Alexander and Imeraj
(2023) on delta-hedging Deribit options under a smile — on which the hedging
conventions in §7 draw.

## 2. Institutional setting and data

### 2.1 Why Deribit

Deribit is the dominant venue for crypto options and, critically for this paper,
lists **daily expiries on all seven weekdays**. Across 342,827 instruments in the
four books used here the expiry-weekday distribution is close to uniform apart
from the expected Friday concentration — every underlying lists between 12% and
14% of its instruments on each of the six non-Friday weekdays. From 2020 onward
there is an expiry on essentially every calendar date (365 of 365 in each year
from 2021 to 2025), and short-dated contracts are the norm rather than a
curiosity: roughly 80% of instruments have seven days or less of life.

That schedule is what makes the design work. Because Saturday and Sunday expiries
exist and trade, a contract quoted on a Thursday afternoon may span no weekend at
all or most of one, and the two sit side by side in the same book at the same
instant. No equity or listed-futures market offers this: when the exchange is
shut there is nothing to expire into, so weekend coverage is perfectly collinear
with maturity.

### 2.2 Sample

We use the complete public trade history collected from `history.deribit.com`:
24,349,954 Bitcoin trades from November 2016, 16,207,332 Ether trades from March
2019, 695,295 Solana trades and 234,640 XRP trades from early 2024, running to
August 2026 — 41.5 million trades in all. Each carries the exchange's own implied
volatility, the index level, the aggressor side, and flags for block trades,
combinations and liquidations.

The baseline sample excludes block trades and combinations, which are bilaterally
negotiated or double-counted, retains liquidations, and keeps contracts with
$|\Delta|$ between 0.30 and 0.70 and maturity between six hours and fourteen
days. Realized variance comes from five-minute perpetual-future returns over
2,923 Bitcoin days, 2,704 Ether days, 915 Solana days and 887 XRP days, at 100%,
100%, 99.9% and 99.9% bar completeness. Five minutes is the conventional
compromise between discretization error and microstructure noise (Zhang, Mykland
and Aït-Sahalia 2005, Hansen and Lunde 2006); §5.3 varies it from five minutes to
two hours, and the direction in which estimates move under that variation is used
there as a diagnostic rather than reported as a robustness check. Returns spanning a feed gap are dropped
rather than winsorized, since a multi-period return carrying a one-period label
inflates exactly the tail statistics §6 depends on.

Solana and XRP options are USDC-settled (linear) rather than coin-settled, carry
contract sizes of ten and one thousand rather than one, and trade on separate
instrument families. They require their own premium and hedging conventions
throughout, which is what makes them genuinely independent replications rather
than relabellings of the same book. One caveat attaches to both: no forward curve
is used, because Deribit's dated futures on these underlyings are close to
untraded — over the whole sample only three SOL and three XRP contracts produced
usable daily closes. Their greeks are computed against the index instead, and the
gap is documented rather than patched.

### 2.3 The reference asset

A fifth asset appears on the realized side only. PAXG is tokenized gold: its
Deribit perpetual trades continuously like every other book here, but the
underlying's price-formation market — London and COMEX — is genuinely shut from
Friday 22:00 to Sunday 22:00 UTC. It therefore turns the paper's mechanism *up*
rather than merely exhibiting it, and §3 uses it as a dose-response check.

It contributes no pricing estimate. Of its 5,346 listed options, 5,304 expire on
a Friday, so within a trade day the weekend fraction of a contract's remaining
life is a deterministic function of its maturity and cannot be separated from the
maturity controls §5.1 requires. Its perpetual covers 618 days from December 2024.

## 3. The fact: weekends are quiet in a market that is open

**Table 1** reports annualized realized volatility by day of week and the
implied weekday/weekend variance ratios.

**Table 1. Realized volatility by weekday, and weekend variance ratios.**

| | Mon | Tue | Wed | Thu | Fri | **Sat** | **Sun** | Weekend/weekday variance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 59.9 | 58.9 | 61.1 | 60.4 | 59.2 | **42.0** | **46.3** | **0.584** |
| ETH | 77.0 | 75.9 | 79.2 | 77.1 | 75.3 | **56.7** | **62.4** | **0.607** |
| SOL | 89.0 | 85.5 | 83.6 | 82.0 | 87.6 | **60.8** | **68.8** | **0.657** |
| XRP | 86.5 | 80.1 | 76.5 | 76.0 | 84.2 | **58.3** | **63.9** | **0.621** |

*Annualized percent, from five-minute returns. Weekday and weekend day counts are
2,089/834 (BTC), 1,932/772 (ETH), 655/260 (SOL) and 634/253 (XRP).*

Saturday is the quietest day of the week in every asset and Sunday the second
quietest, with no weekday in any row falling below any weekend day. **Weekend
variance is 34% to 42% below weekday in every asset, and the exchange is open
throughout.**

The agreement across assets is a sharper test of the mechanism than the level of
any one ratio, and it is worth being explicit about why. If crypto weekends are
quiet because the *traditional* financial system is closed, then every crypto
asset should inherit the same weekly information rhythm regardless of its own
microstructure, because the thing that stops on Saturday is external to all of
them. If instead weekend quiet reflected asset-specific features — retail
participation, venue depth, the composition of the holder base — the ratios would
diverge, because those features differ sharply across these four. They agree
within seven percentage points despite differences in settlement convention
(inverse against linear), contract size (one against a thousand), listing history
(a decade against two years) and volatility level (a factor of two).

The alternative reading, that trading itself generates variance and weekends are
quiet because volume is lower, is not available here in the form it takes in
equity markets: the venue is open, the order book is live, and the perpetual
trades throughout. It survives only as a claim about *endogenous* participation —
that traders choose not to trade at weekends — which is itself most naturally
explained by there being less to trade on.

**Turning the traditional calendar up.** The four crypto assets all sit at the
same dose of the treatment: their own venues never close, and the traditional
system they take information from is shut every weekend. PAXG raises the dose.
Its Deribit perpetual behaves exactly like the others, but the market that forms
gold's price is genuinely shut from Friday 22:00 to Sunday 22:00 UTC, so the
weekend removes not merely the flow of macroeconomic news but the price-formation
process itself.

PAXG's weekend variance ratio is **0.347**, against 0.584 to 0.657 for the four
crypto assets — a weekend discount of 65% where theirs is 34% to 42%, roughly
double. The venue, the estimator, the sampling frequency and the day-type
definition are identical; the only thing that changes is whether the underlying's
own market is running. A dose-response of this shape is difficult to produce from
any account that locates the effect in crypto microstructure.

This is a lower bound, and the reason matters for how it should be read. PAXG's
perpetual repeats 88% of its weekend five-minute closes against 78% of its
weekday ones, and stale prices depress measured variance in both regimes while
biasing their *ratio* toward one. The true weekend effect in gold is therefore at
least this large. Its variance ratio also falls monotonically, from 0.345 to
0.188, as the sampling interval coarsens and the staleness is removed — the
signature of exactly this bias. The four traded books show no such drift, which is
what licenses reading their ratios at face value.

![**Figure 1. Realized volatility by day of week.** Annualized, from five-minute
returns, as a deviation from each asset's own weekday mean. Saturday and Sunday
shaded.](output/figures/w_f1_realized_by_dow.png){width=80%}

## 4. Identification

Write the total variance over an option's life as a time-weighted average of a
weekday and a weekend variance:

$$\sigma^2_{i,t} T_{i,t} = v^{wd}_t (1 - w_{i,t}) T_{i,t} + v^{we}_t\, w_{i,t} T_{i,t},$$

where $w_{i,t}$ is the fraction of contract $i$'s remaining life at time $t$
falling on a Saturday or Sunday. Dividing through,

$$\sigma^2_{i,t} = v^{wd}_t + (v^{we}_t - v^{wd}_t)\, w_{i,t}.$$

The estimating equation is

$$\sigma^2_{i,t} = \gamma_t + \beta\, w_{i,t} + \delta' X_{i,t} + \varepsilon_{i,t},$$

with $\gamma_t$ a day fixed effect and $X$ containing log maturity, its square,
and $|\Delta|$. The coefficient $\beta$ estimates $v^{we} - v^{wd}$, and the
implied weekend variance ratio is $(\bar v^{wd} + \beta)/\bar v^{wd}$. Standard
errors are clustered by day throughout.

Two features make this credible. First, $\gamma_t$ absorbs the level of
volatility and everything else common to the day — the state of the market, the
funding environment, any news — so $\beta$ is identified only from contracts
quoted **at the same instant** that differ in weekend exposure. Second, $w$ is
mechanical: it is a property of the calendar and the expiry date, not of anything
the market chooses in response to volatility. A contract's weekend fraction was
determined when the exchange set its listing schedule, typically years earlier.

Weekend fraction is computed exactly, in closed form, rather than by counting
whole days. Deribit expiries settle at 08:00 UTC, so almost every contract covers
part-days at both ends, and a whole-day count would misstate $w$ by up to two
thirds of a day on precisely the short contracts that carry most of the
identifying variation. The same construction yields the fraction falling on each
of the seven weekdays, which §5.2 uses.

The maturity controls deserve a word, because $w$ and $T$ are mechanically
related: a very short contract listed on a Friday is nearly all weekend, while a
long one is close to the 2/7 calendar share. If the implied volatility surface
has any term structure — and it does — then omitting maturity would load part of
that term structure onto $\beta$. Log maturity and its square absorb the smooth
part; the identifying variation that remains is the difference between two
contracts of *similar* maturity quoted at the same instant whose expiry dates fall
on different weekdays. That variation exists in this venue precisely because
expiries are daily.

The threat this design does not rule out by construction is a listing schedule
chosen in response to expected weekend variance. We treat it as a maintained
assumption. A calendar that lists an expiry on all 365 days of the year, fixed in
advance and uniform across underlyings, makes it a mild one.

## 5. Results

### 5.1 The market prices most of the weekend effect

**Table 2. Implied and realized weekend variance ratios.**

| | slope $\beta$ | se | *t* | n | implied ratio | realized ratio | gap | (se) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | −0.1612 | 0.0149 | **−10.8** | 5,339,133 | 0.635 | 0.584 | +0.051 | (0.066) |
| ETH | −0.2461 | 0.0277 | **−8.9** | 3,624,938 | 0.645 | 0.607 | +0.038 | (0.067) |
| SOL | −0.3568 | 0.0243 | **−14.7** | 189,906 | 0.558 | 0.657 | −0.099 | (0.102) |
| XRP | −0.5513 | 0.0691 | **−8.0** | 70,128 | 0.488 | 0.621 | −0.133 | (0.123) |

*Standard errors clustered by day, over 3,413, 2,703, 886 and 885 days. The gap's
standard error combines the implied slope's with the realized ratio's own
sampling error.*

The slope is negative and overwhelmingly significant in all four: **the market
does price weekend calendar time, and prices a large share of it.** Bitcoin
implies a weekend variance ratio of 0.635 against a realized 0.584 — a discount
of 36.5% where the true discount is 41.6% — and Ether 0.645 against 0.607.
Roughly seven eighths of the effect is in the price in both established books.

**The residual gaps are not individually significant, and that constraint binds
everything said about them.** The four *t*-statistics are +0.78, +0.57, −0.92 and
−1.07. The implied side is estimated to within about three points of variance
ratio, but the realized side is a difference of two means over at most 834
weekend days, and it dominates the uncertainty. Nothing below should be read as a
measured pricing error in a particular book.

The identification is visible directly in the data, without any regression.
Demeaning both squared implied volatility and weekend fraction within each trading
day strips out the volatility level and every common shock, leaving only the
comparison the regression uses: contracts trading at the same instant that differ
in how much weekend they span. Binned that way, the relationship is close to
linear across the full range of weekend fraction in all four books, which is what
the constant-within-regime variance assumption behind §4 requires. (The
binscatters are in the e-companion.)

The raw pattern survives an even cruder cut. Average at-the-money implied
volatility for contracts with three days or less to expiry, by expiry weekday,
puts Sunday expiries cheapest of the week in all four books and Monday expiries
second-cheapest in three — precisely the two that carry the most weekend calendar
time. The market's ordering is right; its magnitude is what §5.1 measures.

**Does the market apply one discount to every underlying, or calibrate to each?**
Pooling the four books and testing the restrictions directly, a strictly uniform
discount is rejected. Beyond that the test is close to uninformative, and saying
so is more useful than reporting the non-rejection of the alternative.

The reason is visible in the dispersion. Across the four assets the standard
deviation of implied weekend discounts is 0.0919 against 0.0384 for realized ones
— **the market's quotes vary 2.4 times more across assets than the weekend risk
they are pricing does.** That is over-differentiation rather than calibration. The
proportionality hypothesis nonetheless fails to reject, and the reason is power,
not support: the four realized effects are bunched inside a span of 0.092, so
dividing by them is close to dividing all four slopes by the same constant, and
the ratio test is then nearly the equality test. It survives only because the
delta-method correction for realized-effect uncertainty inflates the standard
errors on the two short samples to 0.418 and 0.502, against 0.178 and 0.187 for
the mature books. A non-rejection obtained that way is a statement about the
sample, not about the market.

![**Figure 2. Implied against realized weekend variance ratios.** Each asset's
implied ratio with its confidence interval against its realized ratio; the
45-degree line is correct pricing.](output/figures/w_f2_implied_vs_realized.png){width=80%}

### 5.2 The failure is within the weekend

Everything so far concerns the level of the weekend discount, where the market
does well. Its resolution is a separate question, and the answer is sharper.

Estimating a full day-of-week profile — a separate implied effect for each of the
seven days, against the realized volatility of that day — the market's ordering is
otherwise good. Implied and realized profiles correlate at +0.98, +0.88, +0.89 and
+0.82 across the four books. The market knows Tuesday from Thursday. One place
breaks, and it breaks the same way in every book.

**Table 3. Saturday against Sunday, implied and realized.**

| | implied Saturday effect | *t* | realized Saturday effect |
|---|---:|---:|---:|
| BTC | +0.004 | 0.14 | −0.033 |
| ETH | +0.074 | 2.01 | −0.094 |
| SOL | −0.012 | −0.18 | −0.075 |
| XRP | +0.158 | 1.21 | −0.041 |

*Effect of a Saturday relative to a Sunday, in variance-ratio units. Positive
implied values mean the market prices Saturday as the busier day.*

In every asset the market prices Saturday as indistinguishable from — or busier
than — Sunday, when Saturday is the quieter of the two. Not one of the four
implied Saturday effects is significantly negative, while all four realized
effects are negative. **That is the one place in the weekly profile where the
market's ranking is demonstrably wrong rather than merely compressed**, and it is
the same place in all four — across two settlement conventions, a decade of
listing history, and a factor of thirty in trade count.

This is a stronger form of evidence than the level results, for two reasons.
Compression of a discount toward zero is what any smoothing or regularisation in a
pricing model would produce, and is consistent with the market knowing the answer
and shading it. Ranking two adjacent days the wrong way round is not: it requires
the weekend to be represented as a single object. And because Saturday and Sunday
sit inside the same weekend, an error between them cannot be attributed to
anything that varies at weekly frequency — the level of volatility, the news
calendar, the funding environment — all of which are common to the pair.

**And it is the one error the listing schedule protects.** The natural response
is to spread it: sell the Saturday-heavy contract, buy the Sunday-heavy one. Both
legs sit inside the weekend, so the common weekend discount differences out and
what is left is exactly the failure to rank the two days. That trade cannot be
put on. Expiries are daily at 08:00 UTC, so which weekday an option's remaining
life falls on is fixed entirely by its entry time and expiry date; enumerating
every hour of the week against every expiry in the half-day-to-eight-day window
gives not a sample of the menu a desk faces but the whole of it. Monday through
Friday — 120 of the week's 168 hours — **no Sunday-heavy contract is listed at
all**, because any contract reaching Sunday must pass through Saturday to get
there. The two legs coexist in 13 hours, on Saturday between 07:00 and 13:00 UTC
and on Sunday between 15:00 and 20:00, by which time the Saturday being sold is
already under way or finished.

So the market's one demonstrably wrong ranking of calendar time is also the one
its own contract calendar prevents anyone from arbitraging directly. That is a
more economical account of why this error survives than convention or inventory,
and unlike those it needs no quote-level data — it follows from the expiry
schedule alone.

### 5.3 A decade-long trend, and what it tracks

The implied discount is not static. **Table 4** reports it by year.

**Table 4. Implied weekend variance ratio, by year.**

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 0.91 | 0.93 | 0.48 | 0.58 | 0.51 | 0.42 | **0.30** |
| ETH | 1.00 | 0.95 | 0.55 | 0.58 | 0.45 | 0.49 | **0.47** |
| SOL | — | — | — | — | 0.60 | 0.53 | 0.58 |
| XRP | — | — | — | — | 0.45 | 0.52 | 0.62 |

In 2020 Bitcoin and Ether priced essentially no weekend discount at all, against
realized ratios of 0.52 and 0.70 in the same year. By 2026 they price 0.30 and
0.47. Weighting each year by its own precision, the implied weekend effect falls
by **0.144 per year in Bitcoin (*t* = −12.5) and 0.117 in Ether (*t* = −10.5)**.
This also dissolves the apparent cross-sectional split in Table 2: Solana and
XRP quote deeper discounts than Bitcoin and Ether largely because their samples
begin in 2024, late in a market-wide trend.

Measured as this paper measures it everywhere else — mean weekend variance over
mean weekday variance — the realized ratio has no significant trend over the same
years (*t* = −1.25 and −1.09). That contrast looks like a market walking away
from a benchmark standing still. It is not, and the reason is a measurement
point worth stating in general form.

**A ratio of means of a right-skewed series is a weak test, and a weak test is
not a null.** Daily realized variance is extreme enough that each year's mean is
set by a handful of days. Three diagnostics separate an absent effect from an
underpowered estimator, and all three say the same thing here.

**Table 5. The weekend trend, by moment of the realized distribution.**

| | ratio at mid-sample | per year | *t* | 2020 → 2026 |
|---|---:|---:|---:|---|
| BTC arithmetic (ratio of means) | 0.494 | −0.062 | −1.19 | 0.606 → 0.402 |
| BTC **geometric** (ratio of centres) | 0.437 | **−0.136** | **−7.54** | 0.685 → 0.279 |
| ETH arithmetic | 0.564 | −0.037 | −0.97 | 0.637 → 0.499 |
| ETH **geometric** | 0.532 | **−0.098** | **−6.25** | 0.736 → 0.384 |

*Log points per year, within-month fixed effects, month-clustered standard
errors.*

First, **trimming**. Cutting the top one per cent of days from *each day type
within each year* — so the trim itself carries no weekend effect — takes
Bitcoin's arithmetic trend from −0.062 (*t* = −1.2) to −0.132 (*t* = −4.9), and
the estimate then barely moves as the trim deepens to the median. The flatness
was bought entirely in the extreme right tail.

Second, **refitting at the centre**. The same contrast on log variance estimates
the ratio of geometric means and carries three to four times the *t*-statistic on
the same days. The typical Bitcoin weekend has gone from carrying 69% of a
typical weekday's variance to 28%.

Third, **the sampling ladder**, which discriminates economics from measurement.
Observation noise adds roughly the same amount to every day's measured variance,
pushing a measured ratio toward one and attenuating any trend in it — hardest on
the finest grid. A *real* trend seen through noise therefore **strengthens** as
the interval coarsens; a trend manufactured by *shrinking* noise weakens.
Bitcoin's geometric trend runs −0.136 at five minutes and −0.193 at two hours,
and Ether's −0.098 to −0.160. It strengthens. Zero-return shares show no upward
drift in either book, so growing weekend staleness is not the explanation.

**Which of the two is the market pricing?** Both realized measures are now
falling, so the question is no longer whether the market responds to something
but to which something. Fitting the implied ratio quarter by quarter gives trends
of −0.186 (*t* = −10.43) in Bitcoin and −0.149 (*t* = −10.46) in Ether, against
geometric realized trends of −0.136 and −0.098 and arithmetic ones of −0.062 and
−0.037. Differencing implied against realized at each sampling interval, the
*t*-statistic on the difference against the geometric benchmark falls
monotonically to +0.2 and +0.4 at the coarsest sampling, where microstructure
noise cannot reach; against the arithmetic benchmark it sits near two standard
errors throughout and closes only where power runs out. **The implied trend
converges on the geometric benchmark and never on the arithmetic one.**

A backward-looking level test agrees. Regressing each quarter's log implied ratio
on the *previous* quarter's realized ratio with asset fixed effects — which is
what calibrating to recent history means — gives slopes of 0.71 on the geometric
ratio and 0.27 on the arithmetic one. Both regressors are estimates, so both
coefficients are attenuated; correcting each by its own sampling variance lifts
them to 1.15 and 0.48. The correction is large enough that only the ranking should
be read off it, and the ranking is the one the trends give: the market's quotes
move roughly one-for-one with where the weekend's variance usually sits, and about
half as much with where its mean sits.

An option, however, pays off on expected total variance — an arithmetic mean.
**The market is tracking a real decline, at close to the right speed, in the wrong
moment of the distribution.** §6 shows that no proportional risk premium can move
a variance ratio, so the mismatch is not repaired under the pricing measure. Its
size is the gap between a weekend's typical variance and its average one, and that
gap has been widening: measured as $\log$ mean minus mean $\log$, a scale-free
index of right-tail weight, the weekend's excess over the weekday's runs from
−0.23 in 2020 to +0.31 in 2026 for Bitcoin and −0.07 to +0.27 for Ether. The
weekend has not simply gone quiet; it has become *lumpier* — ordinary weekends
much quieter, rare weekends no less violent. A market that watches the middle of
the distribution will mark the weekend down faster than its mean falls, by
precisely the amount the tail is growing.

Two limits on this, stated rather than buried. Solana and XRP show no trend on
either side, which is consistent with a market-wide arc that began before they
listed, but their standard errors are three to thirteen times the mature books'
and their implied trends rest on nine or ten quarters; no difference test rejects
anything for either, so they neither confirm the mechanism nor contradict it. And
the comparison treats the option side and the bar side as independent when a
volatile week moves both; the dependence is positive, which makes the reported
standard errors conservative for the null that the two trends are equal and
anti-conservative for the null that they differ.

![**Figure 3. What the market tracks.** Left: implied, realized-centre and
realized-mean trends with 95% intervals, per asset. Right: the realized trend as
the trimming fraction deepens.](output/figures/w_f10_learning.png){width=90%}

## 6. Racing the risk-based explanation

Implied and realized quantities are measured under different probability
measures, so a market pricing the weekend above its physical variance could be
charging a risk premium rather than making an error. We take that seriously
enough to race it rather than dismiss it, and two features of the setting
constrain what a premium can do.

**A proportional premium cancels.** Suppose the risk-neutral measure inflates
variance by a factor $\lambda$ applied uniformly to calendar time. Then both the
weekend and the weekday numerator and denominator scale by $\lambda$, and the
*ratio* we measure is unchanged. Only weekend-*specific* risk — something about
Saturday and Sunday that differs in kind, not merely in level — can move the
quantity in Table 2. This is the constraint that makes the ratio formulation
worth the loss of information relative to levels.

**Weekend tails are genuinely fatter.** Standardized for scale, weekend returns
carry 15% to 28% more mass beyond five standard deviations than weekday returns
in all four books. So weekend-specific risk exists and has to be priced
explicitly rather than argued away. (A companion tail-asymmetry result on skew
does *not* replicate — two of the four books move the wrong way — so the race
below runs on tail mass only.)

**Bounding what a jump premium can buy.** Split realized variance in each regime
into a continuous part and a jump part using truncated realized variance, and let
the risk-neutral measure price jump variance at a multiple $\kappa \geq 1$ of its
physical value. The variance a dealer would charge is then the continuous part
plus $\kappa$ times the jump part, and the priced weekend ratio $R^*(\kappa)$ is
monotone in $\kappa$. Its limit as $\kappa 	o \infty$ is therefore a **bound**:
no jump-risk premium of any size can push the priced ratio past it.

The split uses threshold truncation in the sense of Mancini (2009), at three
standard deviations, with the local scale taken from the same day's bipower
variation (Barndorff-Nielsen and Shephard 2004) so that a quieter weekend is not
mechanically classified as jump-free, and with an intraday seasonality factor
estimated separately for each regime in the manner of Andersen and Bollerslev
(1997). Estimating the seasonality within regime matters here in a way it does
not in most applications: a factor pooled across day types would carry the very
weekend effect the paper measures. Truncation misclassifies roughly 0.3% of ordinary
returns by construction; the bias applies to both regimes and largely cancels in
the ratio. That the measured jump shares are not an artefact of the estimator's
floor is checked directly: run on a simulated pure diffusion of the same length
and frequency, the same estimator returns a jump share under 5%, against the 24%
to 36% these series produce.

**Table 6. Residual gap under a jump-risk premium of size $\kappa$.**

| | $\kappa$ = 1 | $\kappa$ = 3 | $\kappa$ = 10 | bound ($\kappa 	o \infty$) | reachable? |
|---|---:|---:|---:|---:|---|
| BTC | +0.051 | +0.034 | +0.019 | **+0.009** | no |
| ETH | +0.039 | +0.048 | +0.056 | **+0.039** | no |
| SOL | −0.098 | −0.139 | −0.184 | **−0.098** | no |
| XRP | −0.136 | −0.144 | −0.150 | **−0.136** | no |

*Implied ratio minus the ratio a market pricing weekend jump variance at
$\kappa$ times physical would quote. "Reachable" asks whether any $\kappa$ closes
the gap.*

**Jump compensation cannot account for the gap in any of the four books, and it
fails in three distinct ways.** Bitcoin is the near miss: a premium does push its
priced ratio toward the quote, but the whole path from $\kappa = 1$ to the bound
closes only 82% of a gap of 0.051, and it takes an unbounded premium to get that
far. Ether fails on *direction* — its weekend is less jump-intensive than its
weekdays, so every increase in $\kappa$ widens the gap, from +0.039 at the
physical measure to +0.056 at ten times it. Solana and XRP fail on *sign*: their
quotes sit below their realized ratios, while a jump premium can only push a
priced ratio up. For those two not even $\kappa = 0$ works — pricing weekend jump
variance at zero still leaves continuous ratios of 0.616 and 0.613 against quotes
of 0.558 and 0.488. Closing their gaps needs a negative price of jump risk, which
is to say a market that pays to hold it.

Sampling uncertainty softens the verdict for any single asset without rescuing
the story. Block-bootstrapping whole weeks and redrawing the implied ratio from
its own sampling distribution, the probability that a jump premium of some size
could reach the market's quote is 0.27 for Bitcoin, 0.13 for Ether, 0.10 for
Solana and 0.11 for XRP. No single one of those rejects at conventional levels.
**What is decisive is that the failure repeats in four books and requires
opposite-signed premia in the two pairs** — a large positive price of weekend jump
risk in the mature books and a negative one in the two listed in 2024. No single
risk premium does both. The result survives 44 estimator settings varying the
truncation threshold, the seasonality treatment and the sampling frequency.

**The option surface agrees, and disagrees with the premium story in the same
direction.** If weekend jump risk were being compensated, the compensation should
be concentrated where jump risk is priced — in the far wings. Estimating the
weekend discount separately across the moneyness ladder, the far wing discounts
the weekend *harder* than the money in all four books, by 0.10 to 0.13. Fitted
jointly so the contrast carries a covariance, the far-wing-minus-at-the-money
difference is −0.121 (*t* = −4.15) for Bitcoin and −0.118 (*t* = −4.95) for Ether,
with equality across the smile rejected outright in both ($\chi^2(3)$ = 18.4 and
28.4, $p < 0.001$). The two small books have the same sign and no precision. The
at-the-money estimates also reproduce Table 2 almost exactly — 0.630 against
0.635 for Bitcoin, 0.639 against 0.645 for Ether — which confirms the widened
sample has not changed the object being measured.

That the wings discount the weekend harder rather than more softly is the
opposite of what weekend jump compensation implies, and it is better read as the
smile's moneyness metric following the weekend clock only partway: a level
adjustment made, and a structural one not.

![**Figure 4. The horse race.** Priced weekend variance ratio as the jump-risk
premium $\kappa$ grows, against each book's quote (diamond). The dashed line is
the bound as $\kappa 	o \infty$. Bitcoin approaches its quote and stops short;
Ether moves away from it.](output/figures/w_f6_horse_race.png){width=85%}

## 7. The error is measurable and has never been harvestable

A pricing error that no one can trade against invites the objection that it is an
artefact of the estimator. This section answers that objection in two steps: the
error does show up in a hedged position, with the right sign and the right
cross-sectional order, and it has nonetheless never cleared the venue's costs.

The trade that isolates the effect is a vega-matched calendar spread: sell the
weekend-heavy contract, buy the weekday-heavy one, delta-hedge both in the
perpetual, hold to settlement. Buckets are assigned within each day's own
cross-section, because an absolute weekend-coverage threshold describes a spread
whose two legs rarely exist at the same time. Costs are measured rather than
assumed — Deribit's 0.03% option fee capped at 12.5% of premium, 0.05% taker on
every perpetual rebalance, and an effective half-spread recovered from the tape by
differencing buyer-paid against seller-received implied volatility on the same
instrument-day — the Roll (1984) intuition applied in volatility units, which the
exchange-provided aggressor flag makes direct rather than inferential.

**Table 7. The spread, gross and net of measured costs (daily rehedging).**

| per unit vega | BTC | ETH |
|---|---:|---:|
| gross spread | +0.0418 | +0.0418 |
| exchange and hedging fees, both legs | −0.0579 | −0.0581 |
| spread crossing, both legs | −0.0083 | −0.0127 |
| **taker net** | **−0.0245** (*t* = −2.09) | **−0.0289** (*t* = −1.82) |
| maker net (earns the spread rather than paying it) | −0.0079 | −0.0036 |

**The gross P&L validates the measurement chain.** Ordering the four assets by
the size of their measured pricing gap orders them by gross trading P&L as well,
without exception: Bitcoin's +0.051 gap and +0.023 gross, down to XRP's −0.133 and
−0.025. This is a stronger check than a single profitable backtest, because the
two legs differ in maturity as well as weekend coverage — a mechanical bias in
which short-dated contracts out-earn longer-dated ones would generate same-signed
P&L in every asset regardless of its pricing gap. Instead the sign and the rank
track the gap across four books with two settlement conventions.

**The signal is nonetheless smaller than the toll.** Of the 0.066 per unit vega a
Bitcoin taker pays, the bid-ask accounts for 0.008 and the remaining 0.058 is
exchange and hedging fees, which fall on a maker exactly as they fall on a taker.
Quoting rather than crossing is worth four half-spreads and closes roughly two
thirds of the gap without reaching zero. Only a maker on a fee tier discounting
option fees by 27% clears zero, at roughly +0.022 per unit vega — and not over the
last twelve months, in which every construction we test loses money.

**The pricing error cannot be harvested by the trade that documents it, and the
obstacle is the venue's fee schedule rather than the market.** That is consistent
with the reading suggested by §5.3: a desk that prices the weekend clock
correctly improves its marks on inventory it holds anyway, at no crossing cost
and no capacity limit, and would leave the quoted gap largely intact while making
it unavailable to anyone who has to cross to reach it. We state that as an
inference, not a measurement — separating it from the alternatives requires
quote-level data this tape does not carry.

## 8. Conclusion

Weekend variance in continuously traded crypto is 34% to 42% below weekday
variance, on a venue that never closes, and roughly 65% below for a tokenized
asset whose own underlying market is shut. Trading is possible throughout, so
this isolates the information-arrival channel from the mechanical effect of
closure — the separation French and Roll (1986) could not make, and which Barclay,
Litzenberger and Warner (1990) approached from the opposite direction by opening
an exchange on Saturdays. Both designs point to trading time rather than calendar
time as the relevant clock, and this one adds a dose-response: raise the amount of
the traditional calendar that is switched off, and the weekend deepens on the same
exchange with the same estimator.

The options market prices most of it. Roughly seven eighths of the realized
weekend effect is in the price in both mature books, identified from contracts
quoted at the same instant that differ only in how much weekend they span. That
is a substantially better performance than the practitioner literature on
calendar-time conventions would suggest, and it is worth stating plainly before
the failures: this market reads the calendar well.

What it gets wrong is not the level but the resolution. All four books treat the
weekend as one undifferentiated block, pricing Saturday as indistinguishable from
Sunday when Saturday is reliably the quieter of the two — and because the two days
sit inside the same weekend, that error cannot be attributed to anything varying
at weekly frequency. The venue's own expiry schedule then makes this specific
error unarbitrageable, offering both legs of the correcting spread in 13 hours of
the week and none of them on a weekday. **The market's one demonstrably wrong
ranking of calendar time is the one its own contract calendar protects.** That is
a more economical account of why an error persists than convention or inventory,
and unlike those it follows from the listing schedule alone.

The implied discount has meanwhile deepened for a decade, at 0.144 and 0.117 per
year. That trend turns out to be a response to a real change in the data measured
against the wrong moment of it. The typical weekend really has been getting
quieter — 0.136 log points a year at the centre of Bitcoin's distribution, against
an arithmetic benchmark that appears flat only because each year's mean is set by
a handful of days. The market tracks the centre; an option pays off on the mean.
Since §6 rules out any proportional risk premium moving a variance ratio, the
mismatch is not repaired under the pricing measure, and its size is the widening
gap between a weekend's typical variance and its average one.

That last result carries a methodological point beyond this application. A ratio
of means of a right-skewed series is a weak estimator, and a weak estimator
returning nothing is not evidence that there is nothing there. Three cheap
diagnostics separate the two — trim the tail and refit, refit at the centre of the
distribution, and walk the sampling interval — and here all three agree that a
non-rejection was a power failure. Where a non-rejection is load-bearing, it
warrants the same scrutiny a rejection would receive.

Three limitations bound these claims. Solana and XRP have standard errors three to
thirteen times the mature books', so they replicate the central realized fact
without sharpening any of the pricing tests, and we have been careful not to lean
on them. The gold result is a lower bound, because PAXG's weekend staleness biases
its measured ratio toward one. And the identification assumes the expiry schedule
is exogenous to weekend variance — a maintained assumption, though a listing
calendar fixed years in advance and uniform across underlyings makes it a mild one.

What we cannot say from a trade tape is *why* a desk would calibrate to the centre
of a right-skewed distribution when the payoff is on its mean. Robust estimation
of a skewed quantity is ordinary practice and defensible on its own terms; it is
simply the wrong practice for this quantity. Separating deliberate robustness from
a fitted model with a thin-tailed error, or from nobody looking, requires
quote-level data and a view of who is on the other side of the trade.

## Electronic companion

The e-companion contains: the full identification appendix and within-day
binscatters for all four assets; the pooled convention test and its power
analysis; robustness of the realized effect across sampling frequencies, jump
truncation thresholds and seasonality treatments; the complete day-of-week
profile tables; the full trimming and sampling ladders behind Table 5; the
44-setting robustness grid behind Table 6; the smile and wing analysis; and the
complete trading results, including the rehedge ladder, the outright-short
variant, the contract-selection sweep and the maker fee decomposition.

A full replication package accompanies the submission: all collection and
estimation code, a mapping from every table, figure and in-text number to the
script that produces it, and the test suite that pins each estimator against
simulated data with a planted answer. No licensed or proprietary data is used —
every input comes from a public API requiring no account or agreement — so the
paper is reproducible from nothing.

---

## References

Alexander C, Imeraj A (2023) Delta hedging bitcoin options with a smile.
*Quant. Finance* 23(5):799–817.

Andersen TG, Bollerslev T (1997) Intraday periodicity and volatility persistence
in financial markets. *J. Empirical Finance* 4(2–3):115–158.

Barclay MJ, Litzenberger RH, Warner JB (1990) Private information, trading
volume, and stock-return variances. *Rev. Financial Stud.* 3(2):233–253.

Barndorff-Nielsen OE, Shephard N (2004) Power and bipower variation with
stochastic volatility and jumps. *J. Financial Econometrics* 2(1):1–37.

Bollen NPB, Whaley RE (2004) Does net buying pressure affect the shape of implied
volatility functions? *J. Finance* 59(2):711–753.

Carr P, Wu L (2009) Variance risk premiums. *Rev. Financial Stud.*
22(3):1311–1341.

French KR, Roll R (1986) Stock return variances: The arrival of information and
the reaction of traders. *J. Financial Econom.* 17(1):5–26.

Gârleanu N, Pedersen LH, Poteshman AM (2009) Demand-based option pricing.
*Rev. Financial Stud.* 22(10):4259–4299.

Hansen PR, Lunde A (2006) Realized variance and market microstructure noise.
*J. Bus. Econom. Statist.* 24(2):127–161.

Mancini C (2009) Non-parametric threshold estimation for models with stochastic
diffusion coefficient and jumps. *Scand. J. Statist.* 36(2):270–296.

Oldfield GS, Rogalski RJ (1980) A theory of common stock returns over trading and
non-trading periods. *J. Finance* 35(3):729–751.

Roll R (1984) A simple implicit measure of the effective bid-ask spread in an
efficient market. *J. Finance* 39(4):1127–1139.

Zhang L, Mykland PA, Aït-Sahalia Y (2005) A tale of two time scales: Determining
integrated volatility with noisy high-frequency data. *J. Amer. Statist. Assoc.*
100(472):1394–1411.
