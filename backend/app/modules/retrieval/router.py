# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Retrieval API routes (mounted at ``/api/v1/retrieval`` by the loader).

* ``GET /search`` - faceted, ranked search across the project record
  (documents, correspondence, change orders), with provenance on each hit.

Read-only and project-scoped: the caller must have access to the project.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.retrieval.facet_query import FacetQuery
from app.modules.retrieval.schemas import RetrievalResponse, RetrievalResultOut
from app.modules.retrieval.service import RetrievalService

router = APIRouter(tags=["retrieval"])

#: Body text shown on a result card is truncated to keep payloads lean.
_SNIPPET_LEN = 280


def _one(value: str) -> frozenset[str]:
    """A single-value facet set, or empty when the value is blank."""
    return frozenset([value.strip()]) if value and value.strip() else frozenset()


@router.get("/search", response_model=RetrievalResponse)
async def search_records(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(..., description="Project to search within"),
    text: str = Query("", description="Free-text terms"),
    party: str = Query("", description="Filter to a party"),
    date_from: str = Query("", description="ISO date lower bound (inclusive)"),
    date_to: str = Query("", description="ISO date upper bound (inclusive)"),
    entity: str = Query("", description="Filter to records referencing this entity"),
    record_type: str = Query("", description="Filter to one record type"),
    as_of: str = Query("", description="Reference date for recency weighting"),
) -> RetrievalResponse:
    """Rank the project's records against the supplied facets, newest-best-first."""
    await verify_project_access(project_id, user_id, session)
    query = FacetQuery(
        text=text,
        parties=_one(party),
        date_from=date_from,
        date_to=date_to,
        entity_refs=_one(entity),
        record_types=_one(record_type),
    )
    ranked = await RetrievalService(session).search(project_id, query, as_of=as_of)
    results = [
        RetrievalResultOut(
            record_type=r.record.record_type,
            record_id=r.record.record_id,
            title=r.record.title,
            snippet=r.record.body[:_SNIPPET_LEN],
            source_module=r.record.source_module,
            party=r.record.party,
            occurred_at=r.record.occurred_at,
            entity_refs=list(r.record.entity_refs),
            score=round(r.score, 4),
            matched_facets=list(r.matched_facets),
            provenance=r.provenance,
        )
        for r in ranked
    ]
    return RetrievalResponse(count=len(results), results=results)
