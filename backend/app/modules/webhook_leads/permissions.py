# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Webhook Leads module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_webhook_leads_permissions() -> None:
    """Register permissions for the Webhook Leads module.

    Permission map:
        webhook_leads.read    VIEWER   - list sources / mappings / logs
        webhook_leads.create  MANAGER  - create a source / mapping
        webhook_leads.update  MANAGER  - patch a source / mapping, rotate secret
        webhook_leads.delete  MANAGER  - delete a source / mapping

    Note: the public ingestion endpoint is intentionally NOT permission
    gated here - it authenticates against the per-source credential
    (API key / HMAC / JWT) instead of a logged-in platform user.
    """
    permission_registry.register_module_permissions(
        "webhook_leads",
        {
            "webhook_leads.read": Role.VIEWER,
            "webhook_leads.create": Role.MANAGER,
            "webhook_leads.update": Role.MANAGER,
            "webhook_leads.delete": Role.MANAGER,
        },
    )
