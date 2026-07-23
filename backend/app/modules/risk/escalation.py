# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Risk auto-escalation engine (TOP-30 #24).

When a risk's severity product (``probability_score`` x ``impact_score``)
crosses a configurable threshold, OR its next-review date has lapsed, the
risk is auto-escalated **exactly once per trigger**:

1. the ``escalated`` flag flips to ``True`` and ``escalated_at`` is stamped;
2. ``escalation_trigger`` records which condition fired
   (``"severity"`` | ``"review_lapsed"``);
3. a mitigation/action item is appended to the existing
   ``RiskItem.mitigation_actions`` JSON list (we reuse that model rather
   than adding a new table), tagged ``auto_escalation: True`` so re-runs
   recognise it;
4. a ``risk.escalated`` event is emitted (a notifications subscriber fans
   it out - this module only emits).

Idempotency
-----------
The pure :func:`evaluate_risk` decides whether a risk *should* escalate
given the current row state. A risk that is already ``escalated`` never
escalates again - so the on-update hook and the periodic sweep can both
run repeatedly without producing duplicate actions or duplicate events.
When a risk is de-escalated (severity drops below threshold AND its review
is brought current) the engine clears the flag so a future re-crossing can
escalate again, but it still emits no event and creates no action on the
clear path.

The decision logic is split out as a free function (:func:`evaluate_risk`)
operating on plain values so it can be unit-tested with stubs and with no
database at all. :class:`RiskEscalationService` wires it to the ORM.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risk.models import RiskItem

logger = logging.getLogger(__name__)

# Default escalation threshold on the 1-25 PMBOK product scale
# (probability_score x impact_score). 16 == the "critical" tier boundary
# used by ``service._compute_risk_tier``, so by default a risk escalates
# the moment it becomes critical. Configurable per-risk via
# ``RiskItem.escalation_threshold`` and per-call via the service/sweep.
DEFAULT_ESCALATION_THRESHOLD = 16

# Metadata key under ``RiskItem.metadata_`` holding the ISO date/datetime
# of the next scheduled review. A value in the past lapses the review and
# is itself a trigger. Kept in metadata (not a dedicated column) so we do
# not widen the table for a soft-scheduling field the UI already round-trips.
REVIEW_DATE_KEYS = ("next_review_at", "next_review_date", "review_due_date")

# Trigger identifiers stamped on ``escalation_trigger`` and emitted on the
# event. Severity wins when both conditions hold (it is the harder signal).
TRIGGER_SEVERITY = "severity"
TRIGGER_REVIEW = "review_lapsed"


@dataclass(frozen=True)
class EscalationDecision:
    """Outcome of evaluating a single risk for escalation.

    ``should_escalate`` is True only on the *transition* into the escalated
    state. ``should_clear`` is True when an already-escalated risk no longer
    meets any trigger and the flag should be reset (no event / no action).
    A risk that is already escalated and still meets a trigger yields
    neither (a stable, idempotent no-op).
    """

    should_escalate: bool
    should_clear: bool
    trigger: str | None
    severity_product: int
    threshold: int
    review_lapsed: bool


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO date/datetime string to an aware UTC datetime, or None.

    Accepts ``YYYY-MM-DD`` and full ISO timestamps, with or without a
    trailing ``Z``. A naive value is assumed to be UTC. Anything
    unparseable returns None (the field simply does not lapse).
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        # Bare date string (date.fromisoformat path) handled by fromisoformat
        # on 3.11+, so a failure here means genuinely malformed input.
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def review_date_of(metadata: dict[str, Any] | None) -> datetime | None:
    """Return the next-review datetime from a risk's metadata, if present."""
    if not isinstance(metadata, dict):
        return None
    for key in REVIEW_DATE_KEYS:
        if key in metadata:
            parsed = _parse_iso(metadata.get(key))
            if parsed is not None:
                return parsed
    return None


def severity_product(
    probability_score: int | None,
    impact_score: int | None,
) -> int:
    """Compute the 1-25 PMBOK product, defaulting missing scores to 0.

    A risk that has never been scored on the 5x5 matrix (both None)
    contributes a product of 0 and can never trip the severity trigger -
    only an explicit review-date lapse would escalate it. This is correct:
    we never invent a severity for an unscored risk.
    """
    p = probability_score if probability_score is not None else 0
    i = impact_score if impact_score is not None else 0
    return max(0, int(p)) * max(0, int(i))


def evaluate_risk(
    *,
    probability_score: int | None,
    impact_score: int | None,
    metadata: dict[str, Any] | None,
    already_escalated: bool,
    per_risk_threshold: int | None,
    default_threshold: int = DEFAULT_ESCALATION_THRESHOLD,
    now: datetime | None = None,
) -> EscalationDecision:
    """Decide whether a risk should escalate, clear, or stay put.

    Pure function - no I/O. Used by both the on-update hook and the sweep,
    and directly unit-testable.

    Args:
        probability_score: 1-5 PMBOK probability score (or None if unscored).
        impact_score: 1-5 PMBOK impact score (or None if unscored).
        metadata: the risk's ``metadata_`` dict (may carry a review date).
        already_escalated: current value of the ``escalated`` flag.
        per_risk_threshold: per-risk override of the product threshold.
        default_threshold: project/global default product threshold.
        now: injectable "current time" for deterministic tests.

    Returns:
        An :class:`EscalationDecision`.
    """
    now = now or datetime.now(UTC)
    threshold = per_risk_threshold if per_risk_threshold is not None else default_threshold
    product = severity_product(probability_score, impact_score)

    review_dt = review_date_of(metadata)
    review_lapsed = review_dt is not None and review_dt <= now

    severity_crossed = product >= threshold

    # Severity is the dominant signal: when both fire, attribute to severity.
    if severity_crossed:
        trigger: str | None = TRIGGER_SEVERITY
    elif review_lapsed:
        trigger = TRIGGER_REVIEW
    else:
        trigger = None

    meets_trigger = trigger is not None

    if meets_trigger and not already_escalated:
        return EscalationDecision(
            should_escalate=True,
            should_clear=False,
            trigger=trigger,
            severity_product=product,
            threshold=threshold,
            review_lapsed=review_lapsed,
        )
    if not meets_trigger and already_escalated:
        # Conditions resolved - reset so a future re-crossing can fire again.
        return EscalationDecision(
            should_escalate=False,
            should_clear=True,
            trigger=None,
            severity_product=product,
            threshold=threshold,
            review_lapsed=review_lapsed,
        )
    # Either already escalated and still tripping (idempotent no-op), or
    # not escalated and not tripping (nothing to do).
    return EscalationDecision(
        should_escalate=False,
        should_clear=False,
        trigger=trigger,
        severity_product=product,
        threshold=threshold,
        review_lapsed=review_lapsed,
    )


def build_escalation_action(
    *,
    trigger: str,
    severity_product: int,
    threshold: int,
    now: datetime,
    owner_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Construct the auto-generated mitigation/action item dict.

    Shape matches the existing ``RiskItem.mitigation_actions`` element
    contract ``{description, responsible_id, due_date, status}`` and adds
    ``auto_escalation`` + ``trigger`` markers so re-runs can recognise and
    skip it (defence in depth on top of the ``escalated`` flag).
    """
    if trigger == TRIGGER_REVIEW:
        description = "Auto-escalated: scheduled review date lapsed. Reassess this risk and update its mitigation plan."
    else:
        description = (
            f"Auto-escalated: severity score {severity_product} reached the "
            f"escalation threshold ({threshold}). Define and execute a "
            f"mitigation action for this risk."
        )
    return {
        "description": description,
        "responsible_id": str(owner_user_id) if owner_user_id else None,
        "due_date": None,
        "status": "open",
        "auto_escalation": True,
        "trigger": trigger,
        "created_at": now.isoformat(),
    }


def has_open_escalation_action(actions: list[Any] | None) -> bool:
    """Return True if the actions list already holds an auto-escalation item.

    Defensive idempotency: even if the ``escalated`` flag were somehow lost,
    we never append a second auto-escalation action while an earlier one
    still exists.
    """
    if not isinstance(actions, list):
        return False
    return any(isinstance(a, dict) and a.get("auto_escalation") is True for a in actions)


class RiskEscalationService:
    """ORM-bound escalation engine.

    Two entry points:

    * :meth:`evaluate_one` - the on-update hook. Call after a risk is
      created or updated; escalates that single risk if it now crosses the
      threshold.
    * :meth:`sweep` - the periodic system pass. Iterates every (or one
      project's) un-escalated risk and escalates those whose review date
      has lapsed or whose severity crosses the threshold. The central app
      schedules this exactly like the reports scheduler (it must REPORT the
      need, not edit main.py).

    Both share :meth:`_apply` so the flag/stamp/action/event side-effects
    are written in one place.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate_one(
        self,
        risk_id: uuid.UUID,
        *,
        default_threshold: int = DEFAULT_ESCALATION_THRESHOLD,
        now: datetime | None = None,
    ) -> bool:
        """Evaluate and (if warranted) escalate a single risk.

        Returns True iff this call escalated the risk. Safe to call on
        every update - a no-op for risks that do not cross a trigger or are
        already escalated.
        """
        risk = await self.session.get(RiskItem, risk_id)
        if risk is None:
            return False
        return await self._evaluate_and_apply(risk, default_threshold=default_threshold, now=now)

    async def sweep(
        self,
        *,
        project_id: uuid.UUID | None = None,
        default_threshold: int = DEFAULT_ESCALATION_THRESHOLD,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Escalate every not-yet-escalated risk that now meets a trigger.

        This is the entry point the central scheduler calls. It only loads
        rows where ``escalated`` is False (the review-lapse trigger has no
        update event, so the sweep is the only thing that catches it), then
        evaluates each. Returns a summary ``{scanned, escalated, triggers}``.

        Args:
            project_id: restrict to one project, or None for all projects.
            default_threshold: product threshold for risks with no override.
            now: injectable current time for deterministic tests.
        """
        now = now or datetime.now(UTC)
        stmt = select(RiskItem).where(or_(RiskItem.escalated.is_(False), RiskItem.escalated.is_(None)))
        if project_id is not None:
            stmt = stmt.where(RiskItem.project_id == project_id)
        rows = list((await self.session.execute(stmt)).scalars().all())

        escalated = 0
        triggers: dict[str, int] = {}
        for risk in rows:
            did = await self._evaluate_and_apply(risk, default_threshold=default_threshold, now=now)
            if did and risk.escalation_trigger:
                escalated += 1
                triggers[risk.escalation_trigger] = triggers.get(risk.escalation_trigger, 0) + 1
        logger.info(
            "Risk escalation sweep: scanned=%d escalated=%d project=%s",
            len(rows),
            escalated,
            project_id,
        )
        return {"scanned": len(rows), "escalated": escalated, "triggers": triggers}

    async def _evaluate_and_apply(
        self,
        risk: RiskItem,
        *,
        default_threshold: int,
        now: datetime | None,
    ) -> bool:
        decision = evaluate_risk(
            probability_score=risk.probability_score,
            impact_score=risk.impact_score_cost,
            metadata=risk.metadata_ if isinstance(risk.metadata_, dict) else {},
            already_escalated=bool(risk.escalated),
            per_risk_threshold=risk.escalation_threshold,
            default_threshold=default_threshold,
            now=now,
        )
        if decision.should_clear:
            risk.escalated = False
            risk.escalation_trigger = None
            # Keep ``escalated_at`` as the historical record of the last
            # escalation; the flag being False already says "not active".
            await self.session.flush()
            return False
        if not decision.should_escalate or decision.trigger is None:
            return False
        return await self._apply(risk, decision, now or datetime.now(UTC))

    async def _apply(
        self,
        risk: RiskItem,
        decision: EscalationDecision,
        now: datetime,
    ) -> bool:
        """Write the escalation side-effects for a single risk.

        Defensive double-check on ``escalated`` and on an existing
        auto-escalation action so a racing caller cannot double-escalate.
        """
        if risk.escalated:
            return False

        actions = list(risk.mitigation_actions) if isinstance(risk.mitigation_actions, list) else []
        if not has_open_escalation_action(actions):
            actions.append(
                build_escalation_action(
                    trigger=decision.trigger or TRIGGER_SEVERITY,
                    severity_product=decision.severity_product,
                    threshold=decision.threshold,
                    now=now,
                    owner_user_id=risk.owner_user_id,
                )
            )
            # Reassign so SQLAlchemy detects the mutation on the JSON column.
            risk.mitigation_actions = actions

        risk.escalated = True
        risk.escalated_at = now
        risk.escalation_trigger = decision.trigger
        await self.session.flush()

        await _emit_escalated(
            risk_id=str(risk.id),
            project_id=str(risk.project_id),
            code=risk.code,
            title=risk.title,
            trigger=decision.trigger or TRIGGER_SEVERITY,
            severity_product=decision.severity_product,
            threshold=decision.threshold,
        )
        logger.info(
            "Risk escalated: %s (%s) trigger=%s product=%d>=%d",
            risk.code,
            risk.id,
            decision.trigger,
            decision.severity_product,
            decision.threshold,
        )
        return True


async def _emit_escalated(
    *,
    risk_id: str,
    project_id: str,
    code: str,
    title: str,
    trigger: str,
    severity_product: int,
    threshold: int,
) -> None:
    """Emit ``risk.escalated`` - best-effort, never blocks the caller.

    A notifications subscriber elsewhere fans this out (email / in-app).
    We only emit; we never wire notifications here (stay in-lane).
    """
    from app.core.events import event_bus

    payload = {
        "risk_id": risk_id,
        "project_id": project_id,
        "code": code,
        "title": title,
        "trigger": trigger,
        "severity_product": severity_product,
        "threshold": threshold,
    }
    try:
        event_bus.publish_detached("risk.escalated", payload, source_module="oe_risk")
    except Exception:
        logger.debug("risk.escalated publish skipped", exc_info=True)
