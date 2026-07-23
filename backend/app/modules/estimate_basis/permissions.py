# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Basis-of-estimate permission definitions.

Three permissions gate the document lifecycle. Reading and exporting the basis
is open to viewers (it is a client-facing summary of an estimate they can
already see); drafting and editing it is an estimator action.

* ``estimate_basis.read``     - list, fetch and export documents (VIEWER).
* ``estimate_basis.generate`` - derive and store a fresh basis (EDITOR).
* ``estimate_basis.write``    - save edits to a stored document (EDITOR).
"""

from app.core.permissions import Role, permission_registry


def register_estimate_basis_permissions() -> None:
    """Register permissions for the basis-of-estimate module."""
    permission_registry.register_module_permissions(
        "estimate_basis",
        {
            "estimate_basis.read": Role.VIEWER,
            "estimate_basis.generate": Role.EDITOR,
            "estimate_basis.write": Role.EDITOR,
        },
    )
