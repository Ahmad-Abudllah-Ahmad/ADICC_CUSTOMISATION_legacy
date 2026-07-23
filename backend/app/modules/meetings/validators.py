# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Meetings validation rules.

Ships two first-class rules registered with the platform rule registry so the
meetings module honours the "no module without validation" principle:

* ``MeetingActionOwnershipRule`` (ERROR) - a tracked action item must have an
  owner and a due date, otherwise it cannot be followed up.
* ``MeetingMinutesReadyRule`` (ERROR) - minutes cannot be issued while a
  required agenda item is unaddressed or no attendee is marked present.

The rules run against a plain dict context (no ORM), so they stay pure and are
trivially unit-testable. The service layer enforces the same pure checks
(:mod:`app.modules.meetings.logic`) at the API boundary by raising HTTP 422, so
bad data is blocked, not merely flagged.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.validation.engine import (
    RuleCategory,
    RuleResult,
    Severity,
    ValidationContext,
    ValidationRule,
    rule_registry,
)
from app.modules.meetings.logic import minutes_issue_problems, validate_action_fields

logger = logging.getLogger(__name__)


def _actions(context: ValidationContext) -> list[dict[str, Any]]:
    data = context.data
    if isinstance(data, dict):
        items = data.get("action_items", [])
        return [a for a in items if isinstance(a, dict)]
    if isinstance(data, list):
        return [a for a in data if isinstance(a, dict)]
    return []


def _minutes_content(context: ValidationContext) -> dict[str, Any]:
    data = context.data
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, dict):
            return content
        return data
    return {}


class MeetingActionOwnershipRule(ValidationRule):
    """Every tracked action item must have an owner and a due date."""

    rule_id = "meetings.action_ownership"
    name = "Action item has an owner and a due date"
    standard = "meetings"
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "A tracked action item needs an owner and a due date so it can be followed up"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for idx, action in enumerate(_actions(context)):
            problems = validate_action_fields(
                action.get("owner_id"),
                action.get("owner_name"),
                action.get("due_date"),
                action.get("status"),
            )
            passed = not problems
            label = str(action.get("description") or f"action {idx + 1}")[:80]
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message="OK" if passed else f"'{label}': {' '.join(problems)}",
                    element_ref=str(action.get("id") or ""),
                    suggestion=None if passed else "Set an owner and a due date on the action item",
                )
            )
        return results


class MeetingMinutesReadyRule(ValidationRule):
    """Minutes cannot be issued while a required agenda item is unaddressed."""

    rule_id = "meetings.minutes_ready"
    name = "Minutes are ready to issue"
    standard = "meetings"
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "Every required agenda item must have a discussion or decision before minutes are issued"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        problems = minutes_issue_problems(_minutes_content(context))
        if not problems:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=True,
                    message="OK",
                )
            ]
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=False,
                message=problem,
                suggestion="Record the discussion or decision, then issue the minutes",
            )
            for problem in problems
        ]


def register_meetings_validation_rules() -> None:
    """Register the meetings rules with the platform rule registry."""
    rule_registry.register(MeetingActionOwnershipRule(), ["meetings"])
    rule_registry.register(MeetingMinutesReadyRule(), ["meetings"])
    logger.debug("meetings: registered 2 validation rules")
