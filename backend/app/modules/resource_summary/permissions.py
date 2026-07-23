# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Resource Summary module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_resource_summary_permissions() -> None:
    """Register permissions for the Resource Summary module.

    Reading and exporting the procurement statement is a read action available to
    any viewer. Freezing a run as a stored snapshot is a manager-level action so a
    plain viewer cannot litter a project with saved statements.
    """
    permission_registry.register_module_permissions(
        "resource_summary",
        {
            "resource_summary.read": Role.VIEWER,
            "resource_summary.snapshot": Role.MANAGER,
        },
    )
