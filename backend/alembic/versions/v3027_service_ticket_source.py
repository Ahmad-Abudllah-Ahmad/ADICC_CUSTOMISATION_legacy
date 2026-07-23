"""Add ServiceTicket.source and ServiceTicket.sla_breach_notified_at columns.

Two additive columns on ``oe_service_ticket``:

* ``source`` (varchar(20), NOT NULL, server_default='manual', indexed) —
  channel a ticket arrived on. Values: manual / portal / email / api /
  auto_ppm. Default ``manual`` keeps existing rows behaving as before.
* ``sla_breach_notified_at`` (varchar(40), nullable) — set the first time
  the SLA-scan emits a ``service.sla.breached`` event for a ticket. Lets the
  scan be idempotent (re-runs don't re-notify).

Revision ID: v3027_service_ticket_source
Revises: v3026_bi_dashboards
Created: 2026-05-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3027_service_ticket_source"
down_revision: Union[str, Sequence[str], None] = "v3026_bi_dashboards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``source`` and ``sla_breach_notified_at`` to oe_service_ticket."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("oe_service_ticket")}

    if "source" not in existing_cols:
        op.add_column(
            "oe_service_ticket",
            sa.Column(
                "source",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            ),
        )
        op.create_index(
            "ix_oe_service_ticket_source",
            "oe_service_ticket",
            ["source"],
        )

    if "sla_breach_notified_at" not in existing_cols:
        op.add_column(
            "oe_service_ticket",
            sa.Column(
                "sla_breach_notified_at",
                sa.String(length=40),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Drop the two columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("oe_service_ticket")}
    existing_indexes = {i["name"] for i in inspector.get_indexes("oe_service_ticket")}

    if "ix_oe_service_ticket_source" in existing_indexes:
        op.drop_index("ix_oe_service_ticket_source", table_name="oe_service_ticket")
    if "source" in existing_cols:
        op.drop_column("oe_service_ticket", "source")
    if "sla_breach_notified_at" in existing_cols:
        op.drop_column("oe_service_ticket", "sla_breach_notified_at")
