# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure, database-free logic for the transmittals module.

Everything here is a plain function with no database or network access, so it
can be unit tested in isolation and reused by the service layer. Keeping the
numbering scheme, the response-due-date maths and the "is this ready to
issue" checks here (rather than buried in the async service) makes the rules
easy to read, test and adjust for any country.

Vocabulary for a document controller anywhere in the world:

Statuses
    draft      - being prepared. Still fully editable, not yet sent to anyone.
    issued     - formally sent and locked. It is now a fixed record; recipients
                 can acknowledge receipt and send a response, but the content
                 no longer changes.
    responded  - every recipient has sent a response. The exchange is complete.

Purpose codes (why the documents are being sent, not who they go to)
    for_approval      - the recipient is asked to approve the documents.
    for_review        - the recipient is asked to review and comment.
    for_information   - shared for awareness only, no action expected.
    for_construction  - released so work can be built from these documents.
    for_tender        - issued as part of a tender/bid package.
    for_record        - filed for the record, no action expected.
"""

import re

# ── Status vocabulary ─────────────────────────────────────────────────────

STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"
STATUS_RESPONDED = "responded"

VALID_STATUSES: tuple[str, ...] = (STATUS_DRAFT, STATUS_ISSUED, STATUS_RESPONDED)

# Statuses in which a recipient is allowed to acknowledge receipt or respond.
# You can only acknowledge or respond to something that has actually been sent.
RESPONDABLE_STATUSES: tuple[str, ...] = (STATUS_ISSUED, STATUS_RESPONDED)

# Short, plain-language explanation of each status for tooltips and help text.
STATUS_DESCRIPTIONS: dict[str, str] = {
    STATUS_DRAFT: "Being prepared. Still editable and not yet sent.",
    STATUS_ISSUED: "Formally sent and locked. Recipients can acknowledge and respond.",
    STATUS_RESPONDED: "Every recipient has responded. The exchange is complete.",
}

# ── Purpose vocabulary ────────────────────────────────────────────────────

PURPOSE_CODES: tuple[str, ...] = (
    "for_approval",
    "for_review",
    "for_information",
    "for_construction",
    "for_tender",
    "for_record",
)

PURPOSE_DESCRIPTIONS: dict[str, str] = {
    "for_approval": "The recipient is asked to approve the documents.",
    "for_review": "The recipient is asked to review and comment.",
    "for_information": "Shared for awareness only, no action expected.",
    "for_construction": "Released so work can be built from these documents.",
    "for_tender": "Issued as part of a tender or bid package.",
    "for_record": "Filed for the record, no action expected.",
}


# ── Numbering ─────────────────────────────────────────────────────────────

_TRAILING_INT = re.compile(r"(\d+)\s*$")

# Default prefix and zero-padding. "TR" (transmittal) plus a running counter
# is plain ASCII, sorts correctly and reads the same in every country. Both
# are overridable so a project can follow its own document-control convention.
DEFAULT_NUMBER_PREFIX = "TR"
DEFAULT_NUMBER_PAD = 3


def next_transmittal_number(
    max_existing: str | None,
    *,
    prefix: str = DEFAULT_NUMBER_PREFIX,
    pad: int = DEFAULT_NUMBER_PAD,
) -> str:
    """Return the next sequential transmittal number for a project.

    The scheme is ``<prefix>-<zero-padded counter>`` (default ``TR-001``,
    ``TR-002`` ...). ``max_existing`` is the highest existing number in the
    project, or ``None`` when there are none yet (the sequence then starts at
    1). The trailing digits of ``max_existing`` are used as the counter, so a
    custom prefix such as a project code still increments correctly. ``prefix``
    and ``pad`` let a project match its own convention; use the same prefix
    consistently within a project so the numbers keep sorting in order.
    """
    clean_prefix = (prefix or DEFAULT_NUMBER_PREFIX).strip() or DEFAULT_NUMBER_PREFIX
    width = pad if isinstance(pad, int) and pad > 0 else DEFAULT_NUMBER_PAD

    current = 0
    if max_existing:
        match = _TRAILING_INT.search(max_existing)
        if match:
            current = int(match.group(1))

    return f"{clean_prefix}-{current + 1:0{width}d}"


# ── Dates ─────────────────────────────────────────────────────────────────

# We standardise on ISO 8601 calendar dates (YYYY-MM-DD). This is the one date
# format that is unambiguous everywhere: no confusion between day/month order.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(value: str | None) -> str | None:
    """Return a valid ISO 8601 date string unchanged, or ``None`` if blank.

    Raises :class:`ValueError` with a clear message if the value is present but
    not a real ``YYYY-MM-DD`` calendar date (for example ``2026-13-40``).
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if not _ISO_DATE.match(text):
        raise ValueError(f"Date '{value}' must be written as YYYY-MM-DD, for example 2026-03-31.")
    # ``date.fromisoformat`` rejects impossible dates such as 2026-02-30.
    from datetime import date

    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Date '{value}' is not a real calendar date. Use a valid YYYY-MM-DD date.") from exc
    return text


def compute_response_due_date(
    issued_date: str | None,
    response_period_days: int | None,
) -> str | None:
    """Return the response deadline as ``issued_date`` plus N calendar days.

    Calendar days are used on purpose: working-day and public-holiday rules
    differ from country to country, so counting plain calendar days is the
    only rule that is correct worldwide. If a project needs to skip local
    holidays, set the response due date explicitly instead. Returns ``None``
    when either input is missing (nothing to compute from).
    """
    issued = parse_iso_date(issued_date)
    if issued is None or response_period_days is None:
        return None
    if response_period_days < 0:
        raise ValueError("Response period cannot be negative. Use 0 or more calendar days.")
    from datetime import date, timedelta

    due = date.fromisoformat(issued) + timedelta(days=response_period_days)
    return due.isoformat()


def response_due_error(
    issued_date: str | None,
    response_due_date: str | None,
) -> str | None:
    """Return a plain-language error if the response is due before it is issued.

    A deadline that falls before the issue date is almost always a typo, so we
    catch it early. Returns ``None`` when the two dates are consistent (or when
    either is missing, since there is nothing to compare).
    """
    issued = parse_iso_date(issued_date)
    due = parse_iso_date(response_due_date)
    if issued is None or due is None:
        return None
    if due < issued:
        return (
            f"Response due date ({due}) cannot be earlier than the issue date "
            f"({issued}). Pick a due date on or after the issue date."
        )
    return None


# ── Readiness to issue ────────────────────────────────────────────────────


def issue_blockers(recipient_count: int, item_count: int) -> list[str]:
    """Return the reasons a transmittal is not ready to be issued.

    Issuing is the point of no return: the record is locked and sent. A
    transmittal only makes sense with at least one recipient to send it to and
    at least one document (line item) to transmit, so we block issue and
    explain what to add. An empty list means it is ready to issue.
    """
    problems: list[str] = []
    if recipient_count <= 0:
        problems.append("Add at least one recipient before issuing. A transmittal has to be sent to someone.")
    if item_count <= 0:
        problems.append("Add at least one document (line item) before issuing. There is nothing to transmit yet.")
    return problems
