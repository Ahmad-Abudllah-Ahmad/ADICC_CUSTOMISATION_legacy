# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Wave 23 — worldwide currency parameterisation.

Two strictly-additive changes:

1. ``oe_property_dev_custom_template.override_currency`` (String 3, nullable):
   Per-template ISO 4217 currency override.  Resolution order when
   rendering a document from a custom template:
       override_currency  → project.currency  → tenant default  → "EUR"
   Null means "inherit from project" — existing rows keep their
   current behaviour unchanged.

2. ``oe_reporting_generated.currency`` (String 3, nullable):
   Stores the resolved rendering currency that was stamped into
   ``data_snapshot["currency"]`` at generation time (see
   ``reporting/router.py::_resolve_report_currency``). Denormalised here
   for indexed queries ("give me all USD cost-reports this quarter").
   Null for reports generated before Wave 23.

Both columns are nullable so a fresh migration on production requires
no data back-fill and no down-time (no DEFAULT expression needed — no
NOT NULL constraint on existing rows).

Revision ID: v3137_wave23_currency_parameterization
Revises: v3136_project_country_code
Create Date: 2026-05-25
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3137_wave23_currency_parameterization"
down_revision: Union[str, Sequence[str], None] = "v3136_project_country_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Safe identifier validation (security audit 2026-05-24 #3).
# ---------------------------------------------------------------------------
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TBL_CUSTOM_TEMPLATE = _safe_ident("oe_property_dev_custom_template")
_COL_OVERRIDE_CURRENCY = _safe_ident("override_currency")

_TBL_GENERATED = _safe_ident("oe_reporting_generated")
_COL_CURRENCY = _safe_ident("currency")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. oe_property_dev_custom_template.override_currency
    existing_cols = {c["name"] for c in inspector.get_columns(_TBL_CUSTOM_TEMPLATE)}
    if _COL_OVERRIDE_CURRENCY not in existing_cols:
        op.add_column(
            _TBL_CUSTOM_TEMPLATE,
            sa.Column(
                _COL_OVERRIDE_CURRENCY,
                sa.String(3),
                nullable=True,
                comment="ISO 4217 override; NULL = inherit from project.currency",
            ),
        )

    # 2. oe_reporting_generated.currency
    existing_gen_cols = {c["name"] for c in inspector.get_columns(_TBL_GENERATED)}
    if _COL_CURRENCY not in existing_gen_cols:
        op.add_column(
            _TBL_GENERATED,
            sa.Column(
                _COL_CURRENCY,
                sa.String(3),
                nullable=True,
                comment="Resolved ISO 4217 currency stamped at report-generation time",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_gen_cols = {c["name"] for c in inspector.get_columns(_TBL_GENERATED)}
    if _COL_CURRENCY in existing_gen_cols:
        op.drop_column(_TBL_GENERATED, _COL_CURRENCY)

    existing_cols = {c["name"] for c in inspector.get_columns(_TBL_CUSTOM_TEMPLATE)}
    if _COL_OVERRIDE_CURRENCY in existing_cols:
        op.drop_column(_TBL_CUSTOM_TEMPLATE, _COL_OVERRIDE_CURRENCY)
