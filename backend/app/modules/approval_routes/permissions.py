# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Approval Routes module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_approval_route_permissions() -> None:
    """Register RBAC permissions for the approval_routes module.

    Permission layout:
        approval_routes.read   - list / get routes + instances (VIEWER+)
        approval_routes.write  - create / edit routes, start instances (EDITOR+)
        approval_routes.decide - submit decision on a step (EDITOR+)
        approval_routes.manage - delete routes, cancel instances (MANAGER+)
    """
    permission_registry.register_module_permissions(
        "approval_routes",
        {
            "approval_routes.read": Role.VIEWER,
            "approval_routes.write": Role.EDITOR,
            "approval_routes.decide": Role.EDITOR,
            "approval_routes.manage": Role.MANAGER,
        },
    )
