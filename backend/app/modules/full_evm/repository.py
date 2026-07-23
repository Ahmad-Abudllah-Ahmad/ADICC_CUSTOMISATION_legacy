# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Full EVM data access layer.

All database queries for EVM forecast entities live here.
No business logic - pure data access.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.full_evm.models import EVMForecast


class EVMForecastRepository:
    """Data access for EVMForecast model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, forecast_id: uuid.UUID) -> EVMForecast | None:
        """Get forecast by ID."""
        return await self.session.get(EVMForecast, forecast_id)

    async def list(
        self,
        *,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EVMForecast], int]:
        """List forecasts with optional project filter."""
        base = select(EVMForecast)
        if project_id is not None:
            base = base.where(EVMForecast.project_id == project_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = base.order_by(EVMForecast.forecast_date.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_latest(self, project_id: uuid.UUID) -> EVMForecast | None:
        """Return the most recent forecast for a project, or None.

        Ordered by ``forecast_date`` (an ISO ``YYYY-MM-DD`` string, so
        lexical order == chronological order) then by ``created_at`` as a
        tie-break when several forecasts share the same date.
        """
        stmt = (
            select(EVMForecast)
            .where(EVMForecast.project_id == project_id)
            .order_by(EVMForecast.forecast_date.desc(), EVMForecast.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_active_alerts(self, project_id: uuid.UUID) -> list[EVMForecast]:  # noqa: A003
        """Return forecasts whose alert is still actionable for a project.

        "Active" means ``alert_status`` is ``triggered`` or ``snoozed`` -
        ``acknowledged`` rows are resolved and ``NULL`` rows never alerted.
        Snoozed rows are included so the UI can show a countdown; the
        router decides whether a snooze has lapsed.
        """
        stmt = (
            select(EVMForecast)
            .where(EVMForecast.project_id == project_id)
            .where(EVMForecast.alert_status.in_(("triggered", "snoozed")))
            .order_by(EVMForecast.triggered_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, forecast: EVMForecast) -> EVMForecast:
        """Insert a new EVM forecast."""
        self.session.add(forecast)
        await self.session.flush()
        return forecast
