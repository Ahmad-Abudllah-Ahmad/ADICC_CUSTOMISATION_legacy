# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Feature 06 — RFI ↔ approval-routes wiring tests.

Mirrors the submittal wiring tests with the conservative RFI mapping:

1. ``RFIService.start_approval`` creates an ``Instance`` with
   ``target_kind='rfi'`` and moves a draft RFI to ``open``, recording the
   instance id in metadata.
2. The engine's terminal events carry ``target_kind`` / ``target_id``.
3. ``apply_approval_decision`` only ever drives transitions the RFI FSM
   already allows: an approved chain re-affirms an already-recorded answer
   (``open`` + official_response → ``answered``), a rejection reopens an
   ``answered`` RFI through the manager-gated path. Anything else is a no-op,
   so a stray event can never force an illegal transition.
4. The engine rejects a second pending workflow on the same RFI (409).
5. A project with no route keeps today's direct respond path.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.audit_log  # noqa: F401 — registers ActivityLog
from app.core.events import event_bus
from app.modules.approval_routes.models import (  # noqa: F401 — register ORM
    Instance,
    Route,
    Step,
    StepState,
)
from app.modules.approval_routes.schemas import (
    DecisionSubmit,
    RouteCreate,
    StepCreate,
)
from app.modules.approval_routes.service import ApprovalRouteService
from app.modules.projects.models import Project  # noqa: F401
from app.modules.rfi.models import RFI  # noqa: F401
from app.modules.rfi.schemas import RFICreate, RFIUpdate
from app.modules.rfi.service import RFIService
from app.modules.users.models import User  # noqa: F401
from tests._pg import transactional_session


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with transactional_session() as s:
        yield s


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(
        email=f"rfi-appr-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Approver",
        role="manager",
    )
    session.add(user)
    await session.flush()
    proj = Project(name=f"RFI-Appr {uuid.uuid4().hex[:6]}", owner_id=user.id)
    session.add(proj)
    await session.flush()
    return proj.id, user.id


async def _make_rfi(
    svc: RFIService,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    status: str = "open",
) -> RFI:
    return await svc.create_rfi(
        RFICreate(
            project_id=project_id,
            subject="Clarify slab thickness",
            question="What is the slab thickness at grid B?",
            assigned_to=str(user_id),
            status=status,
        ),
        user_id=str(user_id),
    )


async def _make_route(
    engine: ApprovalRouteService,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    n_steps: int = 1,
) -> Route:
    steps = [StepCreate(ordinal=i + 1, approver_user_id=user_id, mode="all") for i in range(n_steps)]
    return await engine.create_route(
        RouteCreate(
            project_id=project_id,
            name="RFI sign-off",
            target_kind="rfi",
            steps=steps,
        ),
        created_by=user_id,
    )


def _capture() -> list[tuple[str, dict[str, Any]]]:
    captured: list[tuple[str, dict[str, Any]]] = []

    async def _handler(event: Any) -> None:
        captured.append((event.name, dict(event.data or {})))

    for n in (
        "approval_routes.instance.completed",
        "approval_routes.instance.rejected",
    ):
        event_bus.subscribe(n, _handler)
    return captured


@pytest.mark.asyncio
async def test_start_approval_creates_instance(session: AsyncSession) -> None:
    project_id, user_id = await _seed(session)
    svc = RFIService(session)
    engine = ApprovalRouteService(session)
    rfi = await _make_rfi(svc, project_id, user_id, status="draft")
    route = await _make_route(engine, project_id, user_id)

    instance = await svc.start_approval(rfi.id, route.id, started_by=str(user_id))
    assert instance.target_kind == "rfi"
    assert instance.target_id == rfi.id

    fresh = await svc.get_rfi(rfi.id)
    assert fresh.status == "open"  # draft → open through the FSM
    assert (fresh.metadata_ or {}).get("approval_instance_id") == str(instance.id)

    latest = await svc.get_latest_approval(rfi.id)
    assert latest is not None and latest.id == instance.id


@pytest.mark.asyncio
async def test_second_workflow_rejected_409(session: AsyncSession) -> None:
    from fastapi import HTTPException

    project_id, user_id = await _seed(session)
    svc = RFIService(session)
    engine = ApprovalRouteService(session)
    rfi = await _make_rfi(svc, project_id, user_id)
    route = await _make_route(engine, project_id, user_id)

    await svc.start_approval(rfi.id, route.id, started_by=str(user_id))
    with pytest.raises(HTTPException) as exc:
        await svc.start_approval(rfi.id, route.id, started_by=str(user_id))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approval_completed_reaffirms_answer(session: AsyncSession) -> None:
    project_id, user_id = await _seed(session)
    svc = RFIService(session)
    engine = ApprovalRouteService(session)
    rfi = await _make_rfi(svc, project_id, user_id)
    route = await _make_route(engine, project_id, user_id)
    captured = _capture()

    instance = await svc.start_approval(rfi.id, route.id, started_by=str(user_id))

    # No official response yet → completed is a conservative no-op.
    no_op = await svc.apply_approval_decision(rfi.id, decision="approved", decided_by=str(user_id))
    assert no_op is None
    assert (await svc.get_rfi(rfi.id)).status == "open"

    # Record an official response, then approve the chain → RFI answered.
    await svc.respond_to_rfi(
        rfi.id,
        "Slab is 200mm at grid B.",
        responded_by=str(user_id),
        actor_role="manager",
    )
    # Re-open so apply_approval_decision's open+response branch is exercised
    # (answered → open is a manager-gated transition).
    await svc.update_rfi(
        rfi.id,
        RFIUpdate(status="open"),
        actor_id=str(user_id),
        actor_role="manager",
    )

    steps = await engine.list_steps(route.id)
    completed_inst = await engine.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved", comment="ok"),
        approver_id=user_id,
    )
    assert completed_inst.status == "approved"
    assert any(n == "approval_routes.instance.completed" for n, _ in captured)

    result = await svc.apply_approval_decision(rfi.id, decision="approved", decided_by=str(user_id))
    assert result is not None
    assert result.status == "answered"


@pytest.mark.asyncio
async def test_approval_rejection_reopens_answered_rfi(session: AsyncSession) -> None:
    project_id, user_id = await _seed(session)
    svc = RFIService(session)
    engine = ApprovalRouteService(session)
    rfi = await _make_rfi(svc, project_id, user_id)
    route = await _make_route(engine, project_id, user_id)

    await svc.start_approval(rfi.id, route.id, started_by=str(user_id))
    # Answer the RFI so it is in 'answered'.
    await svc.respond_to_rfi(
        rfi.id,
        "Slab is 200mm.",
        responded_by=str(user_id),
        actor_role="manager",
    )
    assert (await svc.get_rfi(rfi.id)).status == "answered"

    # A rejected sign-off reopens the answered RFI (manager-gated path,
    # internal caller bypasses the role gate) with the comment recorded.
    result = await svc.apply_approval_decision(
        rfi.id,
        decision="rejected",
        decided_by=str(user_id),
        comment="answer incomplete",
    )
    assert result is not None
    assert result.status == "open"
    assert (result.metadata_ or {}).get("approval_reject_reason") == "answer incomplete"


@pytest.mark.asyncio
async def test_no_route_keeps_direct_path(session: AsyncSession) -> None:
    project_id, user_id = await _seed(session)
    svc = RFIService(session)
    rfi = await _make_rfi(svc, project_id, user_id)

    assert await svc.get_latest_approval(rfi.id) is None
    answered = await svc.respond_to_rfi(
        rfi.id,
        "Direct answer.",
        responded_by=str(user_id),
        actor_role="manager",
    )
    assert answered.status == "answered"
