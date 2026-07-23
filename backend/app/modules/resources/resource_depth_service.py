# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resource-depth service (T3.1).

Effective-dated rate CRUD, per-assignment spreading curves, the native-units
demand setter, and the time-phased demand/availability/cost histogram. All the
arithmetic lives in the pure :mod:`app.modules.resources.resource_engine`; this
layer only loads rows, applies access scoping, and shapes the response.

Reads intersect a caller's ``accessible_project_ids`` so a shared resource never
leaks another tenant's bookings. Writes ``flush`` only; the request middleware
owns the commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import accessible_project_ids
from app.modules.resources.models import Assignment
from app.modules.resources.resource_depth_models import AssignmentCurve, ResourceRate
from app.modules.resources.resource_depth_schemas import (
    AssignmentUnitsPatch,
    CurveUpsert,
    RateCreate,
    RatePatch,
)
from app.modules.resources.resource_engine import (
    Curve,
    HistogramAssignment,
    RateRow,
    resource_histogram,
)
from app.modules.resources.service import (
    ResourcesService,
    _as_aware,
    _build_capacity_buckets,
    _intervals_overlap,
)

#: Assignment states that consume capacity (mirrors the leveling service).
_ACTIVE_STATES: frozenset[str] = frozenset({"proposed", "confirmed", "in_progress"})
#: Availability-window kinds that zero out a bucket's capacity.
_BLOCKING_WINDOWS: frozenset[str] = frozenset({"unavailable", "holiday", "sick"})


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ResourceDepthService:
    """Rates, curves, native units, and the time-phased histogram."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.base = ResourcesService(session)

    # ── Rates ────────────────────────────────────────────────────────────────

    async def list_rates(self, resource_id: uuid.UUID) -> list[ResourceRate]:
        await self.base.get_resource(resource_id)  # 404 if the resource is gone
        rows = (
            (
                await self.session.execute(
                    select(ResourceRate)
                    .where(ResourceRate.resource_id == resource_id)
                    .order_by(ResourceRate.rate_type, ResourceRate.effective_from),
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get_rate(self, rate_id: uuid.UUID) -> ResourceRate:
        rate = await self.session.get(ResourceRate, rate_id)
        if rate is None:
            raise _not_found("Rate not found")
        return rate

    async def create_rate(self, data: RateCreate) -> ResourceRate:
        await self.base.get_resource(data.resource_id)  # 404 if the resource is gone
        if data.effective_to is not None and data.effective_to <= data.effective_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="effective_to must be after effective_from",
            )
        rate = ResourceRate(
            resource_id=data.resource_id,
            rate=data.rate,
            rate_type=data.rate_type,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            currency=data.currency,
        )
        self.session.add(rate)
        await self.session.flush()
        return rate

    async def patch_rate(self, rate_id: uuid.UUID, data: RatePatch) -> ResourceRate:
        rate = await self.get_rate(rate_id)
        fields = data.model_dump(exclude_unset=True)
        for key, value in fields.items():
            setattr(rate, key, value)
        eff_from = rate.effective_from
        eff_to = rate.effective_to
        if eff_to is not None and eff_to <= eff_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="effective_to must be after effective_from",
            )
        await self.session.flush()
        return rate

    async def delete_rate(self, rate_id: uuid.UUID) -> None:
        rate = await self.get_rate(rate_id)
        await self.session.delete(rate)
        await self.session.flush()

    # ── Curves ───────────────────────────────────────────────────────────────

    async def get_curve(self, assignment_id: uuid.UUID) -> AssignmentCurve | None:
        return (
            await self.session.execute(
                select(AssignmentCurve).where(AssignmentCurve.assignment_id == assignment_id),
            )
        ).scalar_one_or_none()

    async def upsert_curve(self, assignment_id: uuid.UUID, data: CurveUpsert) -> AssignmentCurve:
        await self.base.get_assignment(assignment_id)  # 404 if the assignment is gone
        weights = [float(w) for w in data.manual_weights]
        curve = await self.get_curve(assignment_id)
        if curve is None:
            curve = AssignmentCurve(
                assignment_id=assignment_id,
                curve_type=data.curve_type,
                manual_weights=weights,
            )
            self.session.add(curve)
        else:
            curve.curve_type = data.curve_type
            curve.manual_weights = weights
        await self.session.flush()
        return curve

    async def delete_curve(self, assignment_id: uuid.UUID) -> None:
        await self.session.execute(
            sa_delete(AssignmentCurve).where(AssignmentCurve.assignment_id == assignment_id),
        )
        await self.session.flush()

    # ── Native units ─────────────────────────────────────────────────────────

    async def set_units(self, assignment_id: uuid.UUID, data: AssignmentUnitsPatch) -> Assignment:
        assignment = await self.base.get_assignment(assignment_id)
        fields = data.model_dump(exclude_unset=True)
        if "units" in fields:
            assignment.units = fields["units"]
        if "unit_kind" in fields and fields["unit_kind"] is not None:
            assignment.unit_kind = fields["unit_kind"]
        await self.session.flush()
        return assignment

    # ── Time-phased histogram ────────────────────────────────────────────────

    async def histogram(
        self,
        resource_id: uuid.UUID,
        start: datetime,
        end: datetime,
        user_id: str,
        *,
        bucket: str = "week",
        rate_type: str = "cost",
        hours_per_day: float = 8.0,
    ) -> dict:
        """Build a resource's time-phased demand / availability / cost histogram.

        Demand per bucket is each overlapping assignment's ``units`` (falling
        back to its percent allocation) spread by its curve; the cost lane prices
        that demand at the effective-dated rate in force at the bucket. Bookings
        for projects the caller cannot reach are dropped (tenant isolation), and
        a bucket covered by an unavailable / holiday / sick window has zero
        availability.
        """
        resource = await self.base.get_resource(resource_id)  # 404 if missing
        start = _as_aware(start)
        end = _as_aware(end)
        bucket = bucket if bucket in ("week", "month") else "week"
        buckets = _build_capacity_buckets(start, end, bucket)
        capacity_units = float(resource.capacity_percent) if resource.capacity_percent is not None else None
        if not buckets:
            return {
                "resource_id": resource_id,
                "bucket": bucket,
                "capacity_units": capacity_units,
                "peak_demand": 0.0,
                "over_allocated_buckets": 0,
                "cells": [],
            }
        window_start, window_end = buckets[0][1], buckets[-1][2]

        # Bookings overlapping the window, scoped to what the caller may see.
        scope = await accessible_project_ids(self.session, user_id)
        assignments = (
            (
                await self.session.execute(
                    select(Assignment).where(
                        Assignment.resource_id == resource_id,
                        Assignment.start_at < window_end,
                        Assignment.end_at > window_start,
                    ),
                )
            )
            .scalars()
            .all()
        )
        visible = [
            a
            for a in assignments
            if a.status in _ACTIVE_STATES and (scope is None or a.project_id is None or a.project_id in scope)
        ]

        curve_by_aid = await self._curves_for([a.id for a in visible])
        rate_rows = [
            RateRow(
                rate=r.rate,
                rate_type=r.rate_type,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                currency=r.currency,
            )
            for r in await self.list_rates(resource_id)
        ]

        # Buckets fully covered by a blocking availability window lose capacity.
        windows = await self.base.list_windows(resource_id, start_at=window_start, end_at=window_end)
        blocking = [w for w in windows if w.window_type in _BLOCKING_WINDOWS]
        blocked_idx = [
            bi
            for (bi, b_start, b_end, _label) in buckets
            if any(_intervals_overlap(_as_aware(w.start_at), _as_aware(w.end_at), b_start, b_end) for w in blocking)
        ]

        hist_assignments = []
        for a in visible:
            curve = curve_by_aid.get(a.id)
            units = float(a.units) if a.units is not None else float(a.allocation_percent or 0)
            cost_rate = a.cost_rate if a.cost_rate else resource.default_cost_rate
            hist_assignments.append(
                HistogramAssignment(
                    assignment_id=a.id,
                    project_id=a.project_id,
                    start=_as_aware(a.start_at),
                    end=_as_aware(a.end_at),
                    units=units,
                    cost_rate=cost_rate,
                    curve=Curve(curve_type=curve.curve_type, manual_weights=tuple(curve.manual_weights or ()))
                    if curve is not None
                    else None,
                    unit_kind=a.unit_kind or "labor",
                )
            )

        cells = resource_histogram(
            hist_assignments,
            buckets,
            capacity_units=capacity_units,
            rate_rows=rate_rows,
            blocked_bucket_indices=blocked_idx,
            hours_per_day=hours_per_day,
            rate_type=rate_type,
        )

        bucket_meta = {bi: (b_start, b_end, label) for (bi, b_start, b_end, label) in buckets}
        out_cells = []
        peak = 0.0
        over_buckets = 0
        for cell in cells:
            b_start, b_end, label = bucket_meta[cell.bucket_index]
            peak = max(peak, cell.demand_units)
            if cell.over_allocated:
                over_buckets += 1
            out_cells.append(
                {
                    "bucket_index": cell.bucket_index,
                    "start": b_start,
                    "end": b_end,
                    "label": label,
                    "demand_units": cell.demand_units,
                    "demand_cost": cell.demand_cost,
                    "available": cell.available,
                    "capacity_unknown": cell.capacity_unknown,
                    "over_allocated": cell.over_allocated,
                    "bookings": cell.bookings,
                }
            )

        return {
            "resource_id": resource_id,
            "bucket": bucket,
            "capacity_units": capacity_units,
            "peak_demand": peak,
            "over_allocated_buckets": over_buckets,
            "cells": out_cells,
        }

    async def _curves_for(self, assignment_ids: list[uuid.UUID]) -> dict[uuid.UUID, AssignmentCurve]:
        if not assignment_ids:
            return {}
        rows = (
            (
                await self.session.execute(
                    select(AssignmentCurve).where(AssignmentCurve.assignment_id.in_(assignment_ids)),
                )
            )
            .scalars()
            .all()
        )
        return {c.assignment_id: c for c in rows}
