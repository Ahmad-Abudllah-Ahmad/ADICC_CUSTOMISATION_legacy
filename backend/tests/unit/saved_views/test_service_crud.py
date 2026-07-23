"""Service CRUD and run round-trips (DB-backed, CI-gated).

save -> get -> update -> delete; the unique-name-per-scope constraint; and an
ad-hoc run that returns the seeded rows. Skipped automatically when no
PostgreSQL cluster can be booted.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://oe:oe@localhost:5432/openestimate")
os.environ.setdefault("DATABASE_SYNC_URL", "postgresql://oe:oe@localhost:5432/openestimate")

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.saved_views.errors import ScopeDenied
from app.modules.saved_views.schemas import (
    SavedViewCreate,
    SavedViewUpdate,
)
from app.modules.saved_views.scoper import ScopeContext
from app.modules.saved_views.service import SavedViewService

try:
    from tests._pg import transactional_session

    _PG_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PG_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _PG_AVAILABLE, reason="PostgreSQL test cluster unavailable")


def _register_ledger() -> None:
    from app.modules.saved_views.entities import finance_entity
    from app.modules.saved_views.registry import entity_registry

    if entity_registry.get("ledger_entry") is None:
        finance_entity.register()


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    from app.modules.finance.models import LedgerEntry
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    user = User(email=f"u-{uuid.uuid4().hex[:8]}@test.io", hashed_password="x", full_name="T")
    session.add(user)
    await session.flush()
    project = Project(name="CRUD", owner_id=user.id, metadata_={})
    session.add(project)
    await session.flush()
    session.add(
        LedgerEntry(
            project_id=project.id,
            transaction_ref="R-1",
            account_code="330",
            debit_amount=Decimal("100"),
            credit_amount=Decimal("0"),
            currency_code="EUR",
            posted_at="2026-01-01",
        )
    )
    await session.flush()
    return user.id, project.id


@pytest_asyncio.fixture
async def session():
    _register_ledger()
    async with transactional_session() as s:
        yield s


def _ctx(user_id, project_id, role="editor") -> ScopeContext:
    return ScopeContext(
        user_id=user_id,
        role=role,
        project_id=project_id,
        workspace_slug=None,
        is_admin=role == "admin",
    )


@pytest.mark.asyncio
async def test_save_get_update_delete_round_trip(session: AsyncSession):
    user_id, project_id = await _seed(session)
    ctx = _ctx(user_id, project_id)
    service = SavedViewService(session)

    created = await service.save_view(
        ctx,
        SavedViewCreate(
            entity_type="ledger_entry",
            name="My view",
            project_id=project_id,
        ),
    )
    assert created.id is not None

    fetched = await service.get_view(created.id, ctx)
    assert fetched.name == "My view"

    updated = await service.update_view(created.id, ctx, SavedViewUpdate(name="Renamed", is_pinned=True))
    assert updated.name == "Renamed"
    assert updated.is_pinned is True

    await service.delete_view(created.id, ctx)
    with pytest.raises(ScopeDenied):
        await service.get_view(created.id, ctx)


@pytest.mark.asyncio
async def test_duplicate_name_in_same_scope_rejected(session: AsyncSession):
    from sqlalchemy.exc import IntegrityError

    user_id, project_id = await _seed(session)
    ctx = _ctx(user_id, project_id)
    service = SavedViewService(session)

    await service.save_view(
        ctx,
        SavedViewCreate(entity_type="ledger_entry", name="Dup", project_id=project_id),
    )
    with pytest.raises(IntegrityError):
        await service.save_view(
            ctx,
            SavedViewCreate(entity_type="ledger_entry", name="Dup", project_id=project_id),
        )


@pytest.mark.asyncio
async def test_run_adhoc_returns_seeded_rows(session: AsyncSession):
    from app.modules.saved_views.schemas import FilterSpec

    user_id, project_id = await _seed(session)
    ctx = _ctx(user_id, project_id)
    service = SavedViewService(session)
    result = await service.run_adhoc("ledger_entry", FilterSpec(), ctx)
    assert len(result.rows) == 1
    assert result.rows[0]["transaction_ref"] == "R-1"
    # Money serialized as a decimal string, not a float (NUMERIC(_, 2) -> "100.00").
    assert result.rows[0]["debit_amount"] == "100.00"
    assert isinstance(result.rows[0]["debit_amount"], str)


@pytest.mark.asyncio
async def test_count_for_reminder(session: AsyncSession):
    user_id, project_id = await _seed(session)
    ctx = _ctx(user_id, project_id)
    service = SavedViewService(session)
    view = await service.save_view(
        ctx,
        SavedViewCreate(entity_type="ledger_entry", name="Count", project_id=project_id),
    )
    count = await service.count_for_reminder(view.id, ctx)
    assert count.count == 1
    assert count.truncated is False


@pytest.mark.asyncio
async def test_non_owner_cannot_update(session: AsyncSession):
    user_id, project_id = await _seed(session)
    owner_ctx = _ctx(user_id, project_id)
    service = SavedViewService(session)
    view = await service.save_view(
        owner_ctx,
        SavedViewCreate(entity_type="ledger_entry", name="Owned", project_id=project_id),
    )

    other_ctx = _ctx(uuid.uuid4(), project_id)
    with pytest.raises(ScopeDenied):
        await service.update_view(view.id, other_ctx, SavedViewUpdate(name="Hijacked"))
