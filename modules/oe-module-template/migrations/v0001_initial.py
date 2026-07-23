# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍{{display_name}} initial schema — create ``oe_{{module_short}}_item``.

Idempotent and inspector-guarded so re-runs on a partially-migrated
DB are safe. SQLite-friendly (GUID() ⇒ VARCHAR(36)).

Move this file into ``backend/alembic/versions/`` and set
``down_revision`` to the current head before running
``alembic upgrade head``.

Revision ID: {{module_name}}_v0001_initial
Revises: <FILL_IN_CURRENT_HEAD>
Create Date: 2026-01-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "{{module_name}}_v0001_initial"
down_revision: Union[str, Sequence[str], None] = None  # set to current head!
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_{{module_short}}_item"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, _TABLE):
        return

    is_sqlite = bind.dialect.name == "sqlite"
    guid_type = (
        sa.String(36) if is_sqlite else sa.dialects.postgresql.UUID(as_uuid=True)
    )

    op.create_table(
        _TABLE,
        sa.Column("id", guid_type, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "project_id",
            guid_type,
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        f"ix_{_TABLE}_project_id",
        _TABLE,
        ["project_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        return
    op.drop_index(f"ix_{_TABLE}_project_id", table_name=_TABLE)
    op.drop_table(_TABLE)
