# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Remove stale "Example webhook (disabled)" seed rows that 404 in the UI.

The original gapfill seed on 2026-05-16 dropped one
``Example webhook (disabled)`` row per project into ``oe_integrations_config``
so the empty Integrations page would not look broken on demo installs.
The rows themselves are harmless (``is_active = false``, empty URL), but
the /integrations UI exposes "Test" / edit actions on every row that
404 because the rows do not point at a real webhook configuration —
they were never meant to be interactive. This migration removes them on
every existing install so the cleanup ships with v5.5.2.

Revision ID: v3148_remove_example_webhook_orphans
Revises: v3147_approval_routes
Created: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3148_remove_example_webhook_orphans"
down_revision: Union[str, None] = "v3147_approval_routes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the gapfill-seeded Example webhook rows."""
    bind = op.get_bind()
    # SQLite (dev) supports json_extract; PostgreSQL (prod) supports
    # the JSON arrow operator. Use the SQLAlchemy `dialect.name` to pick
    # the right WHERE clause so the migration runs on both backends.
    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            DELETE FROM oe_integrations_config
            WHERE name = 'Example webhook (disabled)'
              AND json_extract(metadata, '$.seed') = 'gapfill-20260516'
            """
        )
    elif dialect in ("postgresql", "postgres"):
        op.execute(
            """
            DELETE FROM oe_integrations_config
            WHERE name = 'Example webhook (disabled)'
              AND metadata ->> 'seed' = 'gapfill-20260516'
            """
        )
    else:
        # Unknown dialect — fall back to a name-only match. Safe because
        # the row name is unique to the gapfill seed and nobody else
        # creates rows with this exact display name.
        op.execute(
            """
            DELETE FROM oe_integrations_config
            WHERE name = 'Example webhook (disabled)'
            """
        )


def downgrade() -> None:
    """No-op — the seed rows were never load-bearing."""
    # Intentionally empty. We do not restore the orphan rows on
    # downgrade because they were a UX artefact, not data anyone relied
    # on. If a deployment needs them back, re-running the original
    # gapfill seed will reinsert one row per project.
