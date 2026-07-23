# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free tests for ESG metric-key + range validation.

These exercise the pure guard and the catalogue only (no database, no ORM, no
FastAPI), proving the first-class validation rules that gate every write:

* metric_key must be one of the catalogue metrics;
* every value / target must be zero or greater;
* a percentage metric (unit ``%``) must be in 0..100, while a count/quantity
  metric may exceed 100;
* non-numeric and non-finite readings are rejected.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.esg import guard
from app.modules.esg.catalogue import (
    METRIC_DEFINITIONS,
    PERCENT_UNIT,
    get_metric,
    is_percent_metric,
    metric_keys,
)

# The metrics the module is required to ship (task spec), by pillar.
REQUIRED_KEYS = {
    "energy_diesel_l",
    "energy_grid_kwh",
    "water_m3",
    "waste_total_t",
    "waste_recycled_pct",
    "co2e_site_t",
    "local_labour_pct",
    "training_hours",
    "apprentices",
    "incidents",
    "near_misses",
}


# ── Catalogue shape ───────────────────────────────────────────────────────────


def test_catalogue_contains_required_metrics() -> None:
    keys = set(metric_keys())
    assert keys >= REQUIRED_KEYS
    # Keys are unique.
    assert len(metric_keys()) == len(keys)


def test_percent_metrics_flagged_by_unit() -> None:
    # Every %-unit metric is a percent metric, and vice-versa.
    for definition in METRIC_DEFINITIONS:
        assert is_percent_metric(definition.key) == (definition.unit == PERCENT_UNIT)
    assert is_percent_metric("waste_recycled_pct") is True
    assert is_percent_metric("training_hours") is False
    # An unknown key is never a percent metric.
    assert is_percent_metric("does_not_exist") is False


def test_every_metric_has_category_and_direction() -> None:
    for definition in METRIC_DEFINITIONS:
        assert definition.category.value in {"environmental", "social", "governance"}
        assert definition.direction.value in {"lower_better", "higher_better"}
        assert get_metric(definition.key) is definition


# ── validate_metric_key ───────────────────────────────────────────────────────


def test_validate_metric_key_accepts_known_and_trims() -> None:
    assert guard.validate_metric_key("  energy_diesel_l  ") == "energy_diesel_l"


def test_validate_metric_key_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown metric_key"):
        guard.validate_metric_key("co2e_moon_t")


def test_validate_metric_key_rejects_empty() -> None:
    with pytest.raises(ValueError, match="required"):
        guard.validate_metric_key("   ")


# ── validate_reading: value >= 0 ──────────────────────────────────────────────


def test_value_must_be_non_negative() -> None:
    assert guard.validate_reading("energy_diesel_l", "value", Decimal("0")) == Decimal("0")
    assert guard.validate_reading("energy_diesel_l", "value", Decimal("1234.5")) == Decimal("1234.5")
    with pytest.raises(ValueError, match="zero or greater"):
        guard.validate_reading("energy_diesel_l", "value", Decimal("-1"))


def test_non_numeric_and_non_finite_rejected() -> None:
    with pytest.raises(ValueError, match="must be a number"):
        guard.validate_reading("energy_diesel_l", "value", "not-a-number")
    with pytest.raises(ValueError, match="finite"):
        guard.validate_reading("energy_diesel_l", "value", Decimal("NaN"))


# ── validate_reading: percent metrics bounded to 0..100 ───────────────────────


def test_percent_metric_bounded_to_100() -> None:
    assert guard.validate_reading("waste_recycled_pct", "value", Decimal("100")) == Decimal("100")
    with pytest.raises(ValueError, match="between 0 and"):
        guard.validate_reading("waste_recycled_pct", "value", Decimal("100.01"))


def test_non_percent_metric_may_exceed_100() -> None:
    # A count/quantity metric is not capped at 100.
    assert guard.validate_reading("training_hours", "value", Decimal("250")) == Decimal("250")


# ── validate_entry: whole-entry happy path + failures ─────────────────────────


def test_validate_entry_happy_path_returns_key() -> None:
    key = guard.validate_entry("local_labour_pct", Decimal("62.5"), Decimal("70"))
    assert key == "local_labour_pct"


def test_validate_entry_rejects_bad_target_range() -> None:
    with pytest.raises(ValueError, match="between 0 and"):
        guard.validate_entry("waste_recycled_pct", Decimal("40"), Decimal("120"))


def test_validate_entry_allows_missing_target() -> None:
    assert guard.validate_entry("incidents", Decimal("0")) == "incidents"
