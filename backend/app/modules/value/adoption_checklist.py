# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure per-role adoption checklist + adoption score.

Buying the platform is one thing; getting a team to actually USE the parts that
create value is the harder problem the change-and-AI survey keeps surfacing -
rollout, training and "guided adoption" are repeatedly named as what separates a
tool that pays off from shelfware. This engine answers a concrete operational
question for a single user or a whole team: given what they have ACTUALLY done
on the platform, what should they do next, and how far along the first-value
path are they?

The model is deliberately a transparent, ordered checklist, not a black box.
There is a built-in catalogue of first-value steps (:data:`ADOPTION_STEPS`),
ordered by a natural onboarding sequence - create a project, import a bill of
quantities, run a takeoff, route an approval, log a change, run an AI agent,
record the AI's verdict, assemble an evidence pack, generate a value report.
Each step names the platform action keys that mark it done. The integrator
feeds in the SET of action keys a user (or team member) has been observed
performing - these come straight from the activity log - and the engine reports,
per role, which steps are done, a weighted completion score, and the next few
incomplete steps to nudge.

Honesty rules, same spirit as the other value engines:

* A step is done if ANY of its action keys has been observed. We never invent
  progress: an unrecognised action key simply matches nothing.
* The adoption score is a weighted percent of completed steps out of the steps
  that apply to the role - never out of steps the role was never asked to do, so
  a field user is not penalised for not running an estimate.
* Steps can be scoped to specific roles (:attr:`ChecklistStep.role_scope`); an
  empty scope means the step applies to everyone. :func:`steps_for_role`
  resolves that filter once so the score denominator and the checklist agree.

No database, no ORM, no ``app.*`` imports - stdlib only, and written to run on
the local Python 3.11 test runner exactly like the other pure value engines.
The thin service layer (written separately) reads the activity log, projects it
onto a set of observed action keys per user, and calls in here. Nothing here is
money, so there is no Decimal arithmetic; the only number produced is an integer
percent in ``[0, 100]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# Role vocabulary. These are generic, brand-neutral role tokens the integrator
# maps its real roles onto. They are exposed as constants so a service / test
# can reference them without hard-coding strings, but role_scope accepts ANY
# string - an unknown role simply sees only the globally scoped steps.
# --------------------------------------------------------------------------- #

#: Project / commercial lead - the role that owns project setup and reporting.
ROLE_MANAGER = "manager"

#: Estimator / quantity surveyor - the role that prices scope from a takeoff.
ROLE_ESTIMATOR = "estimator"

#: Field / site role - day-to-day execution, lighter on the office workflows.
ROLE_FIELD = "field"

#: Reviewer / approver - the role that signs off routed work.
ROLE_REVIEWER = "reviewer"

# --------------------------------------------------------------------------- #
# Default laggard threshold for team rollups. A member at or below this adoption
# score is flagged as a laggard - someone the rollout still needs to reach.
# 50 is the midpoint of the [0, 100] score range: on balance a member at or
# under it has done less than half of what their role's first-value path asks.
# --------------------------------------------------------------------------- #

#: A team member with ``adoption_score <= this`` is reported as a laggard.
DEFAULT_LAGGARD_THRESHOLD = 50

#: How many incomplete steps :func:`evaluate` surfaces as "do these next". Three
#: is enough to give direction without overwhelming a just-started user with the
#: whole remaining backlog at once.
DEFAULT_NEXT_ACTIONS = 3


@dataclass(frozen=True)
class ChecklistStep:
    """One first-value action on the adoption path.

    ``key`` is a stable, opaque identifier for the step (used to dedupe and to
    line up a step with its status). ``label`` is a short human description.
    ``module`` is the platform area the step belongs to, for grouping in the UI.
    ``action_keys`` is the tuple of activity-log action keys that count as having
    DONE this step - any one of them being observed marks the step complete, so a
    step can be satisfied by more than one route to the same outcome. ``weight``
    is the step's contribution to the adoption score (a heavier step is worth
    more first-value); it is clamped to at least zero when scoring. ``role_scope``
    is the tuple of roles the step applies to - an EMPTY scope means the step
    applies to every role.
    """

    key: str
    label: str
    module: str
    action_keys: tuple[str, ...]
    weight: int = 1
    role_scope: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChecklistStepStatus:
    """A step paired with whether the user has completed it."""

    step: ChecklistStep
    done: bool


@dataclass(frozen=True)
class AdoptionChecklist:
    """One user's adoption picture for a given role.

    ``role`` is the role the checklist was evaluated for. ``steps`` is one
    :class:`ChecklistStepStatus` per step that applies to the role, in catalogue
    order. ``adoption_score`` is the weighted percent of applicable steps that
    are done, an integer in ``[0, 100]``. ``next_actions`` is the leading
    incomplete steps in catalogue order, capped (see
    :data:`DEFAULT_NEXT_ACTIONS`) - the concrete "do these next" nudge. When the
    role has no applicable steps the score is 0 and both tuples are empty.
    """

    role: str
    steps: tuple[ChecklistStepStatus, ...]
    adoption_score: int
    next_actions: tuple[ChecklistStep, ...]


@dataclass(frozen=True)
class TeamMemberAdoption:
    """One team member's adoption score under their own role."""

    user_id: str
    role: str
    adoption_score: int


@dataclass(frozen=True)
class TeamAdoption:
    """A team's adoption rollup.

    ``members`` is one :class:`TeamMemberAdoption` per input member, ordered by
    ascending adoption score then ``user_id`` so the people the rollout still
    needs to reach lead the list and ties are stable. ``team_score`` is the mean
    of the member scores, rounded to the nearest integer (0 for an empty team).
    ``laggards`` is the tuple of ``user_id`` for members at or below the laggard
    threshold, in the same ascending order.
    """

    members: tuple[TeamMemberAdoption, ...]
    team_score: int
    laggards: tuple[str, ...]


# --------------------------------------------------------------------------- #
# The built-in first-value catalogue. Ordered by a natural onboarding sequence:
# stand up a project, get scope and quantities in, then exercise the workflows
# that create the platform's distinctive value (assisted change handling, AI
# verdicts, evidence, and finally a value report that proves the payoff). Action
# keys are generic dotted tokens of the shape "<area>.<event>" the activity log
# can plausibly emit; each step lists every key that should count as done.
#
# Weights lean slightly heavier on the steps that carry the most first-value
# (running an AI agent, recording its verdict, assembling an evidence pack)
# without letting any single step dominate. role_scope keeps office-heavy steps
# (importing a BOQ, pricing, generating the report) off the field role's path so
# its score is measured against what that role is actually asked to do.
# --------------------------------------------------------------------------- #

ADOPTION_STEPS: tuple[ChecklistStep, ...] = (
    ChecklistStep(
        key="create_project",
        label="Create a project",
        module="projects",
        action_keys=("project.created",),
        weight=1,
        # Everyone starts here - global scope.
        role_scope=(),
    ),
    ChecklistStep(
        key="import_boq",
        label="Import a bill of quantities",
        module="boq",
        action_keys=("boq.imported", "boq.created"),
        weight=2,
        role_scope=(ROLE_MANAGER, ROLE_ESTIMATOR),
    ),
    ChecklistStep(
        key="run_takeoff",
        label="Run a takeoff",
        module="takeoff",
        action_keys=("takeoff.parsed", "takeoff.created"),
        weight=2,
        role_scope=(ROLE_MANAGER, ROLE_ESTIMATOR, ROLE_FIELD),
    ),
    ChecklistStep(
        key="start_approval",
        label="Start an approval route",
        module="approvals",
        action_keys=("approval.route.started",),
        weight=2,
        role_scope=(ROLE_MANAGER, ROLE_REVIEWER),
    ),
    ChecklistStep(
        key="log_change_order",
        label="Log a change order",
        module="changeorders",
        action_keys=("change_order.logged", "change_order.created"),
        weight=2,
        # Global: the field role logs changes from site too.
        role_scope=(),
    ),
    ChecklistStep(
        key="run_ai_agent",
        label="Run an AI agent",
        module="ai_agents",
        action_keys=("ai_agents.run.created",),
        weight=3,
        role_scope=(),
    ),
    ChecklistStep(
        key="record_ai_verdict",
        label="Record an AI verdict",
        module="ai_agents",
        action_keys=("ai_agents.outcome.recorded",),
        weight=3,
        role_scope=(ROLE_MANAGER, ROLE_ESTIMATOR, ROLE_REVIEWER),
    ),
    ChecklistStep(
        key="assemble_evidence_pack",
        label="Assemble an evidence pack",
        module="claims_evidence",
        action_keys=("claims_evidence.evidence_pack.assembled",),
        weight=3,
        role_scope=(ROLE_MANAGER, ROLE_REVIEWER),
    ),
    ChecklistStep(
        key="generate_value_report",
        label="Generate a value report",
        module="value",
        action_keys=("value.report.generated",),
        weight=2,
        role_scope=(ROLE_MANAGER,),
    ),
)


def _step_applies_to_role(step: ChecklistStep, role: str) -> bool:
    """Whether *step* is on *role*'s path.

    A step with an empty :attr:`ChecklistStep.role_scope` applies to every role;
    otherwise it applies only when *role* is listed in the scope. Centralised so
    the checklist and its score denominator always agree on what counts.
    """
    if not step.role_scope:
        return True
    return role in step.role_scope


def steps_for_role(
    role: str,
    catalogue: Sequence[ChecklistStep] = ADOPTION_STEPS,
) -> tuple[ChecklistStep, ...]:
    """The steps in *catalogue* that apply to *role*, in catalogue order.

    Filters by :attr:`ChecklistStep.role_scope`: an empty scope means the step
    applies to all roles, so a globally scoped step is always included. Order is
    preserved from the catalogue so the onboarding sequence is stable. An unknown
    role simply sees only the globally scoped steps (it matches no explicit
    scope), which is the honest default rather than an error.
    """
    return tuple(s for s in catalogue if _step_applies_to_role(s, role))


def _step_is_done(step: ChecklistStep, observed: frozenset) -> bool:
    """Whether ANY of *step*'s action keys appears in *observed*.

    The match is intentionally permissive across a step's OWN keys (more than one
    route can satisfy the same outcome) but never beyond them - an action key the
    catalogue does not list contributes nothing, so progress is never invented.
    """
    return any(key in observed for key in step.action_keys)


def _weighted_score(statuses: Sequence[ChecklistStepStatus]) -> int:
    """Weighted percent of *statuses* that are done, an int in ``[0, 100]``.

    The denominator is the total weight of the applicable steps and the
    numerator is the weight of the done ones, so a heavier first-value step moves
    the score more. Each step's weight is floored at zero (a negative weight
    would be a misconfiguration and must not subtract from progress). When the
    total applicable weight is zero - no steps apply, or every applicable step
    has zero weight - the score is 0 rather than a divide-by-zero. The ratio is
    rounded to the nearest integer.
    """
    total = 0
    done = 0
    for status in statuses:
        w = status.step.weight if status.step.weight > 0 else 0
        total += w
        if status.done:
            done += w
    if total <= 0:
        return 0
    return round(done * 100 / total)


def evaluate(
    role: str,
    observed_action_keys: frozenset,
    catalogue: Sequence[ChecklistStep] = ADOPTION_STEPS,
    *,
    next_actions_limit: int = DEFAULT_NEXT_ACTIONS,
) -> AdoptionChecklist:
    """Evaluate one user's adoption for *role* against *observed_action_keys*.

    Resolves the steps that apply to *role* (:func:`steps_for_role`), marks each
    done when any of its action keys is in *observed_action_keys*, computes the
    weighted completion score, and collects the leading incomplete steps - in
    catalogue order - as the next-actions nudge, capped at *next_actions_limit*.

    A step is done if ANY of its action keys was observed; an action key outside
    the catalogue matches nothing, so unrelated activity never inflates the
    score. When the role has no applicable steps the result is an empty checklist
    with a score of 0 and no next actions. The computation is pure and
    deterministic: identical inputs always yield an identical result.
    """
    applicable = steps_for_role(role, catalogue)
    statuses = tuple(
        ChecklistStepStatus(step=step, done=_step_is_done(step, observed_action_keys)) for step in applicable
    )
    score = _weighted_score(statuses)

    limit = next_actions_limit if next_actions_limit > 0 else 0
    incomplete = tuple(status.step for status in statuses if not status.done)
    next_actions = incomplete[:limit]

    return AdoptionChecklist(
        role=role,
        steps=statuses,
        adoption_score=score,
        next_actions=next_actions,
    )


def team_adoption(
    members: Iterable[tuple[str, str, frozenset]],
    catalogue: Sequence[ChecklistStep] = ADOPTION_STEPS,
    *,
    laggard_threshold: int = DEFAULT_LAGGARD_THRESHOLD,
) -> TeamAdoption:
    """Roll a set of members up into a team adoption picture.

    Each member is a ``(user_id, role, observed_action_keys)`` triple. Every
    member is scored with :func:`evaluate` under their OWN role, so a member is
    only measured against what their role is asked to do. The team score is the
    mean of the member scores rounded to the nearest integer (0 for an empty
    team, never a divide-by-zero). Laggards are the members whose score is at or
    below *laggard_threshold* - the people the rollout still needs to reach.

    Members are returned ordered by ascending adoption score then ``user_id`` so
    the laggards lead and ties are stable; the laggards tuple follows that same
    order. The computation is pure and deterministic.
    """
    scored: list = []
    for user_id, role, observed in members:
        checklist = evaluate(role, observed, catalogue)
        scored.append(
            TeamMemberAdoption(
                user_id=user_id,
                role=role,
                adoption_score=checklist.adoption_score,
            )
        )

    scored.sort(key=lambda m: (m.adoption_score, m.user_id))

    if scored:
        team_score = round(sum(m.adoption_score for m in scored) / len(scored))
    else:
        team_score = 0

    laggards = tuple(m.user_id for m in scored if m.adoption_score <= laggard_threshold)

    return TeamAdoption(
        members=tuple(scored),
        team_score=team_score,
        laggards=laggards,
    )


__all__ = [
    "ROLE_MANAGER",
    "ROLE_ESTIMATOR",
    "ROLE_FIELD",
    "ROLE_REVIEWER",
    "DEFAULT_LAGGARD_THRESHOLD",
    "DEFAULT_NEXT_ACTIONS",
    "ADOPTION_STEPS",
    "ChecklistStep",
    "ChecklistStepStatus",
    "AdoptionChecklist",
    "TeamMemberAdoption",
    "TeamAdoption",
    "steps_for_role",
    "evaluate",
    "team_adoption",
]
