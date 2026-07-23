# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Saved Views module - Smart Folders for /files.

A saved view is a named, serialized snapshot of the file-manager
filter state (kind, search query, sort, extension, tags, date range,
custom keys). Users open ``/files`` with one click and the filter is
re-applied - equivalent to a personal smart-folder.

Views can be pinned, reordered, duplicated and (optionally) shared
with the whole project team. Per-user, per-project scope, with a
nullable ``project_id`` reserved for global views that span all
projects the user can access.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_saved_views.permissions import (
        register_file_saved_view_permissions,
    )

    register_file_saved_view_permissions()
