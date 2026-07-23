# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""EVM-snapshot service.

Persists a frozen rollup of the schedule's existing time-phased earned-value
figures (PV / EV / BAC, plus the derived EV/PV schedule performance index) when
the data date advances, so the performance trend can be charted over time.

The figures are NOT recomputed here with new cost math - they are taken verbatim
from :meth:`ScheduleProgressService.planned_value_preview`, the same computation
the read-only PV/EV preview already serves. The only derived value is the SPI,
produced by the pure :func:`evm_snapshot_math.schedule_performance_index` (with a
divide-by-zero guard). Actual cost (AC) and the cost performance index (CPI) are
intentionally not persisted: the schedule EVM rollup never computes an AC.

All writes ``flush`` only; the request middleware owns the commit, matching every
other schedule service. The recording hook is safe by construction - the producer
wraps it so a snapshot failure never breaks the progress / data-date write.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.schedule.evm_snapshot_math import schedule_performance_index
from app.modules.schedule.evm_snapshot_models import ScheduleEvmSnapshot
from app.modules.schedule.progress_service import ScheduleProgressService

logger = logging.getLogger(__name__)


class ScheduleEvmSnapshotService:
    """Record and list a schedule's EVM snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.progress = ScheduleProgressService(session)

    async def record_snapshot(
        self,
        schedule_id: uuid.UUID,
        data_date: str,
    ) -> ScheduleEvmSnapshot:
        """Compute and persist the EVM rollup for *schedule_id* at *data_date*.

        Reuses the existing time-phased PV/EV/BAC computation, derives the EV/PV
        schedule performance index, and upserts the single row keyed by
        ``(schedule_id, data_date)`` - re-recording at the same data date
        replaces that row rather than duplicating the trend point. ``flush`` only.
        """
        schedule = await self.progress.get_schedule(schedule_id)

        # Source of truth: the schedule's own time-phased earned-value figures.
        preview = await self.progress.planned_value_preview(schedule_id, data_date)
        pv = preview["planned_value"]
        ev = preview["earned_value"]
        bac = preview["budget_at_completion"]
        spi = schedule_performance_index(ev, pv)

        existing = await self._get_for_data_date(schedule_id, data_date)
        if existing is not None:
            existing.project_id = schedule.project_id
            existing.pv = pv
            existing.ev = ev
            existing.bac = bac
            existing.spi = spi
            await self.session.flush()
            return existing

        snapshot = ScheduleEvmSnapshot(
            schedule_id=schedule_id,
            project_id=schedule.project_id,
            data_date=data_date,
            pv=pv,
            ev=ev,
            bac=bac,
            spi=spi,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def record_snapshot_safe(
        self,
        schedule_id: uuid.UUID,
        data_date: str | None,
    ) -> ScheduleEvmSnapshot | None:
        """Best-effort snapshot for the data-date-advance hook.

        Never raises and never poisons the outer transaction: a missing data
        date is a no-op, and the write runs inside a SAVEPOINT
        (``begin_nested``) so a failure rolls back only the snapshot and is
        logged + swallowed, leaving the triggering progress / schedule write
        intact (the same per-item isolation other modules use). Returns the
        snapshot when one was recorded, else ``None``.
        """
        if not data_date:
            return None
        try:
            async with self.session.begin_nested():
                return await self.record_snapshot(schedule_id, data_date)
        except Exception:  # noqa: BLE001 - snapshotting must not break the write
            logger.warning(
                "EVM snapshot skipped for schedule=%s data_date=%s",
                schedule_id,
                data_date,
                exc_info=True,
            )
            return None

    async def list_snapshots(self, schedule_id: uuid.UUID) -> list[ScheduleEvmSnapshot]:
        """All snapshots for a schedule ordered by data date (oldest first).

        Raises 404 (via the loader) when the schedule is missing or not visible.
        """
        await self.progress.get_schedule(schedule_id)  # 404 if gone
        stmt = (
            select(ScheduleEvmSnapshot)
            .where(ScheduleEvmSnapshot.schedule_id == schedule_id)
            .order_by(ScheduleEvmSnapshot.data_date, ScheduleEvmSnapshot.recorded_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_for_data_date(
        self,
        schedule_id: uuid.UUID,
        data_date: str,
    ) -> ScheduleEvmSnapshot | None:
        stmt = select(ScheduleEvmSnapshot).where(
            ScheduleEvmSnapshot.schedule_id == schedule_id,
            ScheduleEvmSnapshot.data_date == data_date,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
