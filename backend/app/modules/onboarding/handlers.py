# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Background job handlers for onboarding provisioning.

Wrap the two heavy first-run operations - regional cost base import and sample
project install - as JobRun handlers so the wizard can fire them and move on.
Both underlying operations are already idempotent (they early-return when the
data is already present), and both are wrapped fail-soft here: a first-run new
user must never see the wizard break because an optional cost base could not be
downloaded. Progress is reported through ``update_progress`` so the client's
polling banner can show a real bar rather than a fake ramp.

Heavy imports (``costs.router``, ``demo_projects``) are done lazily inside the
handlers, not at module load, so registering these handlers at startup stays
cheap and free of import cycles.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.core.job_runner import register_handler, update_progress
from app.database import async_session_factory

if TYPE_CHECKING:
    from app.core.job_run import JobRun

logger = logging.getLogger(__name__)

# Job kinds. Also referenced by the router when it submits work and when it
# guards the status endpoint to onboarding jobs only.
KIND_LOAD_CWICR = "onboarding.load_cwicr"
KIND_INSTALL_DEMO = "onboarding.install_demo"

# The CWICR import reads a large parquet and bulk-inserts tens of thousands of
# rows; it is heavy on memory and on the single-writer database. Bound how many
# run at once so a user who picks several bases - or several users onboarding at
# the same time - cannot thrash a 2 GB VPS. Sample installs are lighter and run
# unbounded.
_CWICR_SEMAPHORE = asyncio.Semaphore(2)


async def load_cwicr_handler(job_run: JobRun, payload: dict[str, Any]) -> dict[str, Any]:
    """Import one regional cost base in the background, fail-soft on any error."""
    db_id = str(payload.get("db_id") or "").strip()
    if not db_id:
        return {"skipped": True, "reason": "missing db_id"}

    await update_progress(job_run.id, percent=5, message=f"Preparing cost base {db_id}")

    # Lazy imports: pulling the costs router (and its pandas/parquet stack) at
    # module load would be wasteful and risk a cycle. HTTPException is what
    # load_cwicr_region raises on a missing file (404) or import failure (500).
    from fastapi import HTTPException

    from app.modules.costs.router import load_cwicr_region

    async with _CWICR_SEMAPHORE:
        await update_progress(job_run.id, percent=15, message=f"Importing cost base {db_id}")
        async with async_session_factory() as session:
            try:
                result = await load_cwicr_region(db_id, session)
                await session.commit()
            except HTTPException as exc:
                # A missing regional file or an import error must not fail the
                # user's onboarding - record it and let the user carry on.
                await session.rollback()
                logger.warning(
                    "onboarding: cost base %s could not be loaded: %s",
                    db_id,
                    exc.detail,
                )
                return {"skipped": True, "db_id": db_id, "reason": str(exc.detail)}

    await update_progress(job_run.id, percent=100, message=f"Cost base {db_id} ready")
    return {
        "db_id": db_id,
        "imported": result.get("imported"),
        "total_items": result.get("total_items"),
        "status": result.get("status"),
    }


async def install_demo_handler(job_run: JobRun, payload: dict[str, Any]) -> dict[str, Any]:
    """Install one sample project in the background, fail-soft on any error."""
    demo_id = str(payload.get("demo_id") or "").strip()
    if not demo_id:
        return {"skipped": True, "reason": "missing demo_id"}

    await update_progress(job_run.id, percent=10, message="Installing sample project")

    from app.core.demo_projects import install_demo_project

    async with async_session_factory() as session:
        try:
            result = await install_demo_project(session, demo_id)
            await session.commit()
        except ValueError as exc:
            # Unknown demo id - skip rather than fail the whole onboarding.
            await session.rollback()
            logger.warning("onboarding: sample project %s could not be installed: %s", demo_id, exc)
            return {"skipped": True, "demo_id": demo_id, "reason": str(exc)}

    await update_progress(job_run.id, percent=100, message="Sample project ready")
    return {
        "demo_id": demo_id,
        "project_id": result.get("project_id"),
        "project_name": result.get("project_name"),
        "already_installed": bool(result.get("already_installed", False)),
    }


def register_onboarding_job_handlers() -> None:
    """Wire the onboarding handlers into the job runner."""
    register_handler(KIND_LOAD_CWICR, load_cwicr_handler)
    register_handler(KIND_INSTALL_DEMO, install_demo_handler)
