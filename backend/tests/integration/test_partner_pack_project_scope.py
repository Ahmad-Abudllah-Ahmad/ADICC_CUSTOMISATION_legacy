# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Partner-pack project scoping: an active pack shows only its own projects.

When a pack is active the workspace presents a clean single-client view. Only
projects tagged ``metadata_["partner_pack"] == <slug>`` are listed, and this
overrides the admin-sees-all rule (an operator activating a pack wants the pack's
workspace, not every project ever created). Deactivating the pack untags its
projects so the normal listing returns. These tests run against the real
embedded PostgreSQL the suite boots, so the ``metadata_ ->> 'partner_pack'``
JSON filter is exercised against an actual database, not a mock.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from tests._pg import transactional_session

PACK_SLUG = "batimatech-ca"

ADMIN_ID = uuid.uuid4()
REGULAR_ID = uuid.uuid4()

P_TAGGED_ADMIN = uuid.uuid4()
P_UNTAGGED_ADMIN = uuid.uuid4()
P_TAGGED_REGULAR = uuid.uuid4()


@pytest_asyncio.fixture
async def session():
    """A PG session seeded with one admin + one regular user and three projects.

    * P_TAGGED_ADMIN    — owner=admin,   metadata partner_pack=batimatech-ca
    * P_UNTAGGED_ADMIN  — owner=admin,   no pack tag
    * P_TAGGED_REGULAR  — owner=regular, metadata partner_pack=batimatech-ca
    """
    async with transactional_session() as s:
        from app.modules.projects.models import Project
        from app.modules.users.models import User

        s.add(User(id=ADMIN_ID, email="admin@test.io", hashed_password="x", full_name="Admin"))
        s.add(User(id=REGULAR_ID, email="reg@test.io", hashed_password="x", full_name="Reg"))
        await s.flush()

        s.add(
            Project(
                id=P_TAGGED_ADMIN,
                name="Tagged Admin",
                owner_id=ADMIN_ID,
                currency="CAD",
                status="active",
                metadata_={"partner_pack": PACK_SLUG},
            )
        )
        s.add(
            Project(
                id=P_UNTAGGED_ADMIN,
                name="Untagged Admin",
                owner_id=ADMIN_ID,
                currency="EUR",
                status="active",
                metadata_={},
            )
        )
        s.add(
            Project(
                id=P_TAGGED_REGULAR,
                name="Tagged Regular",
                owner_id=REGULAR_ID,
                currency="CAD",
                status="active",
                metadata_={"partner_pack": PACK_SLUG},
            )
        )
        await s.commit()
        yield s


def _ids(projects) -> set[uuid.UUID]:  # noqa: ANN001
    return {p.id for p in projects}


async def _async_true(*_args, **_kwargs) -> bool:  # noqa: ANN002, ANN003
    return True


@pytest.mark.asyncio
async def test_no_active_pack_admin_sees_all(session, monkeypatch) -> None:
    """With no pack active, the admin listing is unscoped (sees all three)."""
    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: None)
    from app.modules.projects.repository import ProjectRepository

    repo = ProjectRepository(session)
    projects, total = await repo.list_for_user(ADMIN_ID, is_admin=True)
    ids = _ids(projects)
    assert {P_TAGGED_ADMIN, P_UNTAGGED_ADMIN, P_TAGGED_REGULAR} <= ids
    assert total >= 3


@pytest.mark.asyncio
async def test_active_pack_scopes_admin_to_tagged_only(session, monkeypatch) -> None:
    """An active pack hides every untagged project, even from an admin."""
    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: PACK_SLUG)
    from app.modules.projects.repository import ProjectRepository

    repo = ProjectRepository(session)
    projects, total = await repo.list_for_user(ADMIN_ID, is_admin=True)
    ids = _ids(projects)

    # Both tagged projects are visible (admin sees all tagged, regardless of owner).
    assert P_TAGGED_ADMIN in ids
    assert P_TAGGED_REGULAR in ids
    # The untagged project is hidden despite admin-sees-all.
    assert P_UNTAGGED_ADMIN not in ids
    assert total == 2


@pytest.mark.asyncio
async def test_active_pack_scopes_regular_user_to_owned_and_tagged(session, monkeypatch) -> None:
    """A regular user sees only projects they can access AND that the pack tags."""
    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: PACK_SLUG)
    from app.modules.projects.repository import ProjectRepository

    repo = ProjectRepository(session)
    projects, total = await repo.list_for_user(REGULAR_ID, is_admin=False)
    ids = _ids(projects)

    assert ids == {P_TAGGED_REGULAR}
    assert total == 1


@pytest.mark.asyncio
async def test_untagging_releases_project_back_to_listing(session, monkeypatch) -> None:
    """Removing the pack tag (the deactivation effect) makes a project reappear.

    Simulates what ``unapply`` does (clears ``metadata_['partner_pack']``) and
    confirms the now-untagged project is excluded from the still-active-pack
    listing - i.e. it has genuinely left the pack's scope.
    """
    from app.modules.projects.models import Project
    from app.modules.projects.repository import ProjectRepository

    # Untag the admin's tagged project, mirroring _untag_pack_projects.
    proj = await session.get(Project, P_TAGGED_ADMIN)
    md = dict(proj.metadata_ or {})
    md.pop("partner_pack", None)
    proj.metadata_ = md
    await session.flush()

    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: PACK_SLUG)
    repo = ProjectRepository(session)
    projects, _ = await repo.list_for_user(ADMIN_ID, is_admin=True)
    ids = _ids(projects)

    # The freshly untagged project is gone; the still-tagged one remains.
    assert P_TAGGED_ADMIN not in ids
    assert P_TAGGED_REGULAR in ids


@pytest.mark.asyncio
async def test_dashboard_rollup_no_pack_sees_all(session, monkeypatch) -> None:
    """With no pack active, the dashboard rollup access list is unscoped."""
    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: None)
    monkeypatch.setattr("app.modules.dashboard.service.is_admin", _async_true)
    from app.modules.dashboard.service import accessible_projects

    projects = await accessible_projects(session, str(ADMIN_ID))
    ids = _ids(projects)
    assert {P_TAGGED_ADMIN, P_UNTAGGED_ADMIN, P_TAGGED_REGULAR} <= ids


@pytest.mark.asyncio
async def test_dashboard_rollup_active_pack_scopes_to_tagged(session, monkeypatch) -> None:
    """Regression: the dashboard rollup must hide untagged projects under an active pack.

    Without ``scope_project_query`` in ``accessible_projects`` the rollup widgets
    (boq_summary, budget_variance, ...) would aggregate every non-archived project,
    a workspace-scope leak inconsistent with the scoped projects page and cards.
    """
    monkeypatch.setattr("app.core.partner_pack.scope.active_pack_slug", lambda: PACK_SLUG)
    monkeypatch.setattr("app.modules.dashboard.service.is_admin", _async_true)
    from app.modules.dashboard.service import accessible_projects

    projects = await accessible_projects(session, str(ADMIN_ID))
    ids = _ids(projects)
    # Both pack-tagged projects remain (the rollup deliberately overrides
    # admin-sees-all to match the scoped projects page).
    assert P_TAGGED_ADMIN in ids
    assert P_TAGGED_REGULAR in ids
    # The untagged project must NOT leak into the rollup.
    assert P_UNTAGGED_ADMIN not in ids
