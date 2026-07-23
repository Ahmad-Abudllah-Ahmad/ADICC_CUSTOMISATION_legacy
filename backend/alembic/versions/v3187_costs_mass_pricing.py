# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Mass-based pricing columns on cost items (structural members).

A structural-steel section (e.g. a "360UB" universal beam) is priced by mass:
its linear mass (kg per metre) times its length gives a mass, and the rate is
quoted per tonne (or per kg). To support that on a normal length-based BOQ
line WITHOUT a second unit system, two additive columns are added to
``oe_costs_item``:

    mass_per_unit  - String(50) Decimal-as-string. Linear mass in kg per one
                     ``unit`` (e.g. "44.7" for a 360UB at 44.7 kg/m). Empty =
                     not set. String for the same SQLite/JSON precision reason
                     as ``rate``.
    mass_basis     - String(10). The denominator the ``rate`` is quoted
                     against: "t" (per tonne) or "kg" (per kg). Empty = mass
                     pricing OFF (the item behaves as a plain per-unit rate).

The effective per-length rate is computed at apply time
(``costs.service.mass_effective_unit_rate``); the stored ``rate`` is never
mutated. Both columns default to empty, so every existing row is unaffected
and reads as "no mass pricing".

The embedded-PostgreSQL runtime materialises these via the startup column
auto-heal, so this migration is for external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded so a re-run (or a
DB the runtime already auto-created) is a no-op. Additive and backfill-safe.
GUID columns elsewhere are VARCHAR(36) (the app.database.GUID TypeDecorator).
PostgreSQL-only, no SQLite shims.

Revision ID: v3187_costs_mass_pricing
Revises: v3186_payroll_deductions_net
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3187_costs_mass_pricing"
down_revision = "v3186_payroll_deductions_net"
branch_labels = None
depends_on = None

_TABLE = "oe_costs_item"
_MASS_PER_UNIT = "mass_per_unit"
_MASS_BASIS = "mass_basis"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table(_TABLE):
        return
    if not _has_column(_TABLE, _MASS_PER_UNIT):
        op.add_column(
            _TABLE,
            sa.Column(_MASS_PER_UNIT, sa.String(length=50), nullable=False, server_default=""),
        )
    if not _has_column(_TABLE, _MASS_BASIS):
        op.add_column(
            _TABLE,
            sa.Column(_MASS_BASIS, sa.String(length=10), nullable=False, server_default=""),
        )


def downgrade() -> None:
    if _has_column(_TABLE, _MASS_BASIS):
        op.drop_column(_TABLE, _MASS_BASIS)
    if _has_column(_TABLE, _MASS_PER_UNIT):
        op.drop_column(_TABLE, _MASS_PER_UNIT)
