# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Per-user file favourites / pins.

Adds ``oe_file_favorite`` — a single polymorphic table holding one row
per ``user × file`` favourite. It is keyed on ``(file_kind, file_id)``
across the 8 file-manager kinds (document / photo / sheet / bim_model /
dwg_drawing / takeoff / report / markup), with no FK to the underlying
kind table: the file-manager dispatcher sweeps stale favourites when the
underlying row is deleted.

``pinned`` is a tri-state-ish bit: an unpinned row is a *favourite*; a
pinned row is an *elevated favourite* that sorts first in the user's
Recently-Viewed / Favourites strip.

Indexes follow the hot paths:

* UNIQUE (user_id, file_kind, file_id) — the toggle endpoint upserts on
  this scope so starring twice flips the pin instead of duplicating.
* (user_id, project_id) — "list my favourites in this project".
* (file_kind, file_id) — reverse lookup when a file is deleted so the
  dispatcher can sweep favourites pointing at it.

Idempotent: every CREATE is guarded so the migration can be re-run on a
partially-applied install, and a fresh SQLite install that boots the app
first already has the table via ``Base.metadata.create_all``.

Revision ID: v3150_file_favorites
Revises: v3149_audit_indexes_and_fks
Create Date: 2026-05-29
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3150_file_favorites"
down_revision: Union[str, None] = "v3149_audit_indexes_and_fks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "oe_file_favorite"):
        op.create_table(
            "oe_file_favorite",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("file_kind", sa.String(length=32), nullable=False),
            sa.Column("file_id", sa.String(length=64), nullable=False),
            sa.Column(
                "pinned",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0") if bind.dialect.name == "sqlite" else sa.text("false"),
            ),
            sa.UniqueConstraint(
                "user_id",
                "file_kind",
                "file_id",
                name="uq_file_favorite_user_kind_file",
            ),
        )
    if not _index_exists(bind, "oe_file_favorite", "ix_file_favorite_user_project"):
        op.create_index(
            "ix_file_favorite_user_project",
            "oe_file_favorite",
            ["user_id", "project_id"],
        )
    if not _index_exists(bind, "oe_file_favorite", "ix_file_favorite_kind_file"):
        op.create_index(
            "ix_file_favorite_kind_file",
            "oe_file_favorite",
            ["file_kind", "file_id"],
        )

    logger.info("v3150 file_favorites: oe_file_favorite ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "oe_file_favorite"):
        op.drop_table("oe_file_favorite")
