# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design Options ORM models.

Tables:
    oe_design_options_set    - a set of alternative design options for a project
    oe_design_options_option - one option inside a set, paired with its own BOQ

An option pairs a source (an uploaded document, a converted BIM model, or a
match session) with its own priced bill of quantities, so a full set of options
can be compared side by side on total cost, by-trade deltas and cost per m2.

Money, quantity and ratio columns are stored as strings (the platform
Decimal-as-string convention) so precision is never lost through a binary float.
Cross-module references (source document, BIM model, BOQ, match session,
baseline option) are plain GUID columns with NO ForeignKey per the
cross-module-reference convention; only the same-module set<->option link and
the app-core project link are real foreign keys. ``project_id`` is copied onto
the option (denormalised) so option reads can be scoped to a project directly,
which keeps the API IDOR-safe without a join back through the set.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base


class DesignOptionSet(Base):
    """A set of alternative design options compared against each other.

    One option in the set may be marked as the baseline (``baseline_option_id``);
    every other option's cost delta is then measured against it. All options are
    rebased to ``comparison_currency`` for a fair like-for-like comparison (a
    blank value falls back to the project base currency).
    """

    __tablename__ = "oe_design_options_set"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", server_default="draft")
    # Soft pointer to the chosen baseline DesignOption. Same module, but kept a
    # plain GUID (not a ForeignKey) to avoid a circular set<->option constraint.
    baseline_option_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    comparison_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    decision_criteria: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    # Same-module parent -> children. Selectin so a fetched set always carries
    # its options for the comparison without a lazy load in the async context.
    options: Mapped[list["DesignOption"]] = relationship(
        back_populates="set",
        cascade="all, delete-orphan",
        order_by="DesignOption.sort_order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DesignOptionSet {self.name!r} project={self.project_id} status={self.status}>"


class DesignOption(Base):
    """One design option inside a set, paired with its own priced BOQ.

    ``status`` walks the option through its lifecycle:
    ``draft`` -> ``model_attached`` -> ``converting`` -> ``boq_generating`` ->
    ``priced`` (or ``failed`` with ``error`` set). ``boq_id`` is the pairing that
    makes the option estimable: its bill of quantities is totalled directly into
    ``direct_cost`` / ``markups_total`` / ``grand_total``, all rebased to the
    set's comparison currency. ``breakdown`` is the by-element cost snapshot
    (RomElementBreakdown shape) used for the by-trade delta rows.
    """

    __tablename__ = "oe_design_options_option"

    set_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_design_options_set.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised copy of the owning set's project for direct IDOR-safe scoping
    # of option reads. Plain GUID (no ForeignKey) - the project link lives on the
    # set; this copy only exists to avoid a join on every option query.
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Source pairing - all plain GUIDs, no ForeignKey (cross-module references).
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    bim_model_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    boq_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    match_session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", server_default="draft")
    error: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")

    # Priced totals - Decimal-as-string, never floats. Rebased to the set's
    # comparison currency at generation time; ``currency`` records that currency.
    direct_cost: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    markups_total: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    grand_total: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    cost_per_m2: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    gfa: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    gfa_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="m2", server_default="m2")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")

    element_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    position_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    breakdown: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]"
    )

    validation_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="pending"
    )
    validation_score: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    # Same-module child -> parent. raise so an accidental lazy access in the
    # async context fails loudly instead of emitting a stray query; the forward
    # selectin above populates this in memory without tripping the guard.
    set: Mapped["DesignOptionSet"] = relationship(back_populates="options", lazy="raise")

    def __repr__(self) -> str:
        return f"<DesignOption {self.name!r} set={self.set_id} status={self.status} total={self.grand_total}>"
