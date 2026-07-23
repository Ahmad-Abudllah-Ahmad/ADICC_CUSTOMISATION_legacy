# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resumable (chunked) upload module.

Large CAD and PDF files (RVT / IFC / DWG / PDF, up to and beyond the
single-shot ceiling) are uploaded in fixed-size chunks. A session tracks
which chunks have landed so an interrupted upload can resume instead of
restarting from byte zero. On completion the chunks are assembled with a
streamed copy (never the whole file in memory) and handed to the EXISTING
document store plus conversion pipeline, so resumable uploads land in the
same place a single-shot upload does.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.resumable_uploads.permissions import (
        register_resumable_upload_permissions,
    )

    register_resumable_upload_permissions()
