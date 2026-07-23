# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Smart Views module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_smart_views_permissions() -> None:
    """Register RBAC permissions for the smart_views module.

    Mirrors the canonical viewer/editor split used by the sibling
    ``clash`` / ``bcf`` / ``validation`` modules:

    * Viewers can read & list views and run the evaluator.
    * Editors can author, modify and delete their own views.

    Cross-user / cross-project visibility is enforced inside the
    service layer (see :class:`SmartViewService._scope_predicate`),
    not by the RBAC gate - RBAC tells you *whether* you may use the
    feature; scoping tells you *which rows* you may touch.
    """
    permission_registry.register_module_permissions(
        "smart_views",
        {
            "smart_views.read": Role.VIEWER,
            "smart_views.create": Role.EDITOR,
            "smart_views.update": Role.EDITOR,
            "smart_views.delete": Role.EDITOR,
        },
    )
