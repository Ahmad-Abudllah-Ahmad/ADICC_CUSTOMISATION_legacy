# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Off-site / Prefab / DfMA event topic names.

All events are best-effort published via ``event_bus.publish_detached`` inside
the service layer (see ``PrefabService.advance_stage``). Cross-module
subscribers - schedule (to mark an install milestone), logistics /
notifications (to flag a dispatch) - can consume these without coupling to the
prefab ORM.
"""

from __future__ import annotations

# A new off-site unit was registered.
UNIT_CREATED = "prefab.unit.created"

# A unit advanced one (or more) production stages. Carries from/to stages.
UNIT_STAGE_ADVANCED = "prefab.unit.stage_advanced"

# A unit left the factory - required by the task spec. Logistics / transport
# and the client-facing tracker care about this one.
UNIT_DISPATCHED = "prefab.unit.dispatched"

# A unit was installed on site - the terminal milestone. Schedule / progress
# can close out the associated activity on this event.
UNIT_INSTALLED = "prefab.unit.installed"
