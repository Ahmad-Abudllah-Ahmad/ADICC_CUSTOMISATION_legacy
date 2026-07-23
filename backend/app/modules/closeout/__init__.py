# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Handover and Closeout module (TOP-30 #25).

Project-scoped digital handover / closeout package assembly. Builds a
per-project closeout package against a configurable checklist (template
per project type), binds existing CDE documents into checklist slots,
pulls live closure evidence from punchlist / inspections / COBie, tracks
completeness with gaps surfaced, assembles the package as an idempotent
background job and exports a structured ZIP (PDF cover + machine-readable
manifest.json) with an optional portal-shareable readonly view.

This is distinct from the residential property_dev handover (plot/buyer
scoped). This module is the broader construction closeout package.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions, job handler, rules, subscribers.

    The module loader auto-calls this when the module package is discovered.
    """
    from app.modules.closeout.events import register_closeout_subscribers
    from app.modules.closeout.job import register_closeout_job_handler
    from app.modules.closeout.permissions import register_closeout_permissions
    from app.modules.closeout.validators import register_closeout_validation_rules

    register_closeout_permissions()
    register_closeout_job_handler()
    register_closeout_validation_rules()
    register_closeout_subscribers()
