# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Record Publishing RBAC permission definitions."""

from app.core.permissions import Role, permission_registry

# Publishing a record sends it to external recipients as a formal, acknowledged
# transmittal, so it is an editor-level write. Downloading an already-published
# record as a project member is viewer-level; external recipients use the
# separate public token route and need no permission.
RECORD_PUBLISHING_PERMISSIONS: dict[str, Role] = {
    "record_publishing.read": Role.VIEWER,
    "record_publishing.publish": Role.EDITOR,
}


def register_record_publishing_permissions() -> None:
    """Register permissions for the record-publishing module."""
    permission_registry.register_module_permissions(
        "record_publishing",
        RECORD_PUBLISHING_PERMISSIONS,
    )
