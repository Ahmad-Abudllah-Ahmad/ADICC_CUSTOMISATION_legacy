# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Submittals data access layer."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.submittals.models import Submittal


class SubmittalRepository:
    """Data access for Submittal models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, submittal_id: uuid.UUID) -> Submittal | None:
        return await self.session.get(Submittal, submittal_id)

    async def count_for_project(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        submittal_type: str | None = None,
    ) -> int:
        """Single-query count - used by list responses to avoid N+1."""
        base = (
            select(func.count())
            .select_from(Submittal)
            .where(
                Submittal.project_id == project_id,
            )
        )
        if status is not None:
            base = base.where(Submittal.status == status)
        if submittal_type is not None:
            base = base.where(Submittal.submittal_type == submittal_type)
        return (await self.session.execute(base)).scalar_one()

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        submittal_type: str | None = None,
    ) -> tuple[list[Submittal], int]:
        base = select(Submittal).where(Submittal.project_id == project_id)
        if status is not None:
            base = base.where(Submittal.status == status)
        if submittal_type is not None:
            base = base.where(Submittal.submittal_type == submittal_type)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = base.order_by(Submittal.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def next_submittal_number(self, project_id: uuid.UUID) -> str:
        """Generate the next submittal number using MAX to avoid duplicates.

        Numbers are server-generated as ``SUB-%03d`` (the ``SUB-`` prefix is
        4 chars, so the numeric ordinal begins at index 4 of the string).

        Dialect-safety: the previous implementation pushed
        ``CAST(substr(number, 5) AS INTEGER)`` into SQL. That diverges by
        backend - SQLite is lenient (``CAST('001-A' AS INTEGER)`` -> 1), but
        embedded PostgreSQL raises ``invalid input syntax for type integer``
        and 500s the whole create path for any row whose suffix is not a clean
        integer (e.g. a legacy import / seed / migrated row like ``SUBM-1`` or
        ``SUB-001-R2``). We instead select the existing numbers for the project
        and compute the max ordinal in Python, parsing the trailing digits
        defensively and skipping anything non-numeric. This is identical on
        every backend and never feeds a non-numeric string to a SQL cast. The
        candidate set is scoped to a single project so the read stays small.
        """
        stmt = select(Submittal.submittal_number).where(Submittal.project_id == project_id)
        numbers = (await self.session.execute(stmt)).scalars().all()

        max_num = 0
        for number in numbers:
            if not number:
                continue
            # Take the trailing run of digits (handles ``SUB-007`` and tolerates
            # legacy variants like ``SUB-007-R2`` by reading the leading numeric
            # part of the suffix); ignore rows with no numeric ordinal at all.
            suffix = number.rsplit("-", 1)[-1]
            digits = ""
            for ch in suffix:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                max_num = max(max_num, int(digits))

        return f"SUB-{max_num + 1:03d}"

    async def create(self, submittal: Submittal) -> Submittal:
        """Persist a new submittal.

        Raises :class:`sqlalchemy.exc.IntegrityError` on unique-constraint
        collision - the service layer retries with a fresh submittal
        number when this happens (concurrent create race).
        """
        self.session.add(submittal)
        try:
            await self.session.flush()
        except IntegrityError:
            # Rollback only the savepoint of this flush so the surrounding
            # transaction stays alive for the service-layer retry. The
            # caller decides whether to re-issue with a new number or to
            # surface the error as HTTP 409.
            await self.session.rollback()
            raise
        return submittal

    async def update_fields(self, submittal_id: uuid.UUID, **fields: object) -> None:
        stmt = update(Submittal).where(Submittal.id == submittal_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        # Targeted expire: only the row we just touched needs to be
        # re-read. ``session.expire_all()`` previously invalidated every
        # cached attribute on every loaded object (including unrelated
        # rows in long-lived sessions) which forced lazy reloads under
        # async context and risked MissingGreenlet downstream.
        sub = await self.session.get(Submittal, submittal_id)
        if sub is not None:
            self.session.expire(sub)

    async def delete(self, submittal_id: uuid.UUID) -> None:
        submittal = await self.get_by_id(submittal_id)
        if submittal is not None:
            await self.session.delete(submittal)
            await self.session.flush()
