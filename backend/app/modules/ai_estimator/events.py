# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder lifecycle events.

The service emits run-lifecycle events on the platform event bus via
``publish_detached`` (fire-and-forget so the request commits and releases the
DB writer before any subscriber opens a second session). No new machinery -
this mirrors the ``validation.report.created`` / ``ai_agents`` event contracts.

Emitted events (names are stable - subscribers key off them):

* ``ai_estimator.run.started``     - a run kicked off stage 1.
* ``ai_estimator.stage.completed`` - a pipeline stage finished
                                     (``data['stage']`` names it).
* ``ai_estimator.run.applied``     - the assembled estimate was written to a
                                     BOQ (``data['boq_id']`` / counts).
* ``ai_estimator.run.failed``      - a run failed (``data['failure_reason']``).

This module is imported by the module loader at load time (the
``events``-autodiscovery contract). It currently only declares the event
catalogue; there are no in-module subscribers (the events are for cross-module
listeners such as notifications / audit / the vector indexer). The publish
helpers live here so the service imports one place.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.events import event_bus

logger = logging.getLogger(__name__)

EVENT_RUN_STARTED = "ai_estimator.run.started"
EVENT_STAGE_COMPLETED = "ai_estimator.stage.completed"
EVENT_RUN_APPLIED = "ai_estimator.run.applied"
EVENT_RUN_FAILED = "ai_estimator.run.failed"


def _publish(event_name: str, data: dict[str, Any]) -> None:
    """Fire-and-forget publish; never raises into the caller's request path."""
    try:
        event_bus.publish_detached(event_name, data, source_module="oe_ai_estimator")
    except Exception as exc:  # noqa: BLE001 - an event publish must never break a run
        logger.warning("ai_estimator: failed to publish %s: %s", event_name, exc)


def emit_run_started(*, run_id: str, project_id: str, source: str | None) -> None:
    """Announce that a run started stage 1 (source understanding)."""
    _publish(EVENT_RUN_STARTED, {"run_id": run_id, "project_id": project_id, "source": source or ""})


def emit_stage_completed(*, run_id: str, project_id: str, stage: str) -> None:
    """Announce that one pipeline stage finished for a run."""
    _publish(EVENT_STAGE_COMPLETED, {"run_id": run_id, "project_id": project_id, "stage": stage})


def emit_run_applied(*, run_id: str, project_id: str, boq_id: str, positions_created: int) -> None:
    """Announce that the assembled estimate was written to a BOQ."""
    _publish(
        EVENT_RUN_APPLIED,
        {
            "run_id": run_id,
            "project_id": project_id,
            "boq_id": boq_id,
            "positions_created": positions_created,
        },
    )


def emit_run_failed(*, run_id: str, project_id: str, failure_reason: str) -> None:
    """Announce that a run failed, with the structured reason."""
    _publish(
        EVENT_RUN_FAILED,
        {"run_id": run_id, "project_id": project_id, "failure_reason": failure_reason},
    )
