# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Post-calculation module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_postcalc_permissions() -> None:
    """Register permissions for the post-calculation module.

    The report is read-only analysis over data the caller can already see, so a
    single viewer-level read permission gates it. Project-level access is still
    enforced separately by ``verify_project_access`` in the router.
    """
    permission_registry.register_module_permissions(
        "postcalc",
        {
            "postcalc.read": Role.VIEWER,
        },
    )
