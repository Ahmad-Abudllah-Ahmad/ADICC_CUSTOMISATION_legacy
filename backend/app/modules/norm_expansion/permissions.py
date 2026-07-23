# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Production-norm expansion module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_norm_expansion_permissions() -> None:
    """Register permissions for the norm-expansion module.

    Reads (listing norms and running an expansion) are open to viewers; editing
    the shared library is an editor action; deleting a norm is a manager
    action because it removes a reference other estimators may rely on.
    """
    permission_registry.register_module_permissions(
        "norm_expansion",
        {
            "norm_expansion.read": Role.VIEWER,
            "norm_expansion.write": Role.EDITOR,
            "norm_expansion.manage": Role.MANAGER,
        },
    )
