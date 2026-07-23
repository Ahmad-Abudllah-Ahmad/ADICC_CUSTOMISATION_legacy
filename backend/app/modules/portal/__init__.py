# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Customer & Partner Portal module.

External-facing portal users (clients, investors, consultants, subcontractors,
suppliers, building users) with magic-link authentication, row-level security
(via per-resource access rules), notification feed, and append-only document
access audit log.

Portal users are stored in a SEPARATE table from internal ``oe_users_user`` -
they never have internal-system access. Authentication is primarily magic-link
based; the password column is reserved for future use but unused in v0.1.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.portal.permissions import register_portal_permissions

    register_portal_permissions()
