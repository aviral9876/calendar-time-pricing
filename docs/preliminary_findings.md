# Findings

Full sample, both currencies: **40,557,286 trades** — BTC 24,349,954 over 3,545
days (from 2016-11-29), ETH 16,207,332 over 2,703 days (from 2019-03-21), both
through 2026-08-13. 98.2% survive the baseline filter.

> **Read section 1 before anything else.** The ETH replication changes how the
> cross-sectional result should be reported, and the earlier BTC-only version of
> this document overstated it.

All 21 validation checks pass, including two external ones worth stating: our
independently constructed 30-day ATM implied vol correlates **0.9913** with
Deribit's own DVOL index (and sits 4.0 vol points below it, the expected smile
effect), and implied vol spikes on every crisis date in the sample — COVID
(2.81x), May 2021 (1.88x), Luna (1.62x), FTX (1.52x), ETF launch (1.22x).

**One sample constraint shapes everything below.** Expensiveness needs a
volatility forecast, the forecast needs a two-year burn-in, and realized
volatility starts when the perpetual launched in August 2018. So expensiveness
exists only from **August 2020**, giving ~6 years for the pricing regressions,
even though the demand and inventory series run to 2016. The descriptive and
measurement results use the full tape; the regressions do not.

---

## 1. The cross-sectional result is positive on average but not robust

Bucket expensiveness on lagged dealer vega inventory, day and bucket fixed
effects. **Raw coefficients are not comparable across currencies** — the
normalized demand variable turns out not to be scale-free in practice, with a
standard deviation about eighteen times larger for ETH — so everything is
reported as the effect of a one-standard-deviation move in demand, in vol
points.

| Sample | n | raw β | t | **vol pts per 1 sd** |
|---|---:|---:|---:|---:|
| BTC, full (2020-08 →) | 35,045 | 0.000080 | 2.29 | **+0.557** |
| BTC, matched to ETH window (2022-09 →) | 22,621 | 0.000032 | 0.98 | **+0.172** |
| ETH, full (2022-09 →) | 12,842 | −0.000004 | −2.23 | **−0.656** |

Taken at face value, BTC confirms GPP and ETH significantly *contradicts* it.
Neither reading is right. Two things are going on.

**BTC's result is concentrated in the early period.** Restricted to ETH's
window it falls to +0.172 and loses significance. The headline BTC number is a
2020–2023 phenomenon.

**ETH's negative pooled coefficient is one year.** Year by year:

| Currency | Year | n | t | vol pts per 1 sd |
|---|---:|---:|---:|---:|
| BTC | 2020 | 2,235 | 3.05 | +0.800 |
| BTC | 2021 | 5,840 | 1.78 | +0.878 |
| BTC | 2022 | 5,836 | 2.11 | +0.449 |
| BTC | 2023 | 5,838 | 1.55 | +0.432 |
| BTC | 2024 | 5,856 | −0.62 | −0.090 |
| BTC | 2025 | 5,840 | 0.30 | +0.032 |
| BTC | 2026 | 3,600 | 1.99 | +0.300 |
| ETH | 2022 | 830 | 0.69 | +0.671 |
| ETH | **2023** | 3,260 | **−3.21** | **−0.650** |
| ETH | 2024 | 3,264 | 0.30 | +0.073 |
| ETH | 2025 | 3,344 | 1.97 | +0.252 |
| ETH | 2026 | 2,144 | 0.81 | +0.145 |

**Ten of twelve currency-years are positive**, four significantly so (BTC 2020,
2022, 2026; ETH 2025), against one significant negative (ETH 2023). The pooled
ETH sign is driven entirely by 2023 and should not be reported as a currency
difference.

The defensible statement is therefore: *demand pressure moves expensiveness in
the direction GPP predict, by roughly half a vol point per standard deviation of
demand, but the effect is noisy enough that individual years and subsamples
reverse it.* That is considerably weaker than the BTC-only reading, and it is
what the pooled evidence supports.

Two further qualifications survive from the BTC-only analysis. The
gamma-weighted version is insignificant (t = 1.20), so the result concerns vega
exposure rather than convexity. And the effect **vanishes without bucket fixed
effects** (t = 0.11): identification comes from variation over time within a
bucket, not from which parts of the surface dealers are structurally short —
narrower than GPP's claim.

## 2. The time series holds for BTC and not for ETH

Aggregate expensiveness on lagged market-wide dealer inventory:

| Currency | Specification | n | β | t |
|---|---|---:|---:|---:|
| BTC | levels, no controls | 2,191 | 0.000046 | **7.82** |
| BTC | levels, with controls | 979 | 0.000030 | **3.53** |
| BTC | first differences | 2,190 | 0.000035 | **2.85** |
| ETH | levels, no controls | 803 | 0.000014 | 0.07 |
| ETH | levels, with controls | 435 | −0.000290 | −1.64 |
| ETH | first differences | 755 | 0.000087 | 0.33 |

BTC is strong and survives differencing, which matters because levels
regressions on persistent series invite spurious fit. ETH is null throughout.
ETH's window is both shorter and later (803 versus 2,191 observations), so this
is consistent with the same period pattern as the cross-section rather than a
clean contradiction — but it is not a replication either.

## 3. The return-based test fails in both currencies

Forward delta-hedged returns on current dealer inventory — the cleanest test,
since a traded payoff needs no volatility forecast at all:

| Currency | Horizon | n | β | t |
|---|---:|---:|---:|---:|
| BTC | 1 day | 977 | −6.1e-07 | −0.64 |
| BTC | 5 days | 973 | −1.4e-07 | −0.16 |
| BTC | 22 days | 956 | −1.6e-07 | −0.20 |
| ETH | 1 day | 638 | −3.3e-05 | −0.63 |
| ETH | 5 days | 634 | −1.6e-05 | −0.34 |
| ETH | 22 days | 621 | −4.3e-05 | −1.78 |

Null at every horizon in both currencies, and consistently wrong-signed. GPP
predict that when dealers are long vega, subsequent delta-hedged returns to the
long side are higher.

This is the most demanding version of the test — no volatility forecast, no
constructed dependent variable, just a traded payoff — and it fails twice.

**The null is informative, not underpowered.** At the five-day horizon with
2,658 observations, the minimum detectable effect is about **0.20 vol points**
of delta-hedged return per standard deviation of inventory for BTC and 0.25 for
ETH; the point estimates are +0.03 and −0.03, roughly an eighth of what would
be detectable. Meanwhile the cross-sectional *expensiveness* effect is about
**0.56 vol points** per standard deviation — nearly three times the detection
threshold.

So we can rule out a realized-return premium of the size the expensiveness
result implies. The two are not consistent with each other, and that gap is a
finding rather than a limitation: whatever links dealer inventory to the shape
of the implied surface, it does not show up as compensation actually earned by
someone holding and hedging the option. Under GPP's mechanism it should.

## 4. The funding instrument fails its falsification tests

As the literature review anticipated. Three diagnostics, all negative:

**The first stage is too good.** F = 320, coefficient 0.967 — almost exactly
one. The instrument is `funding shock × lagged exposure` and the endogenous
regressor is `funding × exposure`, so this is close to an identity rather than
evidence of a genuine cost shifter.

**The sign-flip test is insignificant.** A hedging-cost shock should move
expensiveness in opposite directions depending on whether dealers are short or
long the risk. The interaction gives t = −1.11.

**The placebo ladder shows no gradient.** The funding channel cannot reach
buckets that are barely delta-hedged in the perpetual, so the coefficient
should fade toward the deep-OTM end. It does not — deep-OTM long-dated buckets
(|Δ| ≈ 0.06) show coefficients of 24–29 with t up to 3.17, as large as or larger
than at-the-money buckets. What varies is maturity, not delta: every long-dated
bucket loads, every short-dated bucket does not.

ETH reproduces every one of these failures: first stage F = 289 with a
coefficient of 1.05, sign-flip interaction t = −0.34, and a placebo ladder with
no delta gradient (there the loading is on *short*-dated buckets instead, which
is not the predicted pattern either).

That is consistent with funding shocks proxying for a market-wide factor, not
with a hedging-cost channel. **The 2SLS should not be presented as
identification.** Either drop it or demote it to a descriptive statement that
funding covaries with expensiveness at some maturities, and say plainly why
that is not causal.

## 5. The elasticity compresses as capital enters

Cross-sectional β estimated within regimes:

| Period | n | β | t |
|---|---:|---:|---:|
| 2020-03 → 2021-05 | 4,443 | 0.000099 | 3.58 |
| 2021-05 → 2022-05 | 5,677 | 0.000119 | 2.20 |
| 2022-05 → 2022-11 | 2,928 | 0.000024 | 0.80 |
| 2022-11 → 2024-01 | 6,861 | 0.000085 | 1.65 |
| **2024-01 → 2026-08 (post-ETF)** | **15,136** | **0.000031** | **1.41** |

Demand pressure was three to four times stronger in 2020–2022 than after the
US spot ETF launch, despite the post-ETF window having the most observations.

**But the year-by-year standardized estimates in section 1 do not support a
clean monotone decline.** BTC runs +0.80, +0.88, +0.45, +0.43, −0.09, +0.03,
+0.30 from 2020 to 2026 — high early, near zero in 2024–2025, then back up in
2026. ETH shows no trend at all. The honest reading is that the effect was
strongest in 2020–2022 and has been weaker and less stable since, which is
*consistent* with intermediation capacity growing but is equally consistent with
the early period simply being more volatile and thinner.

Presenting this as "the elasticity compresses as capital enters" would be
reading a trend into seven noisy annual estimates. It is suggestive, it is
internal to one market so it needs no cross-market rescaling, and it is worth
reporting — but it is not strong enough to carry the paper's magnitude
argument on its own.

## 6. Measurement validation

**Open-interest reconciliation** — the direct test of the passive-side-is-dealer
assumption, on currently-listed instruments:

| | BTC (693) | ETH (563) |
|---|---:|---:|
| share violating \|net flow\| ≤ open interest | **2.2%** | **3.6%** |
| median \|net\| / OI | **0.29** | **0.44** |
| mean \|net\| / OI | 0.42 | 0.62 |
| correlation of \|net\| with OI | 0.65 | 0.39 |
| share of instruments where end users are net long | 0.49 | 0.54 |

The hard bound essentially holds in both, so the position reconstruction is
sound. But the taker cohort's net position is well under open interest — under a
third at the median for BTC — which bounds what the measure can claim: signed
flow identifies the *directional* component of positioning, not the whole book.
The "passive side is one dealer cohort" reading is only partially supported.

This belongs in the paper rather than in a footnote. As far as I can establish,
it is the first direct test of that assumption in any options market: the
equity literature (Barbon & Buraschi, Baltussen et al.) and the crypto
literature (Atanasova et al., and Glassnode commercially) all validate the
assumption only indirectly, by showing the resulting measure predicts what
theory says it should.

**Sign-inference placebo**, on inventory scaled by trailing gross vega:

| Half-life (days) | BTC | ETH |
|---|---:|---:|
| true signs | **639.9** | **∞** (no reversion) |
| shuffled placebo, mean | 213.7 | 355.7 |
| shuffled placebo, 5th–95th pct | 78.6 – 514.3 | 84.5 – 868.4 |

In both currencies the true series lies at or beyond the top of the placebo
distribution, so the aggressor signs carry real information rather than noise:
a random sign sequence with the same daily magnitudes reverts within a year,
the true one does not. The direction is the opposite of what I expected —
reconstructed inventory is *more* persistent than noise, not faster-reverting.
It reflects positions that accumulate and stay, not dealers rapidly laying risk
off, which is itself informative about how this market intermediates.

## 6b. Market structure

From `t1_market_structure.csv`. Two facts matter for the design. Off-book
activity is small but grew steadily — block trades from 0% to about 1.8% of
trades and combos to 2.2% — which supports excluding them from the baseline
demand measure without materially shrinking the sample. And liquidations
collapsed from 5.6% of ETH trades in 2019 to 0.2% by 2022, so forced flow is
negligible in the modern sample and the decision to keep it is immaterial.

Taker buy share stays near 0.44–0.51 throughout, so the aggressor split is
close to balanced in trade counts; the demand signal lives in the size and
moneyness composition, not in a lopsided count of buys versus sells.

---

## 7. The demand sign reversal — full sample, both currencies

**This is the one result that is unambiguous, and it replicates cleanly.**

BTC, 23,823,359 trades, 2016-11-29 to 2026-08-13:

| Moneyness | Net demand (coin) | Net / gross | Net vega (m USD) | Taker buy share |
|---|---:|---:|---:|---:|
| DOTM | **−875,676** | −0.079 | −67.9 | 0.442 |
| OTM | +68,708 | +0.005 | +1,052.6 | 0.482 |
| ATM | +249,675 | +0.034 | +570.1 | 0.510 |
| ITM | +197,102 | +0.160 | +240.3 | 0.566 |
| DITM | +36,364 | +0.108 | +30.5 | 0.488 |

ETH, 15,917,974 trades, 2019-03-21 to 2026-08-13:

| Moneyness | Net demand (coin) | Net / gross | Net vega (m USD) | Taker buy share |
|---|---:|---:|---:|---:|
| DOTM | **−3,791,151** | −0.045 | −180.9 | 0.437 |
| OTM | −290,093 | −0.002 | +496.1 | 0.463 |
| ATM | +2,984,515 | +0.052 | +555.7 | 0.488 |
| ITM | +1,674,731 | +0.197 | +167.8 | 0.589 |
| DITM | +196,586 | +0.075 | +12.9 | 0.579 |

End users **sell deep-OTM options and buy at- and in-the-money**, rising
monotonically from DOTM through ITM in both currencies, over nearly ten years
and forty million trades. Taker buy share tracks it: 0.44 in the deep wings
against 0.57–0.59 in-the-money.

This mirrors the US index-option demand that generates GPP's smirk, where end
users are net long the wings. It independently replicates Alexander et al.
(2023) — who had BTC only, through 2021 — and extends it to ETH and to the full
history with an independent pipeline.

The vega columns sharpen the story rather than just rescaling it: end users are
net **short** deep-tail convexity but net **long** volatility everywhere else,
by more than a billion dollars of vega in OTM BTC options alone. "Crypto end
users sell options" is the wrong summary. They sell tail insurance and buy
at-the-money volatility.

Corroborating evidence from the bucket panel: deep-OTM buckets carry positive
mean expensiveness (+0.07 to +0.10) against slightly negative at-the-money —
the tails they sell are the tails that are priced rich.

---

## Where this leaves the paper

Scorecard across both currencies:

| Test | BTC | ETH |
|---|---|---|
| Cross-section (GPP prediction 2) | positive, t = 2.3–3.3 | negative pooled, driven by one year |
| Cross-section, year by year | positive in 6 of 7 | positive in 4 of 5 |
| Time series (GPP prediction 1) | positive, t = 2.9–7.8 | null |
| Delta-hedged returns | **null, wrong sign, adequately powered** | **null, wrong sign** |
| Funding instrument | **fails all 3 falsifications** | **fails all 3** |
| Demand sign reversal vs US | confirmed, full sample | **confirmed, full sample** |
| Open-interest bound | holds (2.2% violations) | holds (3.6%) |
| Sign placebo | true outside placebo range | true outside placebo range |

**The pricing results are weaker than the BTC-only run suggested and the
identification strategy does not work.** What survives is real but modest:
demand pressure moves expensiveness in the predicted direction in ten of twelve
currency-years, by roughly half a vol point per standard deviation, without
being reliable in any given year; the realized-return counterpart is absent;
and the funding instrument is not usable.

The paper that these results support is not "demand-based pricing is stronger
where intermediation is unconstrained." It is closer to:

1. **The demand sign reversal** — a robust, clean, economically interesting
   fact about who holds tail risk in crypto versus US index options, and the
   one result that is unambiguous.
2. **The measurement contribution** — the first direct test of the
   passive-side-is-dealer assumption, with a quantitative bound (net taker
   position is a third to a half of open interest) that constrains what every
   paper in this literature, including the published ones, can claim from
   signed flow.
3. **A pricing result that splits in an informative way** — demand pressure is
   detectable in the expensiveness cross-section (≈0.56 vol points per standard
   deviation) but *demonstrably absent* from traded delta-hedged returns, where
   we could have detected 0.20. The two are inconsistent, and under GPP's
   mechanism they should agree.

Point 3 is more interesting than a clean confirmation would have been, because
it separates two things this literature routinely conflates: a correlation
between inventory and the shape of the implied surface, and a risk premium
actually earned for warehousing that inventory. We find the first and can rule
out the second at the implied magnitude. That is a measured negative result, and
it should be framed as one.

**Next steps:** the expiry-day mechanical inventory reset as a cleaner
quasi-experiment than funding (predetermined, and not obviously contaminated by
the perp-basis channel); and a decomposition of what *does* drive the
cross-sectional correlation, given that a warehousing premium apparently does
not.
