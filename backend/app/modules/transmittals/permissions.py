# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Transmittals module permission definitions.

Wave-5 audit (2026-05-28) discovered the router declares
``RequirePermission("transmittals.{read|create|update|delete}")`` but the
module never registered the permissions with the live permission
registry, so all non-admin roles received 403 with a stray
"Unknown permission checked" WARN. Admins succeeded only via the role
bypass. This file ships the missing registration; semantics mirror the
neighbouring document-flow modules (submittals, correspondence).
"""

from app.core.permissions import Role, permission_registry


def register_transmittals_permissions() -> None:
    """Register RBAC permissions for the transmittals module.

    Permission layout:
        transmittals.read   - list / get transmittals (VIEWER+)
        transmittals.create - issue a new transmittal (EDITOR+)
        transmittals.update - edit, lock/issue, recipient acknowledge/respond (EDITOR+)
        transmittals.delete - delete a draft transmittal (MANAGER+)
    """
    permission_registry.register_module_permissions(
        "transmittals",
        {
            "transmittals.read": Role.VIEWER,
            "transmittals.create": Role.EDITOR,
            "transmittals.update": Role.EDITOR,
            "transmittals.delete": Role.MANAGER,
        },
    )
