# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Forms & Checklists module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_forms_permissions() -> None:
    """Register permissions for the Forms & Checklists module.

    Reading the library and submissions is open to any viewer. Authoring
    templates and filling / completing submissions is content work (editor).
    Deleting a template or submission is a manager-level action.
    """
    permission_registry.register_module_permissions(
        "forms",
        {
            "forms.read": Role.VIEWER,
            "forms.create": Role.EDITOR,
            "forms.update": Role.EDITOR,
            "forms.delete": Role.MANAGER,
        },
    )
