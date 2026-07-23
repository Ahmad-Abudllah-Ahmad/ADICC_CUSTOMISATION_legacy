# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-rollup permission definitions.

One read permission gates the composition. It is a read-only summary of figures a
viewer can already see across the BOQ, preliminaries and allowances tools, so
reading it is open to viewers.

* ``estimate_rollup.read`` - fetch a project's composed estimate rollup (VIEWER).
"""

from app.core.permissions import Role, permission_registry


def register_estimate_rollup_permissions() -> None:
    """Register permissions for the estimate-rollup module."""
    permission_registry.register_module_permissions(
        "estimate_rollup",
        {
            "estimate_rollup.read": Role.VIEWER,
        },
    )
