# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll domain events.

The payroll module talks to the rest of the platform through the global
:data:`app.core.events.event_bus`. Events are addressed by their dot-notation
name (``{module}.{entity}.{action}``); this module is the single place those
names are declared so publishers and subscribers agree on one spelling.

Published events:

* :data:`EVENT_PAYROLL_BATCH_FINALIZED` - emitted by
  :meth:`PayrollService.finalize_batch` whenever a draft batch transitions to
  ``approved`` and its labour cost is posted onto the cost-spine budget line
  (Gap A). The payload carries ``project_id``, ``batch_id``, the posted
  ``amount`` (project base currency, Decimal-as-string), ``currency`` and
  ``budget_line_id`` (the cost-spine row the actual landed on). Reporting and
  cost-overrun consumers may subscribe for eventual-consistency rollups.

The actual-cost posting itself is owned by the cost-model module (Gap B's
``CostSpineService.post_actual_to_budget_line``), which emits its own
``costmodel.budget_line.actual_posted`` event; this module only announces the
batch-level lifecycle transition.
"""

from __future__ import annotations

import logging

from app.core.events import event_bus

# ── Published event names ───────────────────────────────────────────────────

EVENT_PAYROLL_BATCH_FINALIZED = "payroll.batch.finalized"
EVENT_PAYROLL_BATCH_SUBMITTED = "payroll.batch.submitted"
EVENT_PAYROLL_BATCH_POSTED = "payroll.batch.posted"

_logger = logging.getLogger(__name__)


async def safe_publish(name: str, data: dict, source_module: str = "oe_payroll") -> None:
    """Publish an event without ever letting a bus failure break the caller.

    Finalize is a money-posting transaction; an event-publish hiccup (no
    subscribers, a slow handler, a serialisation edge case) must never roll back
    or 500 the request. Mirrors the cost-model module's ``_safe_publish``.
    """
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:  # pragma: no cover - defensive, bus is best-effort
        _logger.debug("Event publish skipped: %s", name)
