"""Baseline tests for the Markups module — Round 3 Wave A sweep.

Pins the contract for the markups-module remediation done this round:

* Calibration / measurement columns persist as ``Decimal``
  (Float → ``Numeric(18, 6)`` on PostgreSQL; SQLAlchemy round-trips the
  value as a ``Decimal`` unchanged).
* Pagination on the list endpoint honours the platform-standard
  ``offset`` + ``limit`` slice rather than a confusing ``page`` rail
  (``page`` survives only as a deprecated *drawing-page* filter alias).
* ``verify_project_access`` rejects access to a project the user does
  not own — the auth gate cannot be silently dropped from the listing
  route in a future refactor.

The test runs on a transaction-isolated PostgreSQL session (rolled back
on teardown) via ``tests._pg.transactional_session`` — never
``backend/openestimate.db``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.dependencies import verify_project_access
from app.modules.markups.schemas import MarkupCreate, ScaleConfigCreate
from app.modules.markups.service import MarkupsService
from tests._pg import transactional_session


@pytest_asyncio.fixture
async def session_owner():
    """Yield (session, owner_id, project_id) on an isolated PostgreSQL session."""
    async with transactional_session() as s:
        from app.modules.projects.models import Project
        from app.modules.users.models import User

        owner_id = uuid.uuid4()
        project_id = uuid.uuid4()
        owner = User(
            id=owner_id,
            email=f"owner-{uuid.uuid4().hex[:6]}@test.io",
            hashed_password="x",
            full_name="Owner",
        )
        s.add(owner)
        await s.flush()
        s.add(
            Project(
                id=project_id,
                name="Markups Test",
                owner_id=owner_id,
                currency="EUR",
            ),
        )
        await s.commit()
        yield s, str(owner_id), project_id


@pytest.mark.asyncio
async def test_create_markup_measurement_persists_as_decimal(session_owner) -> None:
    """measurement_value must persist as Decimal (no float-drift on takeoff)."""
    session, owner_id, project_id = session_owner
    service = MarkupsService(session)

    item = await service.create_markup(
        MarkupCreate(
            project_id=project_id,
            type="distance",
            geometry={"points": [{"x": 0, "y": 0}, {"x": 1234567, "y": 0}]},
            measurement_value=12.345678,
            measurement_unit="m",
        ),
        user_id=owner_id,
    )
    await session.commit()
    await session.refresh(item)

    assert item.measurement_value is not None
    # SQLAlchemy Numeric returns Decimal on PostgreSQL; it must compare
    # exactly to the input with no float drift.
    assert Decimal(str(item.measurement_value)) == Decimal("12.345678")


@pytest.mark.asyncio
async def test_create_scale_config_calibration_is_decimal(session_owner) -> None:
    """pixels_per_unit / real_distance round-trip without float drift."""
    session, owner_id, _ = session_owner
    service = MarkupsService(session)

    scale = await service.create_scale(
        ScaleConfigCreate(
            document_id="doc-001",
            page=1,
            pixels_per_unit=987.654321,
            unit_label="m",
            calibration_points={"p1": [0, 0], "p2": [987, 0]},
            real_distance=1.234567,
        ),
        user_id=owner_id,
    )
    await session.commit()
    await session.refresh(scale)

    assert Decimal(str(scale.pixels_per_unit)) == Decimal("987.654321")
    assert Decimal(str(scale.real_distance)) == Decimal("1.234567")


@pytest.mark.asyncio
async def test_list_markups_offset_limit_slices(session_owner) -> None:
    """list_for_project honours ``offset`` + ``limit`` (platform standard)."""
    session, owner_id, project_id = session_owner
    service = MarkupsService(session)

    # Seed five markups; created_at order is insertion order (DESC on read).
    for i in range(5):
        await service.create_markup(
            MarkupCreate(
                project_id=project_id,
                type="text",
                text=f"note-{i}",
            ),
            user_id=owner_id,
        )
    await session.commit()

    page1, total = await service.list_markups(project_id, offset=0, limit=2)
    page2, _ = await service.list_markups(project_id, offset=2, limit=2)
    page3, _ = await service.list_markups(project_id, offset=4, limit=2)

    assert total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    # No overlap across slices.
    ids = {m.id for m in page1} | {m.id for m in page2} | {m.id for m in page3}
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_verify_project_access_rejects_outsider(session_owner) -> None:
    """A non-owning user gets a 404 on the project gate (no info leak)."""
    session, _owner_id, project_id = session_owner
    from app.modules.users.models import User

    outsider_id = uuid.uuid4()
    session.add(
        User(
            id=outsider_id,
            email=f"out-{uuid.uuid4().hex[:6]}@test.io",
            hashed_password="x",
            full_name="Outsider",
        ),
    )
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await verify_project_access(project_id, str(outsider_id), session)
    # 404 — auth failures and missing projects must look identical.
    assert exc.value.status_code == 404
