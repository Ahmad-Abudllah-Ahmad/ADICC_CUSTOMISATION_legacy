# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder module-specific validation rules.

The assembled estimate is validated through the core engine with the universal
``boq_quality`` set plus the project's regional set (din276 / nrm /
masterformat / ...). These rules ADD the estimator-specific invariants the
generic rules cannot express, registered into the same rule registry under the
``ai_estimator`` rule set so the run can request them alongside ``boq_quality``.

Rules (severity drives whether they block apply - any ERROR fails ``can_apply``):

* ``ai_estimator.rate_grounding``        - ERROR. Every position must reference
                                           a real cost-database item
                                           (``metadata_.cost_item_id``). The LLM
                                           never invents a rate; a position with
                                           no grounding code is a bug.
* ``ai_estimator.group_has_quantity``    - ERROR. A group that reached assembly
                                           with a zero/negative quantity has
                                           nothing to price.
* ``ai_estimator.rate_currency_matches`` - ERROR. A position's rate currency
                                           must match the run's base currency
                                           (the never-blend invariant; a
                                           mismatch slipping through is a bug).
* ``ai_estimator.resource_breakdown``    - WARNING. A composite position should
                                           carry a resource breakdown.
* ``ai_estimator.low_confidence``        - WARNING. A position applied with a
                                           confidence below MEDIUM and not
                                           human-overridden.
* ``ai_estimator.completeness``          - INFO. Surfaces CHECK_SCOPE missing
                                           items as advisory only.

Each position dict the service feeds in carries: ``id``, ``ordinal``,
``description``, ``unit``, ``quantity``, ``unit_rate``, ``currency``,
``confidence``, ``confidence_band``, ``human_confirmed`` (bool), ``resources``
(list), and ``metadata_`` ({cost_item_id, ...}). The ``metadata['base_currency']``
and ``metadata['missing_items']`` carry run-level context.
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

# Confidence floor below which an applied position is flagged (mirrors the
# medium band threshold the matchers use). A position confirmed by a human is
# exempt - the human took responsibility for the rate.
_MEDIUM_CONFIDENCE = 0.62


def _positions(context: ValidationContext) -> list[dict[str, Any]]:
    """Pull the position dicts the service handed the engine."""
    data = context.data or {}
    if isinstance(data, dict):
        positions = data.get("positions") or []
        return [p for p in positions if isinstance(p, dict)]
    return []


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ref(pos: dict[str, Any]) -> str | None:
    return pos.get("id") or pos.get("group_id") or pos.get("ordinal")


class AiEstimatorRateGrounding(ValidationRule):
    rule_id = "ai_estimator.rate_grounding"
    name = "AI Estimate Rate Grounding"
    standard = "ai_estimator"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "Every AI-estimate position must reference a real cost-database rate (no invented rates)."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for pos in _positions(context):
            meta = pos.get("metadata_") or pos.get("metadata") or {}
            grounded = bool(meta.get("cost_item_id")) or bool(pos.get("candidate_id"))
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=grounded,
                    message=(
                        "OK"
                        if grounded
                        else (
                            f"Position {pos.get('ordinal', '?')} has no grounded cost-database rate - "
                            "rates must come from the cost database, never the LLM."
                        )
                    ),
                    element_ref=_ref(pos),
                    suggestion=None if grounded else "Match this group to a cost-database rate before applying.",
                )
            )
        return results


class AiEstimatorGroupHasQuantity(ValidationRule):
    rule_id = "ai_estimator.group_has_quantity"
    name = "AI Estimate Group Has Quantity"
    standard = "ai_estimator"
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "A group that reached assembly must carry a positive quantity to price."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for pos in _positions(context):
            qty = _to_float(pos.get("quantity"))
            passed = qty is not None and qty > 0
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=("OK" if passed else f"Position {pos.get('ordinal', '?')} has a zero/negative quantity."),
                    element_ref=_ref(pos),
                )
            )
        return results


class AiEstimatorRateCurrencyMatches(ValidationRule):
    rule_id = "ai_estimator.rate_currency_matches"
    name = "AI Estimate Rate Currency Matches Project"
    standard = "ai_estimator"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "A position's rate currency must match the run base currency (currencies are never blended)."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        meta = context.metadata or {}
        base_currency = str(meta.get("base_currency") or "").strip().upper()
        # No base currency resolved (or position has no rate yet): the rule has
        # no signal, so emit a single passing row rather than false ERRORs.
        results: list[RuleResult] = []
        for pos in _positions(context):
            pos_ccy = str(pos.get("currency") or "").strip().upper()
            rate = _to_float(pos.get("unit_rate"))
            if not base_currency or not pos_ccy or rate is None or rate == 0:
                passed = True
            else:
                passed = pos_ccy == base_currency
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=(
                        "OK"
                        if passed
                        else (
                            f"Position {pos.get('ordinal', '?')} rate currency {pos_ccy} does not match "
                            f"the project base currency {base_currency}."
                        )
                    ),
                    element_ref=_ref(pos),
                )
            )
        return results


class AiEstimatorResourceBreakdown(ValidationRule):
    rule_id = "ai_estimator.resource_breakdown"
    name = "AI Estimate Resource Breakdown Present"
    standard = "ai_estimator"
    severity = Severity.WARNING
    category = RuleCategory.QUALITY
    description = "A composite position should carry a resource breakdown (labour / material / equipment)."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for pos in _positions(context):
            resources = pos.get("resources") or []
            has_resources = isinstance(resources, list) and len(resources) > 0
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=has_resources,
                    message=(
                        "OK"
                        if has_resources
                        else f"Position {pos.get('ordinal', '?')} has no resource breakdown - rate is a flat lump."
                    ),
                    element_ref=_ref(pos),
                )
            )
        return results


class AiEstimatorLowConfidence(ValidationRule):
    rule_id = "ai_estimator.low_confidence"
    name = "AI Estimate Low-Confidence Position"
    standard = "ai_estimator"
    severity = Severity.WARNING
    category = RuleCategory.QUALITY
    description = "A position applied below medium confidence that was not human-confirmed should be reviewed."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for pos in _positions(context):
            human_confirmed = bool(pos.get("human_confirmed"))
            conf = _to_float(pos.get("confidence"))
            # A human-confirmed pick passes regardless. A real low confidence
            # warns; a None confidence (no real score) also warns so it is not
            # silently treated as fine.
            if human_confirmed:
                passed = True
            elif conf is None:
                passed = False
            else:
                passed = conf >= _MEDIUM_CONFIDENCE
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=(
                        "OK"
                        if passed
                        else (
                            f"Position {pos.get('ordinal', '?')} has low/unknown match confidence and was "
                            "not human-confirmed."
                        )
                    ),
                    element_ref=_ref(pos),
                    suggestion=None if passed else "Review and confirm the matched rate before applying.",
                )
            )
        return results


class AiEstimatorCompleteness(ValidationRule):
    rule_id = "ai_estimator.completeness"
    name = "AI Estimate Scope Completeness"
    standard = "ai_estimator"
    severity = Severity.INFO
    category = RuleCategory.COMPLETENESS
    description = "Advisory: trades/scope the AI scope-check believes may be missing from the estimate."

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        meta = context.metadata or {}
        missing = meta.get("missing_items") or []
        missing = [str(m) for m in missing if m] if isinstance(missing, list) else []
        passed = len(missing) == 0
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=passed,
                message=("OK" if passed else f"Scope check flags possible missing items: {', '.join(missing[:10])}"),
                element_ref=None,
                details={"missing_items": missing},
            )
        ]


# Rules registered under the ``ai_estimator`` rule set. The run requests this
# set alongside ``boq_quality`` and the project's regional set.
_AI_ESTIMATOR_RULES: tuple[ValidationRule, ...] = (
    AiEstimatorRateGrounding(),
    AiEstimatorGroupHasQuantity(),
    AiEstimatorRateCurrencyMatches(),
    AiEstimatorResourceBreakdown(),
    AiEstimatorLowConfidence(),
    AiEstimatorCompleteness(),
)


def register_ai_estimator_rules() -> None:
    """Register the module's validation rules with the core rule registry.

    Idempotent - the registry overwrites a rule by id, so a re-import / hot
    reload re-registers cleanly. Called from the module ``on_startup`` hook.
    """
    for rule in _AI_ESTIMATOR_RULES:
        rule_registry.register(rule, ["ai_estimator"])
    logger.debug("Registered %d ai_estimator validation rules", len(_AI_ESTIMATOR_RULES))
