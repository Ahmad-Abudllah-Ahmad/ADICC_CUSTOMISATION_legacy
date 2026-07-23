# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ERP Chat module.

AI-powered chat assistant for construction ERP data - sessions,
messages, tool-calling, vector recall, and (T8 / v3.11) per-turn
thumbs feedback + admin observability.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.erp_chat.permissions import register_erp_chat_permissions

    register_erp_chat_permissions()
