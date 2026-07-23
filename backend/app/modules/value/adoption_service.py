# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Thin database layer for the guided adoption checklist (#22).

Reads one project's PRESENT STATE and projects it onto the set of action keys
the pure :mod:`app.modules.value.adoption_checklist` engine understands, then
asks the engine which first-value steps are done, what the weighted adoption
score is, and which few steps to nudge next.

Why project state, not the activity log: a guided "have you done X yet" checklist
for a single project is answered most honestly by whether the thing actually
EXISTS - a bill of quantities in the project, a takeoff measurement, an approval
that ran, a logged change, an AI run and a recorded verdict - not by whether a
particular event happened to land in the activity log. The activity-log
vocabulary is heterogeneous across modules and several first-value milestones
leave no single canonical row, so existence is both clearer and more robust than
event-name matching. The two milestones with no table of their own - assembling
an evidence pack and generating a value report, both composed on the fly - are
read from the activity-log rows those deliberate actions land
(``claims_evidence`` / ``evidence_pack_assembled``, written when a reconstructed
pack is exported, and ``value`` / ``report_generated``, written by the value
router's POST ``.../report``), scoped to the project exactly like the timeline
and the hours-saved signal.

The engine stays pure: this module decides the observed-key SET, the engine
decides done-ness and the score. Every read is project-scoped and read-only; the
request-scoped session owns the commit and this layer only ever queries. Nothing
is invented: a milestone with no detectable trace simply stays absent, so the
engine reports it as a next action rather than as done.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import ActivityLog
from app.modules.ai_agents.models import AgentRun
from app.modules.approval_routes.models import Instance as ApprovalInstance
from app.modules.approval_routes.models import Route as ApprovalRoute
from app.modules.boq.models import BOQ
from app.modules.changeorders.models import ChangeOrder
from app.modules.takeoff.models import TakeoffMeasurement
from app.modules.value.adoption_checklist import AdoptionChecklist, evaluate

# --------------------------------------------------------------------------- #
# Observed action keys. These MUST match the ``action_keys`` the engine's
# ADOPTION_STEPS catalogue accepts; the service decides which are present from
# project state and the engine matches them. Defined as constants so a test can
# reference them without re-typing the dotted strings.
# --------------------------------------------------------------------------- #

#: Project setup. The checklist is always scoped to an existing project, so this
#: is observed unconditionally - reaching the checklist means a project exists.
KEY_PROJECT_CREATED = "project.created"
#: A bill of quantities belongs to the project.
KEY_BOQ = "boq.created"
#: A takeoff measurement was produced for the project.
KEY_TAKEOFF = "takeoff.parsed"
#: An approval instance ran against a route that belongs to the project.
KEY_APPROVAL = "approval.route.started"
#: A change order is logged against the project.
KEY_CHANGE_ORDER = "change_order.logged"
#: An AI agent run is recorded against the project.
KEY_AI_RUN = "ai_agents.run.created"
#: An AI run's actual outcome (the human verdict) has been recorded.
KEY_AI_VERDICT = "ai_agents.outcome.recorded"
#: An evidence pack was assembled (read from the activity-log row assembly lands).
KEY_EVIDENCE_PACK = "claims_evidence.evidence_pack.assembled"
#: A value report was generated (read from the activity-log row generation lands).
KEY_VALUE_REPORT = "value.report.generated"

# The activity-log coordinates the evidence-pack assembly already records. The
# pack itself is computed on the fly and has no table, so this row is the only
# durable trace that assembly happened. ``module`` / ``action`` match the
# ``time_saved`` factor key (("claims_evidence", "evidence_pack_assembled")).
_EVIDENCE_MODULE = "claims_evidence"
_EVIDENCE_ACTION = "evidence_pack_assembled"

# The activity-log coordinates a value-report generation records (see the value
# router's POST .../report). Like the pack, a value report is composed on the fly
# and has no table, so this row is its durable trace.
_VALUE_REPORT_MODULE = "value"
_VALUE_REPORT_ACTION = "report_generated"

# Key inside ``AgentRun.trust`` (JSON) that holds the recorded verdict. Mirrors
# ``app.modules.ai_agents.accuracy_service.OUTCOME_KEY``; kept as a literal here
# so this read-only layer does not import the accuracy service.
_OUTCOME_KEY = "actual_outcome"


async def _exists(session: AsyncSession, id_select) -> bool:  # type: ignore[no-untyped-def]
    """Whether *id_select* (a ``select(Model.id).where(...)``) matches any row.

    Caps the query at one row and tests for a returned id, so an existence check
    never scans more than it must and never materialises a row it does not need.
    """
    return (await session.scalar(id_select.limit(1))) is not None


async def _activity_exists(
    session: AsyncSession,
    project_id_str: str,
    module: str,
    action: str,
) -> bool:
    """Whether a project-scoped activity-log row with *module* / *action* exists.

    Used for the milestones that leave only an activity-log trace (an assembled
    evidence pack, a generated value report). Scoped the same way the timeline
    and hours-saved signals are: the row's ``parent_entity_id`` (a module event
    rolled up to its project) or ``entity_id`` is the project.
    """
    stmt = select(ActivityLog.id).where(
        or_(ActivityLog.parent_entity_id == project_id_str, ActivityLog.entity_id == project_id_str),
        ActivityLog.module == module,
        ActivityLog.action == action,
    )
    return await _exists(session, stmt)


async def _has_recorded_verdict(session: AsyncSession, project_id: uuid.UUID) -> bool:
    """Whether any of the project's AI runs carries a recorded verdict.

    The verdict lives inside the run's ``trust`` JSON envelope (under
    ``actual_outcome``), so this reads the envelopes of the project's runs that
    have one and stops at the first with the key set. Run counts per project are
    modest, and only runs whose ``trust`` is non-null are fetched.
    """
    stmt = select(AgentRun.trust).where(
        AgentRun.project_id == project_id,
        AgentRun.trust.isnot(None),
    )
    for trust in (await session.scalars(stmt)).all():
        if isinstance(trust, dict) and trust.get(_OUTCOME_KEY) is not None:
            return True
    return False


async def gather_observed_action_keys(session: AsyncSession, project_id: uuid.UUID) -> frozenset[str]:
    """Project one project's present state onto observed adoption action keys.

    Each membership reflects a real, durable fact about the project: a BOQ
    exists, a takeoff measurement exists, an approval instance ran against one of
    the project's routes, a change order is logged, an AI run exists, a verdict
    was recorded, an evidence pack was assembled. Project setup is always
    observed (the checklist is project-scoped). Nothing is invented: a milestone
    with no detectable trace simply stays absent, so the engine reports it as a
    next action rather than as done.
    """
    pid = project_id
    observed: set[str] = {KEY_PROJECT_CREATED}

    if await _exists(session, select(BOQ.id).where(BOQ.project_id == pid)):
        observed.add(KEY_BOQ)

    if await _exists(session, select(TakeoffMeasurement.id).where(TakeoffMeasurement.project_id == pid)):
        observed.add(KEY_TAKEOFF)

    approval_started = (
        select(ApprovalInstance.id)
        .join(ApprovalRoute, ApprovalRoute.id == ApprovalInstance.route_id)
        .where(ApprovalRoute.project_id == pid)
    )
    if await _exists(session, approval_started):
        observed.add(KEY_APPROVAL)

    if await _exists(session, select(ChangeOrder.id).where(ChangeOrder.project_id == pid)):
        observed.add(KEY_CHANGE_ORDER)

    if await _exists(session, select(AgentRun.id).where(AgentRun.project_id == pid)):
        observed.add(KEY_AI_RUN)

    if await _has_recorded_verdict(session, pid):
        observed.add(KEY_AI_VERDICT)

    pid_str = str(pid)
    if await _activity_exists(session, pid_str, _EVIDENCE_MODULE, _EVIDENCE_ACTION):
        observed.add(KEY_EVIDENCE_PACK)

    if await _activity_exists(session, pid_str, _VALUE_REPORT_MODULE, _VALUE_REPORT_ACTION):
        observed.add(KEY_VALUE_REPORT)

    return frozenset(observed)


async def build_adoption_checklist(
    session: AsyncSession,
    project_id: uuid.UUID,
    role: str,
) -> AdoptionChecklist:
    """Build one project's guided adoption checklist for *role*.

    Resolves the observed action keys from project state
    (:func:`gather_observed_action_keys`) and runs them through the pure engine,
    which returns the role's applicable steps with their done flags, the weighted
    adoption score and the leading incomplete steps to nudge. An unknown role
    sees only the globally scoped steps (the engine's honest default).
    """
    observed = await gather_observed_action_keys(session, project_id)
    return evaluate(role, observed)
