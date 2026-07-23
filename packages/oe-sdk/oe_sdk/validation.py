"""Validation primitives, re-exported from the platform core, plus a helper.

Validation is a first-class extension point. A module contributes rules by
subclassing ``ValidationRule`` and registering an instance into one or more
named rule sets. The loader auto-imports a module's ``validators.py`` at
startup, so registering at import time is the whole contract.

The pieces, straight from ``app.core.validation.engine``:

- ``ValidationRule`` is the abstract base. Set the class attributes ``rule_id``,
  ``name``, ``standard``, ``severity``, ``category`` and ``description``, then
  implement ``async def validate(self, context) -> list[RuleResult]``.
- ``ValidationContext`` carries the ``data`` to check plus ``project_id``,
  ``region``, ``standard`` and ``metadata``.
- ``RuleResult`` records ``passed``, ``severity``, a ``message``, an optional
  ``element_ref`` back to the offending element, and an optional ``suggestion``.
- ``rule_registry`` is the global registry, ``validation_engine`` runs the
  rule sets over data and returns a ``ValidationReport``.
"""

from __future__ import annotations

from app.core.validation.engine import (
    RuleCategory,
    RuleRegistry,
    RuleResult,
    Severity,
    ValidationContext,
    ValidationEngine,
    ValidationReport,
    ValidationRule,
    ValidationStatus,
    rule_registry,
    validation_engine,
)

__all__ = [
    "ValidationRule",
    "RuleResult",
    "ValidationContext",
    "ValidationReport",
    "Severity",
    "RuleCategory",
    "ValidationStatus",
    "rule_registry",
    "validation_engine",
    "register_rule",
    "RuleRegistry",
    "ValidationEngine",
]


def register_rule(rule: ValidationRule, *rule_sets: str) -> None:
    """Register a rule instance into the global registry under rule sets.

    Thin convenience over ``rule_registry.register(rule, [...])`` that takes the
    rule set names as positional arguments instead of a list:

        register_rule(
            SiteLogEntryHasNoteRule(),
            "site_log",
            "project_completeness",
        )

    With no rule sets given, the rule falls back to its own ``standard`` (the
    same default ``rule_registry.register`` uses). Call this at import time from
    your module's ``validators.py`` so the loader picks it up on the next boot.
    """
    rule_registry.register(rule, list(rule_sets) or None)
