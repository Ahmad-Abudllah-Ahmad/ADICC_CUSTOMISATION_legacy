# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for the basis-of-estimate derivation engine.

The engine (``app.modules.estimate_basis.derivation``) is pure - stdlib only, no
ORM or app imports - so it is loaded here directly from its file path. That keeps
the test independent of the FastAPI dependency graph (which does not import
cleanly on a bare interpreter) while still exercising the real module, and it
runs identically here and in CI.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

_DERIVATION_PATH = Path(__file__).resolve().parents[2] / "app" / "modules" / "estimate_basis" / "derivation.py"
_spec = importlib.util.spec_from_file_location("estimate_basis_derivation", _DERIVATION_PATH)
assert _spec and _spec.loader
derivation = importlib.util.module_from_spec(_spec)
# Register before exec: dataclasses under ``from __future__ import annotations``
# resolve field types via ``sys.modules[cls.__module__]``, which must exist.
sys.modules["estimate_basis_derivation"] = derivation
_spec.loader.exec_module(derivation)

to_decimal = derivation.to_decimal
fmt_decimal = derivation.fmt_decimal
normalize_din276_main_group = derivation.normalize_din276_main_group
derive_trades = derivation.derive_trades
draft_basis = derivation.draft_basis


def _pos(
    *,
    din276: str | None = None,
    description: str = "",
    quantity: str = "1",
    unit_rate: str = "100",
    total: str = "100",
) -> dict:
    classification = {"din276": din276} if din276 is not None else {}
    return {
        "classification": classification,
        "description": description,
        "quantity": quantity,
        "unit_rate": unit_rate,
        "total": total,
    }


# ── to_decimal: money parsing degrades, never raises ────────────────────────


def test_to_decimal_parses_and_degrades() -> None:
    assert to_decimal("1234.56") == Decimal("1234.56")
    assert to_decimal(10) == Decimal("10")
    assert to_decimal(None) == Decimal("0")
    assert to_decimal("") == Decimal("0")
    assert to_decimal("not-a-number") == Decimal("0")
    assert to_decimal("NaN") == Decimal("0")
    assert to_decimal("Infinity") == Decimal("0")


def test_fmt_decimal_is_two_places_plain() -> None:
    assert fmt_decimal(Decimal("1234.5")) == "1234.50"
    assert fmt_decimal(Decimal("0")) == "0.00"
    # Never scientific notation for a large rollup.
    assert "E" not in fmt_decimal(Decimal("100000000"))


# ── DIN 276 main-group normalisation ────────────────────────────────────────


def test_normalize_din276_main_group() -> None:
    assert normalize_din276_main_group("300") == "300"
    assert normalize_din276_main_group("331") == "300"
    assert normalize_din276_main_group("330.10") == "300"  # dotted CAD form
    assert normalize_din276_main_group("420") == "400"
    assert normalize_din276_main_group("") == ""
    assert normalize_din276_main_group("abc") == ""
    assert normalize_din276_main_group(None) == ""
    assert normalize_din276_main_group("030") == ""  # KG 0xx is not a main group


# ── derive_trades ────────────────────────────────────────────────────────────


def test_present_trades_from_classification_rollup_and_order() -> None:
    positions = [
        _pos(din276="330", total="500"),
        _pos(din276="331", total="1500"),  # same main group 300
        _pos(din276="420", total="800"),  # group 400
    ]
    coverage = derive_trades(positions)

    present = {p.code: p for p in coverage.present}
    assert set(present) == {"300", "400"}
    assert present["300"].position_count == 2
    assert present["300"].total == Decimal("2000")
    assert present["400"].total == Decimal("800")
    # Richest trade first.
    assert coverage.present[0].code == "300"
    assert coverage.classified_positions == 3
    assert coverage.unclassified_positions == 0


def test_absent_core_trade_becomes_available_for_exclusion() -> None:
    # Only building construction (300) present -> technical systems (400) absent.
    coverage = derive_trades([_pos(din276="330", total="100")])
    absent_codes = {t.code for t in coverage.absent_core}
    assert absent_codes == {"400"}

    # Both core trades present -> nothing expected-but-absent.
    both = derive_trades([_pos(din276="330"), _pos(din276="410")])
    assert both.absent_core == []


def test_keyword_fallback_classifies_unclassified_positions() -> None:
    positions = [
        _pos(description="Reinforced concrete slab to ground floor"),  # -> 300
        _pos(description="Supply and install HVAC ductwork"),  # -> 400
        _pos(description="Miscellaneous sundry line with no trade word"),  # -> none
    ]
    coverage = derive_trades(positions)
    present = {p.code for p in coverage.present}
    assert present == {"300", "400"}
    # None carried a DIN code, so none count as classified.
    assert coverage.classified_positions == 0
    assert coverage.unclassified_positions == 1


def test_quality_flags_are_counted() -> None:
    positions = [
        _pos(din276="330", unit_rate="0", total="0"),  # unpriced
        _pos(din276="330", quantity="0", total="0"),  # missing quantity
        _pos(din276="330", description="Provisional sum for signage"),  # provisional
        _pos(din276="330", description="Fire protection by others"),  # by others / excluded
    ]
    coverage = derive_trades(positions)
    assert coverage.total_positions == 4
    assert coverage.zero_rate_positions == 1
    assert coverage.missing_quantity_positions == 1
    assert coverage.provisional_positions == 1
    assert coverage.by_others_positions == 1


def test_empty_estimate_is_handled() -> None:
    coverage = derive_trades([])
    assert coverage.total_positions == 0
    assert coverage.present == []
    # Both core trades are missing from an empty estimate.
    assert {t.code for t in coverage.absent_core} == {"300", "400"}


# ── draft_basis ──────────────────────────────────────────────────────────────


def test_draft_produces_three_editable_lists() -> None:
    coverage = derive_trades(
        [
            _pos(din276="330", total="1000"),
            _pos(din276="330", unit_rate="0", total="0"),
        ]
    )
    draft = draft_basis(coverage, currency="EUR", base_date="2026-01-01")

    # One inclusion for the present trade.
    inc_codes = {q.trade_code for q in draft.inclusions}
    assert "300" in inc_codes
    assert all(q.category == "inclusion" for q in draft.inclusions)

    # Absent core trade (400) is offered as an exclusion, plus the standard set.
    exc_ids = {q.id for q in draft.exclusions}
    assert "exc-trade-400" in exc_ids
    assert "exc-vat" in exc_ids
    assert all(q.category == "exclusion" for q in draft.exclusions)

    # Flag-driven + context assumptions.
    asm_ids = {q.id for q in draft.assumptions}
    assert "asm-unpriced" in asm_ids  # one line had no rate
    assert "asm-base-date" in asm_ids
    assert "asm-currency" in asm_ids
    assert all(q.category == "assumption" for q in draft.assumptions)


def test_draft_is_deterministic() -> None:
    positions = [_pos(din276="330", total="10"), _pos(din276="410", total="20")]
    a = draft_basis(derive_trades(positions))
    b = draft_basis(derive_trades(positions))
    assert [q.id for q in a.inclusions] == [q.id for q in b.inclusions]
    assert [q.id for q in a.exclusions] == [q.id for q in b.exclusions]
    assert [q.id for q in a.assumptions] == [q.id for q in b.assumptions]


def test_qualification_to_dict_shape() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    item = draft_basis(coverage).inclusions[0]
    data = item.to_dict()
    assert set(data) == {
        "id",
        "category",
        "text",
        "trade_code",
        "trade_label",
        "basis",
        "source",
        "enabled",
    }
    assert data["source"] == "auto"
    assert data["enabled"] is True


def test_no_currency_or_base_date_omits_those_assumptions() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    draft = draft_basis(coverage)
    asm_ids = {q.id for q in draft.assumptions}
    assert "asm-currency" not in asm_ids
    assert "asm-base-date" not in asm_ids
    # Standard assumptions are always present.
    assert "asm-quantities" in asm_ids


# ── Sibling estimating-module assumptions (allowances / prelims / base date) ──


def _by_id(draft: object) -> dict:
    return {q.id: q for q in draft.assumptions}


def test_allowance_assumptions_one_line_each_plus_contingency_note() -> None:
    coverage = derive_trades([_pos(din276="330", total="1000")])
    allowances = [
        {
            "id": "a1",
            "label": "Ground works PS",
            "allowance_type": "provisional_sum",
            "held_amount": "50000",
            "currency": "EUR",
        },
        {
            "id": "a2",
            "label": "Design reserve",
            "allowance_type": "contingency",
            "held_amount": "25000",
            "currency": "EUR",
        },
    ]
    draft = draft_basis(coverage, allowances=allowances)
    by_id = _by_id(draft)

    assert by_id["asm-allowance-a1"].text == ("Allowance included: Ground works PS - 50000.00 EUR (provisional sum).")
    assert by_id["asm-allowance-a2"].text == ("Allowance included: Design reserve - 25000.00 EUR (contingency).")
    # A contingency is present -> the note names its amount.
    assert by_id["asm-contingency"].text == ("Contingency of 25000.00 EUR is included in the estimate total.")
    assert by_id["asm-allowance-a1"].basis == "allowance"
    assert all(q.category == "assumption" for q in draft.assumptions)


def test_allowances_without_contingency_note_says_not_included() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    allowances = [
        {
            "id": "a1",
            "label": "Facade PC",
            "allowance_type": "pc_sum",
            "held_amount": "12000",
            "currency": "GBP",
        },
    ]
    draft = draft_basis(coverage, allowances=allowances)
    by_id = _by_id(draft)

    assert by_id["asm-allowance-a1"].text == ("Allowance included: Facade PC - 12000.00 GBP (prime cost sum).")
    assert by_id["asm-contingency"].text == "Contingency is not included in the estimate total."


def test_allowance_blank_label_and_currency_degrade() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    # No id, no label, no currency - the line still reads cleanly.
    allowances = [{"allowance_type": "contingency", "held_amount": "1000"}]
    draft = draft_basis(coverage, allowances=allowances)
    by_id = _by_id(draft)

    assert by_id["asm-allowance-0"].text == ("Allowance included: Contingency - 1000.00 (contingency).")
    assert by_id["asm-contingency"].text == ("Contingency of 1000.00 is included in the estimate total.")


def test_preliminaries_assumption_summarises_rollup() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    prelim = {
        "grand_total": "80000",
        "time_related_total": "60000",
        "fixed_total": "20000",
        "item_count": 4,
        "currency": "EUR",
    }
    draft = draft_basis(coverage, preliminaries=prelim)
    by_id = _by_id(draft)

    assert by_id["asm-preliminaries"].text == (
        "Preliminaries assumed: 80000.00 EUR (4 items, 60000.00 EUR time-related)."
    )
    assert by_id["asm-preliminaries"].basis == "preliminaries"


def test_preliminaries_singular_item_word_and_no_currency() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    prelim = {"grand_total": "5000", "time_related_total": "0", "item_count": 1}
    draft = draft_basis(coverage, preliminaries=prelim)
    by_id = _by_id(draft)

    assert by_id["asm-preliminaries"].text == ("Preliminaries assumed: 5000.00 (1 item, 0.00 time-related).")


def test_pricing_base_date_assumption() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    draft = draft_basis(coverage, pricing_base_date="2026-03-31")
    by_id = _by_id(draft)

    assert by_id["asm-pricing-date"].text == (
        "Prices are current as of 2026-03-31; escalation beyond this date is excluded unless stated."
    )
    assert by_id["asm-pricing-date"].basis == "pricing-date"


def test_sibling_module_assumptions_omitted_when_absent() -> None:
    coverage = derive_trades([_pos(din276="330", total="10")])
    draft = draft_basis(coverage)
    asm_ids = {q.id for q in draft.assumptions}

    assert not any(i.startswith("asm-allowance-") for i in asm_ids)
    assert "asm-contingency" not in asm_ids
    assert "asm-preliminaries" not in asm_ids
    assert "asm-pricing-date" not in asm_ids

    # An empty allowance list and a zero-item prelim summary also draft nothing.
    draft2 = draft_basis(coverage, allowances=[], preliminaries={"item_count": 0})
    ids2 = {q.id for q in draft2.assumptions}
    assert "asm-contingency" not in ids2
    assert "asm-preliminaries" not in ids2
