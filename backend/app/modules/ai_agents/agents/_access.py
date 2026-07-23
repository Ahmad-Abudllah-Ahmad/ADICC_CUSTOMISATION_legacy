# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared per-call project access guard for agent data-reading tools.

Agent tools run OUTSIDE the request cycle (in a background task), so they
cannot raise ``HTTPException`` the way a route guard does - a raised
exception would crash the whole run. Instead every data-reading tool calls
:func:`assert_user_can_access_project` with the run's *trusted* invoking
user (threaded through ``__agent_context__`` by the runner) and, when it
returns ``False``, returns its own "cannot read / no access" observation so
the LLM reasons "I have no access" rather than blowing up.

The check mirrors :func:`app.dependencies.verify_project_access` (owner OR
team-member grants access) but uses the lower-level primitives directly so
it can answer with a boolean instead of raising. It is best-effort: any
failure resolving the project or membership is treated as *no access*
(fail-closed) and never propagates.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def assert_user_can_access_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """True if *user_id* owns or is a member of *project_id*.

    Best-effort and fail-closed: returns ``False`` (never raises) when the
    project is missing, the user lacks access, or any lookup errors. Callers
    must translate ``False`` into the tool's existing "no access" observation
    rather than leaking whether the project exists (IDOR defence).
    """
    try:
        from app.modules.projects.repository import ProjectRepository
        from app.modules.teams.access import is_project_member

        project = await ProjectRepository(session).get_by_id(project_id)
        if project is None:
            return False
        if str(project.owner_id) == str(user_id):
            return True
        return await is_project_member(session, project_id, user_id)
    except Exception:  # noqa: BLE001 - fail closed; never crash a tool/run
        logger.debug(
            "assert_user_can_access_project failed for project=%s user=%s",
            project_id,
            user_id,
            exc_info=True,
        )
        return False


def coerce_user_id(context: dict | None) -> uuid.UUID | None:
    """Extract the trusted ``user_id`` from the runner ``__agent_context__``.

    Returns ``None`` when no user id is present or it is not a valid UUID, so
    callers can fail closed (treat as denied) instead of querying with a
    blank/garbage identity. The runner strips any LLM-forged context and
    re-injects the trusted one, so a non-empty value here is the real
    invoking user.
    """
    if not isinstance(context, dict):
        return None
    raw = context.get("user_id")
    if raw in (None, ""):
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None
