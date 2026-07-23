# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Submittals vector adapter - feeds the ``oe_submittals_submittals`` collection.

Each :class:`~app.modules.submittals.models.Submittal` row is embedded as
the submittal number, title, spec section and type so the AI advisor and
the global Cmd+K modal can recall submittals by meaning ("concrete mix
design", "fire-rated door shop drawings") rather than exact text match.

The adapter is deliberately narrow - it knows nothing about the event bus
or HTTP routing.  Wiring lives in :mod:`app.modules.submittals.events`.
Implements the :class:`~app.core.vector_index.EmbeddingAdapter` protocol.
"""

from __future__ import annotations

from typing import Any

from app.core.vector_index import COLLECTION_SUBMITTALS
from app.modules.submittals.models import Submittal


class SubmittalVectorAdapter:
    """Embed submittal rows into the unified vector store."""

    collection_name: str = COLLECTION_SUBMITTALS
    module_name: str = "submittals"

    def to_text(self, row: Submittal) -> str:
        """Build the canonical text that gets embedded.

        Concatenates the submittal number, title, spec section, type and
        status so semantic queries match regardless of which review stage
        the submittal is in.
        """
        parts: list[str] = []
        if row.submittal_number:
            parts.append(str(row.submittal_number).strip())
        if row.title:
            parts.append(row.title.strip())
        spec_section = getattr(row, "spec_section", None)
        if spec_section:
            parts.append(str(spec_section).strip())
        submittal_type = getattr(row, "submittal_type", None)
        if submittal_type:
            parts.append(str(submittal_type))
        status = getattr(row, "status", None)
        if status:
            parts.append(str(status))
        return " | ".join(p for p in parts if p)

    def to_payload(self, row: Submittal) -> dict[str, Any]:
        """Light metadata returned with every search hit so the UI can
        render a row card without an extra Postgres roundtrip."""
        return {
            "title": (row.title or row.submittal_number or "")[:160],
            "submittal_number": row.submittal_number or "",
            "status": row.status or "",
            "submittal_type": getattr(row, "submittal_type", "") or "",
            "spec_section": getattr(row, "spec_section", "") or "",
        }

    def project_id_of(self, row: Submittal) -> str | None:
        """Resolve the owning project id directly from the row."""
        project_id = getattr(row, "project_id", None)
        if project_id is None:
            return None
        return str(project_id)


# Singleton instance - adapters are stateless so one shared object is fine.
submittal_vector_adapter = SubmittalVectorAdapter()
