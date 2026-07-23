# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Clash cost-impact module permission definitions.

This module is a cross-module read-projection: it never mutates clash or
BOQ data. The router additionally requires the caller to hold BOTH
``clash.read`` AND ``boq.read`` so a viewer who can only see the BOQ
side cannot lift a coordination grid out via this surface, and vice
versa - the module-loader's coarse permission gate enforces ``clash.read``
and the router's runtime guard enforces ``boq.read``.
"""

from app.core.permissions import Role, permission_registry


def register_clash_cost_impact_permissions() -> None:
    """Register the cross-module read permission.

    The single permission ``clash_cost.read`` is granted at viewer level
    - pure read-projection, no writes, no costly compute. Endpoints
    layer an additional ``clash.read`` + ``boq.read`` runtime check on
    top so the cross-module surface respects both upstream gates even
    if only one of them tightens later.
    """
    permission_registry.register_module_permissions(
        "clash_cost_impact",
        {
            "clash_cost.read": Role.VIEWER,
        },
    )
