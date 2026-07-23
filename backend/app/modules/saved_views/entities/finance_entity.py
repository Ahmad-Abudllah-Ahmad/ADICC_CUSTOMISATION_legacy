# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Built-in queryable entity: ``ledger_entry``.

This is the starting-point adapter for the append-only finance ledger
(``oe_finance_ledger``). When the Chart of Accounts lands, finance owns the final
field list; until then this reference registration already turns "trial balance
for an account this period", "all reversals last month", and a reminder badge
into saved views rather than bespoke queries. ``LedgerEntry`` carries a direct
``project_id`` column, so the project pin is a plain column comparison.
"""

from __future__ import annotations

from app.modules.saved_views.registry import (
    FieldSpec,
    QueryableEntity,
    register_queryable_entity,
)
from app.modules.saved_views.scoper import project_member_scoper

ENTITY_TYPE = "ledger_entry"


def build_entity() -> QueryableEntity:
    """Construct the ``ledger_entry`` queryable entity."""
    from app.modules.finance.models import LedgerEntry

    fields = {
        "account_code": FieldSpec(name="account_code", column="account_code", kind="string"),
        "transaction_ref": FieldSpec(
            name="transaction_ref",
            column="transaction_ref",
            kind="string",
            # transaction_ref carries index=True on the model -> groupable.
            groupable=True,
        ),
        "currency_code": FieldSpec(name="currency_code", column="currency_code", kind="string"),
        "posted_at": FieldSpec(name="posted_at", column="posted_at", kind="date"),
        "debit_amount": FieldSpec(name="debit_amount", column="debit_amount", kind="money"),
        "credit_amount": FieldSpec(name="credit_amount", column="credit_amount", kind="money"),
        "source_type": FieldSpec(name="source_type", column="source_type", kind="string"),
        "is_reversal": FieldSpec(name="is_reversal", column="is_reversal", kind="bool"),
        "description": FieldSpec(name="description", column="description", kind="string"),
        "created_at": FieldSpec(name="created_at", column="created_at", kind="date"),
    }
    return QueryableEntity(
        entity_type=ENTITY_TYPE,
        model=LedgerEntry,
        fields=fields,
        scoper=project_member_scoper,
        project_fk_column="project_id",
        default_sort=("posted_at", "desc"),
        default_columns=(
            "account_code",
            "transaction_ref",
            "debit_amount",
            "credit_amount",
            "currency_code",
            "posted_at",
        ),
    )


def register() -> None:
    """Register the ``ledger_entry`` entity with the global registry."""
    register_queryable_entity(build_entity())
