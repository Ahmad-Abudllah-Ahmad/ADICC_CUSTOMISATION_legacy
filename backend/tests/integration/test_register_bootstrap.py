"""Registration bootstrap — first user becomes admin, subsequent users viewer.

Regression test for the v2.0.0 RBAC UX regression where self-registered users
were universally demoted to `viewer`, causing every write action to 403 in
fresh dev installs.

The fix: `UserRepository.has_admin()` replaces the raw `count()` check. If no
admin user exists in the DB, the next registrant is promoted to admin. Once
any admin is on record, subsequent self-registered users default to viewer.

This test drives the service layer directly against a transaction-isolated
PostgreSQL session so neither the persistent dev DB nor the demo-seed lifespan
taint the result.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pg import transactional_session


@pytest_asyncio.fixture
async def session():
    """Transaction-isolated PostgreSQL session — guarantees no admin exists at t=0."""
    async with transactional_session() as s:
        yield s


def _payload(email: str):
    from app.modules.users.schemas import UserCreate

    return UserCreate(email=email, password="BootstrapTest99", full_name="Bootstrap")


def _service(session: AsyncSession):
    from app.config import get_settings
    from app.modules.users.service import UserService

    return UserService(session, get_settings())


@pytest.mark.asyncio
async def test_first_registrant_is_admin(session):
    """Fresh DB with no admin → first registrant must be promoted to admin."""
    from app.modules.users.repository import UserRepository

    repo = UserRepository(session)
    assert await repo.has_admin() is False

    email = f"first-{uuid.uuid4().hex[:6]}@bootstrap.io"
    user = await _service(session).register(_payload(email))
    await session.commit()

    assert user.role == "admin"
    assert await repo.has_admin() is True


@pytest.mark.asyncio
async def test_second_registrant_is_viewer(session):
    """After an admin exists, the next registrant defaults to viewer."""
    svc = _service(session)

    first = await svc.register(_payload(f"first-{uuid.uuid4().hex[:6]}@bootstrap.io"))
    await session.commit()
    assert first.role == "admin"

    second = await svc.register(_payload(f"second-{uuid.uuid4().hex[:6]}@bootstrap.io"))
    await session.commit()
    assert second.role == "viewer"


@pytest.mark.asyncio
async def test_non_admin_seed_does_not_block_bootstrap(session):
    """Demo/viewer seed rows must not prevent the first admin promotion.

    This is the actual v2.0.0 regression: a prior ``count() == 0`` check
    treated any pre-seeded viewer as "DB not empty" and downgraded the
    first real user to viewer too. ``has_admin()`` looks for admin
    specifically, so seed viewer rows are irrelevant.
    """
    import uuid as _uuid

    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from app.modules.users.service import hash_password

    seed = User(
        id=_uuid.uuid4(),
        email="seed@viewer.io",
        hashed_password=hash_password("SeedPass1234!"),
        full_name="Seed",
        role="viewer",
        locale="en",
        is_active=True,
        metadata_={},
    )
    session.add(seed)
    await session.commit()

    repo = UserRepository(session)
    assert await repo.has_admin() is False, "has_admin must ignore non-admin seed rows"

    first = await _service(session).register(_payload(f"first-{_uuid.uuid4().hex[:6]}@bootstrap.io"))
    await session.commit()
    assert first.role == "admin", "Pre-seeded viewer must not block first real user from becoming admin"


@pytest.mark.asyncio
async def test_demo_admin_seed_does_not_block_bootstrap(session):
    """The seeded demo admin (demo@openconstructionerp.com) must not block the
    first real registrant from claiming admin.

    Without this carve-out, every fresh ``pip install openconstructionerp``
    leaves the user permanently dormant: ``_seed_demo_account`` puts an
    ``admin`` row at boot, ``has_admin()`` returns True, and in the
    default ``admin-approve`` mode the next self-registered user is
    inactive with no real admin around to flip them.
    """
    import uuid as _uuid

    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from app.modules.users.service import hash_password

    demo = User(
        id=_uuid.uuid4(),
        email="demo@openconstructionerp.com",
        hashed_password=hash_password("DemoPass1234!"),
        full_name="Demo User",
        role="admin",
        locale="en",
        is_active=True,
        metadata_={},
    )
    session.add(demo)
    await session.commit()

    repo = UserRepository(session)
    assert await repo.has_admin() is False, "has_admin must ignore the seeded demo@openconstructionerp.com admin"

    first = await _service(session).register(_payload(f"first-{_uuid.uuid4().hex[:6]}@bootstrap.io"))
    await session.commit()
    assert first.role == "admin", "First real user must claim admin even when demo seed is present"
    assert first.is_active is True, "Bootstrap admin must be is_active=True regardless of registration_mode"
