# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Integrations module - chat connectors (Teams, Slack, Telegram), webhooks, calendar feeds."""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions + the connector bridge.

    Invoked by :class:`app.core.module_loader` after the module's models,
    hooks and router are loaded. Registering here (rather than in
    ``main.py``) keeps the permission contract colocated with the module
    that enforces it, exactly like the sibling ``reporting`` /
    ``finance`` modules.

    The connector bridge (issue #279) subscribes to
    ``notifications.notification.created`` so in-app notifications are
    delivered to each user's connected chat connectors (Telegram, Slack,
    Teams, Discord, WhatsApp). It is purely additive - it adds a new event
    subscriber and changes no existing dispatch behaviour.
    """
    from app.modules.integrations.notification_bridge import (
        register_integration_notification_bridge,
    )
    from app.modules.integrations.permissions import register_integrations_permissions

    register_integrations_permissions()
    register_integration_notification_bridge()
