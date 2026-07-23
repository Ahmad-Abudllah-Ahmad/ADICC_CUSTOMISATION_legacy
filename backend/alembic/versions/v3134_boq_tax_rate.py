# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""boq: add tax_rate column to oe_boq_boq (Wave 25 / task #168).

Adds ``oe_boq_boq.tax_rate NUMERIC(5,4) NULL`` so each BOQ can carry an
optional tax rate (e.g. 0.1900 = 19 % DE VAT, 0.2000 = 20 % UK VAT).

When set, the service layer computes::

    tax_amount = net_total * tax_rate          (rounded to cents, HALF_UP)
    grand_total = net_total + tax_amount

``NULL`` means "no tax line" — the BOQ grand_total equals net_total as
before, preserving existing behaviour for all BOQs without a tax rate.

Idempotent: the column is only added when absent (checked via
inspector.get_columns).

Revision ID: v3134_boq_tax_rate
Revises: v3133_field_diary_init
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3134_boq_tax_rate"
down_revision: Union[str, Sequence[str], None] = "v3133_field_diary_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_boq_boq"
_COLUMN = "tax_rate"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}

    if _COLUMN not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Numeric(precision=5, scale=4),
                nullable=True,
                comment=(
                    "Optional tax rate applied to the BOQ net total (direct cost + markups). "
                    "Stored as a decimal fraction: 0.1900 = 19 % DE VAT, 0.2000 = 20 % UK VAT. "
                    "NULL = no tax line. See app.core.tax.get_vat_rate() for canonical lookups."
                ),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}

    if _COLUMN in existing_cols:
        op.drop_column(_TABLE, _COLUMN)
