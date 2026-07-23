# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ per-position AI copilot ORM model.

Table:
    oe_boq_position_copilot_message - one chat turn (user or assistant) in the
        per-position AI copilot thread, plus any structured action proposals
        the assistant produced for that turn.

The copilot is a position-scoped chat: the user asks the assistant to refine a
single BOQ position (rewrite its description, set a quantity / unit rate, or
add resources) and the assistant replies with prose plus zero or more
:class:`CopilotActionProposal` actions. High-confidence actions are
auto-applied through the existing ``BOQService.update_position`` write path and
recorded here; lower-confidence actions are persisted as proposals the user can
apply later.

Tenant scoping mirrors the sibling :class:`app.modules.boq.models.Position`:
positions carry no direct tenant column - ownership is resolved through the
owning BOQ -> project chain (``_verify_boq_owner`` in the router). We therefore
denormalise ``boq_id`` and ``project_id`` onto every message so the same
ownership check can run from a copilot row without an extra position load, and
so per-project / per-BOQ audit queries stay cheap.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class PositionCopilotMessage(Base):
    """A single turn in a BOQ position's AI copilot thread.

    Columns:
        position_id - owning BOQ position (CASCADE on delete; indexed for the
            per-position thread read path).
        boq_id - denormalised owning BOQ (the tenant-scoping anchor, mirroring
            how every other BOQ child row scopes access via the BOQ -> project
            chain). Indexed for per-BOQ audit listing.
        project_id - denormalised owning project, for cheap per-project audit
            queries and to resolve ``region``/currency without a join.
        role - ``user`` (the estimator's message) or ``assistant`` (the model's
            reply / applied-action audit note).
        content - the message text (prose). For assistant turns this is the
            model's natural-language ``reply``.
        actions - the structured :class:`CopilotActionProposal` list for an
            assistant turn, stored verbatim as JSON (JSONB on PostgreSQL via the
            generic-JSON -> JSONB DDL rewrite). ``None`` for plain user turns or
            replies with no proposals.
        created_by - the acting user (nullable: assistant/system turns may carry
            no user id, matching the nullable-actor convention used by
            ``BOQActivityLog.user_id``).
    """

    __tablename__ = "oe_boq_position_copilot_message"
    __table_args__ = (
        # Hot read path: the per-position thread is fetched ordered by time
        # (``WHERE position_id=? ORDER BY created_at``). The composite turns the
        # listing into an index range scan instead of a filter + sort.
        Index("ix_boq_copilot_position_created", "position_id", "created_at"),
        # Per-BOQ audit feed (all copilot activity for a BOQ, newest first).
        Index("ix_boq_copilot_boq_created", "boq_id", "created_at"),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_boq_position.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised tenant-scoping anchor. Not a hard FK with a cascade because
    # the position FK above already guarantees referential cleanup; this column
    # exists so the BOQ -> project ownership check can run straight off a
    # copilot row (and for per-BOQ audit listing).
    boq_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Structured action proposals (assistant turns). Generic JSON for SQLite
    # portability; the pg_optimizations @compiles hook renders this as JSONB on
    # PostgreSQL DDL, so the on-disk type is JSONB while reads/writes are
    # unchanged. Nullable: plain user turns carry no actions.
    actions: Mapped[list | None] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    def __repr__(self) -> str:
        return f"<PositionCopilotMessage {self.role} pos={self.position_id}>"
