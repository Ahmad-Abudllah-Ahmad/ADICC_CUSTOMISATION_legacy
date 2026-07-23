# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Cost Explorer module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_cost_explorer_permissions() -> None:
    """Register permissions for the Cost Explorer module.

    Searching the cost and resource databases is a read action available to any
    viewer. Rebuilding the resource -> work reverse index rewrites a whole
    region's edges, so it is a manager-level maintenance action.
    """
    permission_registry.register_module_permissions(
        "cost_explorer",
        {
            "cost_explorer.read": Role.VIEWER,
            "cost_explorer.reindex": Role.MANAGER,
        },
    )
