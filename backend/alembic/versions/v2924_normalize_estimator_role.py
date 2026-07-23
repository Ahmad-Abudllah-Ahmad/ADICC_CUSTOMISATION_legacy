"""v2.9.24 — Normalize legacy ``estimator`` role to ``editor``.

The 2.8.x demo seeder shipped Sarah Chen with ``role="estimator"`` while the
public ``/auth/register`` and admin ``/users/{id}`` update endpoints have
always restricted ``role`` to ``admin|manager|editor|viewer``. The frontend
``UserRole`` type and role-config map likewise don't know about
``estimator``, so the seeded row rendered with the fallback (Viewer) and
could not be edited via the UI without first re-typing the role through a
direct DB write.

This migration brings any pre-existing ``estimator`` rows into the canonical
4-role set. The seeder itself was updated to write ``editor`` directly, so
fresh installs after v2.9.24 won't need this migration — but production
boxes that booted with the older seeder do.

Revision ID: v2924_normalize_estimator_role
Revises: v2918_risk_owner_user_id
Create Date: 2026-05-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "v2924_normalize_estimator_role"
down_revision: Union[str, Sequence[str], None] = "v2918_risk_owner_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE oe_users_user SET role = 'editor' WHERE role = 'estimator'")


def downgrade() -> None:
    # No-op. Reverting would require knowing which editor rows were originally
    # estimators, which we did not record. Operators who depended on the old
    # value can re-set role manually.
    pass
