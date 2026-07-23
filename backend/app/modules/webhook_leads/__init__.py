# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Webhook Leads module.

Secure INCOMING webhook endpoints that auto-create CRM leads from
external sources (marketing forms, ad platforms, other CRMs).

The public ingestion endpoint authenticates against a per-source
credential (API key / HMAC-SHA256 / JWT) - *not* the normal JWT user
session. Every attempt (accepted, rejected, or errored) is recorded as
a ``WebhookLog`` row for audit. Admin CRUD over sources / mappings / logs
is gated through the standard RBAC permission registry.

Lead creation is delegated to :class:`app.modules.crm.service.CrmService`
- this module never duplicates CRM tables.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.webhook_leads.permissions import (
        register_webhook_leads_permissions,
    )

    register_webhook_leads_permissions()
