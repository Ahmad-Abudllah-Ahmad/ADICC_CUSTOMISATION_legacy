# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Teams API routes.

Endpoints:
    GET    /project/{project_id}        - List teams for project
    POST   /                            - Create team (auth required)
    PATCH  /{team_id}                   - Update team
    DELETE /{team_id}                   - Delete team
    POST   /{team_id}/members           - Add member
    DELETE /{team_id}/members/{user_id} - Remove member
    GET    /{team_id}/members           - List members
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.teams.schemas import (
    AddMemberRequest,
    MembershipResponse,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
)
from app.modules.teams.service import TeamService

router = APIRouter(tags=["teams"])
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> TeamService:
    return TeamService(session)


# ── Teams ────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[TeamResponse])
async def list_teams_by_query(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: TeamService = Depends(_get_service),
) -> list[TeamResponse]:
    """List teams for a project (query-param style).

    IDOR-gated on the parent project: a caller may only list teams of a
    project they own / admin / belong to. The service repeats the same
    check (``actor_id``) as defence in depth.
    """
    await verify_project_access(project_id, str(user_id) if user_id else "", session)
    teams = await service.list_teams(project_id, actor_id=user_id)
    return [TeamResponse.model_validate(t) for t in teams]


@router.get("/project/{project_id}", response_model=list[TeamResponse])
async def list_teams(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: TeamService = Depends(_get_service),
) -> list[TeamResponse]:
    """List teams for a project.

    IDOR-gated on the parent project (see ``list_teams_by_query``).
    """
    await verify_project_access(project_id, str(user_id) if user_id else "", session)
    teams = await service.list_teams(project_id, actor_id=user_id)
    return [TeamResponse.model_validate(t) for t in teams]


@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    data: TeamCreate,
    user_id: CurrentUserId,
    service: TeamService = Depends(_get_service),
) -> TeamResponse:
    """Create a new team within a project.

    RBAC: caller must own (or be admin of) the parent project. The
    service-layer ``_assert_project_access`` enforces this - the router
    just forwards ``user_id``.
    """
    try:
        team = await service.create_team(data, actor_id=user_id)
        return TeamResponse.model_validate(team)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create team")
        raise HTTPException(status_code=500, detail="Failed to create team")


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    data: TeamUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: TeamService = Depends(_get_service),
) -> TeamResponse:
    """Update team fields.

    IDOR-gated at the router on the parent project; the service repeats the
    same check as defence in depth for internal (non-HTTP) callers.
    """
    team = await service.get_team(team_id)  # 404 if missing
    await verify_project_access(team.project_id, str(user_id), session)
    updated = await service.update_team(team_id, data, actor_id=user_id)
    return TeamResponse.model_validate(updated)


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: TeamService = Depends(_get_service),
) -> None:
    """Delete a team and all its memberships (IDOR-gated on the parent project)."""
    team = await service.get_team(team_id)  # 404 if missing
    await verify_project_access(team.project_id, str(user_id), session)
    await service.delete_team(team_id, actor_id=user_id)


# ── Members ──────────────────────────────────────────────────────────────


@router.get("/{team_id}/members/", response_model=list[MembershipResponse])
async def list_members(
    team_id: uuid.UUID,
    user_id: CurrentUserId,
    service: TeamService = Depends(_get_service),
) -> list[MembershipResponse]:
    """List members of a team (IDOR-gated on the parent project in the service)."""
    members = await service.list_members(team_id, actor_id=user_id)
    return [MembershipResponse.model_validate(m) for m in members]


@router.post("/{team_id}/members/", response_model=MembershipResponse, status_code=201)
async def add_member(
    team_id: uuid.UUID,
    data: AddMemberRequest,
    user_id: CurrentUserId,
    service: TeamService = Depends(_get_service),
) -> MembershipResponse:
    """Add a user to a team.

    RBAC: ``actor_id=user_id`` is passed to the service so it can (a)
    verify the caller has access to the team's parent project and
    (b) block elevation into ``owner`` / ``project_manager`` unless the
    caller is system-admin or the project owner. Closes the
    self-elevation hole where any authenticated user could grant
    themselves owner-equivalent permissions by joining a team.
    """
    try:
        membership = await service.add_member(team_id, data, actor_id=user_id)
        return MembershipResponse.model_validate(membership)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to add member to team")
        raise HTTPException(status_code=500, detail="Failed to add member")


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_user_id: CurrentUserId,
    service: TeamService = Depends(_get_service),
) -> None:
    """Remove a user from a team.

    ``actor_user_id`` is the caller (from JWT); ``user_id`` is the
    membership being revoked. The service uses ``actor_user_id`` to
    enforce project-access RBAC.
    """
    await service.remove_member(team_id, user_id, actor_id=actor_user_id)
