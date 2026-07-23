# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Project Controls permission definitions."""

from app.core.permissions import Role, permission_registry


def register_project_controls_permissions() -> None:
    """Register permissions for the Project Controls module."""
    permission_registry.register_module_permissions(
        "project_controls",
        {
            # The controls snapshot + drill-down are broadly readable; project
            # scoping is enforced separately via verify_project_access.
            "project_controls.read": Role.VIEWER,
        },
    )
