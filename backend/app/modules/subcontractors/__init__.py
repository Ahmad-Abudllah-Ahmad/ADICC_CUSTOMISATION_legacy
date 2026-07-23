# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Subcontractor Management module.

Manages the subcontractor lifecycle: prequalification, certificates,
agreements, work packages, payment applications, retention, and rating.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.subcontractors.permissions import register_subcontractors_permissions

    register_subcontractors_permissions()
