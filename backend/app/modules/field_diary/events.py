# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Field Diary event publishers - feed diary labour into cost / payroll.

When a diary entry is submitted, the work activities it carries (each with
an ``hours`` figure) are a labour signal just like a field report's
workforce log. We publish the *same* canonical
``fieldreports.labour.logged`` event so the cost model and payroll
subscribers have a single code path to roll labour hours up against the
budget and into a draft pay batch.

Auto-imported by the module loader when ``oe_field_diary`` loads.
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.fieldreports.events import LABOUR_LOGGED, publish_labour_logged

logger = logging.getLogger(__name__)

__all__ = ["LABOUR_LOGGED", "publish_diary_labour"]


def publish_diary_labour(
    *,
    entry_id: str,
    project_id: str,
    entry_date: str,
    author_id: str | None,
    activity_rows: list[dict[str, Any]],
) -> None:
    """Publish diary work hours as a ``fieldreports.labour.logged`` event.

    Args:
        entry_id: Diary entry UUID as a string (used as the dedup key).
        project_id: Owning project UUID as a string.
        entry_date: ISO ``YYYY-MM-DD`` date the work was performed.
        author_id: Diary author, surfaced as the labour ``actor_id``.
        activity_rows: Pre-normalised rows, each with ``worker_type`` and
            ``hours`` (float); optional ``resource_id`` / ``cost_rate`` /
            ``currency`` from the activity metadata.

    No-op when there are no labour-bearing rows. The diary entry id is
    forwarded as the labour ``report_id`` so the downstream idempotency key
    ``(report_id, status)`` cannot collide with a real field report.
    """
    if not activity_rows:
        return
    publish_labour_logged(
        report_id=entry_id,
        project_id=project_id,
        report_date=entry_date,
        status="submitted",
        rows=activity_rows,
        actor_id=author_id,
    )
    logger.info(
        "Published %s from diary entry=%s (%d activity rows)",
        LABOUR_LOGGED,
        entry_id,
        len(activity_rows),
    )
