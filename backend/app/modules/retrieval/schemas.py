# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the retrieval (findability) API."""

from __future__ import annotations

from pydantic import BaseModel


class RetrievalResultOut(BaseModel):
    """One ranked record with the provenance needed to reconstruct it."""

    record_type: str
    record_id: str
    title: str
    snippet: str
    source_module: str
    party: str
    occurred_at: str
    entity_refs: list[str]
    score: float
    matched_facets: list[str]
    provenance: dict


class RetrievalResponse(BaseModel):
    """A ranked, faceted view across the project record."""

    count: int
    results: list[RetrievalResultOut]
