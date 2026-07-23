# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""5D Cost Model domain events.

The cost-model module talks to the rest of the platform through the global
:data:`app.core.events.event_bus`. Events are addressed by their dot-notation
name (``{module}.{entity}.{action}``); this module is the single place those
names are declared so publishers and subscribers agree on one spelling.

Published events:

* :data:`EVENT_BUDGET_LINE_ACTUAL_POSTED` - emitted by
  :meth:`CostSpineService.post_actual_to_budget_line` whenever a realised cost
  is posted onto a ``BudgetLine.actual_amount`` (Gap B). The payload carries
  ``project_id``, ``budget_line_id``, ``cost_line_id`` (nullable), ``category``,
  ``source_kind``, ``source_ref`` and the posted ``amount`` (base currency,
  Decimal-as-string). Gap D (cost-overrun alerts) and the reporting module
  subscribe to it for eventual-consistency rollups.

The labour-actuals subscriber (Gap A) is bound inside ``service.py`` at import
time; it listens to ``fieldreports.labour.logged`` (owned by the field-reports
module) and is therefore not re-declared here.

The cost-overrun-alert subscriber (Gap D) is likewise bound inside
``service.py`` at import time. It listens to BOTH
:data:`EVENT_BUDGET_LINE_UPDATED` (manual edits + threshold arming) and
:data:`EVENT_BUDGET_LINE_ACTUAL_POSTED` (Gap B / labour postings, which raise
``actual_amount`` without an ``updated`` event), and when a line's actual cost
breaches its armed threshold it creates a ``cost_overrun_alert`` notification
for the project owner (subject to a 24h cooldown). No new published event name
is introduced; the notification itself is the side effect.
"""

from __future__ import annotations

# ── Published event names ───────────────────────────────────────────────────

EVENT_BUDGET_LINE_ACTUAL_POSTED = "costmodel.budget_line.actual_posted"

# Existing cost-model events already published by ``service.py`` (declared here
# for discoverability; the strings remain the source of truth at the call site).
EVENT_SNAPSHOT_CREATED = "costmodel.snapshot.created"
EVENT_SNAPSHOT_DELETED = "costmodel.snapshot.deleted"
EVENT_BUDGET_LINE_CREATED = "costmodel.budget_line.created"
EVENT_BUDGET_LINE_UPDATED = "costmodel.budget_line.updated"
EVENT_BUDGET_LINE_DELETED = "costmodel.budget_line.deleted"
EVENT_SPINE_GENERATED = "costmodel.spine.generated"


def register_costmodel_subscribers() -> None:
    """Wire cost-model event subscribers into the global bus.

    The labour-actuals subscriber registers itself at import time in
    ``service.py`` (its binding must live in an allowed source file), so this
    hook is currently a no-op kept for symmetry with the other modules'
    startup wiring and as the home for any future in-module subscribers. It is
    safe to call more than once.
    """
    # Importing the service module ensures the labour-actuals subscriber is
    # bound even if nothing else has imported it yet at startup.
    import app.modules.costmodel.service  # noqa: F401
