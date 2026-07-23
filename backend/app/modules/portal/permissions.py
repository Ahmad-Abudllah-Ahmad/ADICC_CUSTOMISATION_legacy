# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Customer & Partner Portal permission definitions.

These are INTERNAL-admin permissions that gate the ``/api/v1/portal/admin/*``
surface. Portal-user-facing endpoints (``/auth/*``, ``/me/*``) use the
module-local :func:`app.modules.portal.dependencies.RequirePortalSession`
dependency, which is orthogonal to the internal RBAC engine.

Internal ref: ddc-lineage:a17f93c4-portal-01
"""

from app.core.permissions import Role, permission_registry


def register_portal_permissions() -> None:
    """Register internal-admin permissions for the portal module."""
    permission_registry.register_module_permissions(
        "portal",
        {
            "portal.admin.users.read": Role.MANAGER,
            "portal.admin.users.invite": Role.MANAGER,
            "portal.admin.users.suspend": Role.MANAGER,
            "portal.admin.access_rules.manage": Role.MANAGER,
            "portal.admin.audit.read": Role.MANAGER,
        },
    )
