# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""propdev: house-type catalogue — extra fields for the professional editor.

Extends ``oe_property_dev_house_type_catalogue`` with the layout /
pricing / marketing fields the /property-dev/settings/house-types modal
exposes:

* ``region_label`` — free-text fallback when the operator picks
  "Other / Custom region" (e.g. ``EU-wide``, ``DACH``, ``Middle East``).
* ``typical_bedrooms`` / ``typical_bathrooms`` — int hints.
* ``typical_price_min`` / ``typical_price_max`` / ``currency`` — ISO 4217.
* ``construction_type`` — brick | timber_frame | concrete | steel |
  mixed | other.
* ``energy_class`` — A+ | A | B | C | D | E | F | G | not_applicable.
* ``sales_channel`` — off_plan | new_build | resale.
* ``image_url`` — preview thumbnail (≤512 chars).
* ``tags`` — JSON list of free-text strings.

Each column is added behind a per-column ``in_columns`` guard so the
migration is idempotent against the v3112 ``create_all`` fresh-DB path.

Revision ID: v3118_propdev_house_type_extra_fields
Revises: v3117_contact_module_bridge
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3118_propdev_house_type_extra_fields"
down_revision: Union[str, Sequence[str], None] = "v3117_contact_module_bridge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "oe_property_dev_house_type_catalogue"


_NEW_COLUMNS: list[tuple[str, sa.Column]] = [
    ("region_label", sa.Column("region_label", sa.String(length=80), nullable=True)),
    ("typical_bedrooms", sa.Column("typical_bedrooms", sa.Integer(), nullable=True)),
    ("typical_bathrooms", sa.Column("typical_bathrooms", sa.Integer(), nullable=True)),
    (
        "typical_price_min",
        sa.Column("typical_price_min", sa.Numeric(14, 2), nullable=True),
    ),
    (
        "typical_price_max",
        sa.Column("typical_price_max", sa.Numeric(14, 2), nullable=True),
    ),
    ("currency", sa.Column("currency", sa.String(length=3), nullable=True)),
    (
        "construction_type",
        sa.Column("construction_type", sa.String(length=20), nullable=True),
    ),
    ("energy_class", sa.Column("energy_class", sa.String(length=10), nullable=True)),
    ("sales_channel", sa.Column("sales_channel", sa.String(length=20), nullable=True)),
    ("image_url", sa.Column("image_url", sa.String(length=512), nullable=True)),
    (
        "tags",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE):
        # If the table doesn't exist yet (extreme edge — env.py
        # create_all skipped for some reason), let v3114 handle it and
        # bail out; this migration is only an additive ALTER pass.
        return

    existing_cols = {c["name"] for c in inspector.get_columns(TABLE)}
    with op.batch_alter_table(TABLE) as batch:
        for col_name, column in _NEW_COLUMNS:
            if col_name in existing_cols:
                continue
            batch.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    existing_cols = {c["name"] for c in inspector.get_columns(TABLE)}
    with op.batch_alter_table(TABLE) as batch:
        for col_name, _column in reversed(_NEW_COLUMNS):
            if col_name in existing_cols:
                batch.drop_column(col_name)
