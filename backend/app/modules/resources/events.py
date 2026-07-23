# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resources domain events.

The resources module talks to the rest of the platform through the global
:data:`app.core.events.event_bus`. Events are addressed by their dot-notation
name (``{module}.{entity}.{action}``); this module is the single place those
names are declared so publishers and subscribers agree on one spelling.

Published events (emitted by ``service.py``):

* :data:`EVENT_ASSIGNMENT_PROPOSED` - a tentative assignment was created and
  awaits confirm/decline.
* :data:`EVENT_ASSIGNMENT_CONFIRMED` - a proposed assignment was confirmed.
* :data:`EVENT_REQUEST_OPENED` - a project opened a resource request.
* :data:`EVENT_REQUEST_FULFILLED` - a resource request was fulfilled with an
  assignment.
* :data:`EVENT_CERT_EXPIRING` - a certification is approaching expiry.
* :data:`EVENT_TIMECARDS_IMPORTED` - a batch of time-cards landed as
  completed assignments.
* :data:`EVENT_PORTFOLIO_OVERLOAD_DETECTED` - the read-only portfolio leveling
  pass found one or more resources booked beyond their declared capacity in the
  scanned window. Payload carries the window, the overloaded-resource count and
  the per-resource peak so a notification subscriber can alert a planner. This
  is purely informational; leveling NEVER moves a booking automatically (the
  platform philosophy is AI/automation proposes, a human confirms).

The names below are the source of truth; call sites pass the same string
literal to ``event_bus.publish_detached``.
"""

from __future__ import annotations

# ── Published event names ───────────────────────────────────────────────────

EVENT_ASSIGNMENT_PROPOSED = "resources.assignment.proposed"
EVENT_ASSIGNMENT_CONFIRMED = "resources.assignment.confirmed"
EVENT_REQUEST_OPENED = "resources.request.opened"
EVENT_REQUEST_FULFILLED = "resources.request.fulfilled"
EVENT_CERT_EXPIRING = "resources.cert_expiring"
EVENT_TIMECARDS_IMPORTED = "resources.timecards.imported"
EVENT_PORTFOLIO_OVERLOAD_DETECTED = "resources.portfolio.overload_detected"
