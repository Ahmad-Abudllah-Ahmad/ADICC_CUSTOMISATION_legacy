# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Schedule data access layer.

All database queries for schedules, activities, and work orders live here.
No business logic - pure data access.
"""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.modules.schedule.models import Activity, Schedule, ScheduleRelationship, WorkOrder


class ScheduleRepository:
    """Data access for Schedule model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, schedule_id: uuid.UUID) -> Schedule | None:
        """Get schedule by ID."""
        return await self.session.get(Schedule, schedule_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Schedule], int]:
        """List schedules for a project with pagination. Returns (schedules, total_count).

        Activities are NOT loaded in list queries to avoid N+1.
        """
        base = select(Schedule).where(Schedule.project_id == project_id)

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Fetch - skip eager loading of activities for list queries
        stmt = (
            base.options(noload(Schedule.activities)).order_by(Schedule.created_at.desc()).offset(offset).limit(limit)
        )
        result = await self.session.execute(stmt)
        schedules = list(result.scalars().all())

        return schedules, total

    async def create(self, schedule: Schedule) -> Schedule:
        """Insert a new schedule."""
        self.session.add(schedule)
        await self.session.flush()
        return schedule

    async def update_fields(self, schedule_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on a schedule."""
        stmt = update(Schedule).where(Schedule.id == schedule_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        # Expire cached ORM instances so the next get_by_id re-reads from DB
        self.session.expire_all()

    async def delete(self, schedule_id: uuid.UUID) -> None:
        """Delete a schedule and all its activities (via CASCADE)."""
        stmt = delete(Schedule).where(Schedule.id == schedule_id)
        await self.session.execute(stmt)


class ActivityRepository:
    """Data access for Activity model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, activity_id: uuid.UUID) -> Activity | None:
        """Get activity by ID."""
        return await self.session.get(Activity, activity_id)

    async def list_for_schedule(
        self,
        schedule_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 1000,
    ) -> tuple[list[Activity], int]:
        """List activities for a schedule ordered by sort_order. Returns (activities, total).

        Children and work_orders are NOT loaded to avoid N+1 on list queries.
        """
        base = select(Activity).where(Activity.schedule_id == schedule_id)

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Fetch ordered by sort_order, then wbs_code - skip heavy relationships
        stmt = (
            base.options(
                noload(Activity.children),
                noload(Activity.work_orders),
            )
            .order_by(Activity.sort_order, Activity.wbs_code)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        activities = list(result.scalars().all())

        return activities, total

    async def create(self, activity: Activity) -> Activity:
        """Insert a new activity."""
        self.session.add(activity)
        await self.session.flush()
        return activity

    async def update_fields(self, activity_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on an activity."""
        stmt = update(Activity).where(Activity.id == activity_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        # Expire cached ORM instances so the next get_by_id re-reads from DB
        self.session.expire_all()

    async def update_fields_if_revision(self, activity_id: uuid.UUID, expected_revision: int, **fields: object) -> bool:
        """Compare-and-swap update for the optimistic-concurrency guard.

        Sets ``fields`` only if the row's ``revision`` still equals
        ``expected_revision``, in a single atomic ``UPDATE ... WHERE id AND
        revision`` so two concurrent writers on the same base cannot both
        succeed. Returns ``True`` when a row was updated, ``False`` when it was
        changed concurrently (rowcount 0) so the caller can surface a 409
        instead of silently overwriting the other write (lost update).
        """
        stmt = (
            update(Activity).where(Activity.id == activity_id, Activity.revision == expected_revision).values(**fields)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        # Expire cached ORM instances so the next get_by_id re-reads from DB
        self.session.expire_all()
        return bool(result.rowcount and result.rowcount > 0)

    async def bulk_update_fields(self, updates: list[dict[str, object]]) -> None:
        """Update many activities in a single round trip.

        Each entry in ``updates`` must carry the primary key under ``"id"``
        plus the columns to set, e.g.
        ``{"id": <uuid>, "color": "#ef4444", "metadata_": {...}}``. Uses
        SQLAlchemy's ORM-enabled bulk UPDATE by primary key (executemany under
        the hood), which collapses what would otherwise be N separate UPDATE
        statements - and N ``expire_all()`` calls when looping over
        :meth:`update_fields` - into one statement and a single cache
        invalidation. Behaviour matches calling :meth:`update_fields` once per
        row. No-op when ``updates`` is empty.
        """
        if not updates:
            return
        await self.session.execute(update(Activity), updates)
        await self.session.flush()
        # Expire cached ORM instances once so the next get_by_id re-reads from DB
        self.session.expire_all()

    async def delete(self, activity_id: uuid.UUID) -> None:
        """Delete an activity."""
        stmt = delete(Activity).where(Activity.id == activity_id)
        await self.session.execute(stmt)

    async def delete_for_schedule(self, schedule_id: uuid.UUID) -> int:
        """Delete all activities of a schedule in a single statement.

        Returns the number of activities removed. Dependent work orders are
        removed via the ON DELETE CASCADE FK on WorkOrder.activity_id.
        """
        count_stmt = select(func.count()).select_from(
            select(Activity).where(Activity.schedule_id == schedule_id).subquery()
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = delete(Activity).where(Activity.schedule_id == schedule_id)
        await self.session.execute(stmt)
        return int(total)

    async def get_max_sort_order(self, schedule_id: uuid.UUID) -> int:
        """Get the highest sort_order for activities in a schedule."""
        stmt = select(func.coalesce(func.max(Activity.sort_order), -1)).where(Activity.schedule_id == schedule_id)
        result = (await self.session.execute(stmt)).scalar_one()
        return int(result)

    async def get_max_activity_code_seq(self, schedule_id: uuid.UUID) -> int:
        """Get the highest numeric suffix from ACT-NNN activity codes in a schedule.

        Returns 0 if no activity codes exist yet.
        """
        stmt = (
            select(Activity.activity_code)
            .where(Activity.schedule_id == schedule_id)
            .where(Activity.activity_code.isnot(None))
        )
        result = await self.session.execute(stmt)
        codes = [row[0] for row in result.all() if row[0]]

        max_seq = 0
        for code in codes:
            # Parse ACT-NNN pattern
            if code and code.startswith("ACT-"):
                try:
                    seq = int(code[4:])
                    max_seq = max(max_seq, seq)
                except (ValueError, IndexError):
                    pass
        return max_seq


class WorkOrderRepository:
    """Data access for WorkOrder model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, work_order_id: uuid.UUID) -> WorkOrder | None:
        """Get work order by ID."""
        return await self.session.get(WorkOrder, work_order_id)

    async def list_for_activity(
        self,
        activity_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[WorkOrder], int]:
        """List work orders for an activity. Returns (work_orders, total_count)."""
        base = select(WorkOrder).where(WorkOrder.activity_id == activity_id)

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Fetch
        stmt = base.order_by(WorkOrder.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        work_orders = list(result.scalars().all())

        return work_orders, total

    async def list_for_schedule(
        self,
        schedule_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 500,
    ) -> tuple[list[WorkOrder], int]:
        """List work orders for all activities in a schedule.

        Joins through Activity to filter by schedule_id.
        Returns (work_orders, total_count).
        """
        base = (
            select(WorkOrder)
            .join(Activity, WorkOrder.activity_id == Activity.id)
            .where(Activity.schedule_id == schedule_id)
        )

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Fetch
        stmt = base.order_by(WorkOrder.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        work_orders = list(result.scalars().all())

        return work_orders, total

    async def create(self, work_order: WorkOrder) -> WorkOrder:
        """Insert a new work order."""
        self.session.add(work_order)
        await self.session.flush()
        return work_order

    async def update_fields(self, work_order_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on a work order."""
        stmt = update(WorkOrder).where(WorkOrder.id == work_order_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        # Expire cached ORM instances so the next get_by_id re-reads from DB
        self.session.expire_all()

    async def delete(self, work_order_id: uuid.UUID) -> None:
        """Delete a work order."""
        stmt = delete(WorkOrder).where(WorkOrder.id == work_order_id)
        await self.session.execute(stmt)


class RelationshipRepository:
    """Data access for :class:`ScheduleRelationship` - the canonical edge store.

    :class:`ScheduleRelationship` is the single source of truth for schedule
    dependency edges. Activity-embedded ``dependencies`` JSON is a derived
    mirror that the service rebuilds from these rows. All reads and writes of
    the canonical edge set go through this layer so the projection / CPM /
    completion-guard paths share one query surface.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_schedule(self, schedule_id: uuid.UUID) -> list[ScheduleRelationship]:
        """Return every relationship row of a schedule (unbounded - CPM needs all)."""
        stmt = select(ScheduleRelationship).where(ScheduleRelationship.schedule_id == schedule_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_predecessors(self, successor_id: uuid.UUID) -> list[ScheduleRelationship]:
        """Return all relationship rows whose successor is ``successor_id``.

        These are the inbound predecessor edges of a single activity - used by
        the completion guard and the derived-JSON mirror rebuild.
        """
        stmt = select(ScheduleRelationship).where(ScheduleRelationship.successor_id == successor_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, relationship: ScheduleRelationship) -> ScheduleRelationship:
        """Insert a new relationship row."""
        self.session.add(relationship)
        await self.session.flush()
        return relationship

    async def delete_by_id(self, relationship_id: uuid.UUID) -> None:
        """Delete a single relationship by primary key."""
        stmt = delete(ScheduleRelationship).where(ScheduleRelationship.id == relationship_id)
        await self.session.execute(stmt)

    async def delete_edges(
        self,
        successor_id: uuid.UUID,
        predecessor_ids: list[uuid.UUID],
    ) -> None:
        """Delete the inbound edges of ``successor_id`` for the given predecessors.

        No-op when ``predecessor_ids`` is empty.
        """
        if not predecessor_ids:
            return
        stmt = delete(ScheduleRelationship).where(
            ScheduleRelationship.successor_id == successor_id,
            ScheduleRelationship.predecessor_id.in_(predecessor_ids),
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_edge(
        self,
        relationship_id: uuid.UUID,
        *,
        relationship_type: str,
        lag_days: int,
    ) -> None:
        """Update the type / lag of an existing relationship row."""
        stmt = (
            update(ScheduleRelationship)
            .where(ScheduleRelationship.id == relationship_id)
            .values(relationship_type=relationship_type, lag_days=lag_days)
        )
        await self.session.execute(stmt)
        await self.session.flush()
