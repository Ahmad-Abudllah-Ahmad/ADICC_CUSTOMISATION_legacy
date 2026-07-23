# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""RFI vector adapter - feeds the ``oe_rfi_rfis`` collection.

Each :class:`~app.modules.rfi.models.RFI` row is embedded as the RFI
number, subject, question and official response so the AI advisor and
the global Cmd+K modal can recall RFIs by meaning ("structural rebar
clash on level 2", "delivery delay for curtain wall") rather than exact
text match.

The adapter is deliberately narrow - it knows nothing about the event
bus or HTTP routing.  Wiring lives in :mod:`app.modules.rfi.events`.
Implements the :class:`~app.core.vector_index.EmbeddingAdapter` protocol.
"""

from __future__ import annotations

from typing import Any

from app.core.vector_index import COLLECTION_RFI
from app.modules.rfi.models import RFI


class RFIVectorAdapter:
    """Embed RFI rows into the unified vector store."""

    collection_name: str = COLLECTION_RFI
    module_name: str = "rfi"

    def to_text(self, row: RFI) -> str:
        """Build the canonical text that gets embedded.

        Concatenates the RFI number, subject, question, official response,
        discipline and status so semantic queries match regardless of
        which lifecycle state the RFI is in.
        """
        parts: list[str] = []
        if row.rfi_number:
            parts.append(str(row.rfi_number).strip())
        if row.subject:
            parts.append(row.subject.strip())
        if row.question:
            parts.append(row.question.strip())
        if row.official_response:
            parts.append(row.official_response.strip())
        discipline = getattr(row, "discipline", None)
        if discipline:
            parts.append(str(discipline))
        status = getattr(row, "status", None)
        if status:
            parts.append(str(status))
        return " | ".join(p for p in parts if p)

    def to_payload(self, row: RFI) -> dict[str, Any]:
        """Light metadata returned with every search hit so the UI can
        render a row card without an extra Postgres roundtrip."""
        return {
            "title": (row.subject or row.rfi_number or "")[:160],
            "rfi_number": row.rfi_number or "",
            "status": row.status or "",
            "discipline": getattr(row, "discipline", "") or "",
            "priority": getattr(row, "priority", "") or "",
        }

    def project_id_of(self, row: RFI) -> str | None:
        """Resolve the owning project id directly from the row."""
        project_id = getattr(row, "project_id", None)
        if project_id is None:
            return None
        return str(project_id)


# Singleton instance - adapters are stateless so one shared object is fine.
rfi_vector_adapter = RFIVectorAdapter()
