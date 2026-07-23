# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Record Publishing module - one-tap publish-a-record-and-distribute.

Turns a project record (the daily site diary first, meetings and inspections
next) into a single signed PDF and sends it as an acknowledged transmittal in
one action. It reuses the record renderers, the storage backend and the
file-transmittals engine, so it introduces no new tables.
"""

from app.modules.record_publishing.manifest import manifest

__all__ = ["manifest", "on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the read/publish permissions."""
    from app.modules.record_publishing.permissions import (
        register_record_publishing_permissions,
    )

    register_record_publishing_permissions()
