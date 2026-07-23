# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defects-liability module (post-handover warranty and DLP register).

Once a building or a section of works is handed over, the contractor and its
subcontractors stay liable to make good defects for a defined period - the
defects liability period (DLP), also called the rectification period - and many
elements additionally carry a workmanship or manufacturer warranty. This module
tracks each such warranty / DLP entry, the defect notices raised against it while
the period runs, and - the valuable signal - which entries are clean enough for
the final retention money to be released.

Retention-release readiness is never stored: the per-status and per-warranty-type
counts, the expiring and expired lists, the open and overdue defect load, the
per-subcontractor health view, the single overall health score, and the
retention-release-ready list (a warranty whose DLP has ended with no outstanding
defects) are all derived from the warranties and their defects by the pure
functions in :mod:`app.modules.defects_liability.register`.
"""

from app.modules.defects_liability.manifest import manifest

__all__ = ["manifest", "on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the read/write permissions."""
    from app.modules.defects_liability.permissions import (
        register_defects_liability_permissions,
    )

    register_defects_liability_permissions()
