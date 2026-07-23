# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests - the three ai_takeoff validation rules (issue #194).

Validation is first-class for the vision path: the scale sanity belt, the
polygon self-intersection parity rule, and the low-confidence review flag fire
correctly and resolve their messages through the i18n templates in en/de/ru.
Pure-Python, no DB.
"""

from __future__ import annotations

import pytest

from app.core.validation.engine import RuleCategory, Severity, ValidationContext
from app.core.validation.rules import (
    TakeoffLowConfidenceReviewRule,
    TakeoffPolygonSelfIntersectionRule,
    TakeoffScaleSanityRule,
)

# A1 page in PDF points.
A1_W_PT = 1684.0
A1_H_PT = 2384.0


def _ctx(data: dict, locale: str = "en") -> ValidationContext:
    return ValidationContext(data=data, metadata={"locale": locale})


# ---------------------------------------------------------------------------
# Scale sanity belt
# ---------------------------------------------------------------------------


class TestScaleSanityRule:
    @pytest.mark.asyncio
    async def test_realistic_scale_passes(self) -> None:
        rule = TakeoffScaleSanityRule()
        # ~82 px/m on an A1 page implies ~29 m across - plausible.
        ctx = _ctx({"scale_ratio_px_per_unit": 82.0, "page_width_pt": A1_W_PT, "page_height_pt": A1_H_PT})
        results = await rule.validate(ctx)
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_absurd_scale_fails(self) -> None:
        rule = TakeoffScaleSanityRule()
        # A ratio that turns the A1 sheet into millions of metres across.
        ctx = _ctx({"scale_ratio_px_per_unit": 0.0001, "page_width_pt": A1_W_PT, "page_height_pt": A1_H_PT})
        results = await rule.validate(ctx)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_no_scale_produces_no_finding(self) -> None:
        rule = TakeoffScaleSanityRule()
        ctx = _ctx({"scale_ratio_px_per_unit": None, "page_width_pt": A1_W_PT, "page_height_pt": A1_H_PT})
        results = await rule.validate(ctx)
        assert results == []  # an honest "no evidence" is not a finding


# ---------------------------------------------------------------------------
# Polygon self-intersection parity
# ---------------------------------------------------------------------------


class TestPolygonSelfIntersectionRule:
    @pytest.mark.asyncio
    async def test_simple_square_passes(self) -> None:
        rule = TakeoffPolygonSelfIntersectionRule()
        square = {
            "proposals": [
                {
                    "id": "m1",
                    "type": "area",
                    "annotation": "Kitchen",
                    "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}],
                }
            ]
        }
        results = await rule.validate(_ctx(square))
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_bowtie_fails(self) -> None:
        rule = TakeoffPolygonSelfIntersectionRule()
        bowtie = {
            "proposals": [
                {
                    "id": "m2",
                    "type": "area",
                    "annotation": "Bowtie",
                    "points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                }
            ]
        }
        results = await rule.validate(_ctx(bowtie))
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].category == RuleCategory.STRUCTURE

    @pytest.mark.asyncio
    async def test_count_proposals_are_skipped(self) -> None:
        rule = TakeoffPolygonSelfIntersectionRule()
        counts = {"proposals": [{"id": "c1", "type": "count", "points": [{"x": 1, "y": 1}]}]}
        results = await rule.validate(_ctx(counts))
        assert results == []  # only area proposals are checked


# ---------------------------------------------------------------------------
# Low-confidence review
# ---------------------------------------------------------------------------


class TestLowConfidenceReviewRule:
    @pytest.mark.asyncio
    async def test_high_confidence_passes(self) -> None:
        rule = TakeoffLowConfidenceReviewRule()
        ctx = _ctx({"proposals": [{"id": "m1", "annotation": "Kitchen", "confidence": 0.85}]})
        results = await rule.validate(ctx)
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_low_confidence_flagged_as_warning(self) -> None:
        rule = TakeoffLowConfidenceReviewRule()
        ctx = _ctx({"proposals": [{"id": "m2", "annotation": "Bath", "confidence": 0.40}]})
        results = await rule.validate(ctx)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# i18n resolution in en / de / ru
# ---------------------------------------------------------------------------


class TestI18nResolution:
    @pytest.mark.parametrize("locale", ["en", "de", "ru"])
    @pytest.mark.asyncio
    async def test_scale_fail_message_localized(self, locale: str) -> None:
        rule = TakeoffScaleSanityRule()
        ctx = _ctx(
            {"scale_ratio_px_per_unit": 0.0001, "page_width_pt": A1_W_PT, "page_height_pt": A1_H_PT},
            locale=locale,
        )
        results = await rule.validate(ctx)
        msg = results[0].message
        # The key must resolve to a real string, never the raw key itself.
        assert msg
        assert "ai_takeoff.scale_sanity.fail" not in msg

    @pytest.mark.parametrize("locale", ["en", "de", "ru"])
    @pytest.mark.asyncio
    async def test_self_intersection_fail_message_localized(self, locale: str) -> None:
        rule = TakeoffPolygonSelfIntersectionRule()
        bowtie = {
            "proposals": [
                {
                    "id": "m2",
                    "type": "area",
                    "annotation": "X",
                    "points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                }
            ]
        }
        results = await rule.validate(_ctx(bowtie, locale=locale))
        msg = results[0].message
        assert msg
        assert "ai_takeoff.polygon_self_intersection.fail" not in msg

    @pytest.mark.parametrize("locale", ["en", "de", "ru"])
    @pytest.mark.asyncio
    async def test_low_confidence_fail_message_localized(self, locale: str) -> None:
        rule = TakeoffLowConfidenceReviewRule()
        ctx = _ctx({"proposals": [{"id": "m2", "annotation": "Y", "confidence": 0.3}]}, locale=locale)
        results = await rule.validate(ctx)
        msg = results[0].message
        assert msg
        assert "ai_takeoff.low_confidence_review.fail" not in msg


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_ai_takeoff_rules_register_in_the_builtin_set() -> None:
    from app.core.validation.engine import rule_registry
    from app.core.validation.rules import register_builtin_rules

    register_builtin_rules()
    rule_ids = {r["rule_id"] for r in rule_registry.list_rules()}
    assert "ai_takeoff.scale_sanity" in rule_ids
    assert "ai_takeoff.polygon_self_intersection" in rule_ids
    assert "ai_takeoff.low_confidence_review" in rule_ids
