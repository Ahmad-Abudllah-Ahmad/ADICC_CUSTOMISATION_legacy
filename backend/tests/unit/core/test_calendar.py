"""Tests for the working-days calendar engine's multi-year holiday computation.

These exercise the three holiday families that used to be single-year (2026)
stubs and are now computed for any year:

* Hijri (Islamic) holidays - Eid al-Fitr / Eid al-Adha via ``hijridate``.
* Japanese equinoxes - the standard integer approximation (1980-2099).
* Hindu holidays - Diwali / Holi from a curated multi-year lookup table.

Assertions cover 2026, 2027 and 2028 so a regression to a fixed-year stub
would fail immediately, plus graceful behaviour for years outside the curated
Hindu table.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core import calendar as cal
from app.core.calendar import (
    _equinox_day,
    _get_holidays,
    _hijri_dates_in_gregorian_year,
    is_working_day,
)

# ── Hijri (Eid al-Fitr / Eid al-Adha) ────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("year", "eid_al_fitr_start", "eid_al_adha_start"),
    [
        (2026, date(2026, 3, 20), date(2026, 5, 27)),
        (2027, date(2027, 3, 9), date(2027, 5, 16)),
        (2028, date(2028, 2, 26), date(2028, 5, 5)),
    ],
)
def test_eid_dates_multi_year(year: int, eid_al_fitr_start: date, eid_al_adha_start: date) -> None:
    """Eid al-Fitr (3 days) and Eid al-Adha (4 days) land on the Hijri dates."""
    holidays = _get_holidays("AE", year)
    ordinals = {d.toordinal() for d in holidays}

    # Eid al-Fitr spans 3 days from 1 Shawwal.
    for offset in range(3):
        assert (eid_al_fitr_start.toordinal() + offset) in ordinals, f"Eid al-Fitr day {offset} missing for {year}"

    # Eid al-Adha spans 4 days from 10 Dhu al-Hijjah.
    for offset in range(4):
        assert (eid_al_adha_start.toordinal() + offset) in ordinals, f"Eid al-Adha day {offset} missing for {year}"


@pytest.mark.unit
def test_eid_2026_not_using_2025_stub_dates() -> None:
    """Guard against the old hardcoded 2025-era dates leaking back in.

    The previous stub marked 30-31 March and 1 April plus 6-9 June 2026 as
    Eid. Those are actually the 2025 dates; the real 2026 Eids are 20 March
    and 27 May. This locks in the corrected values.
    """
    holidays = _get_holidays("AE", 2026)
    assert date(2026, 3, 20) in holidays
    assert date(2026, 5, 27) in holidays
    # Old wrong stub dates must NOT be present.
    assert date(2026, 3, 30) not in holidays
    assert date(2026, 6, 6) not in holidays


@pytest.mark.unit
def test_eid_can_occur_twice_in_one_gregorian_year() -> None:
    """A lunar holiday can fall twice in a Gregorian year (year is ~11d short).

    Eid al-Fitr (1 Shawwal) lands in both January and December of 2033.
    """
    fitr = _hijri_dates_in_gregorian_year(10, 1, 2033)
    assert len(fitr) == 2
    assert fitr[0].month == 1
    assert fitr[1].month == 12


@pytest.mark.unit
def test_hijri_out_of_range_year_does_not_raise() -> None:
    """Years beyond hijridate's supported range yield no Eid, no exception.

    hijridate supports Gregorian dates up to 2077-11-16, so 2099 is out of
    range and must degrade gracefully (only the fixed Gregorian holidays).
    """
    holidays = _get_holidays("AE", 2099)
    assert _hijri_dates_in_gregorian_year(10, 1, 2099) == []
    # Fixed Gregorian holidays still present.
    assert date(2099, 1, 1) in holidays
    assert date(2099, 12, 2) in holidays


# ── Japanese equinoxes ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("year", "spring_day", "autumn_day"),
    [
        (2026, 20, 23),
        (2027, 21, 23),
        (2028, 20, 22),
    ],
)
def test_equinox_days_multi_year(year: int, spring_day: int, autumn_day: int) -> None:
    """Vernal (March) and autumnal (September) equinox days match the almanac."""
    assert _equinox_day(year, spring=True) == spring_day
    assert _equinox_day(year, spring=False) == autumn_day


@pytest.mark.unit
@pytest.mark.parametrize(
    ("year", "spring", "autumn"),
    [
        (2026, date(2026, 3, 20), date(2026, 9, 23)),
        (2027, date(2027, 3, 21), date(2027, 9, 23)),
        (2028, date(2028, 3, 20), date(2028, 9, 22)),
    ],
)
def test_japan_equinox_holidays_present(year: int, spring: date, autumn: date) -> None:
    """The computed equinox dates appear in Japan's holiday set each year."""
    holidays = _get_holidays("JP", year)
    assert spring in holidays
    assert autumn in holidays
    # The old fixed Sep 22 stub was wrong for 2026/2027 (should be Sep 23).
    if year in (2026, 2027):
        assert date(year, 9, 22) not in holidays


# ── Hindu (Diwali / Holi) ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("year", "holi", "diwali"),
    [
        (2026, date(2026, 3, 4), date(2026, 11, 8)),
        (2027, date(2027, 3, 22), date(2027, 10, 29)),
        (2028, date(2028, 3, 11), date(2028, 10, 17)),
    ],
)
def test_hindu_holidays_multi_year(year: int, holi: date, diwali: date) -> None:
    """Holi and Diwali come from the curated table for covered years."""
    holidays = _get_holidays("IN", year)
    assert holi in holidays
    assert diwali in holidays


@pytest.mark.unit
def test_hindu_out_of_table_year_does_not_raise() -> None:
    """Years outside the curated table omit Holi/Diwali without crashing."""
    holidays = _get_holidays("IN", 2099)  # Far beyond the curated table.
    # Fixed gazetted holidays still present.
    assert date(2099, 1, 26) in holidays  # Republic Day
    assert date(2099, 12, 25) in holidays  # Christmas
    # No March/October lunisolar guesses for an uncovered year.
    march_or_october = {d for d in holidays if d.month in (3, 10) and d.day not in (2,)}
    # Gandhi Jayanti (Oct 2) is excluded above; nothing else should remain.
    assert march_or_october == set()


# ── End-to-end via the public API ─────────────────────────────────────────────


@pytest.mark.unit
def test_is_working_day_reflects_computed_holidays() -> None:
    """The public is_working_day API honours the computed lunar/equinox dates."""
    # Eid al-Adha 2027 (16 May, a Sunday) is a UAE holiday → not working.
    assert is_working_day(date(2027, 5, 16), "AE") is False
    # Diwali 2028 (17 Oct, a Tuesday) is an India holiday → not working.
    assert is_working_day(date(2028, 10, 17), "IN") is False
    # Japan autumnal equinox 2028 (22 Sep, a Friday) → not working.
    assert is_working_day(date(2028, 9, 22), "JP") is False


@pytest.mark.unit
def test_holiday_cache_isolated_per_year() -> None:
    """Different years produce distinct holiday sets (no stale single-year cache)."""
    cal._holiday_cache.clear()
    h2026 = _get_holidays("AE", 2026)
    h2027 = _get_holidays("AE", 2027)
    assert h2026 != h2027
