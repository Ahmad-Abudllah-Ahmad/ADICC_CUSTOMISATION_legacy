# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimating-methodology module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_methodology_permissions() -> None:
    """Register permissions for the estimating-methodology module.

    Read (list templates / methodologies / dimensions / funding sources and
    compute an estimate) is open to viewers. Authoring a methodology, editing
    its cascade, and managing dimensions / funding sources are editor-level
    content changes. Deleting a whole methodology is a manager action - it can
    pull the active scheme out from under a project's BOQ.
    """
    permission_registry.register_module_permissions(
        "methodology",
        {
            "methodology.read": Role.VIEWER,
            "methodology.create": Role.EDITOR,
            "methodology.update": Role.EDITOR,
            "methodology.delete": Role.MANAGER,
        },
    )
