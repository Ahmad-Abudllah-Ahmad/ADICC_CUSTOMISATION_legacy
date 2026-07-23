# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Seed loader for oe_i18n_foundation module.

Loads countries, work calendars, and tax configurations from JSON files.
Idempotent: checks row count before inserting. Only seeds empty tables.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.i18n_foundation.models import Country, TaxConfiguration, WorkCalendar

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parent / "seed_data"


def _load_json(filename: str) -> list[dict]:
    """Load and parse a JSON seed file from the seed_data directory."""
    path = _SEED_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _count_rows(session: AsyncSession, model: type) -> int:
    """Return the number of rows in a table."""
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


async def _seed_countries(session: AsyncSession) -> int:
    """Seed country records from countries.json.

    Returns the number of records inserted (0 if table was already populated).
    """
    count = await _count_rows(session, Country)
    if count > 0:
        logger.info("oe_i18n_country already has %d rows, skipping seed.", count)
        return 0

    data = _load_json("countries.json")
    objects = [
        Country(
            iso_code=row["iso_code"],
            iso_code_3=row.get("iso_code_3"),
            name_en=row["name_en"],
            name_translations=row["name_translations"],
            currency_default=row.get("currency_default"),
            measurement_default=row.get("measurement_default"),
            phone_code=row.get("phone_code"),
            region_group=row.get("region_group"),
            is_active=True,
            metadata_={},
        )
        for row in data
    ]
    session.add_all(objects)
    await session.flush()
    logger.info("Seeded %d countries.", len(objects))
    return len(objects)


async def _seed_work_calendars(session: AsyncSession) -> int:
    """Seed work calendar records from work_calendars.json.

    Returns the number of records inserted (0 if table was already populated).
    """
    count = await _count_rows(session, WorkCalendar)
    if count > 0:
        logger.info("oe_i18n_work_calendar already has %d rows, skipping seed.", count)
        return 0

    data = _load_json("work_calendars.json")
    objects = [
        WorkCalendar(
            country_code=row["country_code"],
            name=row["name"],
            name_translations=row.get("name_translations"),
            year=row["year"],
            work_hours_per_day=row.get("work_hours_per_day", "8"),
            work_days=row["work_days"],
            exceptions=row.get("exceptions", []),
            metadata_={},
        )
        for row in data
    ]
    session.add_all(objects)
    await session.flush()
    logger.info("Seeded %d work calendars.", len(objects))
    return len(objects)


async def _seed_tax_configurations(session: AsyncSession) -> int:
    """Seed tax configuration records from tax_configurations.json.

    Returns the number of records inserted (0 if table was already populated).
    """
    count = await _count_rows(session, TaxConfiguration)
    if count > 0:
        logger.info("oe_i18n_tax_config already has %d rows, skipping seed.", count)
        return 0

    data = _load_json("tax_configurations.json")
    objects = [
        TaxConfiguration(
            country_code=row["country_code"],
            tax_name=row["tax_name"],
            tax_name_translations=row.get("tax_name_translations"),
            tax_code=row.get("tax_code"),
            rate_pct=row["rate_pct"],
            tax_type=row["tax_type"],
            effective_from=row.get("effective_from"),
            effective_to=row.get("effective_to"),
            is_default=row.get("is_default", False),
            metadata_={},
        )
        for row in data
    ]
    session.add_all(objects)
    await session.flush()
    logger.info("Seeded %d tax configurations.", len(objects))
    return len(objects)


async def seed_i18n_data(session: AsyncSession) -> dict[str, int]:
    """Load seed data for countries, work calendars, and tax configurations.

    Idempotent -- checks count before inserting. Only inserts if tables are empty.
    Returns counts of seeded records per entity.
    """
    countries = await _seed_countries(session)
    calendars = await _seed_work_calendars(session)
    taxes = await _seed_tax_configurations(session)

    result = {"countries": countries, "calendars": calendars, "taxes": taxes}
    logger.info("i18n seed complete: %s", result)
    return result
