# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resumable Uploads module permission definitions.

These strings MUST be registered or ``RequirePermission`` silently denies
every non-admin caller (the router would declare a permission the registry
never learned about). ``register_resumable_upload_permissions`` is invoked
from the module ``on_startup`` hook so the registry is populated at load
time, the same contract every other module follows.
"""

from app.core.permissions import Role, permission_registry


def register_resumable_upload_permissions() -> None:
    """Register RBAC permissions for the resumable_uploads module."""
    permission_registry.register_module_permissions(
        "resumable_uploads",
        {
            "resumable_uploads.create": Role.EDITOR,
            "resumable_uploads.read": Role.VIEWER,
            "resumable_uploads.delete": Role.EDITOR,
        },
    )
