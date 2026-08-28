# The price of calendar time in a market that never closes

Research code and replication package for two papers on how crypto options price
the weekend.

Asset prices are far more volatile when exchanges are open than when they are
shut — a fact established by French and Roll (1986). Distinguishing *information
arrival* from the mechanical effect of *closure* has never been possible in
equity markets, because "the exchange is closed" and "no one is trading" are the
same event. Crypto separates them: Deribit trades continuously while the
traditional financial system does not.

## The papers

**[The Price of Calendar Time in a Market That Never Closes](paper/weekend_ms.pdf)**
— the identification result.

Weekend realized variance is 34% to 42% below weekday variance across four
underlyings, on a venue that never closes, and 65% below for tokenized gold,
whose own market in London and on COMEX *is* shut all weekend. Because Deribit
lists daily expiries on all seven weekdays, contracts quoted at the same instant
differ in how much weekend they span, which identifies the market's implied
weekend discount from purely within-instant variation. The market prices roughly
seven eighths of the effect. Its one demonstrable failure is *within* the
weekend: all four books price Saturday as indistinguishable from Sunday when
Saturday is reliably quieter — and the venue's own expiry schedule makes that
error unarbitrageable, offering both legs of the correcting spread in 13 hours of
the week, none of them on a weekday.

**[The Half-Life of a Pricing Error](paper/decay.pdf)** — can it be traded?

No, and the obstacle is the fee schedule rather than the market. The calendar
spread that isolates the error earns +0.042 per unit vega gross, which tracks the
pricing gap across all four books in the right order, and meets 0.066 of measured
exchange fees, hedging costs and spread. Only a market maker on a fee tier
discounting option fees by 27% has ever cleared zero, and not in the last year.

The full working paper, from which the submission draft was cut, is
[`paper/weekend.pdf`](paper/weekend.pdf) — 40 pages, 35 tables, including the
robustness material that the submission moves to an electronic companion.

## Replication

**[REPLICATION.md](REPLICATION.md)** maps every table, figure and in-text number
to the script and output file that produces it, with data provenance, expected
runtimes and the integrity checks built into collection.

Everything is built from Deribit's free public API. No account, no key, no vendor
data, no licensed sources — a replicator with an internet connection can rebuild
both papers from nothing.

```bash
pip install -e .
python scripts/run_backfill.py --all    # collect (overnight per currency)
python scripts/run_weekend_all.py       # estimate everything (offline)
```

## Tests

```bash
python -m pytest tests/ -q              # 238 tests, ~100 s
```

These are not smoke tests. Each estimator is checked against simulated data with
a planted answer, so a failure means a number in a paper would be wrong. Some
examples of what they pin:

- the arithmetic and geometric weekend estimators each recover their own estimand
  and neither recovers the other's
- the sampling ladder points one way for a real trend seen through noise and the
  *opposite* way for one manufactured by noise that is itself shrinking
- the jump/continuous split returns a jump share under 5% on a pure diffusion
- a strategy P&L that differences two separately-costed positions charges both
  legs' costs rather than crediting one — this one exists because it did not

## Layout

```
dbop/            library: API client, instrument parsing, greeks, bars,
                 realized variance, weekend arithmetic, cost model
scripts/         one stage per file; run_weekend_all.py sequences them
tests/           pytest suite
output/tables/   every CSV the papers cite
output/figures/  PNG and PDF
paper/           manuscripts and their build script
docs/            data_notes.md — every correction made during the project,
                 what caused it, and what now guards against it
```

`data/` is excluded from version control: 2.8 GB across 41.5 million option
trades, rebuilt by `scripts/run_backfill.py`.

## A note on the package name

The package is called `dbop`, for "demand-based option pricing" — the project
this repository was originally started for, which these papers are not. The name
is kept because it appears in every import; the research it describes is in
`paper/main.md` and was not pursued.

## Corrections

`docs/data_notes.md` records four errors found during the project, the
superseded numbers, and the guard now in place for each. The most consequential
was a strategy P&L assembled by differencing two separately-costed short
positions, which silently reversed the sign of one leg's costs and turned a trade
that never covered its costs into an apparent Sharpe of 1.5. Every leg was
individually correct and every test passed; only the combination was wrong.

## License

Code is MIT. The papers are drafts and are not for redistribution in modified
form.
