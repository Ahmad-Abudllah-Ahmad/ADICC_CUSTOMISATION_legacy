# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Smart Views - rule-based, re-evaluating BIM viewer presets.

The counter-intuitive design choice - and the single biggest
differentiator from the snapshot-style "save view" feature most BIM
viewers ship - is that a SmartView stores a list of **rule queries**,
not a frozen snapshot of (camera + visibility booleans). Every time the
model is loaded the rules re-execute against the current
``BIMElement.properties`` / ``element_type`` columns, so a view
authored on model rev 3 still works on rev 17 even though the GUIDs
underneath have churned, and the same view can be re-targeted at any
model that happens to expose the property the selector looks at.

The module is self-contained: it never mutates ``bim_hub`` and only
ever reads canonical element rows. Geometry is left untouched - Smart
Views drive visibility / colour / opacity, not topology.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.smart_views.permissions import (
        register_smart_views_permissions,
    )

    register_smart_views_permissions()
