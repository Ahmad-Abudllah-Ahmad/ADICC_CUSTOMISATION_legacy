# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Favourites / Pins module.

Per-user, per-project star + pin for any of the 8 file-manager kinds.

* A *favourite* is a soft personal bookmark - appears in the user's
  "Pinned & favourites" pseudo-section of the Recently Viewed strip.
* A *pin* is an elevated favourite - pinned rows sort above unpinned
  favourites and survive the Recently Viewed strip rolling over.

The table is polymorphic on ``(file_kind, file_id)`` - no FK to the
underlying kind table. The kind row's deletion is the file-manager
dispatcher's responsibility (it sweeps stale favourites the next time
the user opens the strip via a server-side cleanup pass; we don't
hand-wire FK cascades for 8 polymorphic targets).
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_favorites.permissions import (
        register_file_favorites_permissions,
    )

    register_file_favorites_permissions()
