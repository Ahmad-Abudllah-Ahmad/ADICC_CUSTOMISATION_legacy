# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Seeded AI sandbox - "see AI in practice" sample runs.

A prospect evaluating the hosted demo arrives with no data and (usually) no
configured LLM, so every AI surface renders an empty state and the accuracy
scoreboard - the trust moat - shows nothing. That is the worst possible first
impression for a buyer whose #1 stated barrier is "can I trust the AI".

This module seeds a small, clearly-labeled set of already-scored agent runs for
the current user. Each run carries a full trust envelope (calibrated confidence,
rationale, real-looking cited sources, and "what would increase confidence")
plus a recorded outcome, so the existing read paths light up immediately:

* ``build_scoreboard`` scores them (each run has both a confidence and an
  ``actual_outcome``), so the calibration scoreboard renders populated, and
* the run list + trust panels show realistic analytical answers with citations.

It writes NOTHING that a real install would not already support: rows go into
``oe_ai_agents_run`` exactly like a genuine run, tagged ``trigger_source=
"sample"`` and ``trust["sample"]=true`` so they are identifiable and removable.
There is no new table and no new engine - the accuracy engine runs unchanged
over the seeded rows.

The seed is deterministic (each run's primary key is derived with ``uuid5`` from
the user id), so calling it more than once is idempotent: the second call
creates nothing. Seeding is scoped per user because the scoreboard is per user.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.accuracy_service import (
    OUTCOME_AT_KEY,
    OUTCOME_BY_KEY,
    OUTCOME_KEY,
)
from app.modules.ai_agents.models import AgentRun

#: Fixed namespace for deriving deterministic, idempotent run ids per user.
SANDBOX_NAMESPACE = uuid.UUID("5e1f9c40-2a25-4d00-8c00-00000000a125")

#: Markers that flag a row as sandbox sample data (identifiable + removable).
SAMPLE_TRIGGER_SOURCE = "sample"
SAMPLE_FLAG_KEY = "sample"
SAMPLE_MODEL = "sample"

#: The sample runs. Three analytical agents that genuinely emit a trust
#: envelope, each with a few mixed-outcome runs so the scoreboard shows a real
#: calibration story (project/estimate agents land well calibrated; the
#: schedule agent reads slightly over-confident - an honest result, not a
#: rubber stamp). Money figures are illustrative and currency-neutral. The
#: timestamps are fixed (not clock-derived) so the seed is fully deterministic.
SAMPLE_RUNS: tuple[dict, ...] = (
    {
        "agent_name": "project_analyst",
        "user_input": "Where are we against budget on the curtain wall package?",
        "final_output": (
            "The curtain wall package is tracking close to budget. Approved budget 1,250,000. "
            "Committed 1,180,000 across four purchase orders, with 62,000 still uncommitted. "
            "Actuals to date 940,000. No commitment exceeds its line budget, so the package is on "
            "track unless the two open variations are approved."
        ),
        "confidence": 0.88,
        "correct": True,
        "rationale": (
            "Committed plus actuals reconcile to the cost ledger within rounding, and every "
            "commitment maps to an approved budget line."
        ),
        "sources": [
            {"kind": "boq", "ref": "BOQ-CW-01", "label": "Curtain wall BOQ"},
            {"kind": "cost_item", "ref": "COMM-2291", "label": "Committed costs"},
        ],
        "what_would_increase_confidence": "Confirm whether the two open variations will be approved this period.",
        "iterations": 4,
        "total_tokens": 2840,
        "started_at": "2026-06-25T14:32:00+00:00",
        "finished_at": "2026-06-25T14:33:12+00:00",
    },
    {
        "agent_name": "project_analyst",
        "user_input": "Is the substructure trade trending over its budget?",
        "final_output": (
            "Substructure is trending slightly under budget. Approved 820,000, committed 805,000, "
            "actuals 770,000. The remaining works are fully covered by existing commitments, so no "
            "overrun is expected on the current scope."
        ),
        "confidence": 0.72,
        "correct": True,
        "rationale": "The remaining scope is fully committed, so the forecast has little open exposure.",
        "sources": [
            {"kind": "boq", "ref": "BOQ-SUB-03", "label": "Substructure BOQ"},
        ],
        "what_would_increase_confidence": "Verify there are no pending site instructions that would add scope.",
        "iterations": 3,
        "total_tokens": 2110,
        "started_at": "2026-06-25T13:10:00+00:00",
        "finished_at": "2026-06-25T13:11:05+00:00",
    },
    {
        "agent_name": "project_analyst",
        "user_input": "What is the likely final cost of the MEP package?",
        "final_output": (
            "Forecast final cost for MEP is about 2,150,000 against an approved budget of 2,050,000, "
            "a projected overrun near 5 percent driven by ductwork rates. This is a forecast and "
            "depends on three rates that are not yet locked."
        ),
        "confidence": 0.5,
        "correct": False,
        "rationale": "The forecast leans on unlocked ductwork rates, so the projection is uncertain.",
        "sources": [
            {"kind": "boq", "ref": "BOQ-MEP-02", "label": "MEP BOQ"},
            {"kind": "cost_item", "ref": "FCT-MEP", "label": "MEP forecast"},
        ],
        "what_would_increase_confidence": "Lock the three outstanding ductwork rates and re-run the forecast.",
        "iterations": 5,
        "total_tokens": 3520,
        "started_at": "2026-06-25T11:48:00+00:00",
        "finished_at": "2026-06-25T11:49:20+00:00",
    },
    {
        "agent_name": "estimate_reviewer",
        "user_input": "Audit the concrete BOQ for missing or zero rates.",
        "final_output": (
            "The concrete BOQ has 142 priced lines and 3 lines with a zero rate: two formwork items "
            "and one curing item. Filling these three gaps adds an estimated 18,400 to the section "
            "total. No duplicate descriptions were found."
        ),
        "confidence": 0.91,
        "correct": True,
        "rationale": "Zero-rate lines are read directly from the BOQ, so the gap list is exact.",
        "sources": [
            {"kind": "boq", "ref": "BOQ-CONC-01", "label": "Concrete BOQ"},
        ],
        "what_would_increase_confidence": "Confirm the intended rate for the curing item, which has no comparable line.",
        "iterations": 4,
        "total_tokens": 2670,
        "started_at": "2026-06-24T16:20:00+00:00",
        "finished_at": "2026-06-24T16:21:30+00:00",
    },
    {
        "agent_name": "estimate_reviewer",
        "user_input": "Are there duplicate line items in the groundworks BOQ?",
        "final_output": (
            "Two probable duplicates were found in groundworks: an excavation line repeated under two "
            "sections and a disposal line with near-identical wording. Together they may double-count "
            "about 9,500. Review before tender."
        ),
        "confidence": 0.66,
        "correct": True,
        "rationale": "The matches are based on description similarity, so they are likely but not certain duplicates.",
        "sources": [
            {"kind": "boq", "ref": "BOQ-GRND-02", "label": "Groundworks BOQ"},
        ],
        "what_would_increase_confidence": "Have the estimator confirm whether the two excavation lines cover different areas.",
        "iterations": 3,
        "total_tokens": 1980,
        "started_at": "2026-06-24T15:02:00+00:00",
        "finished_at": "2026-06-24T15:03:10+00:00",
    },
    {
        "agent_name": "estimate_reviewer",
        "user_input": "Is the structural steel priced consistently across sections?",
        "final_output": (
            "Structural steel rates look broadly consistent, from 1,820 to 1,910 per tonne, except one "
            "section at 2,240 per tonne. The outlier appears to include erection that other sections "
            "price separately, so the estimate may be sound rather than wrong."
        ),
        "confidence": 0.6,
        "correct": False,
        "rationale": "The outlier could be a pricing error or a legitimate scope difference; the data does not settle which.",
        "sources": [
            {"kind": "boq", "ref": "BOQ-STL-04", "label": "Structural steel BOQ"},
        ],
        "what_would_increase_confidence": "Check whether the high section includes erection within the rate.",
        "iterations": 4,
        "total_tokens": 2400,
        "started_at": "2026-06-24T10:35:00+00:00",
        "finished_at": "2026-06-24T10:36:25+00:00",
    },
    {
        "agent_name": "schedule_analyst",
        "user_input": "Explain the SPI and CPI on the latest update in plain terms.",
        "final_output": (
            "Schedule performance index is 0.94 and cost performance index is 1.02. In plain terms the "
            "project is slightly behind schedule but a little under budget. The slip is concentrated in "
            "the facade works, not spread across the programme."
        ),
        "confidence": 0.88,
        "correct": True,
        "rationale": "SPI and CPI come straight from the earned-value snapshot, so the read is reliable.",
        "sources": [
            {"kind": "schedule", "ref": "EVM-2026-06", "label": "June EVM snapshot"},
        ],
        "what_would_increase_confidence": "Confirm the facade progress claim that drives most of the variance.",
        "iterations": 3,
        "total_tokens": 2050,
        "started_at": "2026-06-23T17:14:00+00:00",
        "finished_at": "2026-06-23T17:15:00+00:00",
    },
    {
        "agent_name": "schedule_analyst",
        "user_input": "Which activities are driving the critical path slip?",
        "final_output": (
            "Three activities drive the current slip: curtain wall installation, level 6 fit-out start, "
            "and roof waterproofing. Curtain wall is the largest contributor at about nine days. The "
            "other two follow it, so recovering curtain wall recovers most of the slip."
        ),
        "confidence": 0.84,
        "correct": True,
        "rationale": "The driving activities are read from the critical path in the current programme.",
        "sources": [
            {"kind": "schedule", "ref": "CPM-R12", "label": "Programme revision 12"},
        ],
        "what_would_increase_confidence": "Verify the curtain wall delivery date that the path depends on.",
        "iterations": 4,
        "total_tokens": 2360,
        "started_at": "2026-06-23T16:40:00+00:00",
        "finished_at": "2026-06-23T16:41:15+00:00",
    },
    {
        "agent_name": "schedule_analyst",
        "user_input": "Will we recover the two-week slip by the next milestone?",
        "final_output": (
            "Recovery of the full two-week slip by the next milestone is unlikely on the current logic. "
            "Even with the proposed acceleration on curtain wall, the model recovers about eight of the "
            "ten days. A logic change or added resource would be needed to close the gap."
        ),
        "confidence": 0.8,
        "correct": False,
        "rationale": "Recovery depends on an acceleration that is proposed but not yet committed, so the outcome is uncertain.",
        "sources": [
            {"kind": "schedule", "ref": "CPM-R12", "label": "Programme revision 12"},
        ],
        "what_would_increase_confidence": "Confirm whether the curtain wall acceleration will be resourced.",
        "iterations": 5,
        "total_tokens": 3180,
        "started_at": "2026-06-23T09:25:00+00:00",
        "finished_at": "2026-06-23T09:26:30+00:00",
    },
)


def _sample_run_id(user_id: uuid.UUID, index: int) -> uuid.UUID:
    """Derive a stable run id for sample ``index`` of ``user_id`` (idempotent)."""
    return uuid.uuid5(SANDBOX_NAMESPACE, f"{user_id}:{index}")


def _build_trust(spec: dict, user_id: uuid.UUID) -> dict:
    """Build the run's trust envelope, pre-scored with the recorded outcome."""
    return {
        "confidence": spec["confidence"],
        "rationale": spec["rationale"],
        "sources": [dict(s) for s in spec["sources"]],
        "what_would_increase_confidence": spec["what_would_increase_confidence"],
        "model": SAMPLE_MODEL,
        SAMPLE_FLAG_KEY: True,
        OUTCOME_KEY: bool(spec["correct"]),
        OUTCOME_AT_KEY: spec["finished_at"],
        OUTCOME_BY_KEY: str(user_id),
    }


async def seed_sandbox_runs(session: AsyncSession, *, user_id: uuid.UUID) -> dict[str, object]:
    """Seed the sample scored agent runs for ``user_id`` (idempotent).

    Returns a small summary: how many runs were created this call, the total
    number of sample runs, and the distinct agent names. A second call creates
    nothing because the run ids are derived deterministically from the user id.
    """
    ids = [_sample_run_id(user_id, i) for i in range(len(SAMPLE_RUNS))]
    existing = set(
        (await session.execute(select(AgentRun.id).where(AgentRun.user_id == user_id, AgentRun.id.in_(ids))))
        .scalars()
        .all()
    )

    new_runs: list[AgentRun] = []
    for index, spec in enumerate(SAMPLE_RUNS):
        run_id = ids[index]
        if run_id in existing:
            continue
        new_runs.append(
            AgentRun(
                id=run_id,
                agent_name=spec["agent_name"],
                project_id=None,
                user_id=user_id,
                status="completed",
                trigger_source=SAMPLE_TRIGGER_SOURCE,
                failure_reason=None,
                user_input=spec["user_input"],
                final_output=spec["final_output"],
                iterations=spec["iterations"],
                total_tokens=spec["total_tokens"],
                started_at=spec["started_at"],
                finished_at=spec["finished_at"],
                trust=_build_trust(spec, user_id),
            )
        )

    if new_runs:
        session.add_all(new_runs)
        await session.flush()

    return {
        "created": len(new_runs),
        "total": len(SAMPLE_RUNS),
        "agents": sorted({spec["agent_name"] for spec in SAMPLE_RUNS}),
    }
