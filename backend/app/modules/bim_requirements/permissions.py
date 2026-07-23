# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""BIM Requirements module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bim_requirements_permissions() -> None:
    """Register RBAC permissions for the bim_requirements module.

    Mirrors the sibling ``clash`` / ``validation`` verb set: viewers read
    requirement sets and run model validations / exports; editors import
    new sets and YAML rule packs; managers can delete a set. Excel/IDS
    export is a read-class capability (it does not mutate stored data -
    it just serialises an existing set).
    """
    permission_registry.register_module_permissions(
        "bim_requirements",
        {
            "bim_requirements.read": Role.VIEWER,
            "bim_requirements.create": Role.EDITOR,
            "bim_requirements.update": Role.EDITOR,
            "bim_requirements.delete": Role.MANAGER,
            "bim_requirements.export": Role.VIEWER,
        },
    )
