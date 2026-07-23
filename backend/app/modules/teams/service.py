# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Teams service - business logic for team management.

Stateless service layer. Handles:
- Team CRUD within projects
- Membership management (add / remove / list)
- Entity visibility grants

Authorisation model
~~~~~~~~~~~~~~~~~~~
Team membership is the seed of permission inheritance: a user added to a
team inherits whatever effective permissions that team grants on the
parent project. That makes ``add_member`` (and to a lesser degree
``create_team`` / ``update_team`` / ``remove_member``) RBAC-sensitive -
we MUST gate them on project ownership / admin status so a low-privilege
user cannot self-elevate by joining a high-permission team.

Elevated team roles (``owner`` / ``project_manager``) carry full
write-on-project semantics in the matrix UI, so they're restricted to
project-owners and system admins regardless of who is making the call.
"""

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import event_bus
from app.modules.teams.models import EntityVisibility, Team, TeamMembership
from app.modules.teams.repository import MembershipRepository, TeamRepository, VisibilityRepository
from app.modules.teams.schemas import (
    ELEVATED_TEAM_ROLES,
    AddMemberRequest,
    TeamCreate,
    TeamUpdate,
)

logger = logging.getLogger(__name__)


class TeamService:
    """Business logic for team operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.team_repo = TeamRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.visibility_repo = VisibilityRepository(session)

    # ── RBAC helpers ─────────────────────────────────────────────────────

    async def _assert_project_access(
        self,
        project_id: uuid.UUID,
        actor_id: str | uuid.UUID | None,
    ) -> None:
        """Gate a team mutation on project-admin access.

        Delegates to :func:`app.dependencies.verify_project_access` which
        already implements the admin-bypass + owner-only rule used across
        every other module. Centralising the call here means service-layer
        callers (cron jobs, tests, future internal modules) get the same
        guard as the HTTP router - defence in depth against routes that
        forget to gate.

        ``actor_id is None`` is treated as a SYSTEM call and skipped (only
        background jobs / migration helpers should pass ``None``).
        """
        if actor_id is None:
            return
        # Late-import: app.dependencies imports a lot of FastAPI machinery
        # that we don't want pulled into module-load order for tests.
        from app.dependencies import verify_project_access

        await verify_project_access(project_id, str(actor_id), self.session)

    async def _is_project_owner_or_admin(
        self,
        project_id: uuid.UUID,
        actor_id: str | uuid.UUID,
    ) -> bool:
        """True iff ``actor_id`` is system admin or owner of ``project_id``.

        Used to gate ELEVATED team roles. Returns False for ordinary
        project members (anyone whose access passes
        :func:`verify_project_access` only because they're already in a
        team) - we deliberately don't propagate elevation through
        team-membership to avoid infinite-bootstrap of `owner`.
        """
        from app.modules.projects.repository import ProjectRepository
        from app.modules.users.repository import UserRepository

        try:
            user_repo = UserRepository(self.session)
            user = await user_repo.get_by_id(uuid.UUID(str(actor_id)))
            if user is not None and getattr(user, "role", "") == "admin":
                return True
        except Exception:
            logger.exception("admin lookup failed during elevated-role check")

        proj_repo = ProjectRepository(self.session)
        project = await proj_repo.get_by_id(project_id)
        if project is None:
            return False
        return str(getattr(project, "owner_id", "")) == str(actor_id)

    # ── Teams ────────────────────────────────────────────────────────────

    async def create_team(
        self,
        data: TeamCreate,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> Team:
        """Create a new team within a project.

        After insert we *re-fetch via ``get()``* instead of returning the
        ``session.add``-ed instance directly. ``get()`` uses
        ``selectinload(memberships)`` so Pydantic's ``model_validate`` can
        access ``team.memberships`` (an empty list at this point) without
        triggering a lazy load on the detached / expired ORM object, which
        is what caused :bug:`247` (``MissingGreenlet`` under async).
        """
        await self._assert_project_access(data.project_id, actor_id)
        team = Team(
            project_id=data.project_id,
            name=data.name,
            name_translations=data.name_translations,
            sort_order=data.sort_order,
            is_default=data.is_default,
            metadata_=data.metadata,
        )
        team = await self.team_repo.create(team)
        # Re-fetch with memberships eager-loaded so serialization is safe.
        fresh = await self.team_repo.get(team.id)
        await self._record_audit(
            actor_id=actor_id,
            team_id=team.id,
            action="created",
            metadata={"project_id": str(data.project_id), "name": data.name},
        )
        await self._publish_event(
            "teams.team.created",
            {
                "team_id": str(team.id),
                "project_id": str(data.project_id),
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
        logger.info("Team created: %s in project %s", data.name, data.project_id)
        return fresh or team

    async def get_team(self, team_id: uuid.UUID) -> Team:
        """Get team by ID. Raises 404 if not found."""
        team = await self.team_repo.get(team_id)
        if team is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        return team

    async def list_teams(
        self,
        project_id: uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
        include_inactive: bool = False,
    ) -> list[Team]:
        """List teams for a project.

        Gated on project access (same policy as ``list_members``): team
        structure reveals who is on a project, so a caller must own / admin /
        belong to the parent project. ``actor_id is None`` is a SYSTEM call
        and skips the check, so existing internal callers keep working.
        """
        await self._assert_project_access(project_id, actor_id)
        return await self.team_repo.list_for_project(
            project_id,
            include_inactive=include_inactive,
        )

    async def update_team(
        self,
        team_id: uuid.UUID,
        data: TeamUpdate,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> Team:
        """Update team fields."""
        team = await self.get_team(team_id)
        await self._assert_project_access(team.project_id, actor_id)

        fields = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if not fields:
            return team

        await self.team_repo.update_fields(team_id, **fields)
        updated = await self.team_repo.get(team_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        await self._record_audit(
            actor_id=actor_id,
            team_id=team_id,
            action="updated",
            metadata={"fields": list(fields.keys())},
        )
        await self._publish_event(
            "teams.team.updated",
            {
                "team_id": str(team_id),
                "project_id": str(team.project_id),
                "fields": list(fields.keys()),
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
        logger.info("Team updated: %s (fields=%s)", team_id, list(fields.keys()))
        return updated

    async def delete_team(
        self,
        team_id: uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> None:
        """Delete a team. Cascades to memberships and visibility grants.

        Cascade is enforced at the ORM level by ``cascade='all, delete-orphan'``
        on ``Team.memberships`` and by ``ondelete='CASCADE'`` on the
        ``oe_teams_membership.team_id`` + ``oe_teams_visibility.team_id`` FKs,
        so no row in either child table is orphaned when a team disappears.
        """
        team = await self.get_team(team_id)  # Raises 404 if not found
        await self._assert_project_access(team.project_id, actor_id)
        # Snapshot member IDs BEFORE deletion so downstream subscribers can
        # invalidate any per-user permission cache they keep.
        member_ids = [str(m.user_id) for m in (team.memberships or [])]
        await self.team_repo.delete(team_id)
        await self._record_audit(
            actor_id=actor_id,
            team_id=team_id,
            action="deleted",
            metadata={
                "project_id": str(team.project_id),
                "member_count": len(member_ids),
            },
        )
        await self._publish_event(
            "teams.team.deleted",
            {
                "team_id": str(team_id),
                "project_id": str(team.project_id),
                "affected_user_ids": member_ids,
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
        logger.info("Team deleted: %s", team_id)

    # ── Memberships ──────────────────────────────────────────────────────

    async def add_member(
        self,
        team_id: uuid.UUID,
        data: AddMemberRequest,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> TeamMembership:
        """Add a user to a team.

        RBAC: caller must have project-admin access (owner / system admin).
        Elevated roles (``owner``, ``project_manager``) are doubly gated -
        even a project owner cannot promote another user into them without
        a separate ownership-transfer flow (see TODO in the matrix UI). This
        closes the self-elevation hole where a low-privilege authenticated
        user could ``POST /teams/{id}/members`` with their own user_id and
        role=owner.
        """
        team = await self.get_team(team_id)  # Raises 404 if team not found
        await self._assert_project_access(team.project_id, actor_id)

        # Block elevation: requesting an ELEVATED role requires owner/admin.
        # ``actor_id is None`` is reserved for system calls (seed scripts);
        # we still allow those because they bootstrap the first owner.
        if actor_id is not None and data.role in ELEVATED_TEAM_ROLES:
            is_priv = await self._is_project_owner_or_admin(team.project_id, actor_id)
            if not is_priv:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only project owner or system admin may grant this role",
                )

        # Check if already a member
        existing = await self.membership_repo.get_membership(team_id, data.user_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this team",
            )

        membership = TeamMembership(
            team_id=team_id,
            user_id=data.user_id,
            role=data.role,
        )
        membership = await self.membership_repo.add(membership)
        await self._record_audit(
            actor_id=actor_id,
            team_id=team_id,
            action="member_added",
            metadata={
                "user_id": str(data.user_id),
                "role": data.role,
                "project_id": str(team.project_id),
            },
        )
        await self._publish_event(
            "teams.membership.added",
            {
                "team_id": str(team_id),
                "user_id": str(data.user_id),
                "role": data.role,
                "project_id": str(team.project_id),
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
        logger.info("Member added: user %s to team %s (%s)", data.user_id, team_id, data.role)
        return membership

    async def remove_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> None:
        """Remove a user from a team."""
        team = await self.get_team(team_id)  # Raises 404 if team not found
        await self._assert_project_access(team.project_id, actor_id)
        removed = await self.membership_repo.remove(team_id, user_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )
        await self._record_audit(
            actor_id=actor_id,
            team_id=team_id,
            action="member_removed",
            metadata={
                "user_id": str(user_id),
                "project_id": str(team.project_id),
            },
        )
        # Publish so any per-user permission cache can drop ``user_id``'s
        # entry - they no longer inherit this team's grants.
        await self._publish_event(
            "teams.membership.removed",
            {
                "team_id": str(team_id),
                "user_id": str(user_id),
                "project_id": str(team.project_id),
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
        logger.info("Member removed: user %s from team %s", user_id, team_id)

    async def list_members(
        self,
        team_id: uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> list[TeamMembership]:
        """List members of a team.

        Gated on project access: team membership is sensitive (it reveals who
        is on a project), so a caller must own / admin / belong to the parent
        project. ``actor_id is None`` is a SYSTEM call and skips the check.
        """
        team = await self.get_team(team_id)  # Raises 404 if team not found
        await self._assert_project_access(team.project_id, actor_id)
        return await self.membership_repo.list_for_team(team_id)

    # ── Visibility ───────────────────────────────────────────────────────

    async def grant_visibility(
        self,
        entity_type: str,
        entity_id: str,
        team_id: uuid.UUID,
    ) -> EntityVisibility:
        """Grant visibility of an entity to a team."""
        await self.get_team(team_id)  # Raises 404 if team not found
        visibility = EntityVisibility(
            entity_type=entity_type,
            entity_id=entity_id,
            team_id=team_id,
        )
        visibility = await self.visibility_repo.grant(visibility)
        logger.info(
            "Visibility granted: %s/%s → team %s",
            entity_type,
            entity_id,
            team_id,
        )
        return visibility

    async def list_entity_visibility(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[EntityVisibility]:
        """List visibility grants for an entity."""
        return await self.visibility_repo.list_for_entity(entity_type, entity_id)

    # ── Audit + events (best-effort) ─────────────────────────────────────

    async def _record_audit(
        self,
        *,
        actor_id: str | uuid.UUID | None,
        team_id: uuid.UUID,
        action: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Write a single audit row; never let a logging failure abort the
        business write. Team modifications change RBAC outcomes, so they
        MUST land in the activity log for compliance trails.
        """
        try:
            await log_activity(
                self.session,
                actor_id=actor_id,
                entity_type="team",
                entity_id=str(team_id),
                action=action,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover - best-effort audit
            logger.exception("audit write failed for team=%s action=%s", team_id, action)

    async def _publish_event(self, name: str, payload: dict[str, object]) -> None:
        """Publish a teams.* event so permission caches / notifications /
        analytics subscribers can react. Failures are swallowed because the
        business write has already committed and event delivery is an
        eventual-consistency concern.
        """
        try:
            publish_detached = getattr(event_bus, "publish_detached", None)
            if publish_detached is not None:
                publish_detached(name, payload, source_module="oe_teams")
            else:
                await event_bus.publish(name, payload, source_module="oe_teams")
        except Exception:  # pragma: no cover - best-effort fanout
            logger.exception("event publish failed: %s", name)
