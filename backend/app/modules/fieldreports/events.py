# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Field Reports event definitions and publishers.

Field reports are the on-site source of truth for labour hours. When a
report is submitted or approved, the workforce log it carries is the
deterministic input for two downstream flows:

* the **cost model** turns ``hours x cost_rate`` into a labour-actuals
  rollup against the project budget (see ``costmodel.events``);
* the **payroll** module aggregates the same hours per worker/date into
  a draft pay batch.

This module owns the canonical event name and a single typed publisher so
both the service layer and any future caller emit an identically-shaped
payload. The payload is intentionally self-contained (it carries the
workforce rows inline) so subscribers never have to re-open the field
report inside a foreign session.

Auto-imported by the module loader when ``oe_fieldreports`` loads
(see ``module_loader._load_module`` -> ``events.py``).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.events import event_bus

logger = logging.getLogger(__name__)

# Canonical event name. ``labour`` (not ``workforce``) so the name reads as
# the business fact ("labour was logged"), matching the cost/payroll vocab.
LABOUR_LOGGED = "fieldreports.labour.logged"


def publish_labour_logged(
    *,
    report_id: str,
    project_id: str,
    report_date: str,
    status: str,
    rows: list[dict[str, Any]],
    actor_id: str | None = None,
) -> None:
    """Publish ``fieldreports.labour.logged`` with the workforce rows inline.

    Args:
        report_id: The field report UUID as a string.
        project_id: Owning project UUID as a string.
        report_date: ISO ``YYYY-MM-DD`` date the labour was performed.
        status: Report status at publish time (``submitted`` / ``approved``).
        rows: Normalised workforce rows. Each row is a dict with at least
            ``worker_type`` and ``hours`` (float); optional ``resource_id``,
            ``cost_rate``, ``currency``, ``overtime_hours``, ``headcount``,
            ``company``, ``wbs_id``, ``cost_category``.
        actor_id: User who triggered the transition, if known.

    The publish is detached (fire-and-forget) so the submitting request can
    commit and release its writer lock before subscribers open a second
    session - identical rationale to ``schedule/events.py``.
    """
    if not rows:
        # Nothing to roll up - skip the bus traffic entirely.
        return
    event_bus.publish_detached(
        LABOUR_LOGGED,
        {
            "report_id": report_id,
            "project_id": project_id,
            "report_date": report_date,
            "status": status,
            "rows": rows,
            "actor_id": actor_id,
        },
        source_module="oe_fieldreports",
    )
    logger.info(
        "Published %s for report=%s (%d workforce rows)",
        LABOUR_LOGGED,
        report_id,
        len(rows),
    )


__all__ = ["LABOUR_LOGGED", "publish_labour_logged"]
