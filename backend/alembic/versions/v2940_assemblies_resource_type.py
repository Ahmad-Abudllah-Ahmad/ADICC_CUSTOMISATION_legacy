# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""assemblies — resource_type as a first-class column on Component.

Promotes the existing metadata-stored hint (``metadata.resource_type``)
into a real column on ``oe_assemblies_component`` so the M/L/E
breakdown can be filtered, indexed and persisted on apply-to-BOQ
without text inference. Pre-existing rows have their type back-filled
from ``metadata->>'resource_type'`` where set, otherwise from a small
description heuristic (kept for legacy data only — new components
arrive with the type already typed in the UI).

Idempotent — re-applying on a DB where ``Base.metadata.create_all``
has already created the column is a no-op.

Revision ID: v2940_assemblies_resource_type
Revises: v2939_document_share_links
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2940_assemblies_resource_type"
down_revision: Union[str, Sequence[str], None] = "v2939_document_share_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "oe_assemblies_component"
_COLUMN = "resource_type"
_INDEX = "ix_assemblies_component_resource_type"


def _existing_columns(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def _existing_indexes(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    return {ix["name"] for ix in inspector.get_indexes(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind)
    if _COLUMN not in cols:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(length=20), nullable=True),
        )
    indexes = _existing_indexes(bind)
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)

    # Back-fill: prefer the metadata-stored hint, fall back to a small
    # heuristic on description so legacy assemblies stop showing every
    # row as "material" once the UI starts filtering by type.
    # JSON extraction differs by backend: SQLite (dev) uses json_extract
    # with a JSON path, PostgreSQL (prod) uses the ->> text operator.
    dialect = bind.dialect.name
    if dialect == "sqlite":
        bind.execute(
            sa.text(
                """
                UPDATE oe_assemblies_component
                   SET resource_type = json_extract(metadata, '$.resource_type')
                 WHERE resource_type IS NULL
                   AND json_extract(metadata, '$.resource_type') IS NOT NULL
                """
            )
        )
    elif dialect in ("postgresql", "postgres"):
        bind.execute(
            sa.text(
                """
                UPDATE oe_assemblies_component
                   SET resource_type = metadata ->> 'resource_type'
                 WHERE resource_type IS NULL
                   AND metadata ->> 'resource_type' IS NOT NULL
                """
            )
        )
    # Unknown dialect: skip the metadata-based back-fill and let the
    # description heuristic below assign a type. This avoids emitting a
    # JSON accessor we cannot guarantee the backend supports.

    # Heuristic for the rest — avoid making it too clever; the user can
    # re-type any row once the new editor lands.
    bind.execute(
        sa.text(
            """
            UPDATE oe_assemblies_component
               SET resource_type =
                 CASE
                   WHEN LOWER(description) LIKE '%labor%'  THEN 'labor'
                   WHEN LOWER(description) LIKE '%worker%' THEN 'labor'
                   WHEN LOWER(description) LIKE '%crew%'   THEN 'labor'
                   WHEN LOWER(description) LIKE '%труд%'   THEN 'labor'
                   WHEN LOWER(description) LIKE '%работ%'  THEN 'labor'
                   WHEN LOWER(description) LIKE '%equip%'  THEN 'equipment'
                   WHEN LOWER(description) LIKE '%machine%' THEN 'equipment'
                   WHEN LOWER(description) LIKE '%crane%'  THEN 'equipment'
                   WHEN LOWER(description) LIKE '%механ%'  THEN 'equipment'
                   WHEN LOWER(description) LIKE '%operator%' THEN 'operator'
                   WHEN LOWER(description) LIKE '%машинист%' THEN 'operator'
                   ELSE 'material'
                 END
             WHERE resource_type IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = _existing_indexes(bind)
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    cols = _existing_columns(bind)
    if _COLUMN in cols:
        op.drop_column(_TABLE, _COLUMN)
