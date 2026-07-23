# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Notifications module permission definitions.

Registered at module startup via ``app.modules.notifications.on_startup``.

The webhook-target admin endpoints (``POST``/``PATCH``/``DELETE`` on
``/api/v1/notifications/webhooks/``) let an operator register an arbitrary
outbound URL that the platform will POST event payloads to. A compromised
account could otherwise turn the dispatcher into an exfiltration / SSRF
relay, so webhook administration is gated at ADMIN rather than MANAGER.

Internal lineage: ddc-lineage:a17f93c4-notif-01
"""

from app.core.permissions import Role, permission_registry


def register_notification_permissions() -> None:
    """Register RBAC permissions for the notifications module."""
    permission_registry.register_module_permissions(
        "notifications",
        {
            # Outbound webhook-target administration (create / update /
            # delete). ADMIN-only: a webhook target points the dispatcher at
            # an arbitrary URL.
            "notifications.admin.webhooks": Role.ADMIN,
        },
    )
