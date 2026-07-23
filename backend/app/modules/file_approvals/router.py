# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Approvals (W8) API routes.

Mounted by the module loader at ``/api/v1/file-approvals``.

Endpoints
~~~~~~~~~
* ``GET    /``                            - list workflows
* ``POST   /``                            - submit a file for approval
* ``GET    /{id}``                         - workflow detail
* ``POST   /{id}/steps/{step_id}/decide/`` - record per-step decision
* ``POST   /{id}/withdraw/``               - submitter withdraws
* ``GET    /{id}/stamped/``                - stamped artifact bytes
* ``GET    /stamp-templates/``             - list templates (global + project)
* ``POST   /stamp-templates/``             - create custom template
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserId, RequirePermission, SessionDep
from app.modules.file_approvals.schemas import (
    ApprovalStepDecide,
    ApprovalWorkflowCreate,
    ApprovalWorkflowResponse,
    StampTemplateCreate,
    StampTemplateResponse,
)
from app.modules.file_approvals.service import ApprovalService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["File Approvals"])


def _get_service(session: SessionDep) -> ApprovalService:
    return ApprovalService(session)


async def _require_project_access(session: AsyncSession, project_id: uuid.UUID, user_id: str) -> None:
    """Verify the caller may access ``project_id`` (owner, admin, or team member).

    Delegates to the app-wide canonical policy
    ``app.dependencies.verify_project_access`` so legitimate project TEAM
    MEMBERS are no longer wrongly denied. The previous owner-only gate was
    over-strict and 403'd valid non-owner approvers on every workflow
    endpoint, breaking the multi-approver premise.
    """
    # RBAC/broken-access-control fix: relax the owner-only gate to the
    # canonical owner/admin/team-member policy. verify_project_access raises
    # HTTPException(404) on denial, preserving the 404-not-403 IDOR behaviour.
    from app.dependencies import verify_project_access

    await verify_project_access(project_id, user_id, session)


# ── Stamp templates ───────────────────────────────────────────────────────


@router.get(
    "/stamp-templates/",
    response_model=list[StampTemplateResponse],
    dependencies=[Depends(RequirePermission("file_approvals.read"))],
)
async def list_stamp_templates(
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
    project_id: uuid.UUID | None = Query(default=None),
) -> list[StampTemplateResponse]:
    """List active stamp templates (globals + ``project_id`` scope)."""
    if project_id is not None:
        await _require_project_access(session, project_id, user_id)
    rows = await service.list_templates(project_id)
    return [StampTemplateResponse.model_validate(r) for r in rows]


@router.post(
    "/stamp-templates/",
    response_model=StampTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("file_approvals.manage_stamps"))],
)
async def create_stamp_template(
    data: StampTemplateCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> StampTemplateResponse:
    """Create a stamp template (global if ``project_id`` is null)."""
    if data.project_id is not None:
        await _require_project_access(session, data.project_id, user_id)
    row = await service.create_template(data)
    return StampTemplateResponse.model_validate(row)


# ── Workflows ─────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[ApprovalWorkflowResponse],
    dependencies=[Depends(RequirePermission("file_approvals.read"))],
)
async def list_workflows(
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
    project_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[ApprovalWorkflowResponse]:
    """List workflows for a project, newest first."""
    await _require_project_access(session, project_id, user_id)
    rows = await service.list_workflows(project_id, status_filter=status_filter)
    return [ApprovalWorkflowResponse.model_validate(r) for r in rows]


@router.post(
    "/",
    response_model=ApprovalWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("file_approvals.submit"))],
)
async def submit_for_approval(
    data: ApprovalWorkflowCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> ApprovalWorkflowResponse:
    """Submit a file for approval - creates the workflow + steps."""
    await _require_project_access(session, data.project_id, user_id)
    workflow = await service.submit(data, submitted_by_id=user_id)
    return ApprovalWorkflowResponse.model_validate(workflow)


@router.get(
    "/{workflow_id}/",
    response_model=ApprovalWorkflowResponse,
    dependencies=[Depends(RequirePermission("file_approvals.read"))],
)
async def get_workflow(
    workflow_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> ApprovalWorkflowResponse:
    """Load a single workflow with steps."""
    workflow = await service.get_workflow(workflow_id)
    await _require_project_access(session, workflow.project_id, user_id)
    return ApprovalWorkflowResponse.model_validate(workflow)


@router.post(
    "/{workflow_id}/steps/{step_id}/decide/",
    response_model=ApprovalWorkflowResponse,
    dependencies=[Depends(RequirePermission("file_approvals.decide"))],
)
async def decide_step(
    workflow_id: uuid.UUID,
    step_id: uuid.UUID,
    data: ApprovalStepDecide,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> ApprovalWorkflowResponse:
    """Record a decision on one approval step.

    On the final approval, the configured stamp template is burned into
    a copy of the file (PDF overlay or JSON sidecar) and the stamped
    path is stored on the workflow.
    """
    workflow = await service.get_workflow(workflow_id)
    await _require_project_access(session, workflow.project_id, user_id)
    workflow = await service.decide(workflow_id, step_id, data, user_id)
    return ApprovalWorkflowResponse.model_validate(workflow)


@router.post(
    "/{workflow_id}/withdraw/",
    response_model=ApprovalWorkflowResponse,
    dependencies=[Depends(RequirePermission("file_approvals.submit"))],
)
async def withdraw_workflow(
    workflow_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> ApprovalWorkflowResponse:
    """Submitter (or admin) withdraws a still-in-review workflow."""
    workflow = await service.get_workflow(workflow_id)
    await _require_project_access(session, workflow.project_id, user_id)
    workflow = await service.withdraw(workflow_id)
    return ApprovalWorkflowResponse.model_validate(workflow)


@router.get(
    "/{workflow_id}/stamped/",
    dependencies=[Depends(RequirePermission("file_approvals.read"))],
)
async def download_stamped(
    workflow_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ApprovalService = Depends(_get_service),
) -> Response:
    """Return the stamped artifact bytes."""
    workflow = await service.get_workflow(workflow_id)
    await _require_project_access(session, workflow.project_id, user_id)
    data, media_type = await service.read_stamped(workflow_id)
    ext = "pdf" if media_type == "application/pdf" else "json"
    filename = f"approval_{workflow.id}.{ext}"
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
