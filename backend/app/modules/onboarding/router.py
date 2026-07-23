# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Onboarding provisioning API (auto-mounted at /api/v1/onboarding).

The wizard POSTs the heavy first-run work here instead of awaiting it inline.
Each requested item becomes a background JobRun; the endpoint returns the job
ids immediately so the client can move the user on and poll ``/status`` for a
progress bar. Jobs are de-duplicated per user and item through an idempotency
key, so a double submit (or a retried request) reuses the running job rather
than starting a second import.

Ownership: the caller's id is stamped into each job payload, and ``/status``
returns only jobs whose payload owner matches the caller, so one user can never
read another's provisioning jobs by guessing ids.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.core.job_run import JobRun
from app.core.job_runner import submit_job
from app.dependencies import CurrentUserId, SessionDep
from app.modules.onboarding.handlers import KIND_INSTALL_DEMO, KIND_LOAD_CWICR
from app.modules.onboarding.schemas import (
    JobState,
    ProvisionRequest,
    ProvisionResponse,
    StatusRequest,
    StatusResponse,
)

router = APIRouter(tags=["onboarding"])
logger = logging.getLogger(__name__)

_ONBOARDING_KINDS = frozenset({KIND_LOAD_CWICR, KIND_INSTALL_DEMO})


def _job_state(row: JobRun) -> JobState:
    """Project a JobRun row into the owner-facing JobState."""
    result = row.result_jsonb or {}
    payload = row.payload_jsonb or {}
    error: str | None = None
    if row.error_jsonb:
        error = str(row.error_jsonb.get("message") or "failed")
    arg = payload.get("db_id") or payload.get("demo_id")
    return JobState(
        id=str(row.id),
        kind=row.kind,
        arg=str(arg) if arg is not None else None,
        state=row.status,
        pct=int(row.progress_percent or 0),
        message=result.get("progress_message"),
        error=error,
    )


@router.post("/provision", response_model=ProvisionResponse)
async def provision(body: ProvisionRequest, user_id: CurrentUserId) -> ProvisionResponse:
    """Kick off the heavy first-run work as background jobs and return their ids.

    Idempotent per user and item: re-provisioning the same region or sample
    reuses the existing job instead of importing twice.
    """
    jobs: list[JobState] = []

    if body.region:
        row = await submit_job(
            KIND_LOAD_CWICR,
            {"db_id": body.region, "owner_user_id": user_id},
            idempotency_key=f"onboarding:{user_id}:load_cwicr:{body.region}",
        )
        jobs.append(_job_state(row))

    # dict.fromkeys de-dupes while preserving the wizard's order.
    for demo_id in dict.fromkeys(body.demo_ids):
        if not demo_id:
            continue
        row = await submit_job(
            KIND_INSTALL_DEMO,
            {"demo_id": demo_id, "owner_user_id": user_id},
            idempotency_key=f"onboarding:{user_id}:install_demo:{demo_id}",
        )
        jobs.append(_job_state(row))

    logger.info("onboarding: provisioned %d job(s) for user %s", len(jobs), user_id)
    return ProvisionResponse(jobs=jobs)


@router.post("/status", response_model=StatusResponse)
async def status(
    body: StatusRequest,
    user_id: CurrentUserId,
    session: SessionDep,
) -> StatusResponse:
    """Return live state for the caller's provisioning jobs, looked up by id."""
    ids: list[uuid.UUID] = []
    for raw in body.ids:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    if not ids:
        return StatusResponse(jobs=[])

    rows = (await session.execute(select(JobRun).where(JobRun.id.in_(ids)))).scalars().all()

    out: list[JobState] = []
    for row in rows:
        payload = row.payload_jsonb or {}
        # Ownership + kind guard: never expose another user's jobs, and never
        # leak unrelated background work through this onboarding endpoint.
        if payload.get("owner_user_id") != user_id:
            continue
        if row.kind not in _ONBOARDING_KINDS:
            continue
        out.append(_job_state(row))
    return StatusResponse(jobs=out)
