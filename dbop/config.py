"""Paths and tunable constants for the demand-based option pricing study.

Data root is overridable with DBOP_DATA so the multi-GB trade tape can live on a
different drive from the code.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DBOP_DATA", ROOT / "data"))
OUTPUT = Path(os.environ.get("DBOP_OUTPUT", ROOT / "output"))

MANIFEST = DATA / "manifest"          # backfill state, one parquet per (kind, currency)
TRADES = DATA / "trades"              # trades/options/BTC/BTC-YYYY-MM-DD.parquet
OPTION_TRADES = TRADES / "options"
BARS = DATA / "bars"                  # 5-min index and perp OHLCV
FUNDING = DATA / "funding"            # perpetual funding rate history
INSTRUMENTS = DATA / "instruments"    # expired + active option metadata
MARKS = DATA / "marks"                # end-of-day mark prices / mark IV per instrument
SURFACES = DATA / "surfaces"          # daily IV surfaces on the fixed (delta, tau) grid
INVENTORY = DATA / "inventory"        # net demand and dealer inventory panels
PANELS = DATA / "panels"              # merged regression panels
DVOL = DATA / "dvol"                  # Deribit volatility index history

TABLES = OUTPUT / "tables"
FIGURES = OUTPUT / "figures"

for _d in (DATA, MANIFEST, TRADES, OPTION_TRADES, BARS, FUNDING, INSTRUMENTS,
           MARKS, SURFACES, INVENTORY, PANELS, DVOL, OUTPUT, TABLES, FIGURES):
    _d.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ endpoints
# history.deribit.com serves the complete trade archive since platform
# inception; www.deribit.com only serves a recent window of trades. The split is
# not uniform across endpoints: funding-rate and volatility-index history return
# HTTP 400 on the history host and must go to www (verified 2026-08).
HISTORY_BASE = "https://history.deribit.com/api/v2/public/"
LIVE_BASE = "https://www.deribit.com/api/v2/public/"

CURRENCIES = ("BTC", "ETH", "SOL", "XRP")
PERPETUAL = {"BTC": "BTC-PERPETUAL", "ETH": "ETH-PERPETUAL",
             "SOL": "SOL_USDC-PERPETUAL", "XRP": "XRP_USDC-PERPETUAL"}
INDEX = {"BTC": "btc_usd", "ETH": "eth_usd", "SOL": "sol_usdc",
         "XRP": "xrp_usdc"}

# SOL and XRP options are not listed under their own currency. Deribit groups
# every USDC-settled book under currency "USDC", so the API is queried with USDC
# and the results filtered by instrument prefix.
API_CURRENCY = {"BTC": "BTC", "ETH": "ETH", "SOL": "USDC", "XRP": "USDC"}
INSTRUMENT_PREFIX = {"BTC": "BTC-", "ETH": "ETH-", "SOL": "SOL_USDC-",
                     "XRP": "XRP_USDC-"}

# BTC and ETH options are inverse: coin-settled, premium quoted in coin, so the
# USD premium is price * forward and the hedge ratio is premium-adjusted. SOL
# and XRP options are linear -- USDC-settled, premium already in dollars per
# unit of underlying -- so both conventions differ and the distinction has to be
# carried explicitly rather than assumed.
LINEAR = {"BTC": False, "ETH": False, "SOL": True, "XRP": True}

# Contract sizes differ across books (SOL_USDC options are 10 SOL per contract,
# XRP_USDC 1000 XRP); per-contract greeks are unaffected but notionals are not.
CONTRACT_SIZE = {"BTC": 1.0, "ETH": 1.0, "SOL": 10.0, "XRP": 1000.0}

# Assets carried on the realized side only. Their perpetuals give a clean
# day-of-week variance profile, but their option books cannot identify the
# pricing slope, so they never enter CURRENCIES and no option tape is collected
# for them. PAXG is tokenized gold: its reference market -- London and COMEX --
# genuinely closes at the weekend, which makes it the dose-response check the
# crypto assets cannot provide. Its Deribit options expire almost exclusively on
# Fridays (5,304 of 5,346 instruments), so within a trade day the weekend
# fraction is a deterministic function of maturity and cannot be separated from
# the maturity controls.
REFERENCE_ASSETS = {"PAXG": "PAXG_USDC-PERPETUAL"}
REFERENCE_START = {"PAXG": dt.date(2024, 12, 5)}

# First observed option trade per currency (probed against the API, not the
# instrument-listing date: BTC instruments exist from Jul 2016 but nothing
# traded until Nov 2016, and XRP instruments from 7 Mar 2024 against a first
# trade on the 12th).
SAMPLE_START = {"BTC": dt.date(2016, 11, 29), "ETH": dt.date(2019, 3, 21),
                "SOL": dt.date(2024, 2, 12), "XRP": dt.date(2024, 3, 12)}

# ------------------------------------------------------------------ API knobs
# Public limit is roughly 20 req/s; we stay well under it because the backfill
# is a many-hour unattended run and being throttled mid-run costs more than the
# headroom saves.
RATE_LIMIT_RPS = 5.0
REQUEST_TIMEOUT = 30
MAX_RETRIES = 5
TRADES_PAGE_SIZE = 1000            # endpoint maximum
BACKFILL_WORKERS = 3               # threads sharing one rate limiter

# ------------------------------------------------------------ market conventions
# Deribit options are inverse (coin-settled, premium quoted in coin) and expire
# at 08:00 UTC. Crypto has no clean risk-free rate; the literature convention is
# r = 0 with the forward taken from the index.
EXPIRY_HOUR_UTC = 8
RISK_FREE = 0.0
YEAR = 365.0                       # calendar-day year: crypto trades 24/7

# ------------------------------------------------------------ measurement knobs
# Bucket grid for the cross-sectional panel. Calls and puts are pooled on
# |delta| with a side flag; buckets are assigned from CURRENT greeks each day,
# so positions migrate as spot moves (GPP weight risk by current exposure).
DELTA_BINS = (0.02, 0.125, 0.375, 0.625, 0.98)
TAU_BINS_DAYS = (0.0, 7.0, 30.0, 90.0, 10_000.0)

# Fixed grid the daily surface is interpolated onto.
GRID_DELTAS = (0.10, 0.25, 0.50)
GRID_TAUS_DAYS = (7, 30, 60, 90)

# Realized vol / HAR
BAR_MINUTES = 5
HAR_BURN_IN_DAYS = 730             # 2y before the first out-of-sample forecast
HAR_HORIZONS_DAYS = (7, 30, 60, 90)
# Rolling estimation window for HAR (None = expanding). Crypto vol trends over
# multi-year horizons, so an expanding window keeps re-fitting on a high-vol
# past and over-forecasts late in the sample. Two years beats expanding and
# longer windows at every horizon out of sample (see docs/data_notes.md).
HAR_WINDOW_DAYS = 756

# Inventory normalization: trailing window used as the market-size proxy.
INVENTORY_SCALE_WINDOW_DAYS = 30

# EOD mark is the instrument's last trade of the day; flag it stale beyond this.
MARK_STALENESS_HOURS = 6

# IV sanity band; outside this we recompute from price rather than trust the
# exchange field.
IV_MIN = 0.01
IV_MAX = 5.0

# ------------------------------------------------------------ sample events
# Regime breaks used for subsample stability and event-window falsifications.
EVENTS = {
    "covid_crash": dt.date(2020, 3, 12),
    "may2021_crash": dt.date(2021, 5, 19),
    "luna_collapse": dt.date(2022, 5, 9),
    "ftx_collapse": dt.date(2022, 11, 8),
    "btc_etf_launch": dt.date(2024, 1, 11),
}
