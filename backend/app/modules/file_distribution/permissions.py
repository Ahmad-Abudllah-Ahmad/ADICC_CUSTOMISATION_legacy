# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Distribution RBAC permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_distribution_permissions() -> None:
    """Register permissions for the file-distribution module.

    ``read``     - list / search lists, members, subscriptions and the
                   cross-project file search itself.
    ``write``    - create / edit / delete lists, members, subscriptions.
    ``subscribe``- specifically subscribe oneself or another user to a
                   project/kind. Pulled out separately so a tenant
                   policy can grant subscription-management to viewers
                   without unlocking list write access.
    """
    permission_registry.register_module_permissions(
        "file_distribution",
        {
            "file_distribution.read": Role.VIEWER,
            "file_distribution.write": Role.EDITOR,
            "file_distribution.subscribe": Role.VIEWER,
        },
    )
