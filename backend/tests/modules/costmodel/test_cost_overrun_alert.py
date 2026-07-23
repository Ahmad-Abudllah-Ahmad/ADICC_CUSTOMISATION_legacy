"""Gap D module tests: ``CostOverrunAlertService.check_and_alert`` + subscriber.

The alerting logic is the single sink the cost-overrun subscriber calls when a
budget line changes. It is exercised directly (single PostgreSQL session, rolled
back on teardown) so the assertions can both drive the input and inspect the
resulting ``Notification`` rows / cooldown stamp without the cross-loop hazards
of a detached background task.

Covers TEST MATRIX cases 9-16 (subscriber):
    9   no threshold       -> 0 notifications
    10  overrun crossed    -> 1 notification
    11  not crossed        -> 0 notifications
    12  cooldown active    -> first sends, second within 24h skipped
    13  cooldown expired   -> emit, wait 25h, emit -> both send
    14  context accuracy   -> body_context fields match the line
    15  sets alerted_at    -> overrun_alerted_at stamped on send
    16  exception swallowed -> subscriber logs, never re-raises
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.costmodel.models import BudgetLine
from app.modules.costmodel.service import (
    CostOverrunAlertService,
    _extract_line_id,
    _on_budget_line_changed,
)
from app.modules.notifications.models import Notification
from tests._pg import transactional_session

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with transactional_session() as sess:
        yield sess


# ── Seed helpers ────────────────────────────────────────────────────────────────


async def _seed_project(session: AsyncSession, *, with_owner: bool = True) -> tuple[uuid.UUID, uuid.UUID | None]:
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    owner_id: uuid.UUID | None = None
    if with_owner:
        user = User(
            id=uuid.uuid4(),
            email=f"gapd-{uuid.uuid4().hex[:10]}@overrun.io",
            hashed_password="x",
            full_name="Gap D Owner",
            role="admin",
        )
        session.add(user)
        await session.flush()
        owner_id = user.id

    project = Project(
        id=uuid.uuid4(),
        name="Gap D project",
        owner_id=owner_id,
        currency="EUR",
        fx_rates=[],
    )
    session.add(project)
    await session.flush()
    return project.id, owner_id


async def _seed_line(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    planned: str = "1000",
    actual: str = "0",
    threshold: str = "0",
    alerted_at: datetime | None = None,
    category: str = "material",
    currency: str = "EUR",
) -> BudgetLine:
    line = BudgetLine(
        project_id=project_id,
        category=category,
        description="RC wall",
        planned_amount=planned,
        committed_amount="0",
        actual_amount=actual,
        forecast_amount=planned,
        currency=currency,
        overrun_alert_threshold_pct=threshold,
        overrun_alerted_at=alerted_at,
    )
    session.add(line)
    await session.flush()
    return line


async def _count_alerts(session: AsyncSession, line_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.notification_type == "cost_overrun_alert",
            Notification.entity_id == str(line_id),
        )
    )
    return (await session.execute(stmt)).scalar_one()


# ── Case 9: no threshold -> no notification ─────────────────────────────────────


async def test_no_threshold_no_alert(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="9999", threshold="0")

    sent = await CostOverrunAlertService(session).check_and_alert(line.id)

    assert sent is False
    assert await _count_alerts(session, line.id) == 0


# ── Case 10: overrun crossed -> 1 notification ──────────────────────────────────


async def test_overrun_crossed_sends_one(session: AsyncSession) -> None:
    project_id, owner_id = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="115", threshold="10")

    sent = await CostOverrunAlertService(session).check_and_alert(line.id)

    assert sent is True
    assert await _count_alerts(session, line.id) == 1
    notif = (await session.execute(select(Notification).where(Notification.entity_id == str(line.id)))).scalar_one()
    assert notif.user_id == owner_id
    assert notif.title_key == "notifications.costmodel.overrun_alert.title"
    assert notif.action_url == f"/costmodel?line={line.id}"


# ── Case 11: not crossed -> no notification ─────────────────────────────────────


async def test_overrun_not_crossed_no_alert(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="105", threshold="10")

    sent = await CostOverrunAlertService(session).check_and_alert(line.id)

    assert sent is False
    assert await _count_alerts(session, line.id) == 0


# ── Case 12: cooldown active -> second call within 24h skipped ───────────────────


async def test_cooldown_active_skips_second(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="200", threshold="10")
    svc = CostOverrunAlertService(session)

    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    first = await svc.check_and_alert(line.id, now=t0)
    # 5 hours later, still overrun, but inside the 24h window.
    second = await svc.check_and_alert(line.id, now=t0 + timedelta(hours=5))

    assert first is True
    assert second is False
    assert await _count_alerts(session, line.id) == 1


# ── Case 13: cooldown expired -> both send ──────────────────────────────────────


async def test_cooldown_expired_sends_again(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="200", threshold="10")
    svc = CostOverrunAlertService(session)

    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    first = await svc.check_and_alert(line.id, now=t0)
    # 25 hours later -> cooldown expired -> sends again.
    second = await svc.check_and_alert(line.id, now=t0 + timedelta(hours=25))

    assert first is True
    assert second is True
    assert await _count_alerts(session, line.id) == 2


# ── Case 14: body_context accuracy ──────────────────────────────────────────────


async def test_body_context_accuracy(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(
        session,
        project_id,
        planned="1000",
        actual="1200",
        threshold="15",
        category="labor",
        currency="EUR",
    )

    await CostOverrunAlertService(session).check_and_alert(line.id)

    notif = (await session.execute(select(Notification).where(Notification.entity_id == str(line.id)))).scalar_one()
    ctx = notif.body_context
    assert ctx["category"] == "labor"
    assert ctx["threshold_pct"] == "15"
    assert ctx["planned"] == "1000"
    assert ctx["actual"] == "1200"
    assert ctx["currency"] == "EUR"


async def test_body_context_uncategorised_label(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="200", threshold="10", category="")

    await CostOverrunAlertService(session).check_and_alert(line.id)

    notif = (await session.execute(select(Notification).where(Notification.entity_id == str(line.id)))).scalar_one()
    assert notif.body_context["category"] == "uncategorised"


# ── Case 15: sets overrun_alerted_at ────────────────────────────────────────────


async def test_sets_alerted_at(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session)
    line = await _seed_line(session, project_id, planned="100", actual="200", threshold="10")
    assert line.overrun_alerted_at is None

    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    await CostOverrunAlertService(session).check_and_alert(line.id, now=t0)

    reloaded = await CostOverrunAlertService(session).budget_repo.get_by_id(line.id)
    assert reloaded is not None
    assert reloaded.overrun_alerted_at is not None


# ── Case 16: exception in the subscriber is swallowed (never re-raised) ──────────


async def test_subscriber_swallows_exception(monkeypatch) -> None:
    """A failure inside the detached subscriber must not propagate.

    Patches the session factory to raise; the subscriber logs at debug and
    returns normally, so the upstream cost update is unaffected.
    """

    def _boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.database.async_session_factory", _boom)

    event = type("E", (), {"data": {"line_id": str(uuid.uuid4())}})()
    # Must not raise.
    await _on_budget_line_changed(event)


# ── Extra: subscriber is a no-op when the payload has no line id ─────────────────


async def test_subscriber_ignores_payload_without_line() -> None:
    event = type("E", (), {"data": {"project_id": str(uuid.uuid4())}})()
    # No line id -> early return, no session opened, no raise.
    await _on_budget_line_changed(event)


def test_extract_line_id_accepts_both_keys() -> None:
    lid = uuid.uuid4()
    assert _extract_line_id(type("E", (), {"data": {"line_id": str(lid)}})()) == lid
    assert _extract_line_id(type("E", (), {"data": {"budget_line_id": str(lid)}})()) == lid
    assert _extract_line_id(type("E", (), {"data": {}})()) is None
    assert _extract_line_id(type("E", (), {"data": {"line_id": "not-a-uuid"}})()) is None


# ── Extra: missing project owner -> no alert, cooldown NOT stamped ───────────────


async def test_no_owner_no_alert_no_cooldown(session: AsyncSession) -> None:
    project_id, _ = await _seed_project(session, with_owner=False)
    line = await _seed_line(session, project_id, planned="100", actual="200", threshold="10")

    sent = await CostOverrunAlertService(session).check_and_alert(line.id)

    assert sent is False
    assert await _count_alerts(session, line.id) == 0
    # Cooldown must remain unset so a later owner assignment still gets alert #1.
    reloaded = await CostOverrunAlertService(session).budget_repo.get_by_id(line.id)
    assert reloaded is not None
    assert reloaded.overrun_alerted_at is None
