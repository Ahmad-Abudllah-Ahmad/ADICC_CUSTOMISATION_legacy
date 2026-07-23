# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Meetings module.

Meeting minutes management - progress, design, safety, subcontractor,
kickoff, and closeout meetings with agendas, attendees, and action items.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and validation rules."""
    from app.modules.meetings.permissions import register_meetings_permissions
    from app.modules.meetings.validators import register_meetings_validation_rules

    register_meetings_permissions()
    register_meetings_validation_rules()
