# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Equipment & Fleet domain events.

The equipment module talks to the rest of the platform through the global
:data:`app.core.events.event_bus`. Events are addressed by their dot-notation
name (``{module}.{entity}.{action}``); this module is the single place those
names are declared so publishers and subscribers agree on one spelling.

Published events (emitted by ``service.py`` / ``router.py``):

* :data:`EVENT_ASSIGNED` - a rental was created linking equipment to a project.
  No cost is posted on assignment (billing is computed on return).
* :data:`EVENT_FUEL_LOGGED` - a fuel fill was recorded. Payload carries
  ``project_id`` (the active rental's project, nullable), ``cost`` and
  ``currency`` so the cost rollup can fold it into the equipment budget line.
* :data:`EVENT_PARTS_LOGGED` - a part was consumed. Payload carries
  ``project_id``, ``quantity``, ``unit_cost``, ``line_total`` and ``currency``.
* :data:`EVENT_RENTAL_RETURNED` - a rental was returned (Gap C). The router
  computes the rental billing (days x day-rate, or hours x hour-rate) and emits
  this with ``billing_amount`` and ``currency`` so the rollup posts the total
  rental charge to the equipment budget line.

Subscribed events:

The Gap C equipment cost-rollup subscribers (``_on_fuel_logged``,
``_on_parts_logged``, ``_on_rental_returned``) are bound inside ``service.py``
at import time (the binding must live in an allowed source file). They feed the
:class:`EquipmentActualsService` which idempotently accumulates equipment cost
into a single ``category="equipment"`` ``BudgetLine.actual_amount`` per project,
mirroring the labour-actuals pattern.
"""

from __future__ import annotations

# ── Published event names ───────────────────────────────────────────────────

EVENT_ASSIGNED = "equipment.assigned"
EVENT_FUEL_LOGGED = "equipment.fuel_logged"
EVENT_PARTS_LOGGED = "equipment.parts_logged"
EVENT_RENTAL_RETURNED = "equipment.rental_returned"

# Other events already published by the module (declared here for
# discoverability; the strings remain the source of truth at the call site).
EVENT_TELEMETRY_RECORDED = "equipment.telemetry.recorded"
EVENT_MAINTENANCE_DUE = "equipment.maintenance_due"
EVENT_DAMAGE_REPORTED = "equipment.damage_reported"


def register_equipment_subscribers() -> None:
    """Wire equipment event subscribers into the global bus.

    The Gap C cost-rollup subscribers register themselves at import time in
    ``service.py`` (their binding must live in an allowed source file). Importing
    the service module here guarantees they are bound at startup even if nothing
    else has imported it yet. Safe to call more than once (the bindings guard
    against double-registration).
    """
    import app.modules.equipment.service  # noqa: F401
