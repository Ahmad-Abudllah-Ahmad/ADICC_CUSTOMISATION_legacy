# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free tests for the site-logistics delivery validation.

Exercises the pure gate-hours + overlap helpers that the service uses to reject
bad bookings, plus the two first-class validation rules. No ORM / DB import, so
this runs on every deployment (including local py3.11 where the service /
router pull PostgreSQL at import time).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.core.validation.engine import ValidationContext
from app.modules.site_logistics.validators import (
    SiteLogisticsDeliveryOverlapRule,
    SiteLogisticsGateHoursRule,
    delivery_within_gate_hours,
    find_first_overlap,
    parse_hhmm,
    windows_overlap,
)


def _dt(hour: int, minute: int = 0, day: int = 8) -> datetime:
    return datetime(2026, 7, day, hour, minute)


# ── parse_hhmm ─────────────────────────────────────────────────────────────


def test_parse_hhmm_valid() -> None:
    assert parse_hhmm("07:00") == 7 * 60
    assert parse_hhmm("18:30") == 18 * 60 + 30
    assert parse_hhmm("00:00") == 0


def test_parse_hhmm_invalid() -> None:
    assert parse_hhmm(None) is None
    assert parse_hhmm("") is None
    assert parse_hhmm("7am") is None
    assert parse_hhmm("24:00") is None
    assert parse_hhmm("12:60") is None


# ── delivery_within_gate_hours ─────────────────────────────────────────────


def test_within_gate_hours_ok() -> None:
    ok, reason = delivery_within_gate_hours("07:00", "18:00", _dt(9), _dt(10))
    assert ok is True
    assert reason is None


def test_before_open_rejected() -> None:
    ok, reason = delivery_within_gate_hours("07:00", "18:00", _dt(6), _dt(6, 30))
    assert ok is False
    assert reason is not None and "opens" in reason


def test_after_close_rejected() -> None:
    ok, reason = delivery_within_gate_hours("07:00", "18:00", _dt(17), _dt(19))
    assert ok is False
    assert reason is not None and "closes" in reason


def test_boundary_is_inclusive() -> None:
    # A window that exactly fills the gate's hours is allowed.
    ok, _ = delivery_within_gate_hours("07:00", "18:00", _dt(7), _dt(18))
    assert ok is True


def test_multiday_window_rejected() -> None:
    ok, reason = delivery_within_gate_hours("07:00", "18:00", _dt(9, day=8), _dt(9, day=9))
    assert ok is False
    assert reason is not None and "same day" in reason


def test_end_before_start_rejected() -> None:
    ok, reason = delivery_within_gate_hours("07:00", "18:00", _dt(10), _dt(9))
    assert ok is False
    assert reason is not None


def test_no_gate_hours_is_unrestricted() -> None:
    # A gate with no configured hours never blocks a delivery.
    ok, reason = delivery_within_gate_hours(None, None, _dt(3), _dt(4))
    assert ok is True
    assert reason is None


# ── windows_overlap / find_first_overlap ───────────────────────────────────


def test_windows_overlap_true() -> None:
    assert windows_overlap(_dt(9), _dt(11), _dt(10), _dt(12)) is True


def test_windows_touching_do_not_overlap() -> None:
    # Back-to-back slots (one ends when the next starts) are allowed.
    assert windows_overlap(_dt(9), _dt(10), _dt(10), _dt(11)) is False


def test_windows_disjoint_do_not_overlap() -> None:
    assert windows_overlap(_dt(9), _dt(10), _dt(13), _dt(14)) is False


def test_find_first_overlap_finds_clash() -> None:
    existing = [(_dt(8), _dt(9)), (_dt(10, 30), _dt(11, 30))]
    clash = find_first_overlap(_dt(11), _dt(12), existing)
    assert clash == (_dt(10, 30), _dt(11, 30))


def test_find_first_overlap_none_when_clear() -> None:
    existing = [(_dt(8), _dt(9)), (_dt(12), _dt(13))]
    assert find_first_overlap(_dt(9), _dt(10), existing) is None


# ── First-class validation rules (still DB-free) ───────────────────────────


def _delivery(
    delivery_id: str,
    gate_id: str,
    start_hour: int,
    end_hour: int,
    status: str = "requested",
) -> dict[str, object]:
    return {
        "id": delivery_id,
        "gate_id": gate_id,
        "status": status,
        "supplier_name": delivery_id,
        "window_start": _dt(start_hour).isoformat(),
        "window_end": _dt(end_hour).isoformat(),
    }


def test_gate_hours_rule_flags_out_of_hours() -> None:
    context = ValidationContext(
        data={
            "gates": {"g1": {"open_time": "07:00", "close_time": "18:00", "name": "Main"}},
            "deliveries": [
                _delivery("d1", "g1", 9, 10),
                _delivery("d2", "g1", 19, 20),
            ],
        }
    )
    results = asyncio.run(SiteLogisticsGateHoursRule().validate(context))
    by_ref = {r.element_ref: r.passed for r in results}
    assert by_ref["d1"] is True
    assert by_ref["d2"] is False


def test_overlap_rule_flags_two_approved_on_same_gate() -> None:
    context = ValidationContext(
        data={
            "deliveries": [
                _delivery("d1", "g1", 9, 11, status="approved"),
                _delivery("d2", "g1", 10, 12, status="approved"),
            ],
        }
    )
    results = asyncio.run(SiteLogisticsDeliveryOverlapRule().validate(context))
    passed = {r.element_ref: r.passed for r in results}
    # First is clear, second clashes with the first.
    assert passed["d1"] is True
    assert passed["d2"] is False


def test_overlap_rule_ignores_unapproved_and_other_gates() -> None:
    context = ValidationContext(
        data={
            "deliveries": [
                # requested (not approved) - never clash-checked
                _delivery("d1", "g1", 9, 11, status="requested"),
                _delivery("d2", "g1", 10, 12, status="requested"),
                # approved but on different gates - no clash with each other
                _delivery("d3", "g2", 9, 11, status="approved"),
                _delivery("d4", "g3", 9, 11, status="approved"),
            ],
        }
    )
    results = asyncio.run(SiteLogisticsDeliveryOverlapRule().validate(context))
    # Only the two approved (different-gate) deliveries are evaluated, both pass.
    assert {r.element_ref for r in results} == {"d3", "d4"}
    assert all(r.passed for r in results)
