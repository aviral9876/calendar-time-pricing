# Weekend risk: the academic path and the commercial path

Both start from the same fact and diverge on what counts as success. The
academic path needs identification; the commercial path needs an edge that
survives measured costs. They reach opposite verdicts, and the reason they
diverge is itself the interesting part.

---

# Path A — academic. Verdict: strong, and worth writing.

## The fact

Crypto trades continuously; the traditional financial system does not. Realized
variance still collapses at the weekend:

| | Weekday variance | Weekend variance | Ratio | t |
|---|---:|---:|---:|---:|
| BTC (2,089 / 834 days) | 0.001418 | 0.000828 | **0.584** | 11.0 |
| ETH (1,223 / 488 days) | 0.002880 | 0.002448 | **0.850** | 3.1 |

BTC weekend *variance* is 42% lower — Saturday is the quietest day of the week —
in a market that never shuts. Because crypto itself stays open, this isolates
information arriving during traditional market hours from the mechanical effect
of an exchange being closed. French & Roll (1986) could not separate those two
in equities, because closure and non-trading are the same event there. This is
the cleanest available measurement of that channel.

## The pricing test

Total variance over an option's life decomposes as

    sigma^2 = v_wd + (v_we - v_wd) * w

with `w` the fraction of remaining life falling on a Saturday or Sunday.
Deribit lists daily expiries on all seven weekdays, so `w` varies across
contracts trading **at the same instant** — a Thursday offers a Friday expiry
with `w = 0` and a Monday expiry with `w > 0.5`. Regressing squared implied vol
on `w` with day fixed effects identifies the slope purely from that
within-instant variation, absorbing the level of volatility and everything else
common to the day.

BTC, 1,206,483 trades over 3,172 days, SEs clustered by day, controlling for
log-maturity, its square, and moneyness:

| | Variance ratio |
|---|---:|
| slope on `w` | −0.0780 (se 0.0212, **t = −3.7**) |
| implied weekend/weekday ratio | **0.898** |
| realized weekend/weekday ratio | **0.584** |
| **gap** | **+0.314** |

The market knows weekends are quieter — the slope is negative and significant,
and Monday expiries (which span the weekend) are the second-cheapest of the week
— but it discounts them by only about 10% when realized variance is 42% lower.
**Options systematically overprice weekend variance**, by roughly 3.1 vol points
on a contract whose weekend coverage is 40 percentage points above a comparable
one.

## The mechanism test: the market uses one weekend discount for both assets

ETH replicates the direction — the slope is negative and significant there too —
and the comparison is where the paper's argument lives:

| | Realized ratio | Implied ratio | Gap | slope t |
|---|---:|---:|---:|---:|
| BTC | **0.584** | 0.898 | **+0.314** | −3.7 |
| ETH | **0.850** | 0.906 | **+0.056** | −2.8 |

The *implied* weekend discount is essentially identical across the two assets —
0.898 and 0.906, about 10% in both — while the *realized* weekend effect differs
enormously, 42% for BTC against 15% for ETH. The market applies what looks like a
single, roughly uniform weekend adjustment regardless of the underlying. That
convention happens to be about right for ETH and badly wrong for BTC.

This is a much sharper claim than "options overprice weekends," and it is
falsifiable: a market calibrating weekend risk asset-by-asset would produce
implied ratios that track the realized ones. They do not — they barely move,
while the realized ratios differ by a factor of nearly three in log terms. It
also explains the asymmetry naturally: BTC carries far more
traditional-finance-linked flow (the ETF complex, institutional hedging), so it
has the larger true weekend effect, and the one-size-fits-all discount fails
hardest exactly there.

## Why this is publishable

The question is canonical, the identification is novel and available nowhere
else, the fact is large and highly significant in both currencies, and the
cross-asset comparison delivers a mechanism rather than just an anomaly. The
partial risk-based explanation below keeps it honest.

## The honest complication

Weekend returns are not merely smaller. Standardizing each regime by its own
volatility, BTC weekend returns are **1.8x more negatively skewed** (−1.25 vs
−0.69) with modestly fatter tails (P(|z|>5) of 44.2bp vs 38.4bp). So part of the
implied premium is compensation for weekend jump risk that average realized
variance does not capture — thin weekend liquidity, no traditional market to
hedge into. It is not enough to explain a 0.314 gap, but the paper must model it
rather than claim a pure mispricing. ETH's tail evidence is mixed and noisy.

---

# Path B — commercial. Verdict: REVISED — it is a trade, and a decaying one.

> **This section was wrong when first written.** It concluded the effect was
> unharvestable, on data corrupted by the index-alignment bug documented in
> `data_notes.md`. Corrected, the spread trade earns a Sharpe ratio of 1.50 net
> of measured costs, and the "P&L noise is 160x the edge" argument was an
> artefact — the true per-trade dispersion is 0.19, not 5.0. The original text
> is kept below the line for the record, because the *reasoning* about power was
> sound and only the inputs were wrong.

## Corrected result

Vega-matched calendar spread, sell weekend-heavy and buy weekday-heavy,
delta-hedged in the perpetual, held to settlement. BTC, 1,231 paired days, per
unit vega, net of Deribit fees and a measured 0.42 vol-point half-spread:

| Rehedge | Level gross | Level net | Spread net | t | Sharpe |
|---|---:|---:|---:|---:|---:|
| 5 min | +0.0445 | −0.0896 | +0.0209 | 3.83 | 1.73 |
| 1 hour | +0.0539 | −0.0038 | +0.0160 | 2.51 | 1.13 |
| 8 hours | +0.0614 | +0.0244 | +0.0288 | 3.19 | 1.44 |
| daily | +0.0583 | +0.0251 | **+0.0391** | **3.33** | **1.50** |

The level is positive gross at every frequency, as the variance risk premium
requires — it only turns negative net under five-minute rehedging, where perp
taker fees are paid ~2,000 times per contract. Best net Sharpe comes from daily
rehedging, where fees are lowest.

**The edge decays.** First half +0.0343 (t 3.80), second half +0.0076 (t 1.24).
Roughly a quarter of the original size and no longer significant — consistent
with the trade being gradually competed away.

**Practical caveats before anyone sizes this.** Capacity is unmeasured and the
relevant contracts are short-dated and thin; the backtest takes one entry per
bucket per day at the first qualifying print, which is optimistic on fills; and
the decay means the current-day edge is likely far below the full-sample figure.

---

## Original (incorrect) analysis, retained for the record

## What was actually tested

Sell the weekend-heavy contract, buy the weekday-heavy one, vega-matched,
delta-hedged in the perpetual, held to settlement. Buckets are assigned **within
each day's own cross-section** — an absolute threshold makes the two legs nearly
mutually exclusive, since Fridays offer weekend-heavy contracts and Tuesdays
offer weekday-only ones, so a fixed cutoff describes a spread that could almost
never be put on.

Costs are measured, not assumed:

* **Fees**: Deribit charges 0.03% of the underlying on options, capped at 12.5%
  of the premium (the cap binds constantly on short-dated contracts), plus 0.05%
  taker on the perpetual hedge, plus delivery fees when settling in the money.
* **Spread**: we have no order book, but every trade carries its aggressor side,
  so buyer-paid minus seller-received implied vol on the same instrument-day is
  twice the effective half-spread. **Measured: 0.62 vol points** (median, 5,420
  instrument-days).

## Result

| | mean per vega | t | Sharpe |
|---|---:|---:|---:|
| gross of all costs | −0.046 | −0.21 | −0.15 |
| net of fees and spread | −0.054 | −0.25 | −0.18 |

Nothing, and it is not costs doing the killing — the gross number is just as
dead.

## But the null is uninformative, and that is the real finding

The pricing gap implies an edge of **+3.14 vol points**, or 0.031 per unit vega.
The realized per-trade P&L has a standard deviation of **5.0 per unit vega**.
With 504 paired days the standard error is 0.22 — **seven times the entire
expected edge**. Detecting it at 80% power would need roughly 199,000 daily
observations, about 545 years.

The obvious suspect was discrete-hedging error, so the backtest was rerun at
**5-minute** rehedging instead of 8-hourly, a 96-fold increase in frequency.
The noise did not move (sd 4.95 versus 4.97). The dispersion is therefore not
hedging error but genuine realized-versus-implied variance dispersion,
concentrated in the handful of expiries where a short-dated option finishes far
in the money against a vanishing vega. That is not fixable by trading more
carefully.

**So the honest verdict is not "no edge" but "this edge cannot be harvested by
this trade."** A 3-vol-point systematic mispricing sits underneath P&L noise two
orders of magnitude larger.

One loose end worth chasing before closing the file: the second half of the
sample is positive and significant net of costs (+0.053, t = 2.97) against
−0.160 in the first half. That is either a regime change as the market matured
or a few early blowups dominating a heavy-tailed average — most likely the
latter, but it has not been established either way.

## Where the commercial value actually is

Not a strategy — a **pricing input**. A desk quoting short-dated crypto options
against a flat calendar-time clock is systematically wrong on every contract
spanning a weekend, and the error is largest exactly where retail flow
concentrates (short-dated, near the money). The applications are:

1. **Quoting and risk systems** — a weekend-aware time clock in the term
   structure. Worth real money to a market maker without one, and it needs no
   tradeable alpha to pay for itself.
2. **A surface/analytics data product** — a corrected short-dated term structure
   for the roughly ten instruments per day where the effect is material.
3. **Execution timing** — the same information tells a directional trader when
   to buy or sell short-dated vol, which is a cost saving rather than a
   strategy.

None of these require the mispricing to be arbitrageable. They require it to be
*real*, which Path A establishes at t = −3.7.

---

# Recommendation

Run Path A as the paper; it is the strongest result this dataset has produced.
Treat Path B as a pricing-model improvement rather than a strategy, and drop the
vol-arb framing — the P&L noise makes it unwinnable as a standalone trade, and
saying so precisely (edge 0.031, SE 0.22, unchanged by 96x more frequent
hedging) is more useful than a vague "didn't work."

The two paths together also give the paper its economic close: the mispricing
survives *because* it is not arbitrageable. That is a limits-to-arbitrage story
with a measured, quantitative bound on why no one has traded it away — which is
a far better ending than claiming to have found free money.
