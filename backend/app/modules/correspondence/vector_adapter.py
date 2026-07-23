# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Correspondence vector adapter - feeds the ``oe_correspondence_correspondence`` collection.

Each :class:`~app.modules.correspondence.models.Correspondence` row is
embedded as the reference number, subject, direction, type and notes so
the AI advisor and the global Cmd+K modal can recall letters / emails /
notices by meaning ("notice of delay", "claim for extension of time")
rather than exact text match.

The adapter is deliberately narrow - it knows nothing about the event bus
or HTTP routing.  Wiring lives in :mod:`app.modules.correspondence.events`.
Implements the :class:`~app.core.vector_index.EmbeddingAdapter` protocol.
"""

from __future__ import annotations

from typing import Any

from app.core.vector_index import COLLECTION_CORRESPONDENCE
from app.modules.correspondence.models import Correspondence


class CorrespondenceVectorAdapter:
    """Embed correspondence rows into the unified vector store."""

    collection_name: str = COLLECTION_CORRESPONDENCE
    module_name: str = "correspondence"

    def to_text(self, row: Correspondence) -> str:
        """Build the canonical text that gets embedded.

        Concatenates the reference number, subject, direction, type and
        free-text notes so semantic queries match the substance of the
        correspondence, not just its subject line.
        """
        parts: list[str] = []
        if row.reference_number:
            parts.append(str(row.reference_number).strip())
        if row.subject:
            parts.append(row.subject.strip())
        direction = getattr(row, "direction", None)
        if direction:
            parts.append(str(direction))
        correspondence_type = getattr(row, "correspondence_type", None)
        if correspondence_type:
            parts.append(str(correspondence_type))
        notes = getattr(row, "notes", None)
        if notes:
            parts.append(notes.strip())
        return " | ".join(p for p in parts if p)

    def to_payload(self, row: Correspondence) -> dict[str, Any]:
        """Light metadata returned with every search hit so the UI can
        render a row card without an extra Postgres roundtrip."""
        return {
            "title": (row.subject or row.reference_number or "")[:160],
            "reference_number": row.reference_number or "",
            "direction": getattr(row, "direction", "") or "",
            "correspondence_type": getattr(row, "correspondence_type", "") or "",
        }

    def project_id_of(self, row: Correspondence) -> str | None:
        """Resolve the owning project id directly from the row."""
        project_id = getattr(row, "project_id", None)
        if project_id is None:
            return None
        return str(project_id)


# Singleton instance - adapters are stateless so one shared object is fine.
correspondence_vector_adapter = CorrespondenceVectorAdapter()
