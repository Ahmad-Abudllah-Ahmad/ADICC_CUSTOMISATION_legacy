# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Preliminaries module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_preliminaries_permissions() -> None:
    """Register RBAC permissions for the preliminaries module.

    Reading the preliminaries and its summary needs viewer access; adding or
    editing items needs editor; deleting an item is a manager-level action so a
    priced preliminaries line is not removed from the estimate by accident.
    """
    permission_registry.register_module_permissions(
        "preliminaries",
        {
            "preliminaries.create": Role.EDITOR,
            "preliminaries.read": Role.VIEWER,
            "preliminaries.update": Role.EDITOR,
            "preliminaries.delete": Role.MANAGER,
        },
    )
