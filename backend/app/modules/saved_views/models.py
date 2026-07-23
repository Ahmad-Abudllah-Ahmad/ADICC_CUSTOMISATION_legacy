# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Saved-views ORM models.

Two tables, both inheriting :class:`app.database.Base` (so ``id`` / ``created_at``
/ ``updated_at`` are free). No money is involved here, so no ``MoneyType``. JSON
columns carry ``server_default`` because the embedded PostgreSQL runtime builds
the schema via ``create_all`` and ignores Python-side defaults on existing dev
databases.

Tables:
    oe_saved_views_view - one named, scoped filter spec against a registered
                          entity.
    oe_saved_views_run  - append-only audit/telemetry of a run (budget overflow
                          attempts and slow views are observable).
"""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class SavedView(Base):
    """A named, scoped saved search against one registered entity.

    The ``spec`` JSON is the serialized ``FilterSpec``; it is re-validated by
    Pydantic on every read and write, never trusted as-is. ``share_scope`` is one
    of ``private`` / ``project`` / ``workspace`` - never ``public``; there is no
    unauthenticated share token in Phase 1.
    """

    __tablename__ = "oe_saved_views_view"
    __table_args__ = (
        Index("ix_saved_views_owner_entity", "owner_id", "entity_type"),
        Index("ix_saved_views_project_entity", "project_id", "entity_type"),
        UniqueConstraint(
            "owner_id",
            "project_id",
            "entity_type",
            "name",
            name="uq_saved_views_owner_scope_name",
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    share_scope: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="private",
        server_default="private",
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<SavedView {self.name!r} entity={self.entity_type} scope={self.share_scope}>"


class SavedViewRun(Base):
    """Append-only audit row written after a run.

    Lets budget-overflow attempts and slow views be observed. ``outcome`` is one
    of ``ok`` / ``budget`` / ``scope`` / ``whitelist`` / ``error``.
    """

    __tablename__ = "oe_saved_views_run"
    __table_args__ = (Index("ix_saved_views_run_view_created", "saved_view_id", "created_at"),)

    saved_view_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_saved_views_view.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<SavedViewRun view={self.saved_view_id} outcome={self.outcome} rows={self.row_count}>"
