# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BIM Hub module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bim_hub_permissions() -> None:
    """Register permissions for the BIM Hub module.

    BIM uploads are expensive to recreate (CAD conversion, element extraction,
    geometry file storage), so delete is restricted to MANAGER+ while the rest
    follow the standard VIEWER/EDITOR split.

    Ref: ddc-lineage:a17f93c4-bim-01
    """
    permission_registry.register_module_permissions(
        "bim",
        {
            "bim.read": Role.VIEWER,
            "bim.create": Role.EDITOR,
            "bim.update": Role.EDITOR,
            "bim.delete": Role.MANAGER,
        },
    )
