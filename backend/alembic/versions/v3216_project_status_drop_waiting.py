# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""projects: retire the "waiting" status (duplicate of "on_hold").

Data-only migration. The project ``status`` column is a free-form varchar
(no DB enum), and the curated UI set dropped ``waiting`` because it was a
duplicate of ``on_hold``. This folds any existing live project rows that
still read ``waiting`` into ``on_hold`` so they keep rendering with a curated
badge instead of falling through to the humanised "Waiting" fallback.

Scope:
  * Touches ONLY ``oe_projects_project.status``.
  * ``oe_project_status_history`` is intentionally LEFT UNTOUCHED so the
    audit trail keeps its historical fidelity (a past "active -> waiting"
    transition stays as it actually happened).

The upgrade is idempotent (re-running matches nothing once converted) and
money-free. The downgrade is a deliberate no-op: ``waiting`` and ``on_hold``
are semantically identical and, once merged, the two populations are
indistinguishable, so there is nothing to safely restore - reverting must
not invent or lose data.

Revision ID: v3216_project_status_drop_waiting
Revises: v3215_bim_view_folders
Create Date: 2026-06-30
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3216_project_status_drop_waiting"
down_revision: Union[str, Sequence[str], None] = "v3215_bim_view_folders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_projects_project"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    # Guard so the migration is a safe no-op on a fresh install where the
    # table was built via ``Base.metadata.create_all`` but is otherwise empty.
    if not _table_exists(bind, _TABLE):
        logger.info("v3216 drop waiting status: %s missing, nothing to do", _TABLE)
        return
    result = bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET status = 'on_hold' WHERE status = 'waiting'"  # noqa: S608 - fixed identifier, no user input
        )
    )
    logger.info(
        "v3216 drop waiting status: %s project(s) moved 'waiting' -> 'on_hold'",
        getattr(result, "rowcount", "?"),
    )


def downgrade() -> None:
    # No-op by design. 'waiting' was merged into 'on_hold' and the two are
    # now indistinguishable, so we cannot reconstruct the original split
    # without losing data. Leaving the data in place is the safe revert.
    logger.info("v3216 drop waiting status: downgrade is a no-op (data merge)")
