"""Add PortalUser.notification_email_opt_in column.

Boolean defaulting to True. Lets a portal user disable transactional /
actionable email notifications while still receiving in-portal feed entries
(those are always on and cannot be opted out of).

Revision ID: v3028_portal_email_optin
Revises: v3027_service_ticket_source
Created: 2026-05-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3028_portal_email_optin"
down_revision: Union[str, Sequence[str], None] = "v3027_service_ticket_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``notification_email_opt_in`` (BOOLEAN, default True)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("oe_portal_user")}
    if "notification_email_opt_in" not in existing_cols:
        op.add_column(
            "oe_portal_user",
            sa.Column(
                "notification_email_opt_in",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1") if bind.dialect.name == "sqlite" else sa.text("true"),
            ),
        )


def downgrade() -> None:
    """Drop ``notification_email_opt_in``."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("oe_portal_user")}
    if "notification_email_opt_in" in existing_cols:
        op.drop_column("oe_portal_user", "notification_email_opt_in")
