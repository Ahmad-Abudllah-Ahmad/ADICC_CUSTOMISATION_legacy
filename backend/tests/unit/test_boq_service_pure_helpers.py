# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure-function unit tests for the BOQ service helper layer.

These pin the small, side-effect-free helpers in
``app.modules.boq.service`` that no DB session can exercise but that several
endpoints depend on for correctness:

* ``_determine_aace_class`` / ``_build_classification`` - the AACE 18R-97
  estimate-class ladder (position count + rate/resource completeness ->
  class 1..5) and the response it assembles.
* ``_content_fingerprint`` / ``_apply_duplicate_warning`` - the
  description/unit/qty/rate duplicate-content signal (BUG-B-014) and its
  idempotent, non-stacking warning marker.
* ``_stamp_cost_item_compat`` - the unit / currency provenance + non-blocking
  mismatch warning recorded when a catalogue rate is applied (BUG-B-013).
* ``_calculate_markup_amounts`` - the ``fixed`` / inactive / ``per_unit``
  branches not covered by the existing ``apply_to='subtotal'`` remediation
  test.
* ``_compute_total`` / ``_str_to_float`` / ``_coerce_audit_value`` - the
  precision-preserving total, the section-detection float coercion, and the
  JSON-safe audit-value coercion.

Like the existing ``test_boq_remediation_part9`` / ``test_boq_machinery_category``
suites, importing ``app.modules.boq.service`` binds ``app.database`` at import
time, so this file runs under CI (Python 3.12 + PostgreSQL) - it does not need
a session, only the engine import to resolve. The logic under test is pure and
deterministic.

Run (CI):
    cd backend
    python -m pytest tests/unit/test_boq_service_pure_helpers.py -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.boq.models import BOQMarkup
from app.modules.boq.service import (
    _AACE_CLASSES,
    _DUPLICATE_WARNING_PREFIX,
    _apply_duplicate_warning,
    _build_classification,
    _calculate_markup_amounts,
    _coerce_audit_value,
    _compute_total,
    _content_fingerprint,
    _determine_aace_class,
    _stamp_cost_item_compat,
    _str_to_float,
)

# ── _determine_aace_class: the class ladder ──────────────────────────────


@pytest.mark.parametrize(
    ("total_positions", "rate_pct", "resource_pct", "expected"),
    [
        # Class 5: < 5 positions OR < 20% have rates (first match wins).
        (0, 0.0, 0.0, 5),
        (4, 100.0, 100.0, 5),  # too few positions
        (500, 10.0, 100.0, 5),  # rate completeness below 20%
        # Class 4: < 20 positions OR < 50% with rates.
        (5, 100.0, 100.0, 4),
        (19, 100.0, 100.0, 4),
        (500, 49.0, 100.0, 4),
        # Class 3: < 50 positions OR < 75% with rates.
        (20, 100.0, 100.0, 3),
        (49, 100.0, 100.0, 3),
        (500, 74.0, 100.0, 3),
        # Class 2: < 100 positions OR < 90% with resources.
        (50, 100.0, 100.0, 2),
        (99, 100.0, 100.0, 2),
        (500, 100.0, 89.0, 2),
        # Class 1: 100+ positions AND >=90% rate AND >=90% resources.
        (100, 100.0, 100.0, 1),
        (250, 95.0, 90.0, 1),
    ],
)
def test_determine_aace_class_ladder(total_positions: int, rate_pct: float, resource_pct: float, expected: int) -> None:
    assert _determine_aace_class(total_positions, rate_pct, resource_pct) == expected


def test_determine_aace_class_first_match_wins() -> None:
    """A huge, fully resource-loaded BOQ with a poor rate ratio is still the
    LEAST-defined class - the rate gate is checked before the position count."""
    assert _determine_aace_class(10_000, 5.0, 100.0) == 5


# ── _build_classification: response assembly ─────────────────────────────


def test_build_classification_empty_boq_is_class_5() -> None:
    """A BOQ with no positions cannot divide-by-zero and lands at class 5."""
    resp = _build_classification(0, 0, 0, 0)
    assert resp.estimate_class == 5
    assert resp.metrics.total_positions == 0
    assert resp.metrics.rate_completeness_pct == 0.0
    assert resp.metrics.resource_completeness_pct == 0.0
    assert resp.metrics.classification_completeness_pct == 0.0
    # The label / accuracy bounds come straight from the class table.
    assert resp.class_label == _AACE_CLASSES[5]["label"]
    assert resp.accuracy_low == _AACE_CLASSES[5]["accuracy_low"]
    assert resp.accuracy_high == _AACE_CLASSES[5]["accuracy_high"]


def test_build_classification_percentages_and_rounding() -> None:
    """Completeness percentages are derived from the counts and rounded to 1dp."""
    # 7/30 rates = 23.333..%, 3/30 resources = 10.0%, 1/30 class = 3.333..%
    resp = _build_classification(30, 7, 3, 1)
    assert resp.metrics.rate_completeness_pct == 23.3
    assert resp.metrics.resource_completeness_pct == 10.0
    assert resp.metrics.classification_completeness_pct == 3.3
    # 30 positions, rate 23.3% -> class 4 (>=20 positions, but <50% rates).
    assert resp.estimate_class == 4


def test_build_classification_full_definitive_estimate() -> None:
    """100+ positions, 100% rates and resources -> class 1, definition 65-100."""
    resp = _build_classification(120, 120, 120, 120)
    assert resp.estimate_class == 1
    assert resp.metrics.rate_completeness_pct == 100.0
    assert resp.metrics.resource_completeness_pct == 100.0
    assert resp.definition_level_low == _AACE_CLASSES[1]["definition_low"]
    assert resp.definition_level_high == _AACE_CLASSES[1]["definition_high"]
    assert resp.class_label == _AACE_CLASSES[1]["label"]


def test_build_classification_counts_are_echoed_verbatim() -> None:
    resp = _build_classification(40, 30, 20, 10)
    assert resp.metrics.total_positions == 40
    assert resp.metrics.positions_with_rates == 30
    assert resp.metrics.positions_with_resources == 20
    assert resp.metrics.positions_with_classification == 10


# ── _content_fingerprint: duplicate-content key ──────────────────────────


def test_content_fingerprint_normalises_case_whitespace_and_precision() -> None:
    """Two positions describing the same work collide regardless of casing,
    internal whitespace, unit case, or numeric trailing-zero precision."""
    a = _content_fingerprint("  RC   Wall  C30/37 ", "M3", "100", "185.5")
    b = _content_fingerprint("rc wall c30/37", "m3", "100.0000", "185.5000")
    assert a == b


def test_content_fingerprint_distinguishes_real_differences() -> None:
    base = _content_fingerprint("RC Wall", "m3", "100", "185.5")
    # Different quantity, unit, rate, and description each break the match.
    assert _content_fingerprint("RC Wall", "m3", "101", "185.5") != base
    assert _content_fingerprint("RC Wall", "m2", "100", "185.5") != base
    assert _content_fingerprint("RC Wall", "m3", "100", "186.0") != base
    assert _content_fingerprint("RC Slab", "m3", "100", "185.5") != base


def test_content_fingerprint_handles_none_inputs() -> None:
    fp = _content_fingerprint(None, None, None, None)
    # Empty description/unit, and zero-quantised numerics - never raises.
    assert fp[0] == ""
    assert fp[1] == ""
    assert _content_fingerprint(None, None, None, None) == fp


# ── _apply_duplicate_warning: idempotent, non-stacking ───────────────────


def test_apply_duplicate_warning_adds_one_marker() -> None:
    meta: dict = {}
    _apply_duplicate_warning(meta, "0010")
    warnings = meta["boq_quality_warnings"]
    assert len(warnings) == 1
    assert warnings[0].startswith(_DUPLICATE_WARNING_PREFIX)
    assert "0010" in warnings[0]


def test_apply_duplicate_warning_is_idempotent() -> None:
    """Re-applying the SAME ordinal must not stack duplicate strings."""
    meta: dict = {}
    _apply_duplicate_warning(meta, "0010")
    _apply_duplicate_warning(meta, "0010")
    _apply_duplicate_warning(meta, "0010")
    assert len(meta["boq_quality_warnings"]) == 1


def test_apply_duplicate_warning_replaces_stale_ordinal() -> None:
    """When the matched ordinal changes, the old duplicate marker is dropped -
    only the current match survives (no accumulation of stale references)."""
    meta: dict = {}
    _apply_duplicate_warning(meta, "0010")
    _apply_duplicate_warning(meta, "0020")
    warnings = meta["boq_quality_warnings"]
    assert len(warnings) == 1
    assert "0020" in warnings[0]
    assert "0010" not in warnings[0]


def test_apply_duplicate_warning_preserves_unrelated_warnings() -> None:
    """Non-duplicate quality warnings already on the metadata are kept."""
    meta: dict = {"boq_quality_warnings": ["Missing unit rate"]}
    _apply_duplicate_warning(meta, "0010")
    warnings = meta["boq_quality_warnings"]
    assert "Missing unit rate" in warnings
    assert any(w.startswith(_DUPLICATE_WARNING_PREFIX) for w in warnings)
    assert len(warnings) == 2


# ── _stamp_cost_item_compat: provenance + mismatch warnings ──────────────


class _CostItem:
    def __init__(self, unit: str = "", currency: str = "") -> None:
        self.unit = unit
        self.currency = currency


def test_stamp_cost_item_compat_records_provenance_when_compatible() -> None:
    """Matching unit + currency: provenance stamped, NO warning, returns False."""
    meta: dict = {}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="m3", currency="EUR"),
        position_unit="m3",
        project_currency="EUR",
    )
    assert warned is False
    assert meta["cost_item_unit"] == "m3"
    assert meta["cost_item_currency"] == "EUR"
    assert "cost_apply_warnings" not in meta


def test_stamp_cost_item_compat_warns_on_unit_mismatch() -> None:
    meta: dict = {}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="m3", currency="EUR"),
        position_unit="m2",
        project_currency="EUR",
    )
    assert warned is True
    warnings = meta["cost_apply_warnings"]
    assert any("m3" in w and "m2" in w for w in warnings)


def test_stamp_cost_item_compat_warns_on_currency_mismatch_via_project() -> None:
    """BUG-B-013: with no per-position currency, the project currency is the
    fallback for the comparison (but is never persisted into metadata)."""
    meta: dict = {}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="m3", currency="EUR"),
        position_unit="m3",
        project_currency="USD",
    )
    assert warned is True
    warnings = meta["cost_apply_warnings"]
    assert any("EUR" in w and "USD" in w for w in warnings)
    # The project currency is only used for the check, not stored.
    assert "project_currency" not in meta


def test_stamp_cost_item_compat_prefers_metadata_currency_over_project() -> None:
    """An explicit per-position metadata currency wins over the project one."""
    meta: dict = {"currency": "GBP"}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="m3", currency="GBP"),
        position_unit="m3",
        project_currency="USD",  # would mismatch, but metadata GBP matches
    )
    assert warned is False
    assert "cost_apply_warnings" not in meta


def test_stamp_cost_item_compat_clears_stale_warning_on_good_relink() -> None:
    """Re-linking to a now-compatible cost item drops the prior warning."""
    meta: dict = {"cost_apply_warnings": ["old mismatch"]}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="m3", currency="EUR"),
        position_unit="m3",
        project_currency="EUR",
    )
    assert warned is False
    assert "cost_apply_warnings" not in meta


def test_stamp_cost_item_compat_case_insensitive() -> None:
    """Unit comparison is case-insensitive; currency is upper-cased - so 'M3'
    vs 'm3' and 'eur' vs 'EUR' are NOT flagged as mismatches."""
    meta: dict = {}
    warned = _stamp_cost_item_compat(
        meta,
        cost_item=_CostItem(unit="M3", currency="eur"),
        position_unit="m3",
        project_currency="EUR",
    )
    assert warned is False
    assert "cost_apply_warnings" not in meta


# ── _calculate_markup_amounts: branches beyond apply_to='subtotal' ───────


def _mk(
    name: str,
    *,
    markup_type: str = "percentage",
    percentage: str = "0",
    fixed_amount: str = "0",
    apply_to: str = "direct_cost",
    is_active: bool = True,
    sort_order: int = 0,
) -> BOQMarkup:
    return BOQMarkup(
        boq_id=None,
        name=name,
        markup_type=markup_type,
        category="overhead",
        percentage=percentage,
        fixed_amount=fixed_amount,
        apply_to=apply_to,
        sort_order=sort_order,
        is_active=is_active,
        metadata_={},
    )


def test_markup_fixed_amount_is_currency_constant() -> None:
    """A ``fixed`` markup contributes its fixed amount regardless of base."""
    dc = Decimal("1000")
    results = _calculate_markup_amounts(dc, [_mk("Mobilisation", markup_type="fixed", fixed_amount="2500")])
    assert results[0][1] == Decimal("2500")


def test_markup_inactive_contributes_zero() -> None:
    """An inactive markup is preserved in the output (order-stable) but zero."""
    dc = Decimal("1000")
    results = _calculate_markup_amounts(
        dc,
        [_mk("Disabled OH", percentage="10", is_active=False)],
    )
    assert len(results) == 1
    assert results[0][1] == Decimal("0")


def test_markup_per_unit_and_unknown_types_are_zero() -> None:
    """``per_unit`` and any unrecognised type default to zero (no crash)."""
    dc = Decimal("1000")
    results = _calculate_markup_amounts(
        dc,
        [
            _mk("Per unit", markup_type="per_unit", percentage="10"),
            _mk("Bogus", markup_type="surcharge", percentage="10"),
        ],
    )
    assert results[0][1] == Decimal("0")
    assert results[1][1] == Decimal("0")


def test_markup_percentage_on_direct_cost() -> None:
    dc = Decimal("1000")
    results = _calculate_markup_amounts(dc, [_mk("OH", percentage="12.5")])
    assert results[0][1] == Decimal("125.0")


def test_markup_inactive_does_not_advance_cumulative_base() -> None:
    """An inactive line between two active ones must not change the cumulative
    base the trailing ``cumulative`` line computes against."""
    dc = Decimal("1000")
    results = _calculate_markup_amounts(
        dc,
        [
            _mk("OH", percentage="10", apply_to="direct_cost", sort_order=0),
            _mk("Skipped", percentage="50", is_active=False, sort_order=1),
            _mk("Profit", percentage="10", apply_to="cumulative", sort_order=2),
        ],
    )
    amounts = {m.name: amt for m, amt in results}
    assert amounts["OH"] == Decimal("100")
    assert amounts["Skipped"] == Decimal("0")
    # Profit base = 1000 + 100 (OH only; skipped added 0) -> 110.
    assert amounts["Profit"] == Decimal("110")


def test_markup_empty_list_returns_empty() -> None:
    assert _calculate_markup_amounts(Decimal("1000"), []) == []


def test_markup_order_is_preserved() -> None:
    dc = Decimal("1000")
    markups = [_mk("A", percentage="1"), _mk("B", percentage="2"), _mk("C", percentage="3")]
    results = _calculate_markup_amounts(dc, markups)
    assert [m.name for m, _ in results] == ["A", "B", "C"]


# ── _compute_total: precision-preserving q x r ───────────────────────────


@pytest.mark.parametrize(
    ("quantity", "unit_rate", "expected"),
    [
        ("10", "185", "1850"),
        ("2.5", "100", "250.0000"),
        ("0", "999", "0"),
        ("100", "0", "0"),
        # Exact 4dp product (no rounding needed) preserved verbatim.
        ("3", "1.1112", "3.3336"),
        # Negative quantity (credit / deduction line) stays signed.
        ("-2", "50", "-100"),
    ],
)
def test_compute_total_basic(quantity: str, unit_rate: str, expected: str) -> None:
    # Compare numerically to stay robust to canonical-string trailing zeros.
    assert Decimal(_compute_total(quantity, unit_rate)) == Decimal(expected)


def test_compute_total_banker_rounding_at_fifth_dp() -> None:
    """A product with a 5th fractional digit is quantised to 4dp with
    ROUND_HALF_EVEN (the storage convention): 3 x 1.11115 = 3.33345 ->
    the 4th digit 4 is even, so the half rounds down to 3.3334."""
    assert Decimal(_compute_total("3", "1.11115")) == Decimal("3.3334")


def test_compute_total_quantises_to_four_dp() -> None:
    """The product never carries more than 4 fractional digits in storage."""
    out = _compute_total("1.23456789", "1")
    frac = out.split(".")[1] if "." in out else ""
    assert len(frac) <= 4


def test_compute_total_handles_none_as_zero() -> None:
    assert Decimal(_compute_total(None, "100")) == Decimal("0")
    assert Decimal(_compute_total("100", None)) == Decimal("0")
    assert Decimal(_compute_total(None, None)) == Decimal("0")


# ── _str_to_float: section-detection coercion ────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0.0),
        ("12.5", 12.5),
        ("-3", -3.0),
        (None, 0.0),
        ("", 0.0),
        ("abc", 0.0),
        ("nan", 0.0),
        ("inf", 0.0),
        ("-inf", 0.0),
    ],
)
def test_str_to_float_coercion(value: str | None, expected: float) -> None:
    assert _str_to_float(value) == pytest.approx(expected)


def test_str_to_float_rejects_non_finite() -> None:
    """Section detection compares against 0.0; a non-finite value there would
    make ``_is_section`` misbehave, so they collapse to 0.0."""
    assert _str_to_float("nan") == 0.0
    assert _str_to_float("inf") == 0.0


# ── _coerce_audit_value: JSON-safe activity-log values ───────────────────


def test_coerce_audit_value_passes_primitives() -> None:
    assert _coerce_audit_value(None) is None
    assert _coerce_audit_value(True) is True
    assert _coerce_audit_value(42) == 42
    assert _coerce_audit_value(3.5) == 3.5
    assert _coerce_audit_value("text") == "text"


def test_coerce_audit_value_stringifies_decimal_and_uuid() -> None:
    import uuid

    uid = uuid.uuid4()
    assert _coerce_audit_value(Decimal("185.50")) == "185.50"
    assert _coerce_audit_value(uid) == str(uid)


def test_coerce_audit_value_recurses_into_containers() -> None:
    import uuid

    uid = uuid.uuid4()
    out = _coerce_audit_value(
        {
            "amount": Decimal("100.00"),
            "id": uid,
            "items": [Decimal("1.5"), "x", 2],
            "nested": {"q": Decimal("3")},
        }
    )
    assert out["amount"] == "100.00"
    assert out["id"] == str(uid)
    assert out["items"] == ["1.5", "x", 2]
    assert out["nested"] == {"q": "3"}


def test_coerce_audit_value_tuple_becomes_list() -> None:
    assert _coerce_audit_value((1, Decimal("2"), "3")) == [1, "2", "3"]
