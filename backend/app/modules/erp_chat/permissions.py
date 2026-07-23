# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ERP Chat module permission definitions (T8).

Adds an ``erp_chat.admin`` permission gating the new admin observability
endpoint. Read-side ``erp_chat.use`` is implied by anyone with editor or
higher and isn't enforced today (the streaming endpoint just needs an
authenticated user), so we don't register that explicitly to avoid
breaking the existing JWT-only path.
"""

from app.core.permissions import Role, permission_registry


def register_erp_chat_permissions() -> None:
    """Register permissions for the ERP Chat module."""
    permission_registry.register_module_permissions(
        "erp_chat",
        {
            # Admin observability dashboard - token spend, thumbs feedback,
            # cache hit rate. Manager+ only because raw user prompts are
            # tenant-sensitive.
            "erp_chat.admin": Role.MANAGER,
        },
    )
