# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Field Reports — UUID typing for approved_by / created_by.

Aligns ``oe_fieldreports_report.approved_by`` and
``oe_fieldreports_report.created_by`` with daily_diary's typing convention:
they were declared as ``String(36)`` but always hold user UUIDs, so the
Python-side type was inconsistent (raw ``str`` instead of ``uuid.UUID``).

Storage layout is unchanged on both SQLite (``GUID()`` impls as
``VARCHAR(36)``) and PostgreSQL — the wire format of a GUID column is
the same VARCHAR/UUID the columns already carry. The migration is
therefore a Python-side no-op on every backend we target, but it is
recorded in the alembic chain so ``alembic upgrade head`` produces a
revision id that matches the new model declaration and so any future
schema diff doesn't flag a phantom type drift.

The body is intentionally empty (skip on every dialect): touching the
columns would force SQLite into a full table rebuild for zero gain, and
Postgres' UUID type is incompatible with the existing VARCHAR data
without an explicit USING cast — which we don't need because the GUID
type already round-trips both representations transparently.

Revision ID: v40_fieldreports_uuid_typing
Revises: v40_bim_federations
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "v40_fieldreports_uuid_typing"
down_revision: Union[str, Sequence[str], None] = "v40_bim_federations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op at the storage layer — see module docstring."""


def downgrade() -> None:
    """No-op — the columns never changed shape on disk."""
