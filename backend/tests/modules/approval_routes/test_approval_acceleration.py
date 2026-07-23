# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Integration tests for approval acceleration (PostgreSQL, py3.12).

Covers one-tap reassignment and out-of-office delegation end to end against
real rows:

* a reassignment pins ``current_assignee_user_id`` so the stand-in becomes the
  sole eligible decider, notifies them, and the original approver is locked out;
* an active delegation lets the delegate decide on the approver's behalf;
* a revoked / expired delegation grants nothing;
* the per-step override clears when the instance advances to the next step.

The pure resolution rules are unit-tested separately in
``tests/unit/test_delegation_engine.py``; this file checks the service wiring.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.audit_log  # noqa: F401 - registers ActivityLog
from app.modules.approval_routes.models import Instance
from app.modules.approval_routes.schemas import (
    DecisionSubmit,
    InstanceCreate,
    RouteCreate,
    StepCreate,
)
from app.modules.approval_routes.service import ApprovalRouteService
from app.modules.notifications.models import Notification
from app.modules.projects.models import Project  # noqa: F401 - register ORM
from app.modules.users.models import User
from tests._pg import transactional_session


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with transactional_session() as s:
        yield s


async def _user(session: AsyncSession, role: str = "editor") -> User:
    u = User(
        email=f"acc-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Acc",
        role=role,
    )
    session.add(u)
    await session.flush()
    return u


async def _project(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID:
    proj = Project(name=f"Acc {uuid.uuid4().hex[:6]}", owner_id=owner_id)
    session.add(proj)
    await session.flush()
    return proj.id


async def _add_member(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Add ``user_id`` to ``project_id``'s default team.

    A reassignment target must belong to the route's project (the service now
    enforces the same owner / team-member / admin rule ``verify_project_access``
    applies to the caller), so a plain stand-in is enrolled as a project member
    before it can be pinned to a step.
    """
    from app.modules.projects.member_schemas import AddProjectMemberRequest
    from app.modules.projects.member_service import add_project_member

    await add_project_member(session, project_id, AddProjectMemberRequest(user_id=user_id))


async def _route_instance(
    session: AsyncSession,
    svc: ApprovalRouteService,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    steps: list[StepCreate],
) -> Instance:
    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="Acc route",
            target_kind="variation",
            steps=steps,
        ),
        created_by=owner_id,
    )
    return await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="variation", target_id=uuid.uuid4()),
        started_by=owner_id,
    )


@pytest.mark.asyncio
async def test_reassign_pins_assignee_and_locks_out_original(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    owner = await _user(session, role="admin")
    project_id = await _project(session, owner.id)
    approver_a = await _user(session)
    stand_in_b = await _user(session)
    await _add_member(session, project_id, stand_in_b.id)

    inst = await _route_instance(
        session,
        svc,
        project_id,
        owner.id,
        [StepCreate(ordinal=1, approver_user_id=approver_a.id, mode="all")],
    )
    step = (await svc.list_steps((await svc.get_instance(inst.id)).route_id))[0]

    reassigned = await svc.reassign_current_step(
        inst.id, to_user_id=stand_in_b.id, actor_id=owner.id, reason="on leave"
    )
    assert reassigned.current_assignee_user_id == stand_in_b.id

    # The new assignee got an actionable notification.
    notifs = (
        (
            await session.execute(
                select(Notification).where(
                    Notification.user_id == stand_in_b.id,
                    Notification.notification_type == "approval_reassigned",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) == 1
    assert notifs[0].entity_id == str(inst.id)

    # The original approver is now locked out of the override step.
    with pytest.raises(HTTPException) as exc:
        await svc.submit_decision(
            inst.id,
            DecisionSubmit(step_id=step.id, decision="approved"),
            approver_id=approver_a.id,
        )
    assert exc.value.status_code == 403

    # The pinned stand-in clears it.
    done = await svc.submit_decision(
        inst.id,
        DecisionSubmit(step_id=step.id, decision="approved"),
        approver_id=stand_in_b.id,
    )
    assert done.status == "approved"


@pytest.mark.asyncio
async def test_active_delegation_lets_delegate_decide(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    owner = await _user(session, role="admin")
    project_id = await _project(session, owner.id)
    approver_a = await _user(session)
    delegate_b = await _user(session)
    stranger_c = await _user(session)

    # A hands their approvals to B (blanket, open-ended).
    await svc.create_delegation(
        delegator_id=approver_a.id,
        delegate_id=delegate_b.id,
        project_id=None,
        starts_at=None,
        ends_at=None,
        reason="out of office",
        created_by=approver_a.id,
    )

    inst = await _route_instance(
        session,
        svc,
        project_id,
        owner.id,
        [StepCreate(ordinal=1, approver_user_id=approver_a.id, mode="all")],
    )
    step = (await svc.list_steps((await svc.get_instance(inst.id)).route_id))[0]

    # A stranger still cannot decide.
    with pytest.raises(HTTPException) as exc:
        await svc.submit_decision(
            inst.id,
            DecisionSubmit(step_id=step.id, decision="approved"),
            approver_id=stranger_c.id,
        )
    assert exc.value.status_code == 403

    # The delegate may decide on A's behalf.
    done = await svc.submit_decision(
        inst.id,
        DecisionSubmit(step_id=step.id, decision="approved"),
        approver_id=delegate_b.id,
    )
    assert done.status == "approved"


@pytest.mark.asyncio
async def test_revoked_delegation_grants_nothing(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    owner = await _user(session, role="admin")
    project_id = await _project(session, owner.id)
    approver_a = await _user(session)
    delegate_b = await _user(session)

    d = await svc.create_delegation(
        delegator_id=approver_a.id,
        delegate_id=delegate_b.id,
        project_id=None,
        starts_at=None,
        ends_at=None,
        reason=None,
        created_by=approver_a.id,
    )
    await svc.revoke_delegation(d.id, actor_id=approver_a.id)

    inst = await _route_instance(
        session,
        svc,
        project_id,
        owner.id,
        [StepCreate(ordinal=1, approver_user_id=approver_a.id, mode="all")],
    )
    step = (await svc.list_steps((await svc.get_instance(inst.id)).route_id))[0]

    with pytest.raises(HTTPException) as exc:
        await svc.submit_decision(
            inst.id,
            DecisionSubmit(step_id=step.id, decision="approved"),
            approver_id=delegate_b.id,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_expired_delegation_grants_nothing(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    owner = await _user(session, role="admin")
    project_id = await _project(session, owner.id)
    approver_a = await _user(session)
    delegate_b = await _user(session)

    # Window already closed.
    await svc.create_delegation(
        delegator_id=approver_a.id,
        delegate_id=delegate_b.id,
        project_id=None,
        starts_at=datetime.now(UTC) - timedelta(days=10),
        ends_at=datetime.now(UTC) - timedelta(days=1),
        reason=None,
        created_by=approver_a.id,
    )

    inst = await _route_instance(
        session,
        svc,
        project_id,
        owner.id,
        [StepCreate(ordinal=1, approver_user_id=approver_a.id, mode="all")],
    )
    step = (await svc.list_steps((await svc.get_instance(inst.id)).route_id))[0]

    with pytest.raises(HTTPException) as exc:
        await svc.submit_decision(
            inst.id,
            DecisionSubmit(step_id=step.id, decision="approved"),
            approver_id=delegate_b.id,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_override_clears_when_instance_advances(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    owner = await _user(session, role="admin")
    project_id = await _project(session, owner.id)
    approver_a = await _user(session)
    stand_in_b = await _user(session)
    approver_c = await _user(session)
    await _add_member(session, project_id, stand_in_b.id)

    inst = await _route_instance(
        session,
        svc,
        project_id,
        owner.id,
        [
            StepCreate(ordinal=1, approver_user_id=approver_a.id, mode="all"),
            StepCreate(ordinal=2, approver_user_id=approver_c.id, mode="all"),
        ],
    )
    route_id = (await svc.get_instance(inst.id)).route_id
    steps = await svc.list_steps(route_id)

    # Reassign step 1 to B, B clears it -> instance advances to step 2.
    await svc.reassign_current_step(inst.id, to_user_id=stand_in_b.id, actor_id=owner.id, reason=None)
    advanced = await svc.submit_decision(
        inst.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=stand_in_b.id,
    )
    assert advanced.status == "pending"
    assert advanced.current_step_ordinal == 2
    # The per-step override is gone; step 2 starts with its own approver.
    assert advanced.current_assignee_user_id is None

    # B (the step-1 stand-in) has no standing on step 2.
    with pytest.raises(HTTPException) as exc:
        await svc.submit_decision(
            inst.id,
            DecisionSubmit(step_id=steps[1].id, decision="approved"),
            approver_id=stand_in_b.id,
        )
    assert exc.value.status_code == 403

    # The real step-2 approver clears it.
    done = await svc.submit_decision(
        inst.id,
        DecisionSubmit(step_id=steps[1].id, decision="approved"),
        approver_id=approver_c.id,
    )
    assert done.status == "approved"


@pytest.mark.asyncio
async def test_cannot_delegate_to_self(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    a = await _user(session)
    with pytest.raises(HTTPException) as exc:
        await svc.create_delegation(
            delegator_id=a.id,
            delegate_id=a.id,
            project_id=None,
            starts_at=None,
            ends_at=None,
            reason=None,
            created_by=a.id,
        )
    assert exc.value.status_code == 422
