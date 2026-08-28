# Demand-Based Option Pricing Without a Clearinghouse

*Working title. Target: Management Science / Review of Finance.*

---

## Framing

Gârleanu, Pedersen and Poteshman (2009) show that when end users are net long an
option, risk-averse intermediaries who take the other side must be compensated
for the risk they cannot hedge, so the option trades rich. The model has been
tested in remarkably few markets, and always in ones where intermediation is
shaped by exchange rules: designated market makers with affirmative obligations,
a mutualized clearinghouse, and net capital requirements.

Crypto option markets are the natural place to ask what demand-based pricing
looks like when those scaffolds are absent. Deribit does maintain private
market-maker agreements with quoting obligations, so the market is not
unintermediated — but those are bilateral commercial arrangements rather than
exchange mandates, there is no OCC-style guarantee, and dealers hedge
continuously in a perpetual future whose funding rate is a directly observable
carry cost.

Two features make this more than a replication.

**End-user demand has the opposite sign.** In US index options end users are net
*long* the wings, especially OTM puts, which is what generates the smirk in the
GPP account. On Deribit end users are net *short* OTM options and net long
at-the-money — and the BTC smile is correspondingly near-symmetric rather than
smirked. The same model applied to inverted demand makes an inverted prediction
about surface shape, which can fail.

**Positions can be reconstructed and then checked.** Deribit's tape carries the
aggressor side natively, and every option ever traded is in the sample, so
cumulative signed flow identifies the net position of the taker cohort exactly.
Whether that cohort is "end users" facing dealers is an assumption — the same
one made throughout this literature — but here it can be tested directly
against reported open interest rather than only validated by its consequences.

## Contributions

1. The GPP demand-pressure elasticity estimated on **expensiveness levels** in
   crypto, in units directly comparable to the published US estimates, rather
   than a reduced-form regression of implied-vol changes on flow.
2. A direct test of the **passive-side-is-the-dealer** assumption that
   underpins every inventory measure in this literature, using the inequality
   |cumulative signed taker flow| ≤ open interest.
3. The **sign-reversal test**: inverted end-user demand, inverted smile
   prediction.
4. Full **2016–2026** coverage of BTC and ETH. Existing work covers 2017–2021
   (BTC only) or 2021–2024 (BTC only).

---

## Section plan

### 1. Introduction
Lead with the sign reversal, not with "crypto is unregulated." State the
elasticity comparison as the headline number. Be explicit that identification
is partial and that the paper's defensive strength is measurement validation.

### 2. Institutional setting
Deribit's market-maker agreements and what they do and do not require; absence
of a mutualized clearinghouse; inverse (coin-margined) contracts; continuous
delta hedging in the perpetual and what funding is. Regime timeline:
Netherlands → Panama (2021) → VARA/Dubai (Jan 2025) → Coinbase (2025). Justify
the subsample splits here rather than treating them as robustness.

### 3. Data and measurement
Source and construction (`docs/data_notes.md` has the verified specifics).
Emphasize three measurement decisions that matter and were tested rather than
assumed:
- **Forward, not index.** Deribit prices options off the per-expiry forward; the
  forward curve is built from ~480 dated futures and interpolated. Using the
  index instead biases recomputed IV by up to +12 vol points at long maturities
  in contango.
- **Inverse-option greeks.** The perpetual hedge ratio is the premium-adjusted
  delta, not the Black delta (Alexander, Chen & Imeraj 2023).
- **Flow vs stock.** Flow is signed volume at trade-time greeks; inventory is
  the accumulated position revalued daily on the fitted surface, because an
  option bought at the money is a different exposure three weeks later.

#### 3.4 Does the passive side absorb the flow? *(first-class result)*
The open-interest reconciliation. Report the share of instruments violating the
bound (should be ~0), the distribution of |net|/OI, and how one-directional the
taker cohort is. Then the sign-shuffle placebo on inventory mean reversion. Then
the block/combo/liquidation decomposition. State plainly what this cannot rule
out: passive non-dealer participants (yield-selling funds, structured-product
issuers, covered-call programs), which is the sharpest objection to the paper.

### 4. Descriptive: who trades what
Volume, instruments and off-book share by year. **The demand-sign table** — net
end-user demand by moneyness bucket — set directly against the GPP equivalent.
This is where the sign reversal is established.

### 5. Cross-section
Bucket expensiveness on lagged dealer inventory, day and bucket fixed effects,
two-way clustered and Driscoll–Kraay standard errors. Gamma-weighted variant for
short maturities. Robustness: excluding liquidations, including blocks,
alternative normalizations.

### 6. Time series and delta-hedged returns
Aggregate inventory against expensiveness in levels and changes. Then the
return-based test, which needs no volatility forecast at all: forward
delta-hedged returns on current inventory, with the perpetual's funding carry
subtracted explicitly.

### 7. Hedging cost and the funding channel
**Present honestly.** State the exclusion problem before the results: option
dealers hedge in the perp, perp flow moves the basis, and funding is a function
of the basis — so the instrument is contaminated by the very channel it is meant
to isolate. The 2SLS point estimate is one piece of evidence; the weight is
carried by the falsification tests:
- placebo ladder across buckets (the channel cannot reach barely-hedged far-OTM
  long-dated buckets);
- sign flip (a cost shock must move expensiveness in opposite directions
  depending on whether dealers are short or long);
- excluding expiry windows, where the contamination is documented.
If the falsifications do not come out clean, report that and downgrade the
section to a descriptive channel test rather than an identification claim.

### 8. Magnitudes: crypto against US equity options
The headline comparison, both scaled per standard deviation of demand relative
to market size. Derivation of the benchmark from GPP's published coefficients
goes in `docs/gpp_calibration.md` so it stays auditable. Subsample estimates:
does the elasticity compress as institutional capital enters?

### 9. Robustness
Expiry-day inventory resets as an auxiliary quasi-experiment (predetermined and
mechanical). ETH replication. Subsample stability. Alternative expensiveness
measures (BKM variance risk premium). Alternative inventory normalizations.

### 10. Conclusion

---

## Status: results are in — see `docs/preliminary_findings.md`

Full sample built and estimated for both currencies (40,557,286 trades). All 21
validation checks pass in each. **The results require the section plan above to
be revised**, and the revision is not cosmetic.

**What survived.** The demand sign reversal, cleanly, in both currencies over
the full history — end users sell deep-OTM and buy at- and in-the-money,
monotonically. The measurement contribution: the open-interest bound holds
(2.2% BTC / 3.6% ETH violations) while showing net taker position is only a
third to a half of open interest, which bounds what *any* signed-flow inventory
measure in this literature can claim.

**What did not.** The funding instrument fails all three falsification tests in
both currencies — do not present it as identification. The delta-hedged return
test is null in both, and adequately powered: we could have detected 0.20 vol
points per standard deviation and found 0.03, while the cross-sectional
expensiveness effect is 0.56. The cross-sectional result itself is positive in
ten of twelve currency-years but reverses in some, so it is a tendency rather
than a robust regularity.

**Consequences for the plan above.** Section 7 (funding channel) should be cut
or demoted to description. Section 8's cross-market elasticity comparison loses
its footing, since our own estimate is unstable — lead instead with the
inventory/expensiveness versus inventory/returns split. Section 6 becomes a
central negative result rather than a supporting one. Section 4's demand-sign
table is promoted to the paper's opening empirical exhibit.

The honest paper is: *crypto end users hold the opposite tail exposure to US
index-option end users; dealer inventory correlates with the shape of the
implied surface; but no one is actually paid for warehousing it.* The third
clause is the contribution, and it is a negative result stated precisely.

Open items:
- [ ] Read Atanasova et al. (2025) in full; confirm what it does and does not claim.
- [ ] Expiry-day inventory resets as a replacement quasi-experiment.
- [ ] Given the return null, decompose what drives the cross-sectional correlation.
- [ ] `docs/gpp_calibration.md` benchmark — lower priority now that the
      cross-market magnitude comparison is no longer the headline.
- [ ] Consider dropping 2017–2018 for thin volume, as Alexander et al. do.
