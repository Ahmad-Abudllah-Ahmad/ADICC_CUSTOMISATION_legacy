# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Document activity log ORM models.

Tables:
    oe_documents_activity - append-only log of per-document events
                            (upload / rename / download / delete / cde
                            state change). Used by the file-preview pane
                            timeline and by audit dashboards.

A separate file (rather than tacking onto ``models.py``) keeps the audit
surface easy to grep for and avoids growing the already-busy ``models``
module. ``models.py`` re-imports the symbol at the bottom so the alembic
autogenerate / module loader still discover the metadata.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class DocumentActivity(Base):
    """Append-only audit event for a single :class:`Document` row.

    ``action`` is a short tag (``uploaded`` / ``renamed`` / ``downloaded``
    / ``deleted`` / ``cde_state_changed``). ``meta`` is a free-form JSON
    blob whose shape is keyed by ``action`` (e.g. ``renamed`` carries
    ``{"old": "...", "new": "..."}``).

    The table is intentionally write-only at the application layer - there
    is no PATCH / DELETE endpoint. Cleanup is delegated to the parent
    document's ``ON DELETE CASCADE``.

    ``id`` / ``created_at`` / ``updated_at`` are inherited from
    :class:`Base`. We add an explicit index on ``created_at`` (the Base
    default has no index) so the newest-first timeline query stays
    sub-millisecond on big projects.
    """

    __tablename__ = "oe_documents_activity"

    __table_args__ = (
        Index("ix_documents_activity_created_at", "created_at"),
        Index(
            "ix_documents_activity_doc_created",
            "document_id",
            "created_at",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_documents_document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    meta: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<DocumentActivity {self.action} doc={self.document_id}>"
