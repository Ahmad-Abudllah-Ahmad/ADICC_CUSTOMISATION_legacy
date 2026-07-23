# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File search module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_search_permissions() -> None:
    """Register permissions for the file_search module.

    * ``file_search.read``  - anyone with project access can query the
      content index.
    * ``file_search.index`` - only editors and up can trigger an
      indexing / reindexing run; OCR is CPU-heavy.
    """
    permission_registry.register_module_permissions(
        "file_search",
        {
            "file_search.read": Role.VIEWER,
            "file_search.index": Role.EDITOR,
        },
    )
