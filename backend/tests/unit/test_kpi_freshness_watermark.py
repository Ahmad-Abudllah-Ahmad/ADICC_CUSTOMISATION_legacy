# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""KPI/EVM freshness watermark (Wave 2, item #3).

The BI dashboards module keeps an in-process watermark per project. When an
upstream data change fans out as ``bi_dashboards.kpi_recompute`` the watermark
advances; the frontend polls a cheap freshness endpoint and refetches the heavy
EVM/KPI payload when ``invalidated_at`` moves past the value it last saw. This
is the event-driven live-refresh signal, so no DB or WebSocket is involved and
the tests run without booting PostgreSQL.
"""

from __future__ import annotations

import pytest

from app.core.events import Event
from app.modules.bi_dashboards import events as bi_events


def test_freshness_reports_server_start_with_no_invalidation() -> None:
    """A project that was never invalidated still reports server_started_at."""
    fresh = bi_events.get_kpi_freshness("00000000-0000-0000-0000-0000000000ff")
    assert fresh["server_started_at"]
    # invalidated_at is either None (never) or a prior global bump; the contract
    # is only that the key exists and server_started_at is present.
    assert "invalidated_at" in fresh


def test_bump_advances_project_watermark() -> None:
    pid = "11111111-1111-1111-1111-111111111111"
    before = bi_events.get_kpi_freshness(pid)["invalidated_at"]
    bi_events._bump_watermark(pid, reason="costmodel_change", source_event="costmodel.budget_line.updated")
    after = bi_events.get_kpi_freshness(pid)
    assert after["invalidated_at"] is not None
    assert after["invalidated_at"] != before
    assert after["reason"] == "costmodel_change"
    assert after["source_event"] == "costmodel.budget_line.updated"


def test_unknown_project_falls_back_to_global_watermark() -> None:
    bi_events._bump_watermark(
        "22222222-2222-2222-2222-222222222222",
        reason="schedule_progress",
        source_event="schedule.activity.progress_updated",
    )
    # A project with no specific entry sees the most recent global watermark.
    other = bi_events.get_kpi_freshness("33333333-3333-3333-3333-333333333333")
    assert other["invalidated_at"] is not None
    assert other["reason"] == "schedule_progress"


@pytest.mark.asyncio
async def test_kpi_recompute_handler_bumps_watermark() -> None:
    pid = "44444444-4444-4444-4444-444444444444"
    event = Event(
        name="bi_dashboards.kpi_recompute",
        data={
            "project_id": pid,
            "reason": "upstream_event",
            "source_event": "invoice.paid",
        },
        source_module="bi_dashboards",
    )
    await bi_events._on_kpi_recompute(event)
    fresh = bi_events.get_kpi_freshness(pid)
    assert fresh["invalidated_at"] is not None
    assert fresh["source_event"] == "invoice.paid"
