# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Deterministic demo seed for the Price Index module.

Loads one generic construction cost index series with a handful of periods and
a few regional factors so the page is never empty on a fresh install. The seed
is idempotent: it keys on the series name and on each region code, so re-running
it never duplicates a row. Only generic vocabulary is used - no named published
index.

Usage:
    >>> from app.modules.price_index.seed import seed_price_index_demo
    >>> await seed_price_index_demo(session)
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.price_index.models import (
    CostIndexPoint,
    CostIndexSeries,
    LocationFactor,
)

_DEMO_SERIES_NAME = "Demo Construction Cost Index"

# A gently rising generic index normalised to 1.0 at the base period, standing
# in for real construction cost inflation across recent years.
_DEMO_POINTS: tuple[tuple[str, str], ...] = (
    ("2019-01", "1.000000"),
    ("2021-01", "1.085000"),
    ("2023-01", "1.240000"),
    ("2025-01", "1.355000"),
    ("2026-01", "1.400000"),
)

# Generic regional factors relative to a national baseline of 1.0.
_DEMO_REGIONS: tuple[tuple[str, str, str], ...] = (
    ("NATIONAL_AVG", "National average", "1.000000"),
    ("HIGH_COST_METRO", "High-cost metro area", "1.150000"),
    ("LOW_COST_RURAL", "Low-cost rural area", "0.900000"),
)


async def seed_price_index_demo(session: AsyncSession) -> dict[str, int]:
    """Insert the demo series and regional factors if they are absent.

    Args:
        session: An open async session; the caller owns the transaction.

    Returns:
        Counts of the rows this call actually inserted.
    """
    series_added = 0
    points_added = 0

    existing_series = (
        await session.execute(select(CostIndexSeries).where(CostIndexSeries.name == _DEMO_SERIES_NAME))
    ).scalar_one_or_none()

    if existing_series is None:
        series = CostIndexSeries(
            name=_DEMO_SERIES_NAME,
            description="Sample index series for trying out period-to-period cost escalation.",
        )
        session.add(series)
        await session.flush()
        series_added = 1
        for period, factor in _DEMO_POINTS:
            session.add(CostIndexPoint(series_id=series.id, period=period, factor=Decimal(factor)))
            points_added += 1
        await session.flush()

    existing_regions = set((await session.execute(select(LocationFactor.region_code))).scalars().all())
    regions_added = 0
    for region_code, label, factor in _DEMO_REGIONS:
        if region_code in existing_regions:
            continue
        session.add(LocationFactor(region_code=region_code, label=label, factor=Decimal(factor)))
        regions_added += 1
    if regions_added:
        await session.flush()

    return {
        "series": series_added,
        "points": points_added,
        "location_factors": regions_added,
    }
