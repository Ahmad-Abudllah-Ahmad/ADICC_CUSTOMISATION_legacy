# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Integrations module permission definitions.

Registered at module startup via ``app.modules.integrations.on_startup``.
Without this, every ``RequirePermission("integrations.*")`` gate in
``router.py`` resolves against an *unregistered* permission, which the
RBAC engine treats as "unknown → deny" for every non-admin role.

Role mapping (R7 audit, 2026-05-24):
    integrations.read    = VIEWER   - list configs / webhooks / deliveries
    integrations.create  = MANAGER  - credentials (webhook URLs, API
                                       tokens, bot secrets) carry outbound
                                       cross-tenant risk; only managers+
                                       may wire up new connectors
    integrations.update  = MANAGER  - rotating/re-pointing credentials is
                                       equivalent in blast-radius to
                                       creating new ones
    integrations.delete  = MANAGER  - disconnecting an active integration
                                       silently drops notification flow;
                                       only managers+ may sever it

The platform-wide convention (mirrors finance / costs / contracts R7
sweeps) is that credential-carrying modules elevate writes to MANAGER
rather than letting EDITOR (estimator/QS) configure outbound HTTP
clients. Estimators authoring BOQ data should not be able to point the
platform at an arbitrary attacker-controlled URL.
"""

from app.core.permissions import Role, permission_registry


def register_integrations_permissions() -> None:
    """Register permissions for the integrations module."""
    permission_registry.register_module_permissions(
        "integrations",
        {
            "integrations.read": Role.VIEWER,
            "integrations.create": Role.MANAGER,
            "integrations.update": Role.MANAGER,
            "integrations.delete": Role.MANAGER,
        },
    )
