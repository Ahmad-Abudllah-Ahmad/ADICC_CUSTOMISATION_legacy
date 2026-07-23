# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Notice / time-bar register service - the thin database layer over the engine.

Derives every open contractual clock for a project from records that already
exist - change orders, variation notices / requests / orders, extension-of-time
claims - and feeds them to the pure :mod:`time_bar` engine. Nothing is written
and there is no table of its own: each clock is computed on read from the event
date already on the record plus the notice / response period configured for the
project's contract standard.

Standard resolution is layered. A variation request or order carries its own
``contract_standard``; that wins for its own clocks. Otherwise the project's
standard is resolved once from its contract records (a ``terms`` hint such as a
clause-template code or family), normalised with
:func:`time_bar.normalize_standard`. When nothing can be resolved the engine's
standard-neutral fallback periods still let a clock be counted down.

Proof of notice is read from the correspondence record: a required notice
(claim, EOT) is marked proven when a correspondence row references the source
record - by an explicit link in its metadata / linked-document ids, or by the
record's code appearing in the letter's subject, reference or notes. The match
is deliberately conservative: an unlinked record reads as "no proof on file",
which is the safe alarming default, because a change proceeding with no served
notice on file is the classic way an entitlement is lost.

How this feeds the already-shipped provability and dispute-risk engines
-----------------------------------------------------------------------
This slice only reads; it does not modify either sibling. The signals it surfaces
are the same ones those engines already consume, and it strengthens both:

* ``claims_evidence/provability_service.py`` scores notice timeliness from a
  record's served-vs-due dates and its linked instructions. The same served /
  due dates drive a clock here, so an overdue or served-late clock corresponds
  directly to a weak notice-timeliness signal there, and a ``proof_on_file``
  match is exactly the served-notice evidence its notice signal rewards.
* ``change_intelligence/dispute_risk.py`` blends evidence weakness and overdue
  age into a money-weighted dispute exposure. An overdue clock here is the same
  overdue age its age factor reads, and an ``entitlement_at_risk`` clock (a
  required notice with none on file) is precisely the weak-evidence condition
  its dominant driver flags. A later integration could pass this register's
  proof / overdue findings straight into those inputs; for now the coupling is
  documented and left un-wired so this slice stays read-only and self-contained.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.change_intelligence.cycle_time import is_open_status
from app.modules.change_intelligence.time_bar import (
    DEFAULT_DUE_SOON_DAYS,
    NOTICE_CLAIM,
    NOTICE_EOT,
    NOTICE_QUOTATION,
    NOTICE_RESPONSE,
    STANDARD_UNKNOWN,
    STATUS_DUE_SOON,
    STATUS_OVERDUE,
    ClockInput,
    NoticeClock,
    RegisterSummary,
    build_register,
    clause_ref_for,
    normalize_standard,
    parse_date,
    period_for,
    summarize_register,
)
from app.modules.changeorders.models import ChangeOrder
from app.modules.contracts.models import Contract
from app.modules.correspondence.models import Correspondence
from app.modules.variations.models import (
    ExtensionOfTimeClaim,
    Notice,
    VariationRequest,
)

# Stable source-kind tokens. The change-family tokens match the cycle-time /
# provability engines so the same token resolves the record and (for the change
# families they share) its audit rows; the EOT token is local to this register.
KIND_CHANGE_ORDER = "change_order"
KIND_VARIATION_NOTICE = "variation_notice"
KIND_VARIATION_REQUEST = "variation_request"
KIND_VARIATION_ORDER = "variation_order"
KIND_EOT_CLAIM = "eot_claim"

#: EOT statuses that stop the clock (the claim is decided or gone).
_EOT_CLOSED = frozenset({"granted", "approved", "rejected", "settled", "closed", "withdrawn", "cancelled", "void"})

#: Contract statuses whose declared standard is preferred as the project default.
_CONTRACT_ACTIVE = frozenset({"active", "signed", "executed", "in_progress", "current"})

#: Correspondence type / subject tokens that read as a served notice document.
_NOTICE_CORR_TOKENS = ("notice", "claim", "early_warning", "early warning", "eot", "variation", "instruction", "letter")

#: Keys a contract's ``terms`` may use to declare its standard / clause form.
_TERMS_STANDARD_KEYS = (
    "contract_standard",
    "standard",
    "standard_form",
    "form_of_contract",
    "clause_template",
    "template_code",
    "family",
)


@dataclass(frozen=True)
class NoticeRegister:
    """The project notice register: the resolved standard, clocks and roll-up."""

    project_id: str
    contract_standard: str
    generated_at: datetime
    due_soon_days: int
    clocks: list[NoticeClock]
    summary: RegisterSummary


def _ref(row: object, kind: str, row_id: uuid.UUID) -> str:
    """Human-facing reference: the record code, else the kind + a short id."""
    code = getattr(row, "code", None)
    if code:
        text = str(code).strip()
        if text:
            return text
    return f"{kind}:{str(row_id)[:8]}"


def _title(row: object) -> str:
    """Best-effort display title for a record (title, else trimmed description)."""
    title = getattr(row, "title", None)
    if title:
        text = str(title).strip()
        if text:
            return text
    description = getattr(row, "description", None)
    if description:
        text = str(description).strip()
        if text:
            return text[:80]
    return ""


def _standard_from_terms(terms: dict | None) -> str:
    """Resolve a contract standard from a ``terms`` mapping, else UNKNOWN."""
    if not terms:
        return STANDARD_UNKNOWN
    for key in _TERMS_STANDARD_KEYS:
        value = terms.get(key)
        if value:
            resolved = normalize_standard(str(value))
            if resolved != STANDARD_UNKNOWN:
                return resolved
    return STANDARD_UNKNOWN


async def _resolve_project_standard(session: AsyncSession, project_id: uuid.UUID) -> str:
    """Resolve the project's contract standard from its contract records.

    Prefers the declared standard of an active / signed contract; otherwise
    accepts any contract's declared standard. Returns :data:`STANDARD_UNKNOWN`
    when no contract on the project declares one - clocks then fall back to the
    engine's standard-neutral periods.
    """
    rows = (
        await session.execute(select(Contract.terms, Contract.status).where(Contract.project_id == project_id))
    ).all()
    fallback = STANDARD_UNKNOWN
    for terms, status in rows:
        resolved = _standard_from_terms(terms)
        if resolved == STANDARD_UNKNOWN:
            continue
        if (status or "").strip().lower() in _CONTRACT_ACTIVE:
            return resolved
        if fallback == STANDARD_UNKNOWN:
            fallback = resolved
    return fallback


@dataclass(frozen=True)
class _CorrRow:
    """Lightweight projection of a correspondence row for proof matching."""

    subject: str
    reference_number: str
    notes: str
    correspondence_type: str
    linked_ids: tuple[str, ...]


async def _load_correspondence(session: AsyncSession, project_id: uuid.UUID) -> list[_CorrRow]:
    """Load the project's correspondence once for proof-of-notice matching."""
    rows = (
        await session.execute(
            select(
                Correspondence.subject,
                Correspondence.reference_number,
                Correspondence.notes,
                Correspondence.correspondence_type,
                Correspondence.linked_document_ids,
                Correspondence.linked_rfi_id,
                Correspondence.metadata_.label("meta"),
            ).where(Correspondence.project_id == project_id)
        )
    ).all()

    out: list[_CorrRow] = []
    for row in rows:
        linked: set[str] = set()
        for value in row.linked_document_ids or []:
            if value:
                linked.add(str(value))
        if row.linked_rfi_id:
            linked.add(str(row.linked_rfi_id))
        meta = row.meta or {}
        # Any id-like value stored on the letter's metadata counts as an explicit
        # link back to a source record (source_ref, change_id, entity_id, ...).
        for value in meta.values():
            if isinstance(value, str) and value:
                linked.add(value)
        out.append(
            _CorrRow(
                subject=row.subject or "",
                reference_number=row.reference_number or "",
                notes=row.notes or "",
                correspondence_type=(row.correspondence_type or "").lower(),
                linked_ids=tuple(linked),
            )
        )
    return out


def _mentions(haystack: str, code: str) -> bool:
    """Whole-token, case-insensitive check that *code* appears in *haystack*.

    Token boundaries avoid a false positive where ``CO-1`` would otherwise match
    inside ``CO-10``.
    """
    if not haystack or not code:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(code) + r"(?![A-Za-z0-9])"
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def _is_notice_document(corr: _CorrRow) -> bool:
    """Whether a correspondence row reads as a served notice / claim document."""
    if any(token in corr.correspondence_type for token in _NOTICE_CORR_TOKENS):
        return True
    return any(token in corr.subject.lower() for token in _NOTICE_CORR_TOKENS)


def _has_proof(source_id: str, source_code: str, corr_rows: list[_CorrRow]) -> bool:
    """Whether a served-notice document referencing the record is on file.

    A correspondence row proves the notice when it references the record - by an
    explicit id link in its metadata / linked ids, or by the record code
    appearing in its subject, reference or notes - and reads as a notice / claim
    document. An explicit id link alone is accepted even without a notice-type
    hint, since a deliberate link is the strongest signal.
    """
    for corr in corr_rows:
        if source_id and source_id in corr.linked_ids:
            return True
        if not _is_notice_document(corr):
            continue
        if source_code and (
            _mentions(corr.subject, source_code)
            or _mentions(corr.reference_number, source_code)
            or _mentions(corr.notes, source_code)
        ):
            return True
    return False


def _co_inputs(co: ChangeOrder, standard: str) -> list[ClockInput]:
    """Response-due clock for one change order (no served notice required)."""
    is_open = is_open_status(KIND_CHANGE_ORDER, co.status)
    trigger = parse_date(co.submitted_at) or parse_date(co.contractor_submission_date)
    explicit_due = parse_date(co.response_due_date)
    satisfied = parse_date(co.approved_at) or parse_date(co.rejected_at)
    ref = _ref(co, KIND_CHANGE_ORDER, co.id)
    return [
        ClockInput(
            source_kind=KIND_CHANGE_ORDER,
            source_id=str(co.id),
            source_ref=ref,
            title=_title(co),
            standard=standard,
            notice_type=NOTICE_RESPONSE,
            clause_ref=clause_ref_for(standard, NOTICE_RESPONSE),
            trigger_date=trigger,
            explicit_due=explicit_due,
            period_days=period_for(standard, NOTICE_RESPONSE),
            satisfied_at=satisfied,
            requires_notice=False,
            proof_on_file=False,
            is_open=is_open,
        )
    ]


def _notice_inputs(notice: Notice, standard: str) -> list[ClockInput]:
    """Response clock for one early-warning notice (recipient owes a response)."""
    is_open = is_open_status(KIND_VARIATION_NOTICE, notice.status)
    trigger = parse_date(notice.raised_at)
    explicit_due = parse_date(notice.target_response_date)
    satisfied = parse_date(notice.response_received_at)
    return [
        ClockInput(
            source_kind=KIND_VARIATION_NOTICE,
            source_id=str(notice.id),
            source_ref=_ref(notice, KIND_VARIATION_NOTICE, notice.id),
            title=_title(notice),
            standard=standard,
            notice_type=NOTICE_RESPONSE,
            clause_ref=clause_ref_for(standard, NOTICE_RESPONSE),
            trigger_date=trigger,
            explicit_due=explicit_due,
            period_days=period_for(standard, NOTICE_RESPONSE),
            satisfied_at=satisfied,
            requires_notice=False,
            proof_on_file=False,
            is_open=is_open,
        )
    ]


def _vr_inputs(vr: VariationRequest, project_standard: str, corr_rows: list[_CorrRow]) -> list[ClockInput]:
    """Claim-notice plus optional quotation clock for one variation request.

    The variation request is treated as a compensation event / claim: its
    entitlement clock (the claim notice) runs from the awareness / requested date
    to the notice submission, and requires a served notice on file. When the
    record carries an explicit quotation deadline, a response-style quotation
    clock is added too.
    """
    # The record's own contract standard wins; fall back to the project standard
    # when the record does not name one.
    standard = normalize_standard(vr.contract_standard)
    if standard == STANDARD_UNKNOWN:
        standard = project_standard
    is_open = is_open_status(KIND_VARIATION_REQUEST, vr.status)
    ref = _ref(vr, KIND_VARIATION_REQUEST, vr.id)
    code = getattr(vr, "code", "") or ""
    submitted = parse_date(vr.submitted_at)
    trigger = parse_date(vr.requested_at) or parse_date(getattr(vr, "created_at", None))

    inputs: list[ClockInput] = [
        ClockInput(
            source_kind=KIND_VARIATION_REQUEST,
            source_id=str(vr.id),
            source_ref=ref,
            title=_title(vr),
            standard=standard,
            notice_type=NOTICE_CLAIM,
            clause_ref=clause_ref_for(standard, NOTICE_CLAIM, vr.contract_clause_ref),
            trigger_date=trigger,
            explicit_due=None,
            period_days=period_for(standard, NOTICE_CLAIM),
            satisfied_at=submitted,
            requires_notice=True,
            proof_on_file=_has_proof(str(vr.id), code, corr_rows),
            is_open=is_open,
        )
    ]

    quotation_due = parse_date(vr.quotation_due_at)
    if quotation_due is not None or submitted is not None:
        inputs.append(
            ClockInput(
                source_kind=KIND_VARIATION_REQUEST,
                source_id=str(vr.id),
                source_ref=ref,
                title=_title(vr),
                standard=standard,
                notice_type=NOTICE_QUOTATION,
                clause_ref=clause_ref_for(standard, NOTICE_QUOTATION),
                trigger_date=submitted,
                explicit_due=quotation_due,
                period_days=period_for(standard, NOTICE_QUOTATION),
                satisfied_at=parse_date(vr.decision_at),
                requires_notice=False,
                proof_on_file=False,
                is_open=is_open,
            )
        )
    return inputs


def _eot_inputs(eot: ExtensionOfTimeClaim, standard: str, corr_rows: list[_CorrRow]) -> list[ClockInput]:
    """EOT-notice clock for one extension-of-time claim.

    The clock runs from the delay event (the claim-period start, else the raised
    date) and is satisfied by the date the EOT notice was actually raised; it
    requires a served notice on file.
    """
    is_open = (eot.status or "").strip().lower() not in _EOT_CLOSED
    trigger = parse_date(eot.claim_period_start) or parse_date(eot.raised_at)
    satisfied = parse_date(eot.raised_at)
    ref = _ref(eot, KIND_EOT_CLAIM, eot.id)
    return [
        ClockInput(
            source_kind=KIND_EOT_CLAIM,
            source_id=str(eot.id),
            source_ref=ref,
            title=_title(eot) or "Extension of time claim",
            standard=standard,
            notice_type=NOTICE_EOT,
            clause_ref=clause_ref_for(standard, NOTICE_EOT),
            trigger_date=trigger,
            explicit_due=None,
            period_days=period_for(standard, NOTICE_EOT),
            satisfied_at=satisfied,
            requires_notice=True,
            proof_on_file=_has_proof(str(eot.id), "", corr_rows),
            is_open=is_open,
        )
    ]


def _include(clock: NoticeClock) -> bool:
    """Keep a clock in the register when it is live or a lapsed / at-risk bar.

    A clock for an open record is always shown; a clock for a closed record is
    shown only when it lapsed (overdue) or is flagged at risk, so a compliant,
    already-served notice on a closed record does not clutter the live register.
    """
    return clock.is_open or clock.status == STATUS_OVERDUE or clock.entitlement_at_risk


async def build_notice_register(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    now: datetime | None = None,
    standard_override: str | None = None,
    due_soon_days: int = DEFAULT_DUE_SOON_DAYS,
) -> NoticeRegister:
    """Build the contractual notice / time-bar register for one project.

    Reads the project's change orders, variation notices / requests, and
    extension-of-time claims, derives each open contractual clock from the event
    date already on the record plus the notice period for the resolved contract
    standard, checks correspondence for proof of any required notice, and returns
    the ordered clocks (worst-first) with a roll-up. Read-only: no record is
    modified and nothing is persisted.
    """
    moment = now or datetime.now(UTC)
    project_standard = (
        normalize_standard(standard_override)
        if standard_override
        else await _resolve_project_standard(session, project_id)
    )
    corr_rows = await _load_correspondence(session, project_id)

    inputs: list[ClockInput] = []

    for co in (await session.execute(select(ChangeOrder).where(ChangeOrder.project_id == project_id))).scalars():
        inputs.extend(_co_inputs(co, project_standard))

    for notice in (await session.execute(select(Notice).where(Notice.project_id == project_id))).scalars():
        inputs.extend(_notice_inputs(notice, project_standard))

    for vr in (
        await session.execute(select(VariationRequest).where(VariationRequest.project_id == project_id))
    ).scalars():
        inputs.extend(_vr_inputs(vr, project_standard, corr_rows))

    for eot in (
        await session.execute(select(ExtensionOfTimeClaim).where(ExtensionOfTimeClaim.project_id == project_id))
    ).scalars():
        inputs.extend(_eot_inputs(eot, project_standard, corr_rows))

    # build_register orders every derivable clock; the register keeps the live
    # and lapsed ones (see _include) and summarises that kept set.
    ordered, _all_summary = build_register(inputs, now=moment, due_soon_days=due_soon_days)
    kept = [clock for clock in ordered if _include(clock)]
    summary = summarize_register(kept)
    return NoticeRegister(
        project_id=str(project_id),
        contract_standard=project_standard,
        generated_at=moment,
        due_soon_days=due_soon_days,
        clocks=kept,
        summary=summary,
    )


async def dispatch_time_bar_reminders(
    session: AsyncSession,
    project_id: uuid.UUID,
    recipient_user_ids: list[uuid.UUID | str],
    *,
    now: datetime | None = None,
    due_soon_days: int = DEFAULT_DUE_SOON_DAYS,
) -> int:
    """Raise reminders for the project's overdue / due-soon / at-risk clocks.

    Reuses the existing notifications module for delivery (it builds no new
    channel): every urgent clock becomes an in-app notification for each
    recipient, carrying the source record as the entity so the UI can deep-link.
    Returns the number of notifications created. This is the reuse point a
    scheduler or the notifications worker calls; the read endpoint never invokes
    it, so listing the register stays side-effect free.
    """
    register = await build_notice_register(session, project_id, now=now, due_soon_days=due_soon_days)
    urgent = [
        clock
        for clock in register.clocks
        if clock.status in (STATUS_OVERDUE, STATUS_DUE_SOON) or clock.entitlement_at_risk
    ]
    if not urgent or not recipient_user_ids:
        return 0

    from app.modules.notifications.service import NotificationService

    service = NotificationService(session)
    created = 0
    for clock in urgent:
        notifications = await service.notify_users(
            recipient_user_ids,
            notification_type="change_intelligence.time_bar.reminder",
            title_key="notifications.time_bar.reminder.title",
            body_key="notifications.time_bar.reminder.body",
            body_context={
                "ref": clock.source_ref,
                "clause": clock.clause_ref,
                "status": clock.status,
                "days_remaining": clock.days_remaining,
                "at_risk": clock.entitlement_at_risk,
            },
            entity_type=clock.source_kind,
            entity_id=clock.source_id,
            action_url=f"/projects/{project_id}/change-intelligence",
        )
        created += len(notifications)
    return created


__all__ = [
    "KIND_CHANGE_ORDER",
    "KIND_VARIATION_NOTICE",
    "KIND_VARIATION_REQUEST",
    "KIND_VARIATION_ORDER",
    "KIND_EOT_CLAIM",
    "NoticeRegister",
    "build_notice_register",
    "dispatch_time_bar_reminders",
]
