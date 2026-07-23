# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Periodic predictive-forecast batch job (TOP-30 #19).

Registers a ``full_evm.forecast_batch`` handler with the platform job
runner. The handler recomputes the EVM forecast for every project that
has at least one finance EVM snapshot, evaluates each forecast against
that project's AlertRules, and on a breach stamps the forecast row,
publishes ``forecast.alert_triggered`` and dispatches notifications
(all inside :meth:`EVMService.compute_project_forecasts_batch`).

Why a job and not a request handler: the forecast surface is only as
fresh as the latest snapshot, but alert *detection* must happen even
when nobody is looking at the dashboard. The job runner already gives
us Celery-or-in-process execution, idempotency and progress reporting,
so we lean on it rather than adding a second scheduler. Operators (and
tests) trigger a run by submitting the job with an explicit
``project_ids`` list, or with ``project_ids: null`` to sweep every
project with a snapshot.

This module owns ONLY its own job kind; it talks to the job runner
through the public ``register_handler`` / ``submit_job`` API and never
edits ``app.core.job_runner`` itself.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.core.job_runner import register_handler
from app.database import async_session_factory
from app.modules.full_evm.service import EVMService

if TYPE_CHECKING:
    from app.core.job_run import JobRun

logger = logging.getLogger(__name__)

JOB_KIND = "full_evm.forecast_batch"


def _coerce_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _projects_with_snapshots(session: Any) -> list[uuid.UUID]:
    """Return every project id that has at least one EVM snapshot."""
    try:
        rows = (
            await session.execute(
                text("SELECT DISTINCT project_id FROM oe_finance_evm_snapshot"),
            )
        ).fetchall()
    except Exception:
        logger.debug("full_evm: snapshot project scan failed", exc_info=True)
        return []
    out: list[uuid.UUID] = []
    for r in rows:
        pid = _coerce_uuid(r[0])
        if pid is not None:
            out.append(pid)
    return out


async def run_forecast_batch_job(job_run: JobRun, payload: dict[str, Any]) -> dict[str, Any]:
    """Job handler: recompute forecasts + fire alerts for a set of projects.

    Payload:
        project_ids: list[str] | None - explicit project scope, or null/absent
            to sweep every project that has an EVM snapshot.
        forecast_method: "cpi" | "spi_cpi" - defaults to "cpi".
    """
    from app.core.job_runner import update_progress

    method = str(payload.get("forecast_method") or "cpi")
    raw_ids = payload.get("project_ids")

    await update_progress(job_run.id, percent=5, message="Resolving project scope")

    async with async_session_factory() as session:
        if raw_ids:
            project_ids = [pid for pid in (_coerce_uuid(x) for x in raw_ids) if pid is not None]
        else:
            project_ids = await _projects_with_snapshots(session)

        if not project_ids:
            await update_progress(job_run.id, percent=100, message="No projects in scope")
            return {"projects": 0, "alerted": 0, "results": []}

        await update_progress(
            job_run.id,
            percent=20,
            message=f"Computing forecasts for {len(project_ids)} project(s)",
        )

        service = EVMService(session)
        results = await service.compute_project_forecasts_batch(
            project_ids,
            forecast_method=method,
        )
        await session.commit()

    alerted = sum(1 for r in results if r.get("status") == "alerted")
    await update_progress(
        job_run.id,
        percent=100,
        message=f"Done - {alerted} project(s) with new alerts",
    )
    logger.info(
        "full_evm: forecast batch complete - %d project(s), %d alerted",
        len(results),
        alerted,
    )
    return {"projects": len(results), "alerted": alerted, "results": results}


def register_forecast_job_handler() -> None:
    """Register the forecast-batch handler with the job runner (idempotent)."""
    register_handler(JOB_KIND, run_forecast_batch_job)
    logger.info("Full EVM: forecast batch job handler registered (kind=%s)", JOB_KIND)
