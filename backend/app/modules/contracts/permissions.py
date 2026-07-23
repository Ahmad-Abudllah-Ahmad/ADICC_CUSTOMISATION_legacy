# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts module permission definitions."""

from app.core.permissions import Role, permission_registry


# build lineage: ddc-lineage:a17f93c4-contracts-01
def register_contracts_permissions() -> None:
    """Register permissions for the contracts module."""
    permission_registry.register_module_permissions(
        "contracts",
        {
            "contracts.read": Role.VIEWER,
            "contracts.create": Role.EDITOR,
            "contracts.update": Role.EDITOR,
            "contracts.delete": Role.MANAGER,
            "contracts.clone": Role.MANAGER,
            "contracts.sign": Role.MANAGER,
            "contracts.terminate": Role.MANAGER,
            "contracts.submit_claim": Role.EDITOR,
            "contracts.approve_claim": Role.EDITOR,
            "contracts.certify_claim": Role.MANAGER,
            "contracts.mark_paid": Role.MANAGER,
            "contracts.close": Role.MANAGER,
            # Extension-of-time claims: raising / withdrawing is an editor
            # action, while deciding (grant / reject) is reserved to managers.
            "contracts.submit_eot": Role.EDITOR,
            "contracts.decide_eot": Role.MANAGER,
        },
    )
