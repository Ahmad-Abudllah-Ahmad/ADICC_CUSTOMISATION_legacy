# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Retrieval service: gather project records and rank them with the facet engine.

The ranking + filtering logic is the pure, IO-free
:mod:`app.modules.retrieval.facet_query`. This service only supplies the IO:
it reads candidate records from the modules that hold the dispute-relevant
record (documents, correspondence and change orders), maps each row to a
:class:`~app.modules.retrieval.facet_query.RetrievableRecord`, then hands the
set to :func:`run_query`. Everything stays scoped to one project.

Reads are bounded per source so a huge project cannot pull an unbounded set
into memory; the cap is logged-friendly and intentionally generous for v1.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.changeorders.models import ChangeOrder
from app.modules.correspondence.models import Correspondence
from app.modules.documents.models import Document
from app.modules.retrieval.facet_query import FacetQuery, RankedResult, RetrievableRecord, run_query

#: Per-source row cap so a single source cannot dominate memory for v1.
SOURCE_LIMIT = 500

#: Every record starts from this neutral relevance; a production wiring can
#: layer a vector-adapter score in here, but the facet filter + rank stand
#: alone and deterministically without it.
BASE_SCORE = 0.5


def _iso(value: object) -> str:
    """Best-effort ISO string for a datetime / string / None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


def _clean_refs(*values: object) -> tuple[str, ...]:
    """Keep only non-empty string refs, de-duplicated, order preserved."""
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value not in out:
            out.append(value.strip())
    return tuple(out)


class RetrievalService:
    """Gather project records from several modules and rank them by facets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _documents(self, project_id: uuid.UUID) -> list[RetrievableRecord]:
        stmt = (
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
            .limit(SOURCE_LIMIT)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            RetrievableRecord(
                record_type="document",
                record_id=str(row.id),
                title=row.name or "",
                body=row.description or "",
                source_module="documents",
                party=row.uploaded_by or "",
                occurred_at=_iso(row.created_at),
                entity_refs=_clean_refs(row.category, getattr(row, "drawing_number", "")),
                base_score=BASE_SCORE,
            )
            for row in rows
        ]

    async def _correspondence(self, project_id: uuid.UUID) -> list[RetrievableRecord]:
        stmt = (
            select(Correspondence)
            .where(Correspondence.project_id == project_id)
            .order_by(Correspondence.created_at.desc())
            .limit(SOURCE_LIMIT)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            RetrievableRecord(
                record_type="correspondence",
                record_id=str(row.id),
                title=row.subject or "",
                body=row.notes or "",
                source_module="correspondence",
                party=row.from_contact_id or "",
                occurred_at=row.date_sent or row.date_received or _iso(row.created_at),
                entity_refs=_clean_refs(row.reference_number, row.linked_rfi_id),
                base_score=BASE_SCORE,
            )
            for row in rows
        ]

    async def _change_orders(self, project_id: uuid.UUID) -> list[RetrievableRecord]:
        stmt = (
            select(ChangeOrder)
            .where(ChangeOrder.project_id == project_id)
            .order_by(ChangeOrder.created_at.desc())
            .limit(SOURCE_LIMIT)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            RetrievableRecord(
                record_type="change_order",
                record_id=str(row.id),
                title=row.title or "",
                body=row.description or "",
                source_module="changeorders",
                party=row.ball_in_court or "",
                occurred_at=_iso(row.created_at),
                entity_refs=_clean_refs(row.code),
                base_score=BASE_SCORE,
            )
            for row in rows
        ]

    async def gather(self, project_id: uuid.UUID) -> list[RetrievableRecord]:
        """Collect candidate records from every wired source for a project."""
        records: list[RetrievableRecord] = []
        records.extend(await self._documents(project_id))
        records.extend(await self._correspondence(project_id))
        records.extend(await self._change_orders(project_id))
        return records

    async def search(
        self,
        project_id: uuid.UUID,
        query: FacetQuery,
        *,
        as_of: str = "",
    ) -> list[RankedResult]:
        """Gather the project's records and rank them against ``query``."""
        records = await self.gather(project_id)
        return list(run_query(records, query, as_of=as_of))
