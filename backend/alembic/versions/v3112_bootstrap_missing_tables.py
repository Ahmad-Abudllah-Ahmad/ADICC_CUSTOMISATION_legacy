# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""bootstrap: defense-in-depth create-all for ORM-only tables.

This migration is a documented no-op on installs that took the
canonical boot-then-stamp path or the fresh-DB ``alembic upgrade
head`` shortcut wired into ``alembic/env.py``. It exists for two
reasons:

1. **Documentation marker** at the head of the chain that captures
   the fresh-blank-DB install bug closed in this release (same class
   as #154 seed-loader cascade). Anyone debugging a future
   ``no such table:`` crash during ``alembic upgrade head`` can land
   here and trace the fix.

2. **Defense in depth**: if a downstream operator (or test harness)
   bypasses ``env.py``'s fresh-DB shortcut and instead drives alembic
   programmatically through the migration chain, this migration runs
   ``Base.metadata.create_all(checkfirst=True)`` as the last step.
   That guarantees every ORM-defined table — including the 60+ tables
   no historical migration ever ``create_table``'d (oe_users_user,
   oe_projects_project, oe_assemblies_component, oe_costs_item, all
   of clash/*, file_*, geo_hub/*, property_dev/*, ...) — is present
   at head. Idempotent on installs that already have those tables.

The list of tables the fresh-DB install used to miss is enumerated
in the release notes for this version; the source of truth is the
union of every ``__tablename__`` in ``app/modules/*/models.py``
minus the set of tables actually ``op.create_table``'d by any
migration prior to this one. The list intentionally is **not**
hard-coded here — the create_all dispatch via Base.metadata is
self-updating as new modules ship.

Revision ID: v3112_bootstrap_missing_tables
Revises: v3111_takeoff_measurement_numeric
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "v3112_bootstrap_missing_tables"
down_revision: Union[str, Sequence[str], None] = "v3111_takeoff_measurement_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Defense-in-depth: create_all any ORM table that doesn't yet exist.

    ``checkfirst=True`` makes this a no-op on every existing install
    (boot-then-stamp deployments already have these tables; fresh-DB
    ``alembic upgrade head`` installs took the env.py shortcut and
    materialised them at the head stamp). Running it anyway as the
    last step in the chain closes the corner case where a future
    operator drives alembic past the env.py shortcut and forgets to
    boot the app — in that path this migration is the safety net.
    """
    try:
        # env.py has already imported every module's models so
        # Base.metadata is fully populated by the time we get here.
        from app.database import Base  # noqa: WPS433
    except Exception:  # noqa: BLE001 — never break alembic on import path
        return

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # No-op: dropping every ORM table on baseline-bootstrap downgrade
    # would wipe the DB, which is never what the user wants from
    # ``alembic downgrade``. Mirrors 129188e46db8_init_create_all_tables.
    pass
