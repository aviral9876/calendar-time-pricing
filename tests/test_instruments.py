"""Instrument-name parsing.

A silently wrong strike corrupts moneyness, which corrupts the delta filter,
which changes the sample the headline regression runs on. ``instruments.validate``
raises when the parsed strike disagrees with exchange metadata by more than
1e-6, so these cases are the ones that must round-trip exactly.
"""
import datetime as dt

import pytest

from dbop.instruments import parse_instrument_name


def test_parses_a_plain_inverse_name():
    expiry, strike, cp = parse_instrument_name("BTC-27DEC24-60000-C")
    assert expiry == dt.datetime(2024, 12, 27, 8, tzinfo=dt.timezone.utc)
    assert strike == 60000.0
    assert cp == "C"


def test_parses_single_digit_day():
    expiry, _, _ = parse_instrument_name("BTC-1JUN18-7000-P")
    assert expiry.date() == dt.date(2018, 6, 1)


@pytest.mark.parametrize("name,expected", [
    # Sub-dollar strikes encode the decimal point as 'd': the hyphen-delimited
    # name has no room for a period.
    ("XRP_USDC-9MAR24-0d54-C", 0.54),
    ("TRX_USDC-16AUG25-0d33-P", 0.33),
    ("AVAX_USDC-16AUG25-22d5-C", 22.5),
    # The same book mixes the two forms in one expiry once strikes cross 1.0,
    # so the form cannot be switched on the currency.
    ("XRP_USDC-22MAR24-1-C", 1.0),
    ("SOL_USDC-13FEB24-96-C", 96.0),
])
def test_parses_decimal_and_integer_strikes(name, expected):
    _, strike, _ = parse_instrument_name(name)
    assert strike == expected


def test_underscored_currency_does_not_confuse_the_split():
    expiry, strike, cp = parse_instrument_name("SOL_USDC-13FEB24-96-P")
    assert (expiry.date(), strike, cp) == (dt.date(2024, 2, 13), 96.0, "P")


def test_rejects_non_option_names():
    with pytest.raises(ValueError):
        parse_instrument_name("BTC-PERPETUAL")
    with pytest.raises(ValueError):
        parse_instrument_name("XRP_USDC-1APR26")
