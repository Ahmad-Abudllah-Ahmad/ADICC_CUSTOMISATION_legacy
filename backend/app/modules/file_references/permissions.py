# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File References module permission definitions.

Three permissions cover both surfaces (ISO 19650 validation and
cross-entity references):

* ``file_references.read``  - list violations / list references
                              (VIEWER tier).
* ``file_references.write`` - create / delete references, run
                              project-wide name scans, acknowledge
                              violations (EDITOR tier).
"""

from app.core.permissions import Role, permission_registry


def register_file_references_permissions() -> None:
    """Register permissions for the file_references module."""
    permission_registry.register_module_permissions(
        "file_references",
        {
            "file_references.read": Role.VIEWER,
            "file_references.write": Role.EDITOR,
        },
    )
