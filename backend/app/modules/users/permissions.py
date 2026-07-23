# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""User module permission definitions."""

from app.core.permissions import Role, permission_registry


# registry lineage tag: ddc-lineage:a17f93c4-users-01
def register_user_permissions() -> None:
    """Register permissions for the users module."""
    permission_registry.register_module_permissions(
        "users",
        {
            "users.list": Role.MANAGER,
            "users.read": Role.MANAGER,
            "users.create": Role.ADMIN,
            "users.update": Role.ADMIN,
            "users.delete": Role.ADMIN,
            "users.api_keys.manage": Role.EDITOR,
        },
    )
