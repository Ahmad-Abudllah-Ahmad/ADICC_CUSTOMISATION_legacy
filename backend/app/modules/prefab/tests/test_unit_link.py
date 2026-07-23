# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Tests for the prefab unit cost-link service path.

Every test uses a transaction-isolated PostgreSQL session (rolled back on
teardown) from ``tests._pg`` - never the production / shared test DB. They prove
the link feature's guarantees: a unit links only to a BOQ position / assembly in
its own project, the linked rate becomes the unit's cost basis, earned value
follows the production stage, and a link can be cleared.

Coverage
--------
* linking a BOQ position surfaces its unit_rate as the cost basis + earned value
* linking an assembly surfaces its total_rate; a platform template is allowed
* a BOQ position link takes precedence over an assembly link
* clearing a link nulls the column and drops the cost view
* a cross-project or missing BOQ position / assembly is rejected cleanly
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from tests._pg import transactional_session

from app.modules.assemblies.models import Assembly
from app.modules.boq.models import BOQ, Position
from app.modules.prefab.schemas import PrefabUnitCreate, PrefabUnitLinkRequest
from app.modules.prefab.service import PrefabService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Transaction-isolated PostgreSQL session with two projects pre-seeded.

    Two projects under one owner so the cross-project link tests can probe the
    project boundary without extra setup.
    """
    async with transactional_session() as s:
        from app.modules.projects.models import Project
        from app.modules.users.models import User

        owner = User(
            id=uuid.uuid4(),
            email=f"owner-{uuid.uuid4().hex[:6]}@test.io",
            hashed_password="x",
            full_name="Owner",
        )
        s.add(owner)
        await s.flush()
        project_a = Project(id=uuid.uuid4(), name="Prefab Project A", owner_id=owner.id, currency="EUR")
        project_b = Project(id=uuid.uuid4(), name="Prefab Project B", owner_id=owner.id, currency="EUR")
        s.add_all([project_a, project_b])
        await s.commit()
        s.info["project_a_id"] = project_a.id
        s.info["project_b_id"] = project_b.id
        yield s


async def _make_position(session: AsyncSession, project_id: uuid.UUID, unit_rate: str) -> Position:
    """Create a BOQ + one position with the given unit_rate in a project."""
    boq = BOQ(id=uuid.uuid4(), project_id=project_id, name="Estimate")
    session.add(boq)
    await session.flush()
    position = Position(
        id=uuid.uuid4(),
        boq_id=boq.id,
        ordinal="01.01.0010",
        description="RC wall C30/37, 24cm",
        unit="m3",
        quantity="10",
        unit_rate=unit_rate,
        total="0",
    )
    session.add(position)
    await session.flush()
    return position


async def _make_assembly(
    session: AsyncSession,
    total_rate: str,
    *,
    project_id: uuid.UUID | None,
) -> Assembly:
    """Create an assembly (template when project_id is None) with a total_rate."""
    assembly = Assembly(
        id=uuid.uuid4(),
        code=f"ASM-{uuid.uuid4().hex[:8]}",
        name="RC wall recipe",
        unit="m3",
        total_rate=total_rate,
        is_template=project_id is None,
        project_id=project_id,
    )
    session.add(assembly)
    await session.flush()
    return assembly


async def _make_unit(service: PrefabService, project_id: uuid.UUID, *, status: str) -> uuid.UUID:
    unit = await service.create_unit(
        PrefabUnitCreate(project_id=project_id, ref=f"POD-{uuid.uuid4().hex[:5]}", status=status),
    )
    return unit.id


# ── 1. link a BOQ position ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_link_boq_position_sets_cost_basis_and_earned_value(session: AsyncSession) -> None:
    """Linking a BOQ position exposes its unit_rate as the cost basis."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    position = await _make_position(session, project_a, "500.00")
    unit_id = await _make_unit(service, project_a, status="qa")

    resp = await service.set_link(unit_id, PrefabUnitLinkRequest(boq_position_id=position.id))
    await session.commit()

    assert resp.boq_position_id == position.id
    assert resp.assembly_id is None
    assert resp.cost_source == "boq_position"
    assert Decimal(resp.cost_basis) == Decimal("500.00")
    # qa is the lifecycle midpoint -> half the basis is earned.
    assert resp.completed_fraction == 0.5
    assert Decimal(resp.earned_value) == Decimal("250.00")


# ── 2. link an assembly (platform template) ─────────────────────────────────


@pytest.mark.asyncio
async def test_link_assembly_template_sets_cost_basis(session: AsyncSession) -> None:
    """Linking a platform template assembly exposes its total_rate."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    assembly = await _make_assembly(session, "1200.00", project_id=None)
    unit_id = await _make_unit(service, project_a, status="installed")

    resp = await service.set_link(unit_id, PrefabUnitLinkRequest(assembly_id=assembly.id))
    await session.commit()

    assert resp.assembly_id == assembly.id
    assert resp.cost_source == "assembly"
    assert Decimal(resp.cost_basis) == Decimal("1200.00")
    # installed is terminal -> the full basis is earned.
    assert resp.completed_fraction == 1.0
    assert Decimal(resp.earned_value) == Decimal("1200.00")


# ── 3. BOQ position takes precedence over assembly ──────────────────────────


@pytest.mark.asyncio
async def test_boq_position_link_takes_precedence_over_assembly(session: AsyncSession) -> None:
    """When both links are set, the BOQ position drives the cost basis."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    position = await _make_position(session, project_a, "777.00")
    assembly = await _make_assembly(session, "1200.00", project_id=project_a)
    unit_id = await _make_unit(service, project_a, status="installed")

    resp = await service.set_link(
        unit_id,
        PrefabUnitLinkRequest(boq_position_id=position.id, assembly_id=assembly.id),
    )
    await session.commit()

    assert resp.boq_position_id == position.id
    assert resp.assembly_id == assembly.id
    assert resp.cost_source == "boq_position"
    assert Decimal(resp.cost_basis) == Decimal("777.00")


# ── 4. clearing a link ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_boq_position_link(session: AsyncSession) -> None:
    """Passing an explicit null clears the link and drops the cost view."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    position = await _make_position(session, project_a, "500.00")
    unit_id = await _make_unit(service, project_a, status="qa")

    await service.set_link(unit_id, PrefabUnitLinkRequest(boq_position_id=position.id))
    await session.commit()

    cleared = await service.set_link(unit_id, PrefabUnitLinkRequest(boq_position_id=None))
    await session.commit()

    assert cleared.boq_position_id is None
    assert cleared.cost_source is None
    assert cleared.cost_basis is None
    assert cleared.earned_value is None


# ── 5. integrity: cross-project / missing targets are rejected ──────────────


@pytest.mark.asyncio
async def test_link_cross_project_boq_position_rejected(session: AsyncSession) -> None:
    """A BOQ position from another project cannot be linked."""
    project_a: uuid.UUID = session.info["project_a_id"]
    project_b: uuid.UUID = session.info["project_b_id"]
    service = PrefabService(session)
    foreign = await _make_position(session, project_b, "300.00")
    unit_id = await _make_unit(service, project_a, status="design")

    with pytest.raises(HTTPException) as exc:
        await service.set_link(unit_id, PrefabUnitLinkRequest(boq_position_id=foreign.id))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_link_missing_boq_position_rejected(session: AsyncSession) -> None:
    """An unknown BOQ position id is rejected with a 404."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    unit_id = await _make_unit(service, project_a, status="design")

    with pytest.raises(HTTPException) as exc:
        await service.set_link(unit_id, PrefabUnitLinkRequest(boq_position_id=uuid.uuid4()))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_link_cross_project_assembly_rejected(session: AsyncSession) -> None:
    """A project-scoped assembly from another project cannot be linked."""
    project_a: uuid.UUID = session.info["project_a_id"]
    project_b: uuid.UUID = session.info["project_b_id"]
    service = PrefabService(session)
    foreign = await _make_assembly(session, "900.00", project_id=project_b)
    unit_id = await _make_unit(service, project_a, status="design")

    with pytest.raises(HTTPException) as exc:
        await service.set_link(unit_id, PrefabUnitLinkRequest(assembly_id=foreign.id))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_link_missing_assembly_rejected(session: AsyncSession) -> None:
    """An unknown assembly id is rejected with a 404."""
    project_a: uuid.UUID = session.info["project_a_id"]
    service = PrefabService(session)
    unit_id = await _make_unit(service, project_a, status="design")

    with pytest.raises(HTTPException) as exc:
        await service.set_link(unit_id, PrefabUnitLinkRequest(assembly_id=uuid.uuid4()))
    assert exc.value.status_code == 404
