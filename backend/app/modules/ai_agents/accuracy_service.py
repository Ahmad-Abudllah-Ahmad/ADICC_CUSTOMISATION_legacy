# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Accuracy scoreboard service for AI agent runs.

Reads the trust confidence persisted on each :class:`AgentRun` together with a
recorded actual outcome and scores every agent's calibration with the pure
:mod:`app.modules.ai_agents.accuracy` engine. The outcome is stored back inside
the run's ``trust`` JSON (a fresh dict is assigned so SQLAlchemy detects the
change), so no schema migration is needed to turn a stated confidence into a
scored prediction.

Privacy: every read is scoped to the caller's own runs, mirroring the run
detail and insights endpoints, so the scoreboard never exposes another user's
agent activity.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.accuracy import (
    AccuracyScore,
    Prediction,
    clamp01,
    score_by_agent,
)
from app.modules.ai_agents.feedback_summary import (
    FeedbackItem,
    FeedbackSummary,
    summarize_feedback,
)
from app.modules.ai_agents.models import AgentRun, AIFeedback

#: Keys written into the run's trust JSON when an outcome is recorded.
OUTCOME_KEY = "actual_outcome"
OUTCOME_AT_KEY = "outcome_recorded_at"
OUTCOME_BY_KEY = "outcome_recorded_by"
OUTCOME_NOTE_KEY = "outcome_note"


def _demo_mode_enabled() -> bool:
    """Whether this deployment is the public hosted demo (``OE_DEMO_MODE`` set).

    Mirrors the same env check the sandbox-seeding endpoint guards on, so the
    seeded sample runs only ever count toward the scoreboard on the demo box.
    """
    return os.environ.get("OE_DEMO_MODE", "").lower() in ("1", "true", "yes")


def _is_sample_run(trigger_source: object, trust: object) -> bool:
    """Whether a run row is seeded sandbox sample data.

    Checks both markers the seeder writes - the ``trigger_source`` column and the
    ``trust["sample"]`` flag - so a sample row is recognised even if only one
    marker survives. The sandbox constants are imported lazily to avoid a module
    import cycle (``sandbox`` already imports the outcome keys from this module).
    """
    from app.modules.ai_agents.sandbox import SAMPLE_FLAG_KEY, SAMPLE_TRIGGER_SOURCE

    if trigger_source == SAMPLE_TRIGGER_SOURCE:
        return True
    return isinstance(trust, dict) and bool(trust.get(SAMPLE_FLAG_KEY))


def _confidence_of(trust: object) -> float | None:
    """Extract a usable [0,1] confidence from a run's trust JSON, or None."""
    if not isinstance(trust, dict):
        return None
    raw = trust.get("confidence")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return clamp01(float(raw))
    except (TypeError, ValueError):
        return None


def _outcome_of(trust: object) -> bool | None:
    """Extract the recorded actual outcome from a run's trust JSON, or None."""
    if not isinstance(trust, dict):
        return None
    value = trust.get(OUTCOME_KEY)
    return value if isinstance(value, bool) else None


async def record_run_outcome(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    correct: bool,
    recorded_by: uuid.UUID,
    note: str | None = None,
) -> AgentRun | None:
    """Record whether an agent run turned out correct, scoped to its owner.

    Returns the updated run, or ``None`` when the run does not exist or does not
    belong to *recorded_by* (so a caller can never write an outcome onto another
    user's run). The outcome is merged into a fresh copy of the trust JSON.
    """
    run = (
        await session.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == recorded_by))
    ).scalar_one_or_none()
    if run is None:
        return None

    trust = dict(run.trust) if isinstance(run.trust, dict) else {}
    trust[OUTCOME_KEY] = bool(correct)
    trust[OUTCOME_AT_KEY] = datetime.now(UTC).isoformat()
    trust[OUTCOME_BY_KEY] = str(recorded_by)
    if note:
        trust[OUTCOME_NOTE_KEY] = note
    run.trust = trust  # reassign so the JSON column change is flushed
    await session.flush()
    return run


async def record_ai_feedback(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    surface: str,
    correct: bool,
    project_id: uuid.UUID | None = None,
    ref: str | None = None,
    note: str | None = None,
) -> AIFeedback:
    """Persist a correct / incorrect verdict on a non-run AI surface.

    The generic trust-loop sink for AI outputs that have no agent-run row (the
    AI Estimator result, a match suggestion, an advisor answer). Always scoped
    to *user_id*; ``project_id`` is verified by the caller before this runs. The
    row is flushed (not committed) so the route owns the transaction boundary.
    """
    row = AIFeedback(
        user_id=user_id,
        project_id=project_id,
        surface=surface.strip()[:40],
        ref=(ref.strip()[:200] if ref and ref.strip() else None),
        correct=bool(correct),
        note=(note.strip()[:2000] if note and note.strip() else None),
    )
    session.add(row)
    await session.flush()
    return row


async def build_scoreboard(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    agent_name: str | None = None,
) -> list[AccuracyScore]:
    """Score each agent's calibration over the caller's own scored runs.

    A run contributes a prediction only when it carries both a usable trust
    confidence and a recorded actual outcome. Results are ordered by agent name
    for a stable response.

    Defense-in-depth: seeded sandbox sample runs are excluded from the aggregate
    unless this is the hosted demo box (``OE_DEMO_MODE``). The sandbox-seeding
    endpoint is already demo-gated, so this only matters if a box was once run in
    demo mode and later carries real runs - there, a misconfigured demo flag can
    no longer blend illustrative sample numbers into genuine accuracy. On the demo
    the sample rows still count, so the scoreboard lights up as intended.
    """
    stmt = select(AgentRun.agent_name, AgentRun.trust, AgentRun.trigger_source).where(AgentRun.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(AgentRun.project_id == project_id)
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)

    include_samples = _demo_mode_enabled()
    predictions: list[Prediction] = []
    for row in (await session.execute(stmt)).all():
        if not include_samples and _is_sample_run(row.trigger_source, row.trust):
            continue
        confidence = _confidence_of(row.trust)
        outcome = _outcome_of(row.trust)
        if confidence is None or outcome is None:
            continue
        predictions.append(Prediction(agent_name=row.agent_name, confidence=confidence, outcome=outcome))

    scored = score_by_agent(predictions)
    return [scored[name] for name in sorted(scored)]


async def build_feedback_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    surface: str | None = None,
) -> FeedbackSummary:
    """Roll up the caller's AI feedback verdicts overall and per surface.

    Turns the write-only ``oe_ai_feedback`` sink into a readable signal: how the
    AI Estimator, match suggestions and advisor answers are actually landing for
    this user. Scoped to the caller's own verdicts (mirrors :func:`build_scoreboard`
    privacy, so it never exposes another user's feedback), optionally narrowed to
    one project or one surface. The ``user_id`` filter is the security boundary,
    so no project-access check is needed: a caller only ever sees rows they wrote.
    """
    stmt = select(AIFeedback.surface, AIFeedback.correct).where(AIFeedback.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(AIFeedback.project_id == project_id)
    if surface:
        stmt = stmt.where(AIFeedback.surface == surface.strip()[:40])

    items = [
        FeedbackItem(surface=row.surface, correct=bool(row.correct)) for row in (await session.execute(stmt)).all()
    ]
    return summarize_feedback(items)
