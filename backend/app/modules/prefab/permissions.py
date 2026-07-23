# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Off-site / Prefab / DfMA permission definitions."""

from app.core.permissions import Role, permission_registry


def register_prefab_permissions() -> None:
    """Register permissions for the Prefab / DfMA module.

    Reading the register is a viewer action. Creating, editing and deleting
    units is a single ``write`` action at editor level. Advancing a unit's
    production stage is called out separately (``advance``) so it can later be
    tightened - for example to a factory/QA role - without touching the plain
    create/edit permission.
    """
    permission_registry.register_module_permissions(
        "prefab",
        {
            "prefab.read": Role.VIEWER,
            "prefab.write": Role.EDITOR,
            "prefab.advance": Role.EDITOR,
        },
    )
