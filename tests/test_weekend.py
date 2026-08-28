"""Weekend-fraction arithmetic.

These are pure calendar facts, so they can be checked against hand-computed
values rather than against the pipeline's own output.
"""
import datetime as dt

import numpy as np
import pytest

from dbop import weekend


def ms(y, m, d, h=0):
    return int(dt.datetime(y, m, d, h, tzinfo=dt.timezone.utc).timestamp() * 1000)


# 2026-08-14 is a Friday, so 15th Sat, 16th Sun, 17th Mon. Deribit settles at
# 08:00 UTC, so the 08:00-anchored constants below are the realistic case and
# deliberately straddle calendar days; the midnight ones isolate whole days.
FRI, SAT, SUN, MON = (ms(2026, 8, 14, 8), ms(2026, 8, 15, 8),
                      ms(2026, 8, 16, 8), ms(2026, 8, 17, 8))
SAT_0, MON_0 = ms(2026, 8, 15), ms(2026, 8, 17)
DAY = 24 * 3_600_000


def test_whole_weekend_is_one():
    # Saturday 00:00 to Monday 00:00 is entirely weekend.
    f = weekend.weekend_fraction([SAT_0], [MON_0])
    assert f[0] == pytest.approx(1.0, abs=1e-9)


def test_expiry_at_0800_straddles_two_days():
    # Sat 08:00 -> Mon 08:00 is 48 hours, of which 40 are Sat/Sun and 8 are
    # Monday morning. This is the shape almost every real contract has.
    f = weekend.weekend_fraction([SAT], [MON])
    assert f[0] == pytest.approx(40 / 48, abs=0.01)


def test_weekday_only_is_zero():
    # Monday 08:00 to Tuesday 08:00 contains no weekend hours.
    f = weekend.weekend_fraction([MON], [MON + 24 * 3_600_000])
    assert f[0] == pytest.approx(0.0, abs=1e-9)


def test_friday_to_monday_is_two_thirds():
    # Fri 08:00 -> Mon 08:00 is 72 hours, 48 of them Saturday and Sunday.
    f = weekend.weekend_fraction([FRI], [MON])
    assert f[0] == pytest.approx(2 / 3, abs=0.01)


def test_long_dated_tends_to_two_sevenths():
    f = weekend.weekend_fraction([MON], [MON + 364 * 24 * 3_600_000])
    assert f[0] == pytest.approx(2 / 7, abs=0.005)


def test_expired_or_inverted_is_nan():
    f = weekend.weekend_fraction([MON, MON], [MON, MON - 1000])
    assert np.isnan(f).all()


def test_all_day_fractions_sum_to_one():
    starts = [FRI, MON, SAT]
    ends = [MON, MON + 10 * 24 * 3_600_000, SUN + 3 * 3_600_000]
    fr = weekend.all_day_fractions(starts, ends)
    assert fr.shape == (3, 7)
    assert np.allclose(fr.sum(axis=1), 1.0, atol=1e-9)


def test_all_day_fractions_agree_with_weekend_fraction():
    starts = [FRI, MON, SAT, MON]
    ends = [MON, MON + 10 * 24 * 3_600_000, SUN + 3 * 3_600_000,
            MON + 364 * 24 * 3_600_000]
    fr = weekend.all_day_fractions(starts, ends)
    direct = weekend.weekend_fraction(starts, ends)
    assert np.allclose(fr[:, 5] + fr[:, 6], direct, atol=1e-9)


def test_all_day_fractions_single_weekday():
    # Monday 00:00 -> Tuesday 00:00 is entirely Monday.
    fr = weekend.all_day_fractions([MON_0], [MON_0 + DAY])
    assert fr[0, 0] == pytest.approx(1.0, abs=1e-9)
    assert fr[0, 1:].sum() == pytest.approx(0.0, abs=1e-9)


def test_all_day_fractions_split_across_0800_boundary():
    # Monday 08:00 -> Tuesday 08:00 is two thirds Monday, one third Tuesday.
    fr = weekend.all_day_fractions([MON], [MON + DAY])
    assert fr[0, 0] == pytest.approx(2 / 3, abs=0.01)
    assert fr[0, 1] == pytest.approx(1 / 3, abs=0.01)


def _exact_weekend_fraction(a, b):
    """Reference: walk real day boundaries and sum true overlaps.

    Fixed-width blocks anchored at the start are not exact -- they straddle
    midnight and get charged wholly to one day.
    """
    we = tot = 0.0
    t = a
    while t < b:
        e = min((t // DAY + 1) * DAY, b)
        w = e - t
        tot += w
        if dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).weekday() >= 5:
            we += w
        t = e
    return we / tot


def test_closed_form_matches_exact_reference():
    rng = np.random.default_rng(7)
    base = ms(2024, 1, 1)
    starts = base + rng.integers(0, 400 * DAY, 200)
    ends = starts + rng.integers(3_600_000, 20 * DAY, 200)
    fast = weekend.weekend_fraction(starts, ends)
    slow = np.array([_exact_weekend_fraction(int(a), int(b))
                     for a, b in zip(starts, ends)])
    assert np.abs(fast - slow).max() < 1e-12


def test_implied_weekend_ratio_recovers_inputs():
    v_wd, v_we = 0.80, 0.50
    slope = v_we - v_wd
    assert weekend.implied_weekend_ratio(slope, v_wd) == pytest.approx(
        v_we / v_wd, rel=1e-12)
