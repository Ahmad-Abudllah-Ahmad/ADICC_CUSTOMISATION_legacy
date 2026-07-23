# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Apply audit-flagged indexes + file_version self-ref FKs to existing installs.

Wave 7 of the v5.6.x post-release audit flagged that several `created_by`
and `assignee_id` columns were declared on models without ``index=True``,
and the two ``oe_file_version`` self-reference pointers were missing both
their ``ForeignKey`` constraint and an index. The model files have been
updated, but SQLAlchemy ``index=True`` only takes effect at
``create_all`` time — existing prod/dev DBs need this migration to
actually gain the indexes.

Indexes only — no data changes.

Revision ID: v3149_audit_indexes_and_fks
Revises: v3148_remove_example_webhook_orphans
Created: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3149_audit_indexes_and_fks"
down_revision: Union[str, None] = "v3148_remove_example_webhook_orphans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, index_name)
_INDEXES = [
    ("oe_file_version", "previous_version_id", "ix_oe_file_version_previous_version_id"),
    ("oe_file_version", "superseded_by_id", "ix_oe_file_version_superseded_by_id"),
    ("oe_clash_issue", "assignee_id", "ix_oe_clash_issue_assignee_id"),
    ("oe_compliance_docs_document", "created_by", "ix_oe_compliance_docs_document_created_by"),
    ("oe_geo_hub_poi", "created_by", "ix_oe_geo_hub_poi_created_by"),
    ("oe_geo_hub_site", "created_by", "ix_oe_geo_hub_site_created_by"),
    ("oe_reporting_report", "created_by", "ix_oe_reporting_report_created_by"),
]


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(bind, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, index_name in _INDEXES:
        if not _table_exists(bind, table):
            # Module not installed on this deployment — skip.
            continue
        if not _column_exists(bind, table, column):
            # Older deployment that pre-dates the column — skip.
            continue
        if _index_exists(bind, table, index_name):
            continue
        op.create_index(index_name, table, [column])


def downgrade() -> None:
    bind = op.get_bind()
    for table, _column, index_name in _INDEXES:
        if not _table_exists(bind, table):
            continue
        if not _index_exists(bind, table, index_name):
            continue
        op.drop_index(index_name, table_name=table)
