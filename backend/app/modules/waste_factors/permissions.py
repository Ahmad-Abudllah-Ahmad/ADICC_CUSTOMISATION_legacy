# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Waste Factors module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_waste_factors_permissions() -> None:
    """Register permissions for the waste-factor module.

    The factor library is a shared reference catalogue and mutating a factor
    re-prices every net-to-gross conversion that resolves it, so reads are open
    to any viewer while writes (create / update / delete / seed) are gated at
    manager level, mirroring the other shared-catalogue modules.
    """
    permission_registry.register_module_permissions(
        "waste_factors",
        {
            "waste_factors.read": Role.VIEWER,
            "waste_factors.manage": Role.MANAGER,
        },
    )
