# Related work and positioning

Written after a systematic search (August 2026). The headline: **the paper is
not scooped, but the framing it started with does not survive contact with the
literature, and two of its premises were factually wrong.** What follows is the
honest version.

## What is already done

**Alexander, Deng, Feng & Wan (2023), "Net Buying Pressure and the Information
in Bitcoin Option Trades," *Journal of Financial Markets* 63, 100764.**
Deribit BTC options, tick by tick, Jan 2017 – Jul 2021, 3.43m trades, aggregated
hourly. Uses Deribit's native aggressor flag, exactly as we do. Builds
Bollen–Whaley net buying pressure by option type and moneyness bucket, then the
Chen–Wang decomposition into directional and volatility demand, and regresses
**changes in implied vol** on it. Finds limits-to-arbitrage effects throughout.

This is the closest prior work and it establishes that demand pressure moves
implied vol on Deribit. It is a reduced-form flow paper: no dealer inventory
*stock*, no GPP structural elasticity, no identification, no ETH, and it ends in
July 2021.

One of its findings is the most useful fact in this literature for us:
**Deribit end users consistently *sell* OTM and deep-OTM options and *buy*
ATM/ITM** — the mirror image of the net-long-index-put demand that generates
GPP's smirk in US index options. BTC smiles are correspondingly near-symmetric
rather than smirked.

**Atanasova, Miao, Segarra & Willeboordse (2025), "Aggregate illiquidity and
crypto option returns," *Finance Research Letters* 85, 108003.** Deribit BTC,
Jan 2021 – Dec 2024. Builds an **aggregate gamma inventory from signed Deribit
flow**, with the same "net demand negative implies market makers net long"
reading. Outcomes are effective spreads and the cross-section of option returns.
A one standard deviation fall in aggregate gamma inventory widens effective
spreads by 0.12% (OTM calls) to 0.19% (OTM puts).

This partially pre-empts our *measurement*: signed-flow dealer inventory on
Deribit already exists in print. What it does not do is implied-vol levels, the
GPP elasticity, or causal identification.

> **Open item:** the full text was paywalled at all three mirrors. Read it
> before finalizing positioning, specifically to check whether it cites GPP and
> whether it touches IV levels anywhere.

**Glassnode, "Taker-Flow-Based Gamma Exposure" (Dec 2025)** does our exact
measurement commercially, stating the assumption that the maker is a dealer,
with no public validation. Not academic, so not a scoop, but it means we cannot
claim the *measure* is novel, and referees may know it.

**Kim et al. (2025), *Journal of Futures Markets* 45(10), 1512–1543** already
puts GPP and Deribit in one paper, but uses demand pressure as a control rather
than as the object of study.

## Two premises that were wrong

**1. "No designated market maker obligations" is false as stated.** Deribit runs
negotiated market-maker agreements specifying minimum quoting time, instrument
coverage, maximum spreads and minimum quote sizes, plus Market Maker Protection.
The defensible version of the claim is narrower and still interesting:
obligations are *private bilateral commercial agreements rather than
exchange-rule mandates, and are not backed by a mutualized clearinghouse, net
capital rules, or an OCC-style guarantee*. The paper must be reframed to that.

**2. The sample is not one institutional regime.** Deribit moved from the
Netherlands to Panama (2021), became VARA-regulated in Dubai (Jan 2025), and was
acquired by Coinbase (2025). 2017–2018 volumes are thin — Alexander et al. drop
them. A pooled 2016–2026 elasticity would be dominated by regime shifts, so the
subsample split is substantive, not decorative.

## Where the contribution actually is

The question must move from *"does demand pressure matter in crypto"* — answered
twice, yes — to **"is the demand-pressure elasticity different where
intermediation is less constrained, and by how much."** Three things are
genuinely unclaimed:

1. **The GPP structural object, not a reduced-form flow regression.** Prior work
   regresses IV *changes* on flow, or spreads on inventory. Nobody has estimated
   GPP's demand-pressure coefficient — price impact proportional to the variance
   of the unhedgeable component, and cross-contract impact proportional to its
   covariance — on **expensiveness levels** in crypto. The cross-option
   covariance restriction is the identifying content of the model and it is
   untouched. Reporting the elasticity as a number directly comparable to GPP's
   US estimates is the paper.

2. **The sign reversal as the economic headline.** Crypto end users are net
   *short* the wings where US end users are net *long*. That is close to a
   natural experiment on GPP: same model, opposite sign of end-user demand,
   opposite predicted smile shape — and the observed BTC smile is indeed
   near-symmetric rather than smirked. This is a sharper paper than "the effect
   is bigger here," and it is a directional prediction that can fail.

3. **Direct validation of the passive-side-is-the-dealer assumption.** GPP
   observed end-user positions from CBOE open/close codes. Everyone since —
   Barbon & Buraschi, Baltussen et al., Atanasova et al., Glassnode — has
   assumed the maker is a dealer and validated only *indirectly*, by showing the
   measure predicts what theory says it should. **The assumption has never been
   directly tested in any options market.** Deribit publishes per-instrument
   open interest, which yields a hard inequality that no story about
   counterparties can evade:

   > |cumulative signed taker flow| ≤ open interest

   A violation proves missing trades or an inverted sign. The ratio itself
   measures how one-directional the taker cohort is, which is exactly what the
   end-user/dealer reading requires. This is implemented in `dbop/oi.py` and is
   the paper's strongest defensive move — plausibly a contribution in itself.

Supporting differentiators: full 2016–2026 span (Alexander et al. stop in 2021,
Atanasova et al. start in 2021 — nobody has both eras) and ETH replication,
which nobody has done.

## Threats to identification, and what to do about them

**The funding instrument is weak at best, and the paper that undermines it
already exists.** A 2026 *Finance Research Letters* study of Deribit option
expiries documents that perpetual-futures activity *rises around option
expiries* and that spot reversals concentrate where dealer gamma is negative. If
option-dealer hedging flows into the perp move the basis, they move funding *by
construction*, since funding is a function of the basis. That is direct reverse
causality from option demand into the instrument.

Schmeling, Schrimpf & Todorov ("Crypto Carry," BIS WP 1087) attribute funding to
leveraged directional demand from trend-chasing retail and to limited arbitrage
capital. Both plausibly co-move with option demand (the same investors buy calls
and go long perps) and with dealer risk-bearing capacity — the latter being the
Fournier–Jacobs channel, which affects option supply *directly* rather than
through hedging cost, and so violates exclusion.

Consequences for the paper:

- Do **not** present 2SLS as the headline identification. Present it as one
  piece of evidence with the exclusion problem stated plainly up front.
- The falsification tests carry the weight, not the first-stage F. In
  particular the **placebo ladder** (the channel cannot operate in far-OTM
  long-dated buckets that are barely delta-hedged) and the **sign-flip test**
  (a cost shock should move expensiveness in opposite directions depending on
  whether dealers are short or long) are what distinguish a hedging-cost channel
  from a common factor. Both are implemented in `dbop/econo/iv2sls.py`.
- Worth exploring as alternatives: cross-venue funding *dispersion*; funding on
  a venue where these dealers do not hedge; expiry-driven mechanical inventory
  resets, which are predetermined and not obviously contaminated by the same
  channel.
- Exclude expiry windows from the funding-shock sample as a robustness check,
  precisely because that is where the FRL paper locates the contamination.

**Maker is not always a dealer.** Deribit has large passive non-dealer
participants: yield-selling funds, treasury companies, structured-product
issuers, covered-call programs. Given that end users net *sell* OTM options, a
large share of the passive side at OTM strikes may be end-user buyers rather
than intermediaries — which would flip the inventory sign exactly where GPP
predicts the largest effect. This is the sharpest single objection to the paper
and the open-interest reconciliation is the response to it.

**Inverse-option conventions are not optional.** Alexander, Chen & Imeraj (2023,
*Mathematical Finance* 33(4)) on inverse and quanto options, and Alexander &
Imeraj (2023, *Quantitative Finance* 23(5)) on delta hedging BTC options with a
smile, establish that Black–Scholes deltas are materially wrong for BTC even
before the inverse adjustment. Our greeks use the premium-adjusted inverse delta
for exactly this reason; a delta-weighted demand measure carried over unmodified
from the equity literature would be misspecified.

## The GPP lineage, for the benchmark comparison

| Paper | Outlet | Market | What it gives us |
|---|---|---|---|
| Gârleanu, Pedersen & Poteshman (2009) | *RFS* 22(10) 4259 | CBOE 1996–2001, true end-user positions | The model and the benchmark elasticity |
| Bollen & Whaley (2004) | *JF* 59, 711 | SPX + equity | The delta-weighted NBP measure everyone uses |
| Muravyev (2016) | *JF* 71(2), 673 | US equity options | Inventory-risk component dominates asymmetric information; ~5x larger price impact than previously estimated. The best methodological template for separating the two |
| Chen, Joslin & Ni (2019) | *RFS* 32(1), 228 | DOTM SPX puts | Infers intermediary constraint tightness from quantities |
| Fournier & Jacobs (2020) | *JFQA* 55(4), 1117 | SPX | Structural MM inventory and wealth; the omitted channel that threatens our exclusion restriction |
| Jacobs & Mai (2024) | *J. Empirical Finance* | VIX options | The closest "GPP in a second market" precedent |

Non-US tests (Hang Seng, KOSPI 200, TAIEX) are all Bollen–Whaley lineage rather
than structural GPP. **No test of GPP's structural model on commodities or FX
was found**, which is worth a sentence: the model has been tested in
strikingly few markets.

## Bottom line

Lead with the sign reversal and the elasticity comparison; make the open-interest
reconciliation a first-class result rather than a footnote; present the funding
instrument honestly as suggestive and let the falsification tests carry it; fix
the market-maker-mandate claim; and split the sample by regime.
