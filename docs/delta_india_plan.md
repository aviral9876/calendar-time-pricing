# Delta Exchange India: data plan and strategy research plan

Written 2026-08-25. Everything below was verified live against
`https://api.india.delta.exchange/v2` unless marked otherwise.

## 0. What the venue gives us (verified)

| Item | Status | Evidence |
|---|---|---|
| Live option chain | 692 BTC + 332 ETH + 118 XAUT contracts | `/v2/tickers?contract_types=call_options,put_options` |
| Expiries | daily, weekly, monthly: 250826, 260826, 270826, 280826, 040926, 110926, 250926, 301026 | ticker symbols |
| Liquidity | BTC options 24h turnover ≈ **$3.54B**, OI ≈ $679M; near-expiry ATM strikes trade $90–225M/day each | tickers `turnover_usd`, `oi_value_usd` |
| 1m candles | ≥ 13 months history (checked 400 days back, data from Jul 2025 returned) | `/v2/history/candles?resolution=1m&symbol=BTCUSD` |
| **Expired options keep history** | traded candles AND `MARK:` (model) candles both return after expiry | `C-BTC-80000-210826` and `MARK:C-BTC-80000-210826` both served data post-expiry |
| Trades with aggressor side | `buyer_role`/`seller_role` maker/taker on every print | `/v2/trades/BTCUSD` |
| Greeks + bid/ask IV in tickers | delta/gamma/vega/theta, `bid_iv`/`ask_iv`/`mark_iv`, best bid/ask with sizes | ticker payload |
| Rate limit | 10,000 req-units / 5 min; candles are cheap reads | docs |

Limitations, equally important:

* `/v2/trades` is **recent-only** — no historical tape endpoint. A signed-flow
  history on Delta must be built forward by polling/WS from day one.
* Tickers are snapshots — bid/ask IV history must also be collected forward.
* No public L2 history; `/v2/orderbook` is current-state only.
* Backtests on the past 13 months therefore rest on **candles (traded + mark)**,
  which is enough for expiry-anchored strategies but not for microstructure ones.

## 1. Cost model (this decides everything)

Delta India option fee: **0.03% of notional, capped at 3.5% of premium**,
futures/perp taker 0.05% — and **+18% GST on all fees**. Compare Deribit
(0.03% capped at 12.5%): the *cap* is much tighter here, which is materially
**friendlier to short-dated OTM options**, but GST claws back a fifth.

Effective spread: observed near-expiry ATM bid/ask IV gaps of ~0.5–3.0 vol pts
(e.g. 58.5/61.2, 41.6/42.1). Wings are far wider. Extend `dbop/costs.py` with a
`delta_india` fee schedule and estimate effective spread two ways: (a) quoted
bid/ask IV from our own ticker polling, (b) Roll-style buy-vs-sell IV from the
polled tape, reusing `effective_spread_iv`.

**Gate: no strategy graduates unless its gross edge is > 2× the round-trip cost
(fees + GST + half-spread both legs + hedging perp fees).**

## 2. Data collection

### 2a. Historical backfill (runs once, ~13 months)

1. Symbol discovery for the past: reconstruct expired option symbols from the
   grid (daily expiries × strike ladder) and probe `/v2/history/candles` — the
   venue serves expired symbols, so discovery-by-probe works. Cache misses.
2. For every option symbol: 1h (and 5m near expiry) **traded** candles and
   **MARK:** candles → `data/delta_india/options/{CUR}/`.
3. Underlying: 1m `BTCUSD`, `ETHUSD` perp candles + `MARK:` → realized vol,
   hedging prices, and funding proxy.
4. Reuse `dbop` modules: Black-76 inversion (`greeks.py`) on mark candles to
   build an IV surface history (`surfaces.py` grid), realized vol (`rv.py`).

### 2b. Forward collection (start immediately — this data cannot be recovered later)

* Poll `/v2/tickers` (full option chain) every 5 min → bid/ask IV, sizes, OI,
  greeks snapshots.
* Poll `/v2/trades/{symbol}` for the top-OI options + perp every 1–2 min
  (or WebSocket `trades`/`ob_l2` for a clean feed) → signed tape, the input
  `inventory.py` needs.
* Daily OI snapshot per instrument → rerun the OI-reconciliation bound test on
  this venue.

Windows Task Scheduler or a small always-on poller; resumable like `backfill.py`.

## 3. Strategy candidates, ranked by prior evidence

### S1 — Weekend variance premium (primary; our own Deribit result)

`docs/alternative_directions.md`: BTC realized vol is **26% lower** on weekends
but weekend-expiry options are only **13%** cheaper — implied prices half the
effect. Delta India lists **daily expiries including weekend-spanning ones**, so
the trade is directly implementable here:

* Short Friday-open → Monday-expiry ATM straddles (or Sat/Sun expiries when
  listed), delta-hedged in the perp at fixed intervals.
* Backtest on 13 months of Delta mark + traded candles; cross-validate the same
  dates on our Deribit tape (already built).
* Conditioning per the caveat already recorded: match by date, control for vol
  level, check it is not a maturity artifact.
* Robustness: does the gap survive on Delta specifically? Indian retail flow may
  price weekends differently from Deribit's institutional book.

### S2 — Cross-venue IV basis: Delta India vs Deribit (new, venue-specific)

An FIU-registered INR venue with heavy retail flow against the global
institutional venue for the *same* underlying and near-identical expiries. We
already hold ten years of Deribit surfaces; polling gives us Delta's.

* Map matched (strike, expiry) pairs; measure `IV_delta − IV_deribit` by
  moneyness/tenor; test persistence, direction (retail net buying should make
  Delta systematically rich, plausibly in wings), and mean-reversion horizon.
* Tradeable as sell-rich-venue / buy-cheap-venue if the basis exceeds combined
  costs; also valuable one-sided (choose which venue to express S1/S3 on).
* Needs only forward-collected tickers plus the existing Deribit pipeline;
  first read after ~4–6 weeks of polling.

### S3 — Tail-insurance richness (from the demand-reversal finding)

Our one unambiguous Deribit result: end users net-sell DOTM and DOTM buckets
carry positive expensiveness (+0.07–0.10). On Delta the retail composition may
*invert* the sign (Indian retail lottery-buying wings, as in Indian equity
options). Measure first, then decide which side to be on:

* Build the moneyness-bucket net-demand table (section 7 of
  `preliminary_findings.md`) from the polled Delta tape.
* Delta-hedged returns by bucket (existing machinery) on the 13-month mark
  history to see which buckets are rich after costs.

### S4 — Expiry-day mechanics (daily expiries = 5× the events)

Already flagged as the next step in the findings doc: expiry inventory resets as
a quasi-experiment. Delta's daily expiries give ~30 events/month. Descriptive
first: pinning, pre-expiry IV behavior of next-day contracts, post-expiry
surface reset. Only promote to a strategy if the pattern is stable across ≥6
months of events.

**Not pursued:** funding-instrument-style identification (failed all
falsifications on Deribit); liquidation flow (too thin to matter).

## 4. Execution plan and gates

| Phase | Work | Gate to proceed |
|---|---|---|
| 1 (days 1–3) | Start forward pollers; write `delta_india` fee/cost module; backfill underlying 1m candles | pollers stable 48h |
| 2 (week 1–2) | Backfill expired-option candle history; validate: our Black-76 IV vs ticker `mark_iv` on live symbols (target corr > 0.99, like the DVOL check) | validation passes |
| 3 (week 2–4) | S1 backtest on Delta history, net of full cost model, with the vol-level conditioning | Sharpe > 1 net, edge > 2× costs, sign stable across quarters |
| 4 (week 4–8) | S2 basis study as ticker history accrues; S3 bucket tables from polled tape; S4 descriptives | any effect > 2× costs |
| 5 | Paper-trade the survivor(s) 4+ weeks against live quotes (fills at bid/ask, not mark) before any capital | paper P&L consistent with backtest |

Deliverables land in the existing structure: `dbop/venues/delta_india.py`
(API client + schedule), `scripts/run_delta_backfill.py`,
`docs/delta_india_findings.md`.

## 5. Risk and compliance notes (flags, not advice)

* Short-straddle strategies (S1) have unbounded tail loss; size via the
  worst-weekend move in our ten-year Deribit history (COVID weekend, May 2021),
  not the 13-month Delta sample, and always specify a stop/hedge rule in the
  backtest.
* Settlement is USD-quoted but the venue is INR-funded; INR/USD conversion and
  the Indian tax treatment of crypto-derivative gains need independent
  verification with a tax professional — the cost model should carry a
  configurable tax haircut.
* Venue risk: single FIU-registered exchange, no clearinghouse; cap allocation.
* Marks vs fills: every backtest must price entries at traded candles or quoted
  bid/ask, never at mark, for the headline P&L number.
