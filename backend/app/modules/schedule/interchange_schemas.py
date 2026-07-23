# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request / response schemas for lossless schedule interchange (T1.1).

The interchange document itself is carried as a free-form ``dict`` (its shape is
owned and validated by the pure ``schedule_interchange`` module), so there are no
money-named fields here - the body is opaque to the money-serialisation guard.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ScheduleExportResponse(BaseModel):
    """A schedule exported to the neutral interchange document."""

    schedule_id: UUID
    document: dict[str, Any]


class CleanActionModel(BaseModel):
    """One repair the normalise-on-import cleaner applied (or would apply)."""

    code: str
    target: str
    detail: str


class ScheduleCleanPreviewResponse(BaseModel):
    """Dry-run hygiene report for a live schedule - what cleaning would change."""

    schedule_id: UUID
    actions: list[CleanActionModel]
    stats: dict[str, int]


class ScheduleImportRequest(BaseModel):
    """Create a new schedule from an interchange document.

    ``clean`` runs the normalise-on-import repair (recommended); with it off a
    structurally broken document is rejected instead of silently mis-imported.
    ``name_override`` renames the imported schedule without editing the document.
    """

    project_id: UUID
    document: dict[str, Any]
    clean: bool = True
    name_override: str | None = None


class ScheduleImportResponse(BaseModel):
    """Outcome of an import: the new schedule plus what was created / repaired."""

    schedule_id: UUID
    activity_count: int
    relationship_count: int
    clean_actions: list[CleanActionModel]
    stats: dict[str, int]
    #: Document activity ``ref`` -> freshly minted activity id, so the caller can
    #: correlate the source document with the created rows.
    ref_map: dict[str, UUID]
