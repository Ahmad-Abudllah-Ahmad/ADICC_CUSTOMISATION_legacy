# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-basis ORM models.

Tables:
    oe_estimate_basis_document - one drafted, editable basis-of-estimate per
        generation, scoped to a project (and optionally the BOQ it was drawn
        from). The three qualification lists and the coverage snapshot are held
        as JSON so a regenerate or a user edit is a single-row write.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class EstimateBasis(Base):
    """A drafted basis-of-estimate (inclusions, exclusions, assumptions).

    Columns:
        project_id - owning project (CASCADE on delete).
        boq_id - the BOQ the basis was generated from, when a single BOQ was
            targeted; ``None`` means it spans every BOQ of the project. Kept as a
            bare indexed GUID (no hard FK) so deleting a BOQ never cascades away
            the client-facing document.
        title - human-readable heading for the document.
        status - ``draft`` while being edited, ``final`` once signed off.
        inclusions / exclusions / assumptions - JSON lists of qualification
            dicts (see :class:`.derivation.Qualification`); each item carries a
            stable id, its text, the trade it derives from and an enabled flag,
            so the UI edits, reorders and toggles lines without losing identity.
        coverage - JSON snapshot of the present/absent trade picture and quality
            flags at generation time, so the export shows the basis even after
            the source estimate moves on.
        generated_at - ISO-8601 UTC timestamp of the derivation.
        created_by - the user who generated the document (provenance).
        metadata_ - module-extensible blob.
    """

    __tablename__ = "oe_estimate_basis_document"
    __table_args__ = (
        # The list endpoint reads a project's documents newest-first.
        Index("ix_estimate_basis_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    boq_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Basis of estimate")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    inclusions: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    exclusions: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    assumptions: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    coverage: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    generated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<EstimateBasis project={self.project_id} status={self.status} title={self.title!r}>"
