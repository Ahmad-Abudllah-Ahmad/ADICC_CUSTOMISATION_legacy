# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Compliance documents module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_compliance_docs_permissions() -> None:
    """Register permissions for the compliance docs tracker."""
    permission_registry.register_module_permissions(
        "compliance_docs",
        {
            "compliance_docs.create": Role.EDITOR,
            "compliance_docs.read": Role.VIEWER,
            "compliance_docs.update": Role.EDITOR,
            "compliance_docs.delete": Role.MANAGER,
        },
    )
