# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Approval Workflows + Stamps module (Wave W8).

A user submits a file for approval → a workflow with N ordered steps is
created → each approver records a decision → on final approval, the
configured stamp template is "burned" into a copy of the artifact:

* For PDFs, ``pypdf`` overlays a stamp page (when available).
* For everything else (or when ``pypdf`` is absent), a sidecar JSON
  file is written next to the canonical name describing the stamp.

Tables
~~~~~~
* :class:`ApprovalWorkflow`     - ``oe_file_approval_workflow``
* :class:`ApprovalStep`         - ``oe_file_approval_step``
* :class:`StampTemplate`        - ``oe_file_stamp_template``
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_approvals.permissions import (
        register_file_approval_permissions,
    )

    register_file_approval_permissions()
