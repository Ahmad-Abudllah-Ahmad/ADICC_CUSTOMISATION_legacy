# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Approval Routes module.

Generic multi-step approval engine. Every other module that needs a
routed sign-off workflow (markup approval, submittal review, change
order, RFI, contract signature, …) starts an :class:`Instance` against
this module's tables instead of inventing its own approve/reject schema.

Schema
~~~~~~

* :class:`Route` - template/definition (project-scoped or tenant-wide)
* :class:`Step` - ordered approver slot inside a route
* :class:`Instance` - running workflow against a concrete target row
* :class:`StepState` - per-step decision (pending → approved/rejected)

The engine deliberately does NOT touch the target tables; consumers
read ``status`` and ``current_step_ordinal`` off the instance row and
render their own UI.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.approval_routes.permissions import register_approval_route_permissions

    register_approval_route_permissions()
