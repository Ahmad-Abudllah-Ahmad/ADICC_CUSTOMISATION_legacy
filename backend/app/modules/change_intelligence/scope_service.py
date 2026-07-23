# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pre-construction scope-ambiguity service - the thin database layer.

Reads a project's bill-of-quantities lines and feeds them to the pure
:mod:`app.modules.change_intelligence.scope_ambiguity` engine, which grades how
vague each line is and why. The engine owns all the scoring; this layer only
gathers rows and maps them onto :class:`ScopeLine`. Nothing is persisted, so
there is no new table and no migration.

A line that is a parent of other lines is treated as a section heading (it
carries no measure of its own) so the missing-quantity / missing-unit /
under-specified signals do not fire against a grouping row. Quantities and rates
are stored as strings on the position (SQLite-precision reasons), so they are
parsed to :class:`~decimal.Decimal` here; an unparseable or blank quantity is
passed as ``None`` and the engine reads it as missing.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import BOQ, Position
from app.modules.change_intelligence.scope_ambiguity import (
    ScopeAmbiguityReport,
    ScopeLine,
    assess,
)


def _to_decimal(value: object) -> Decimal | None:
    """Parse a stored string quantity / rate to a Decimal, or None.

    A blank, ``None`` or unparseable value becomes ``None`` (the engine reads a
    ``None`` quantity as missing); a parseable numeric string becomes its exact
    Decimal so no measure ever flows through a float.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


async def assess_project_scope(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    boq_id: uuid.UUID | None = None,
) -> ScopeAmbiguityReport:
    """Grade the scope ambiguity of a project's BOQ lines.

    Gathers every position under the project's bills of quantities (optionally a
    single bill when *boq_id* is given), maps each onto a :class:`ScopeLine`, and
    returns the pure engine's :class:`ScopeAmbiguityReport` (worst-first, with a
    per-band count, a project ambiguity index and the dominant reasons). The
    query is fenced to the project, so a ``boq_id`` from another project resolves
    to no rows and yields an empty report rather than leaking it. Read-only; the
    same project state always yields the same report.
    """
    stmt = (
        select(
            Position.id,
            Position.description,
            Position.unit,
            Position.quantity,
            Position.unit_rate,
            Position.parent_id,
        )
        .join(BOQ, Position.boq_id == BOQ.id)
        .where(BOQ.project_id == project_id)
    )
    if boq_id is not None:
        stmt = stmt.where(BOQ.id == boq_id)

    rows = (await session.execute(stmt)).all()

    # A line that is the parent of another line is a section / grouping heading:
    # it carries no measure of its own, so it is exempt from the quantity / unit
    # / under-specification signals. Collected in one pass over the same rows.
    parent_ids = {row.parent_id for row in rows if row.parent_id is not None}

    lines = [
        ScopeLine(
            line_id=str(row.id),
            description=row.description or "",
            unit=row.unit or "",
            quantity=_to_decimal(row.quantity),
            rate=_to_decimal(row.unit_rate),
            is_provisional_sum=False,
            is_heading=row.id in parent_ids,
        )
        for row in rows
    ]
    return assess(lines)
