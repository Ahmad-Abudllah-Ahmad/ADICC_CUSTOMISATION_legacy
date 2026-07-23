# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts validation rules.

Ships three first-class rules registered with the platform rule registry under
the ``contracts`` rule set:

* ``ContractPartyRolesRule`` (ERROR) - a signed contract (active / completed)
  must carry at least one employer party and one contractor party.
* ``ContractPerformanceBondRule`` (WARNING) - a contract whose terms require a
  performance bond should have an active security row of that type.
* ``EOTDaysRule`` (ERROR) - a decided extension-of-time claim must never grant
  more days than were claimed.

The rules run against a plain dict context (no ORM), shaped by the service /
caller as::

    {
        "contract": {"id", "status", "contract_type", "terms": {...}},
        "parties": [{"party_role", "party_type", ...}],
        "securities": [{"security_type", "status", ...}],
        "eot_claims": [{"eot_number", "days_claimed", "days_granted", "status"}],
    }

Keeping the rules pure and dict-driven makes them trivially unit-testable and
satisfies the platform "no module without validation rules" requirement.
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

#: Rule set this module's rules register under.
CONTRACTS_RULE_SET = "contracts"

#: Contract statuses that count as "signed" (commercially live) for the
#: party-completeness check.
_SIGNED_STATUSES = frozenset({"active", "completed"})


def _data(context: ValidationContext) -> dict[str, Any]:
    return context.data if isinstance(context.data, dict) else {}


def _contract(context: ValidationContext) -> dict[str, Any]:
    contract = _data(context).get("contract")
    return contract if isinstance(contract, dict) else {}


def _rows(context: ValidationContext, key: str) -> list[dict[str, Any]]:
    rows = _data(context).get(key, [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _truthy(value: Any) -> bool:
    """Coerce a JSON-ish flag (bool / "true" / 1 / "yes") to a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "required")
    return False


class ContractPartyRolesRule(ValidationRule):
    """A signed contract must name both an employer and a contractor party."""

    rule_id = "contracts.parties_complete"
    name = "Contract has employer and contractor parties"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.COMPLETENESS
    description = "A signed contract must record at least one employer and one contractor party"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        contract = _contract(context)
        # The rule only applies to a signed (commercially live) contract; a
        # draft may still be assembling its party register.
        if str(contract.get("status", "")) not in _SIGNED_STATUSES:
            return []
        roles = {str(p.get("party_role", "")) for p in _rows(context, "parties")}
        ref = str(contract.get("id", ""))
        checks = (
            ("employer", "employer"),
            ("contractor", "contractor"),
        )
        results: list[RuleResult] = []
        for role, label in checks:
            present = role in roles
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=present,
                    message="OK" if present else f"Signed contract has no {label} party",
                    element_ref=ref,
                    suggestion=None if present else f"Add a party with role '{label}'",
                )
            )
        return results


class ContractPerformanceBondRule(ValidationRule):
    """A contract that requires a performance bond should hold an active one."""

    rule_id = "contracts.performance_bond_active"
    name = "Required performance bond is active"
    standard = CONTRACTS_RULE_SET
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS
    description = "A contract whose terms require a performance bond should have an active bond"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        contract = _contract(context)
        terms = contract.get("terms") if isinstance(contract.get("terms"), dict) else {}
        securities = _rows(context, "securities")
        # "Required" is signalled either by a terms flag or by a tracked bond
        # row still sitting in the "required" state.
        flagged = _truthy(terms.get("requires_performance_bond"))
        tracked = any(
            s.get("security_type") == "performance_bond" and s.get("status") == "required" for s in securities
        )
        if not (flagged or tracked):
            return []
        has_active = any(
            s.get("security_type") == "performance_bond" and s.get("status") == "active" for s in securities
        )
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=has_active,
                message="OK" if has_active else "Required performance bond is not active",
                element_ref=str(contract.get("id", "")),
                suggestion=(None if has_active else "Record an active performance bond security"),
            )
        ]


class EOTDaysRule(ValidationRule):
    """An EOT claim must never grant more days than were claimed."""

    rule_id = "contracts.eot_days_valid"
    name = "EOT granted days within claimed days"
    standard = CONTRACTS_RULE_SET
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "An extension-of-time claim cannot grant more days than were claimed"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for claim in _rows(context, "eot_claims"):
            try:
                claimed = int(claim.get("days_claimed", 0) or 0)
                granted = int(claim.get("days_granted", 0) or 0)
            except (TypeError, ValueError):
                # A non-numeric value is itself a data fault; flag it.
                claimed, granted = 0, 1
            passed = granted <= claimed
            number = claim.get("eot_number") or claim.get("id") or "claim"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=passed,
                    message=("OK" if passed else f"EOT {number} grants {granted} day(s) but only {claimed} claimed"),
                    element_ref=str(claim.get("id", "")),
                    suggestion=None if passed else "Reduce granted days to at most the claimed days",
                )
            )
        return results


def register_contracts_validation_rules() -> None:
    """Register the contracts rules with the platform rule registry."""
    rule_registry.register(ContractPartyRolesRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(ContractPerformanceBondRule(), [CONTRACTS_RULE_SET])
    rule_registry.register(EOTDaysRule(), [CONTRACTS_RULE_SET])
    logger.debug("contracts: registered 3 validation rules")
