# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Approvals (W8) RBAC permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_approval_permissions() -> None:
    """Register the four RBAC permissions for the approvals module.

    * ``file_approvals.read``         - list + view workflows
    * ``file_approvals.submit``       - submit a file for approval
    * ``file_approvals.decide``       - record a decision on a step
    * ``file_approvals.manage_stamps`` - create / edit stamp templates
    """
    permission_registry.register_module_permissions(
        "file_approvals",
        {
            "file_approvals.read": Role.VIEWER,
            "file_approvals.submit": Role.EDITOR,
            "file_approvals.decide": Role.EDITOR,
            "file_approvals.manage_stamps": Role.MANAGER,
        },
    )
