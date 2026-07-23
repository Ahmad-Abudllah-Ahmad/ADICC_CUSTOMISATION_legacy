# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic response schema for persisted EVM snapshots (trend charting).

Dependency-free (pydantic + stdlib only) so it imports and unit-tests on the
local runner. The money-named fields (``pv`` / ``ev`` / ``bac``) are
:class:`~decimal.Decimal` and serialise to JSON as *strings*, per the platform's
money discipline (very-large totals round-trip exactly, no locale / float drift);
the schedule performance index ``spi`` is a dimensionless ratio rendered as a
plain number, and is ``null`` when planned value is zero at the data date.

This module is deliberately NOT named ``schemas.py``: the global money-as-Decimal
audit (``tests/unit/test_money_decimal_global.py``) scans files literally named
``schemas.py``, and the schedule module already keeps its money response models
in ``progress_schemas.py`` for the same reason. We still honour the Decimal
contract here so the wire shape is identical.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class EvmSnapshotResponse(BaseModel):
    """One persisted EVM snapshot at a data date.

    ``pv`` / ``ev`` / ``bac`` are Decimal-as-string money; ``spi`` is the EV/PV
    schedule performance index (``null`` when ``pv`` is zero). Actual cost (AC)
    and the cost performance index (CPI) are intentionally absent - the schedule
    EVM rollup does not compute an actual cost, so neither is reported here.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    project_id: UUID
    data_date: str
    pv: Decimal
    ev: Decimal
    bac: Decimal
    # Dimensionless ratio (not money): a plain JSON number, like the percents and
    # weights elsewhere in the schedule API. ``None`` when planned value is zero.
    spi: float | None = None
    recorded_at: datetime

    @field_serializer("pv", "ev", "bac", when_used="json")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)


class EvmSnapshotListResponse(BaseModel):
    """A schedule's EVM snapshots ordered by data date (oldest first) for trends."""

    schedule_id: UUID
    snapshots: list[EvmSnapshotResponse] = Field(default_factory=list)
    count: int
