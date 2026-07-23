# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Database-free unit tests for the CVR margin math and the single-currency guard.

These pin the pure behaviour the module exists for, with no database, session or
fixtures:

* :func:`app.modules.cvr.compute.summarise_lines` - the cost / value / forecast
  roll-up, ``margin_to_date = value - cost``,
  ``forecast_margin = forecast_value - forecast_cost``, the two margin
  percentages, division-by-zero safety on a value-less report, and the advisory
  forecast warnings. Every money figure is asserted as a 2dp ``Decimal``.
* :func:`app.modules.cvr.validators.assert_single_currency` - a line may only
  carry the report currency (blank inherits, case-insensitive), and a real
  mismatch raises :class:`CvrValidationError`.
* the cumulative cashflow S-curve and the net-of-retention helper.

testpaths in ``backend/pyproject.toml`` is ``["tests"]``, so this module-local
test is not auto-collected by a bare ``pytest`` run; run it explicitly with
``pytest app/modules/cvr/tests/`` or fold the module tests dir into testpaths
during integration.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.cvr.compute import cumulative_series, net_of_retention, summarise_lines
from app.modules.cvr.validators import (
    CvrValidationError,
    assert_single_currency,
    forecast_flags,
)

# ── Banned characters, built from code points (never a literal string) ─────
# em dash, en dash, curly quotes, and the zero-width family. Assembled from
# chr() so this source file itself stays free of them, matching the house rule.
_BANNED_CODE_POINTS = (
    0x2014,  # em dash
    0x2013,  # en dash
    0x2018,  # left single quotation mark
    0x2019,  # right single quotation mark
    0x201C,  # left double quotation mark
    0x201D,  # right double quotation mark
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x200D,  # zero width joiner
    0x2060,  # word joiner
    0xFEFF,  # zero width no-break space
)
_BANNED_CHARS = frozenset(chr(cp) for cp in _BANNED_CODE_POINTS)


def _line(**kw: object) -> SimpleNamespace:
    """Build a line-like object with the money attributes summarise_lines reads."""
    base = {
        "cost_code": "",
        "cost_to_date": "0",
        "value_to_date": "0",
        "accruals": "0",
        "forecast_cost": "0",
        "forecast_value": "0",
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── Margin roll-up ─────────────────────────────────────────────────────────


def test_summarise_lines_totals_and_margins_as_decimals() -> None:
    lines = [
        _line(
            cost_code="A1",
            cost_to_date="100.00",
            value_to_date="150.00",
            accruals="10.00",
            forecast_cost="200.00",
            forecast_value="300.00",
        ),
        _line(
            cost_code="B2",
            cost_to_date="50.50",
            value_to_date="40.00",
            accruals="5.00",
            forecast_cost="80.00",
            forecast_value="90.00",
        ),
    ]

    summary = summarise_lines(lines)

    # Totals (money as 2dp Decimals, never floats).
    assert summary["total_cost_to_date"] == Decimal("150.50")
    assert summary["total_value_to_date"] == Decimal("190.00")
    assert summary["total_accruals"] == Decimal("15.00")
    assert summary["total_forecast_cost"] == Decimal("280.00")
    assert summary["total_forecast_value"] == Decimal("390.00")

    # margin_to_date = 190.00 - 150.50 ; forecast_margin = 390.00 - 280.00
    assert summary["margin_to_date"] == Decimal("39.50")
    assert summary["forecast_margin"] == Decimal("110.00")

    # 39.50 / 190.00 * 100 = 20.7894... -> 20.79 ; 110 / 390 * 100 -> 28.21
    assert summary["margin_to_date_pct"] == Decimal("20.79")
    assert summary["forecast_margin_pct"] == Decimal("28.21")

    # Both lines carry a healthy forecast, so no advisory warnings.
    assert summary["warnings"] == []

    # Every emitted money figure is a Decimal, never a float.
    for key in (
        "total_cost_to_date",
        "margin_to_date",
        "forecast_margin",
        "margin_to_date_pct",
    ):
        assert isinstance(summary[key], Decimal)


def test_summarise_lines_empty_report_is_all_zero_no_division() -> None:
    summary = summarise_lines([])
    assert summary["total_value_to_date"] == Decimal("0.00")
    assert summary["margin_to_date"] == Decimal("0.00")
    # A value-less report must not divide by zero - percentages fall back to 0.
    assert summary["margin_to_date_pct"] == Decimal("0.00")
    assert summary["forecast_margin_pct"] == Decimal("0.00")
    assert summary["warnings"] == []


def test_summarise_lines_flags_forecast_below_position() -> None:
    lines = [
        _line(
            cost_code="C3",
            cost_to_date="100.00",
            value_to_date="100.00",
            forecast_cost="90.00",  # below cost_to_date
            forecast_value="80.00",  # below value_to_date
        )
    ]
    summary = summarise_lines(lines)
    assert "C3:forecast_cost_below_cost_to_date" in summary["warnings"]
    assert "C3:forecast_value_below_value_to_date" in summary["warnings"]


def test_forecast_flags_pure() -> None:
    healthy = forecast_flags(
        cost_to_date=Decimal("10"),
        value_to_date=Decimal("20"),
        forecast_cost=Decimal("15"),
        forecast_value=Decimal("25"),
    )
    assert healthy == []

    both = forecast_flags(
        cost_to_date=Decimal("30"),
        value_to_date=Decimal("40"),
        forecast_cost=Decimal("20"),
        forecast_value=Decimal("35"),
    )
    assert both == [
        "forecast_cost_below_cost_to_date",
        "forecast_value_below_value_to_date",
    ]


# ── Single-currency guard ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("report_currency", "incoming"),
    [
        ("USD", "USD"),
        ("USD", "usd"),  # case-insensitive
        ("USD", None),  # inherit
        ("USD", ""),  # inherit
        ("USD", "  usd  "),  # trimmed + case-insensitive
        ("", "EUR"),  # report has no currency set yet -> nothing to conflict with
    ],
)
def test_assert_single_currency_allows(report_currency: str, incoming: str | None) -> None:
    # Must not raise.
    assert_single_currency(report_currency, incoming)


def test_assert_single_currency_rejects_mismatch() -> None:
    with pytest.raises(CvrValidationError):
        assert_single_currency("USD", "EUR")


def test_single_currency_error_message_has_no_typographic_punctuation() -> None:
    try:
        assert_single_currency("USD", "EUR")
    except CvrValidationError as exc:
        message = str(exc)
    else:  # pragma: no cover - the call above always raises
        pytest.fail("expected CvrValidationError")
    assert "USD" in message and "EUR" in message
    assert not (_BANNED_CHARS & set(message))


# ── Cumulative cashflow S-curve + net of retention ─────────────────────────


def _point(period: str, cash_in: str, cash_out: str, currency: str = "GBP") -> SimpleNamespace:
    return SimpleNamespace(period=period, cash_in=cash_in, cash_out=cash_out, currency=currency)


def test_cumulative_series_runs_a_running_sum() -> None:
    points = [
        _point("2026-01", "100.00", "40.00"),
        _point("2026-02", "200.00", "250.00"),
    ]
    series = cumulative_series(points)

    first, second = series["points"]
    assert first["net"] == Decimal("60.00")
    assert first["cumulative_cash_in"] == Decimal("100.00")
    assert first["cumulative_net"] == Decimal("60.00")

    assert second["net"] == Decimal("-50.00")
    assert second["cumulative_cash_in"] == Decimal("300.00")
    assert second["cumulative_cash_out"] == Decimal("290.00")
    assert second["cumulative_net"] == Decimal("10.00")

    assert series["total_cash_in"] == Decimal("300.00")
    assert series["total_cash_out"] == Decimal("290.00")
    assert series["net_position"] == Decimal("10.00")


def test_net_of_retention_clamps_at_zero() -> None:
    assert net_of_retention("1000.00", "50.00") == Decimal("950.00")
    # Retention larger than gross can never produce a negative net payable.
    assert net_of_retention("100.00", "150.00") == Decimal("0.00")
