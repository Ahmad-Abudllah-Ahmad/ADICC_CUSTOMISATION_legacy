# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File tags module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_tags_permissions() -> None:
    """Register permissions for the file_tags module.

    * ``file_tags.read``   - any project member can see the tag list.
    * ``file_tags.write``  - editor and up can create/rename/delete.
    * ``file_tags.assign`` - editor and up can attach tags to files
      (bulk + single).
    """
    permission_registry.register_module_permissions(
        "file_tags",
        {
            "file_tags.read": Role.VIEWER,
            "file_tags.write": Role.EDITOR,
            "file_tags.assign": Role.EDITOR,
        },
    )
