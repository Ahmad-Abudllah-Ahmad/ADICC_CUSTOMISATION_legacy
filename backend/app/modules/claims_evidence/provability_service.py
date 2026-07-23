# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Provability scoring service - the thin database layer over the pure engine.

Gathers the evidence signals already on a project for one change / claim subject
and feeds them to the pure :func:`app.modules.claims_evidence.provability.compute_provability`
engine, producing a 0-100 provability score with a transparent per-signal
breakdown (present vs missing) and the ordered list of weaknesses to cure.

The engine is intentionally ORM-free; this service maps real change-family rows
and recovered ownership hand-offs onto its primitive :class:`ProvabilitySignals`
input. Nothing is persisted, so there is no new table and no migration. Every
signal is best-effort: where a signal cannot be cheaply established for a subject
the engine's conservative default applies (the change is scored as if that
signal were missing rather than waved through), which is the documented
behaviour and is noted per-signal below.

What each signal is read from
-----------------------------
* **notice timeliness** - for a variation notice, the row's own served date
  (``raised_at``) versus its due date (``response_due_date`` then
  ``target_response_date``). For the other change families, the governing notice
  soft-linked to the change (when one exists) supplies the served / due dates;
  otherwise the change's own submission timestamp is treated as the served date
  with an unknown deadline (partial credit), since a request that was issued but
  carries no contractual deadline cannot be proven timely.
* **acknowledgement** - the notice's ``response_received_at``, or the change's
  own decision / approval timestamp (proof the counterparty engaged).
* **linked instruction** - a contract clause reference on the change, a recorded
  soft link to a governing change order, or a linked RFI - any one anchors the
  change to a contractual basis.
* **ownership continuity** - reconstructed from the same ``ownership_handoff`` /
  ``status_changed`` activity-log rows the change-intelligence ownership view
  uses, fed through the pure :mod:`change_intelligence.ownership_chain` engine
  (imported for its pure functions only; no service-layer dependency).
* **date completeness** - the count and span of dated activity-log rows for the
  subject, which is the contemporaneous trail behind it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.change_intelligence.ownership_chain import (
    HandoffRow,
    build_ownership_chain,
)
from app.modules.changeorders.models import ChangeOrder
from app.modules.claims_evidence.evidence_pack import parse_iso
from app.modules.claims_evidence.provability import (
    ProvabilityScore,
    ProvabilitySignals,
    compute_provability,
)
from app.modules.moc.models import MoCEntry
from app.modules.variations.models import Notice, VariationOrder, VariationRequest

# Stable kind tokens for the change-family record types a subject can be. Kept
# in lock-step with the change-intelligence cycle-time tokens (and the audit
# ``entity_type`` each module writes) so the same token resolves the source
# record and filters its activity rows.
KIND_CHANGE_ORDER = "change_order"
KIND_VARIATION_NOTICE = "variation_notice"
KIND_VARIATION_REQUEST = "variation_request"
KIND_VARIATION_ORDER = "variation_order"
KIND_MOC_ENTRY = "moc_entry"

_KIND_TO_MODEL: dict[str, type] = {
    KIND_CHANGE_ORDER: ChangeOrder,
    KIND_VARIATION_NOTICE: Notice,
    KIND_VARIATION_REQUEST: VariationRequest,
    KIND_VARIATION_ORDER: VariationOrder,
    KIND_MOC_ENTRY: MoCEntry,
}

#: Activity-log action verbs the ownership chain reads back (kept in sync with
#: the change-intelligence ownership view's write side).
_ACTION_OWNERSHIP_HANDOFF = "ownership_handoff"
_ACTION_STATUS_CHANGED = "status_changed"


class UnknownSubjectKind(Exception):
    """Raised when a subject ``kind`` is not a recognised change family."""


class SubjectNotFound(Exception):
    """Raised when no change record matches the subject ``kind`` + ``id``."""


@dataclass(frozen=True)
class SubjectProvability:
    """A subject's provability score plus the resolved subject metadata.

    Bundles the pure-engine :class:`ProvabilityScore` with the change record's
    human reference and the dated-record span the score was built from, so the
    router can build its response without a second database round-trip.
    """

    subject_kind: str
    subject_id: str
    subject_ref: str
    score: ProvabilityScore
    entry_count: int
    date_from: datetime | None
    date_to: datetime | None


def _first_attr(row: object, *names: str) -> str | None:
    """Return the first non-empty string attribute among *names*, else None."""
    for name in names:
        value = getattr(row, name, None)
        if value:
            text = str(value).strip()
            if text:
                return text
    return None


def _subject_ref(row: object, kind: str, subject_id: uuid.UUID) -> str:
    """Human-facing reference for the subject: its code, else kind + short id."""
    code = _first_attr(row, "code")
    if code:
        return code
    return f"{kind}:{str(subject_id)[:8]}"


def _served_and_due(row: object, kind: str) -> tuple[datetime | None, datetime | None]:
    """Notice served-at + due-at datetimes for the subject, best-effort.

    A variation notice carries its own served (``raised_at``) and due
    (``response_due_date`` / ``target_response_date``) timestamps. For the other
    families the change's submission timestamp stands in for "served" with no
    provable deadline (so the engine awards partial notice credit and flags the
    unknown due date) - unless a due date happens to be recorded on the change.
    """
    if kind == KIND_VARIATION_NOTICE:
        served = parse_iso(_first_attr(row, "raised_at"))
        due = parse_iso(_first_attr(row, "response_due_date", "target_response_date"))
        return served, due

    # Other change families: the date the change was put on the record.
    served = parse_iso(_first_attr(row, "submitted_at", "requested_at", "proposed_at", "agreed_at"))
    due = parse_iso(_first_attr(row, "response_due_date"))
    return served, due


def _has_acknowledgement(row: object, kind: str) -> bool:
    """Whether a counterparty response / decision is on the record for *row*."""
    if kind == KIND_VARIATION_NOTICE:
        return _first_attr(row, "response_received_at") is not None
    return _first_attr(row, "decision_at", "decided_at", "approved_at") is not None


def _linked_instruction_count(row: object, kind: str) -> int:
    """Count of governing instructions / clauses anchoring the change.

    Best-effort across the families: a contract clause reference, a recorded
    soft link to a governing change order, or a linked RFI each counts as one
    anchor. The exact figure is not load-bearing - the engine only checks
    whether at least one anchor is present - so a conservative count is fine.
    """
    count = 0
    if _first_attr(row, "contract_clause_ref"):
        count += 1
    # Any recorded soft link to a governing document anchors the change: the
    # change order it references, the request it derived from, or the notice it
    # follows. Each of these is a single nullable id on one or another family.
    for link in ("reference_change_order_id", "change_order_id", "variation_request_id", "notice_id"):
        if getattr(row, link, None) is not None:
            count += 1
    linked_rfis = getattr(row, "linked_rfi_ids", None)
    if linked_rfis:
        count += len(linked_rfis)
    return count


async def _ownership_signals(
    session: AsyncSession,
    kind: str,
    subject_id: uuid.UUID,
    *,
    now: datetime,
) -> tuple[bool, bool, bool]:
    """Ownership chain-present / ambiguous / inconsistent flags for the subject.

    Reconstructs the chain from the recorded ``ownership_handoff`` /
    ``status_changed`` rows for this entity (mirroring the change-intelligence
    ownership view) and feeds them to the pure engine. Returns
    ``(chain_present, ambiguous, inconsistent)``.
    """
    # Local import keeps the engine read decoupled from the audit model at import
    # time (mirrors the change-intelligence service's lazy import).
    from app.core.audit_log import ActivityLog

    rows = (
        await session.execute(
            select(
                ActivityLog.action,
                ActivityLog.from_status,
                ActivityLog.to_status,
                ActivityLog.actor_id,
                ActivityLog.reason,
                ActivityLog.created_at,
            )
            .where(ActivityLog.entity_type == kind)
            .where(ActivityLog.entity_id == str(subject_id))
            .where(ActivityLog.action.in_((_ACTION_OWNERSHIP_HANDOFF, _ACTION_STATUS_CHANGED)))
            .order_by(ActivityLog.created_at.asc())
        )
    ).all()

    handoffs: list[HandoffRow] = []
    status_transition_times: list[datetime] = []
    for row in rows:
        if row.action == _ACTION_OWNERSHIP_HANDOFF:
            handoffs.append(
                HandoffRow(
                    at=row.created_at,
                    from_party=row.from_status,
                    to_party=row.to_status,
                    set_by=str(row.actor_id) if row.actor_id is not None else None,
                    reason=row.reason,
                )
            )
        elif row.action == _ACTION_STATUS_CHANGED:
            status_transition_times.append(row.created_at)

    if not handoffs:
        # No custody record on the log: the ownership signal earns nothing (a
        # missing chain is distinct from an ambiguous one). The chain engine is
        # only meaningful with at least one hand-off, so report "no chain".
        return False, False, False

    chain = build_ownership_chain(
        handoffs,
        now=now,
        status_transition_times=status_transition_times or None,
    )
    return True, chain.ownership_ambiguous, chain.chain_inconsistent


async def _dated_record(
    session: AsyncSession,
    kind: str,
    subject_id: uuid.UUID,
) -> tuple[int, datetime | None, datetime | None]:
    """Count + span of dated activity-log rows for the subject (its trail).

    Returns ``(entry_count, earliest, latest)`` over every activity-log row
    recorded against this entity that carries a parseable timestamp. This is the
    contemporaneous record the date-completeness signal grades.
    """
    from app.core.audit_log import ActivityLog

    rows = (
        await session.execute(
            select(ActivityLog.created_at)
            .where(ActivityLog.entity_type == kind)
            .where(ActivityLog.entity_id == str(subject_id))
        )
    ).all()

    dated: list[datetime] = []
    for row in rows:
        when = row.created_at
        if when is None:
            continue
        # Stored timestamps are already datetimes; normalise to aware UTC for a
        # stable span (mirrors the evidence-pack parser's UTC assumption).
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        dated.append(when)

    if not dated:
        return 0, None, None
    dated.sort()
    return len(dated), dated[0], dated[-1]


async def score_subject_provability(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    subject_kind: str,
    subject_id: uuid.UUID,
    now: datetime | None = None,
) -> SubjectProvability:
    """Grade how provable one change / claim subject is from its evidence.

    Resolves the change record by ``subject_kind`` + ``subject_id`` (its
    ``project_id`` is checked against *project_id* so a subject from another
    project is treated as not found), gathers the notice / acknowledgement /
    linked-instruction / ownership / dated-record signals already on the project,
    and feeds them to the pure provability engine. Returns a
    :class:`SubjectProvability` bundling the score with the subject reference and
    dated-record span so the caller needs no second read.

    Raises :class:`UnknownSubjectKind` for an unrecognised kind and
    :class:`SubjectNotFound` when no matching record exists in the project.
    """
    moment = now or datetime.now(UTC)
    model = _KIND_TO_MODEL.get(subject_kind)
    if model is None:
        raise UnknownSubjectKind(subject_kind)

    row = (await session.execute(select(model).where(model.id == subject_id))).scalar_one_or_none()
    if row is None or getattr(row, "project_id", None) != project_id:
        # Fence to the project: an out-of-project (or missing) id is "not found"
        # so the endpoint never leaks the existence of another project's record.
        raise SubjectNotFound(subject_kind)

    served, due = _served_and_due(row, subject_kind)
    has_ack = _has_acknowledgement(row, subject_kind)
    instruction_count = _linked_instruction_count(row, subject_kind)
    chain_present, ambiguous, inconsistent = await _ownership_signals(session, subject_kind, subject_id, now=moment)
    entry_count, date_from, date_to = await _dated_record(session, subject_kind, subject_id)

    signals = ProvabilitySignals(
        notice_served_at=served,
        notice_due_at=due,
        has_acknowledgement=has_ack,
        linked_instruction_count=instruction_count,
        ownership_chain_present=chain_present,
        ownership_ambiguous=ambiguous,
        ownership_chain_inconsistent=inconsistent,
        entry_count=entry_count,
        date_from=date_from,
        date_to=date_to,
        chronology_has_gap=False,
    )
    score = compute_provability(signals)
    return SubjectProvability(
        subject_kind=subject_kind,
        subject_id=str(subject_id),
        subject_ref=_subject_ref(row, subject_kind, subject_id),
        score=score,
        entry_count=entry_count,
        date_from=date_from,
        date_to=date_to,
    )


__all__ = [
    "KIND_CHANGE_ORDER",
    "KIND_VARIATION_NOTICE",
    "KIND_VARIATION_REQUEST",
    "KIND_VARIATION_ORDER",
    "KIND_MOC_ENTRY",
    "UnknownSubjectKind",
    "SubjectNotFound",
    "SubjectProvability",
    "score_subject_provability",
]
