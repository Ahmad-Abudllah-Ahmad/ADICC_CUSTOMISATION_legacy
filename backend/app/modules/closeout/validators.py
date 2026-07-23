# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Closeout validation rules.

Ships two first-class rules registered with the platform rule registry:

* ``CloseoutCompletenessRule`` (ERROR) - any required slot left unbound is a
  blocking gap in the handover package.
* ``CloseoutEvidenceRule`` (WARNING) - a bound required slot whose evidence
  has not yet been human-verified is flagged for sign-off.

The rules run against a plain dict context (no ORM), shaped by the service /
caller as ``{"slots": [{slot_key, title, is_required, status,
source_kind, generated_artifact}], "project_id": ...}``. ``status`` is one of
``empty`` / ``bound`` / ``verified``. This keeps the rules pure and trivially
unit-testable while satisfying the platform "no module without validation
rules" requirement.
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

logger = logging.getLogger(__name__)

# Generated artifacts the build always produces; they are never a hard gap.
_GENERATED_ARTIFACTS = {"cobie_xlsx", "punch_closure_report", "inspection_cert_pdf"}


def _slots(context: ValidationContext) -> list[dict[str, Any]]:
    data = context.data
    if isinstance(data, dict):
        slots = data.get("slots", [])
        return [s for s in slots if isinstance(s, dict)]
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    return []


def _is_generated(slot: dict[str, Any]) -> bool:
    return slot.get("source_kind") == "generated" and slot.get("generated_artifact") in _GENERATED_ARTIFACTS


class CloseoutCompletenessRule(ValidationRule):
    """Every required slot must carry evidence before the package is issued."""

    rule_id = "closeout.completeness"
    name = "Closeout required items bound"
    standard = "closeout"
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "Every required closeout checklist item must be bound to evidence"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for slot in _slots(context):
            if not slot.get("is_required"):
                continue
            if _is_generated(slot):
                # Produced by the build itself; not a binding gap.
                continue
            status = str(slot.get("status", "empty"))
            passed = status in ("bound", "verified")
            title = slot.get("title") or slot.get("slot_key") or "item"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message="OK" if passed else f"Required item '{title}' has no evidence bound",
                    element_ref=str(slot.get("slot_key") or ""),
                    suggestion=None if passed else "Bind a CDE document or external reference to this item",
                )
            )
        return results


class CloseoutEvidenceRule(ValidationRule):
    """A bound required slot should be human-verified before handover."""

    rule_id = "closeout.evidence_verified"
    name = "Closeout evidence verified"
    standard = "closeout"
    severity = Severity.WARNING
    category = RuleCategory.CONSISTENCY
    description = "Bound required closeout items should be human-verified before issue"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for slot in _slots(context):
            if not slot.get("is_required"):
                continue
            if _is_generated(slot):
                continue
            status = str(slot.get("status", "empty"))
            if status == "empty":
                # Completeness rule already covers unbound; no double-flag.
                continue
            passed = status == "verified"
            title = slot.get("title") or slot.get("slot_key") or "item"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message="OK" if passed else f"Evidence for '{title}' is not yet verified",
                    element_ref=str(slot.get("slot_key") or ""),
                    suggestion=None if passed else "Review and verify the bound evidence (manager sign-off)",
                )
            )
        return results


def register_closeout_validation_rules() -> None:
    """Register the closeout rules with the platform rule registry."""
    rule_registry.register(CloseoutCompletenessRule(), ["closeout"])
    rule_registry.register(CloseoutEvidenceRule(), ["closeout"])
    logger.debug("closeout: registered 2 validation rules")
