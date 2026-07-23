# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure, database-free iCalendar (RFC 5545) builder for meetings.

Everything here is a pure function: given the same input it returns the same
output and never touches a database, ORM, network, or FastAPI. That keeps the
calendar feed trivially unit-testable and easy for a site engineer to reason
about.

The module hand-builds the iCalendar text per RFC 5545 with the standard
library only - no third-party ``icalendar`` dependency - exactly the way the
platform hand-builds its GAEB and BCF XML. It emits a ``VCALENDAR`` wrapping a
single ``VEVENT`` for a one-off meeting, and the same ``VEVENT`` carrying an
``RRULE`` line for a recurring series (one event plus a recurrence rule is how
iCalendar represents a whole series).

Design notes:

- **No METHOD.** The feed is a plain iCalendar object, not an iTIP
  (RFC 5546) message, so ``ORGANIZER`` and ``ATTENDEE`` may both appear as
  descriptive information without the ``PUBLISH``/``REQUEST`` restrictions an
  iTIP method would impose. This is the correct shape for a downloadable
  "add to calendar" file / subscribable feed.
- **UTC everywhere.** ``DTSTART``/``DTEND``/``DTSTAMP`` are written in the UTC
  "Zulu" form (``YYYYMMDDTHHMMSSZ``). A meeting stores only a calendar date, so
  a start time and duration are derived (defaults, overridable from metadata)
  and interpreted as UTC.
- **Escaping + folding.** TEXT values are escaped per RFC 5545 section 3.3.11
  (backslash, comma, semicolon, newline) and every content line is folded to at
  most 75 octets (section 3.1) without splitting a multi-byte UTF-8 character.
  Lines are terminated with CRLF.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

__all__ = [
    "PRODID",
    "CalendarEvent",
    "ICSAttendee",
    "build_calendar",
    "build_vevent_lines",
    "calendar_from_meeting",
    "escape_text",
    "event_from_meeting",
    "fold_line",
    "format_utc",
    "map_rrule",
]

# Product identifier written into every VCALENDAR (RFC 5545 section 3.7.3).
PRODID = "-//DataDrivenConstruction//OpenConstructionERP Meetings//EN"
# Right-hand side of the stable per-meeting UID.
UID_DOMAIN = "openconstructionerp"
# Reserved ``.invalid`` TLD (RFC 2606) used when an attendee has no real email:
# it keeps the CAL-ADDRESS a syntactically valid ``mailto:`` while signalling
# the address is a placeholder, not a deliverable mailbox.
FALLBACK_EMAIL_DOMAIN = "openconstructionerp.invalid"
# RFC 5545 section 3.1: content lines are folded at 75 octets (excluding CRLF).
MAX_LINE_OCTETS = 75
# HTTP media type of the produced document (RFC 5545 section 8.1).
MEDIA_TYPE = "text/calendar; charset=utf-8"

_VALID_FREQ = {
    "SECONDLY",
    "MINUTELY",
    "HOURLY",
    "DAILY",
    "WEEKLY",
    "MONTHLY",
    "YEARLY",
}

# Meeting lifecycle status -> VEVENT STATUS (RFC 5545 section 3.8.1.11).
_STATUS_MAP = {
    "draft": "TENTATIVE",
    "scheduled": "CONFIRMED",
    "in_progress": "CONFIRMED",
    "completed": "CONFIRMED",
    "cancelled": "CANCELLED",
}

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


# ── Text + line primitives ────────────────────────────────────────────────────


def escape_text(value: object) -> str:
    """Escape a value for an RFC 5545 TEXT property (section 3.3.11).

    Backslash is escaped first (so the escapes added afterwards are not
    re-escaped), then comma and semicolon, then every newline form (CRLF, CR,
    LF) collapses to a literal ``\\n``. Colon is intentionally not escaped: it
    is only significant in property parameters, not in a TEXT value.
    """
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


def _param_value(value: object) -> str:
    """Render a property-parameter value (e.g. ``CN``), quoting when needed.

    RFC 5545 section 3.2: a parameter value that contains a colon, semicolon or
    comma must be wrapped in double quotes, and a double quote may not appear
    inside a quoted value (it is replaced with a single quote). Control
    characters are flattened to spaces.
    """
    text = str(value).replace("\r", " ").replace("\n", " ")
    if any(ch in text for ch in (":", ";", ",")) or '"' in text:
        return '"' + text.replace('"', "'") + '"'
    return text


def fold_line(line: str) -> str:
    """Fold one logical content line to <=75 octets per physical line.

    Continuation lines are introduced with CRLF followed by a single space
    (RFC 5545 section 3.1). Folding counts UTF-8 octets and never splits a
    multi-byte character. The single leading space on a continuation counts
    toward that line's 75-octet budget and is stripped again when the reader
    unfolds, so the original value is reconstructed exactly.
    """
    if len(line.encode("utf-8")) <= MAX_LINE_OCTETS:
        return line

    segments: list[str] = []
    buf = ""
    buf_octets = 0
    first = True
    for ch in line:
        ch_octets = len(ch.encode("utf-8"))
        budget = MAX_LINE_OCTETS if first else MAX_LINE_OCTETS - 1
        if buf_octets + ch_octets > budget:
            segments.append(buf if first else " " + buf)
            first = False
            buf = ch
            buf_octets = ch_octets
        else:
            buf += ch
            buf_octets += ch_octets
    segments.append(buf if first else " " + buf)
    return "\r\n".join(segments)


def _crlf_join(lines: Sequence[str]) -> str:
    """Fold each logical line and join with CRLF, including a trailing CRLF."""
    return "".join(fold_line(line) + "\r\n" for line in lines)


def format_utc(value: datetime) -> str:
    """Format a datetime as an RFC 5545 UTC date-time (``YYYYMMDDTHHMMSSZ``).

    A naive datetime is assumed to already be in UTC; an aware datetime is
    converted to UTC first.
    """
    dt = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return dt.strftime("%Y%m%dT%H%M%SZ")


# ── Recurrence ────────────────────────────────────────────────────────────────


def _normalize_until(value: str) -> str:
    """Coerce an RRULE ``UNTIL`` token to a UTC date-time form.

    RFC 5545 section 3.3.10 requires ``UNTIL`` to match the value type of
    ``DTSTART``. Our ``DTSTART`` is always a UTC date-time, so a date-only
    ``UNTIL`` (``YYYYMMDD`` or ``YYYY-MM-DD``) is promoted to end-of-day UTC and
    an existing date-time is normalised to carry the ``Z`` suffix.
    """
    compact = value.strip().replace("-", "").replace(":", "").upper()
    if "T" in compact:
        return compact if compact.endswith("Z") else compact + "Z"
    digits = re.sub(r"[^0-9]", "", compact)
    if len(digits) >= 8:
        return f"{digits[:8]}T235959Z"
    return value.strip()


def map_rrule(stored: str | None, *, dtstart_is_datetime: bool = True) -> str | None:
    """Map a stored RRULE string to a normalised ICS RRULE property value.

    The meeting stores an RFC 5545 rule such as ``FREQ=WEEKLY;BYDAY=MO;COUNT=12``
    on the series master. This returns the value that follows ``RRULE:`` in the
    VEVENT (the property name itself is added by :func:`build_vevent_lines`), or
    ``None`` when the input is empty or has no valid ``FREQ``.

    Normalisation tolerates a leading ``RRULE:`` prefix and surrounding
    whitespace, upper-cases the part names, and (when ``dtstart_is_datetime``)
    rewrites ``UNTIL`` to a UTC date-time so it stays type-compatible with
    ``DTSTART``.
    """
    if not stored:
        return None
    text = str(stored).strip()
    if text.upper().startswith("RRULE:"):
        text = text[len("RRULE:") :].strip()
    if not text:
        return None

    parts: list[tuple[str, str]] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, raw = chunk.split("=", 1)
        parts.append((name.strip().upper(), raw.strip()))

    freq = next((v for k, v in parts if k == "FREQ"), "")
    if freq.upper() not in _VALID_FREQ:
        return None

    out: list[str] = []
    for name, raw in parts:
        if name in ("FREQ", "BYDAY", "WKST"):
            raw = raw.upper()
        elif name == "UNTIL" and dtstart_is_datetime:
            raw = _normalize_until(raw)
        out.append(f"{name}={raw}")
    return ";".join(out)


# ── Event model ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ICSAttendee:
    """A calendar user (ORGANIZER or ATTENDEE) - a name plus an email address."""

    name: str = ""
    email: str | None = None
    role: str = "REQ-PARTICIPANT"
    partstat: str = "NEEDS-ACTION"
    rsvp: bool = True


@dataclass
class CalendarEvent:
    """A single VEVENT. ``start``/``end`` should be timezone-aware (UTC used)."""

    uid: str
    start: datetime
    end: datetime
    summary: str = ""
    description: str | None = None
    location: str | None = None
    organizer: ICSAttendee | None = None
    attendees: list[ICSAttendee] = field(default_factory=list)
    rrule: str | None = None
    sequence: int = 0
    status: str | None = None
    dtstamp: datetime | None = None


def _synth_email(name: str) -> str:
    """Build a placeholder ``local@openconstructionerp.invalid`` from a name."""
    slug = re.sub(r"[^a-z0-9]+", ".", (name or "").strip().lower()).strip(".")
    return f"{slug or 'attendee'}@{FALLBACK_EMAIL_DOMAIN}"


def _mailto(contact: ICSAttendee) -> str:
    """Return the ``mailto:`` CAL-ADDRESS for a contact, synthesising if empty."""
    email = (contact.email or "").strip()
    if email.lower().startswith("mailto:"):
        email = email[len("mailto:") :].strip()
    if not email:
        email = _synth_email(contact.name)
    return "mailto:" + email


def _contact_line(prop: str, contact: ICSAttendee, *, is_attendee: bool) -> str:
    """Build an ORGANIZER or ATTENDEE content line with its parameters."""
    params: list[str] = []
    if contact.name:
        params.append(f"CN={_param_value(contact.name)}")
    if is_attendee:
        if contact.role:
            params.append(f"ROLE={contact.role}")
        if contact.partstat:
            params.append(f"PARTSTAT={contact.partstat}")
        if contact.rsvp:
            params.append("RSVP=TRUE")
    prefix = prop if not params else prop + ";" + ";".join(params)
    return f"{prefix}:{_mailto(contact)}"


def build_vevent_lines(event: CalendarEvent) -> list[str]:
    """Return the unfolded content lines of one VEVENT (BEGIN/END inclusive)."""
    dtstamp = event.dtstamp or datetime.now(UTC)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{escape_text(event.uid)}",
        f"DTSTAMP:{format_utc(dtstamp)}",
        f"DTSTART:{format_utc(event.start)}",
        f"DTEND:{format_utc(event.end)}",
    ]
    if event.summary:
        lines.append(f"SUMMARY:{escape_text(event.summary)}")
    if event.description:
        lines.append(f"DESCRIPTION:{escape_text(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{escape_text(event.location)}")
    if event.organizer is not None:
        lines.append(_contact_line("ORGANIZER", event.organizer, is_attendee=False))
    for attendee in event.attendees:
        lines.append(_contact_line("ATTENDEE", attendee, is_attendee=True))
    if event.rrule:
        lines.append(f"RRULE:{event.rrule}")
    if event.status:
        lines.append(f"STATUS:{event.status}")
    lines.append(f"SEQUENCE:{int(event.sequence)}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(
    events: Sequence[CalendarEvent],
    *,
    prodid: str = PRODID,
    calscale: str = "GREGORIAN",
) -> str:
    """Serialise events into a complete, folded, CRLF-terminated VCALENDAR."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{prodid}"]
    if calscale:
        lines.append(f"CALSCALE:{calscale}")
    for event in events:
        lines.extend(build_vevent_lines(event))
    lines.append("END:VCALENDAR")
    return _crlf_join(lines)


# ── Mapping a meeting to a CalendarEvent ───────────────────────────────────────


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _parse_time(raw: object) -> time | None:
    """Parse ``HH:MM`` / ``HH:MM:SS`` into a naive :class:`~datetime.time`."""
    if raw is None:
        return None
    match = _TIME_RE.match(str(raw).strip())
    if not match:
        return None
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def _parse_datetime(raw: str) -> tuple[datetime | None, bool]:
    """Parse a meeting date string.

    Returns ``(dt, has_time)`` where ``dt`` is a UTC-aware datetime (or
    ``None`` if unparseable) and ``has_time`` says whether the source carried a
    clock time (so the caller knows whether to apply a default start time).
    """
    text = (raw or "").strip()
    if not text:
        return None, False
    has_time = "T" in text.upper() or ":" in text
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = date.fromisoformat(text[:10])
        except ValueError:
            return None, False
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC), False
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt, has_time


def _resolve_times(
    meeting: Mapping[str, Any],
    meta: Mapping[str, Any],
    default_start: time,
    default_duration_minutes: int,
) -> tuple[datetime, datetime]:
    """Derive UTC start and end datetimes for a meeting.

    A meeting stores only a calendar date, so the start time comes from
    ``metadata.start_time`` (else ``default_start``) and the end from
    ``metadata.end_time`` or ``metadata.duration_minutes`` (else
    ``default_duration_minutes``). Everything is interpreted as UTC.
    """
    base, has_time = _parse_datetime(str(meeting.get("meeting_date") or ""))
    if base is None:
        base = datetime.now(UTC).replace(microsecond=0)
        has_time = False

    if has_time:
        start = base
    else:
        start_t = _parse_time(meta.get("start_time")) or default_start
        start = datetime.combine(base.date(), start_t, tzinfo=UTC)

    end_t = _parse_time(meta.get("end_time"))
    duration = meta.get("duration_minutes")
    if end_t is not None and not has_time:
        end = datetime.combine(start.date(), end_t, tzinfo=UTC)
        if end <= start:
            end = start + timedelta(minutes=default_duration_minutes)
    elif isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        end = start + timedelta(minutes=int(duration))
    else:
        end = start + timedelta(minutes=default_duration_minutes)
    return start, end


def _organizer_from_meeting(meeting: Mapping[str, Any], meta: Mapping[str, Any]) -> ICSAttendee | None:
    """Resolve the ORGANIZER from the chairperson, or ``None`` if unknown.

    Mirrors the minutes builder: a human name comes from
    ``metadata.chairperson_name`` (or ``organizer_name``); a bare contact UUID
    in ``chairperson_id`` is not a name and is ignored. An explicit
    ``organizer_email``/``chairperson_email`` is honoured when present.
    """
    name = str(meta.get("chairperson_name") or meta.get("organizer_name") or "").strip()
    email = str(meta.get("organizer_email") or meta.get("chairperson_email") or "").strip()
    if not name:
        raw = str(meeting.get("chairperson_id") or "").strip()
        if raw and not _looks_like_uuid(raw):
            name = raw
    if not name and not email:
        return None
    return ICSAttendee(name=name, email=email or None, role="CHAIR", partstat="ACCEPTED", rsvp=False)


def _attendee_from_entry(entry: Mapping[str, Any]) -> ICSAttendee:
    """Map one ``Meeting.attendees`` JSON entry to an ATTENDEE contact."""
    name = str(entry.get("name") or "").strip()
    email = str(entry.get("email") or entry.get("mail") or entry.get("mailto") or "").strip()
    return ICSAttendee(
        name=name or "Attendee",
        email=email or None,
        role="REQ-PARTICIPANT",
        partstat="NEEDS-ACTION",
        rsvp=True,
    )


def _description_from_meeting(meeting: Mapping[str, Any]) -> str:
    """Compose a DESCRIPTION from the agenda topics and the minutes summary."""
    lines: list[str] = []
    topics: list[str] = []
    for idx, item in enumerate(meeting.get("agenda_items") or [], 1):
        if not isinstance(item, Mapping):
            continue
        topic = str(item.get("topic") or item.get("title") or "").strip()
        if not topic:
            continue
        number = str(item.get("number") or idx).strip()
        topics.append(f"{number}. {topic}")
    if topics:
        lines.append("Agenda:")
        lines.extend(topics)
    minutes = str(meeting.get("minutes") or "").strip()
    if minutes:
        if lines:
            lines.append("")
        lines.append(minutes)
    return "\n".join(lines)


def event_from_meeting(
    meeting: Mapping[str, Any],
    *,
    dtstamp: datetime | None = None,
    default_start: time = time(9, 0),
    default_duration_minutes: int = 60,
    sequence: int | None = None,
) -> CalendarEvent:
    """Build a :class:`CalendarEvent` from a plain meeting mapping.

    ``meeting`` is a plain dict of the meeting fields (``id``, ``title``,
    ``meeting_date``, ``location``, ``chairperson_id``, ``status``,
    ``attendees``, ``agenda_items``, ``minutes``, ``recurrence_rule`` and
    ``metadata``/``metadata_``). A recurrence rule, when present, becomes the
    event's ``RRULE`` so a single event represents the whole series.
    """
    meta_raw = meeting.get("metadata")
    if not isinstance(meta_raw, Mapping):
        meta_raw = meeting.get("metadata_")
    meta: Mapping[str, Any] = meta_raw if isinstance(meta_raw, Mapping) else {}

    start, end = _resolve_times(meeting, meta, default_start, default_duration_minutes)

    if sequence is not None:
        seq = int(sequence)
    else:
        meta_seq = meta.get("ics_sequence")
        seq = int(meta_seq) if isinstance(meta_seq, int) and not isinstance(meta_seq, bool) and meta_seq >= 0 else 0

    description = _description_from_meeting(meeting)
    location = str(meeting.get("location") or "").strip()

    return CalendarEvent(
        uid=f"meeting-{meeting.get('id')}@{UID_DOMAIN}",
        start=start,
        end=end,
        summary=str(meeting.get("title") or "").strip(),
        description=description or None,
        location=location or None,
        organizer=_organizer_from_meeting(meeting, meta),
        attendees=[_attendee_from_entry(a) for a in (meeting.get("attendees") or []) if isinstance(a, Mapping)],
        rrule=map_rrule(meeting.get("recurrence_rule")),
        sequence=seq,
        status=_STATUS_MAP.get(str(meeting.get("status") or "").strip().lower()),
        dtstamp=dtstamp,
    )


def calendar_from_meeting(meeting: Mapping[str, Any], **kwargs: Any) -> str:
    """Convenience: build a full VCALENDAR text for a single meeting mapping.

    Any keyword arguments are forwarded to :func:`event_from_meeting` (e.g.
    ``dtstamp`` for deterministic output in tests).
    """
    return build_calendar([event_from_meeting(meeting, **kwargs)])
