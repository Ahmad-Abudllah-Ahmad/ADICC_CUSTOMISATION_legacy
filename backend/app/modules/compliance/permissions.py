# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Compliance DSL module permission definitions.

A user-authored DSL rule is registered into the global validation engine
and runs against project data - authoring or deleting one is a privileged
action, not something a read-only VIEWER should be able to do. These
permissions gate the write/delete verbs on the rule-builder router. The
read-only natural-language helper endpoints (``from-nl``, ``nl-patterns``,
``validate-syntax``) stay auth-only because they have no side effects.
"""

from app.core.permissions import Role, permission_registry


def register_compliance_permissions() -> None:
    """Register permissions for the compliance DSL rule builder."""
    permission_registry.register_module_permissions(
        "compliance",
        {
            "compliance.rule.create": Role.MANAGER,
            "compliance.rule.read": Role.EDITOR,
            "compliance.rule.delete": Role.MANAGER,
        },
    )
