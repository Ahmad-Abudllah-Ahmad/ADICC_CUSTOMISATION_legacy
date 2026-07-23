# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, plain-language helpers for correspondence.

This module is deliberately free of any database, ORM, or FastAPI import so
it can be reasoned about and unit-tested in isolation. It answers the small
set of questions a site engineer or contract administrator anywhere in the
world asks about a letter, an RFI, or a notice:

    - How long did a reply take (response time in days)?
    - Is a reply overdue (given a due date and a reference "today")?
    - What share of what we sent has been answered (response rate)?
    - What does the type / status / direction word mean in my language?

Design rules that keep it usable worldwide:

    - No hardcoded locale. Dates are ISO 8601 (``YYYY-MM-DD``) on the wire;
      the "response due" window is a caller-supplied parameter, never a
      baked-in assumption about a jurisdiction.
    - No 500s and no ``NaN`` / ``inf``. Bad input raises a clean
      :class:`ValueError` with a plain message, or returns a well-defined
      value (an empty set has a response rate of ``0.0``, not a crash).
    - Every figure is explainable. The report helpers expose the raw
      components (counts, dates, day-deltas) next to a one-line sentence,
      so a reviewer can see exactly how a number was derived.
    - Localisation covers English, German, and Russian with an English
      fallback for anything unknown, mirroring the platform's en/de/ru
      message convention.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

# ── Language handling ─────────────────────────────────────────────────────

#: Languages with first-class translations. Anything else falls back to English.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "de", "ru")

#: Fallback language used whenever a requested one is unknown or unsupported.
DEFAULT_LANGUAGE = "en"

#: A neutral default response window (in calendar days) when a caller has no
#: contract-specific figure. It is only a default: every function that uses a
#: due window takes ``response_due_days`` as an explicit parameter so a project
#: in any jurisdiction can set its own value.
DEFAULT_RESPONSE_DUE_DAYS = 14


def normalize_language(language: str | None) -> str:
    """Return a supported language code, defaulting to English.

    The match is case-insensitive and tolerant of region tags, so ``"DE"``,
    ``"de-AT"`` and ``"de_DE"`` all resolve to ``"de"``. Unknown or empty
    input resolves to :data:`DEFAULT_LANGUAGE`.
    """
    if not language:
        return DEFAULT_LANGUAGE
    base = language.replace("_", "-").split("-", 1)[0].strip().lower()
    if base in SUPPORTED_LANGUAGES:
        return base
    return DEFAULT_LANGUAGE


# ── Localised vocabulary ──────────────────────────────────────────────────

# Correspondence types match the schema pattern (letter|email|notice|memo).
_TYPE_LABELS: dict[str, dict[str, str]] = {
    "letter": {"en": "Letter", "de": "Brief", "ru": "Письмо"},
    "email": {"en": "Email", "de": "E-Mail", "ru": "Электронное письмо"},
    "notice": {"en": "Notice", "de": "Mitteilung", "ru": "Уведомление"},
    "memo": {"en": "Memo", "de": "Memo", "ru": "Служебная записка"},
}

_DIRECTION_LABELS: dict[str, dict[str, str]] = {
    "incoming": {"en": "Incoming", "de": "Eingehend", "ru": "Входящее"},
    "outgoing": {"en": "Outgoing", "de": "Ausgehend", "ru": "Исходящее"},
}

# Status words describe where a piece of correspondence stands in its reply
# lifecycle. They are derived, not stored, by :func:`derive_status`.
_STATUS_LABELS: dict[str, dict[str, str]] = {
    "draft": {"en": "Draft", "de": "Entwurf", "ru": "Черновик"},
    "no_response_needed": {
        "en": "No response needed",
        "de": "Keine Antwort erforderlich",
        "ru": "Ответ не требуется",
    },
    "awaiting_response": {
        "en": "Awaiting response",
        "de": "Wartet auf Antwort",
        "ru": "Ожидает ответа",
    },
    "responded": {"en": "Responded", "de": "Beantwortet", "ru": "Отвечено"},
    "overdue": {"en": "Overdue", "de": "Ueberfaellig", "ru": "Просрочено"},
}


def _lookup(table: dict[str, dict[str, str]], code: str | None, language: str) -> str:
    """Resolve one vocabulary entry with an English then raw-code fallback."""
    lang = normalize_language(language)
    if not code:
        return ""
    key = code.strip().lower()
    entry = table.get(key)
    if entry is None:
        # Unknown code: return it unchanged so nothing is silently dropped.
        return code
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or code


def localize_type(type_code: str | None, language: str = DEFAULT_LANGUAGE) -> str:
    """Return a human label for a correspondence type in ``language``."""
    return _lookup(_TYPE_LABELS, type_code, language)


def localize_direction(direction_code: str | None, language: str = DEFAULT_LANGUAGE) -> str:
    """Return a human label for a direction (incoming / outgoing)."""
    return _lookup(_DIRECTION_LABELS, direction_code, language)


def localize_status(status_code: str | None, language: str = DEFAULT_LANGUAGE) -> str:
    """Return a human label for a derived reply status in ``language``."""
    return _lookup(_STATUS_LABELS, status_code, language)


# ── Date parsing (ISO 8601 only) ──────────────────────────────────────────


def parse_iso_date(value: str | date) -> date:
    """Parse an ISO 8601 ``YYYY-MM-DD`` string into a :class:`date`.

    Accepts an already-parsed :class:`date` unchanged so callers can pass
    either form. Raises a clean :class:`ValueError` on anything else, never a
    bare ``TypeError`` or a 500-inducing surprise.
    """
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a non-empty ISO 8601 string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"invalid ISO 8601 date: {value!r}") from exc


# ── Core numeric helpers ──────────────────────────────────────────────────


def response_time_days(date_sent: str | date, date_responded: str | date) -> int:
    """Whole calendar days between a sent date and the date it was answered.

    Both bounds are ISO dates (or :class:`date` objects). A reply on the same
    day is ``0``. A response dated *before* the sent date is not a
    well-defined turnaround, so it raises :class:`ValueError` rather than
    returning a misleading negative number.
    """
    sent = parse_iso_date(date_sent)
    responded = parse_iso_date(date_responded)
    delta = (responded - sent).days
    if delta < 0:
        raise ValueError("response date is before the sent date")
    return delta


def compute_due_date(date_sent: str | date, response_due_days: int = DEFAULT_RESPONSE_DUE_DAYS) -> date:
    """Return the date by which a reply is due, given the sent date.

    ``response_due_days`` is the caller's contractual window and must be zero
    or positive; a negative window is meaningless and raises
    :class:`ValueError`.
    """
    if response_due_days < 0:
        raise ValueError("response_due_days must be zero or positive")
    from datetime import timedelta

    return parse_iso_date(date_sent) + timedelta(days=response_due_days)


def is_overdue(due_date: str | date, reference_date: str | date) -> bool:
    """True when ``reference_date`` is strictly after ``due_date``.

    ``reference_date`` is the "today" the caller measures against (passed in
    rather than read from the clock, so results are deterministic and
    timezone-free). Being due exactly today is not yet overdue.
    """
    due = parse_iso_date(due_date)
    reference = parse_iso_date(reference_date)
    return reference > due


def days_until_due(due_date: str | date, reference_date: str | date) -> int:
    """Signed day count from ``reference_date`` to ``due_date``.

    Positive means days remaining, zero means due today, negative means days
    overdue. Exposed so a UI can show "3 days left" or "2 days late" without
    re-deriving the arithmetic.
    """
    due = parse_iso_date(due_date)
    reference = parse_iso_date(reference_date)
    return (due - reference).days


def response_rate(responded_count: int, sent_count: int) -> float:
    """Share of sent correspondence that has been answered, in ``[0.0, 1.0]``.

    Guards the two edge cases that would otherwise crash or mislead:

        - Nothing sent (``sent_count == 0``): returns ``0.0`` instead of
          dividing by zero and producing ``NaN``.
        - Inconsistent counts (negative, or more answered than sent): raises
          :class:`ValueError`, because that is a data-integrity problem the
          caller should see, not a value to paper over.
    """
    if responded_count < 0 or sent_count < 0:
        raise ValueError("counts must be zero or positive")
    if responded_count > sent_count:
        raise ValueError("responded_count cannot exceed sent_count")
    if sent_count == 0:
        return 0.0
    return responded_count / sent_count


# ── Derived status ────────────────────────────────────────────────────────


def derive_status(
    *,
    date_sent: str | date | None,
    date_responded: str | date | None,
    reference_date: str | date | None = None,
    response_due_days: int = DEFAULT_RESPONSE_DUE_DAYS,
    needs_response: bool = True,
) -> str:
    """Work out the reply status of a single item from its dates.

    Returns one of the keys in :data:`_STATUS_LABELS`:

        - ``draft`` - not sent yet (no ``date_sent``).
        - ``no_response_needed`` - sent, but ``needs_response`` is False.
        - ``responded`` - a reply date is recorded.
        - ``overdue`` - no reply yet and the due date has passed relative to
          ``reference_date``.
        - ``awaiting_response`` - no reply yet but still within the window.

    ``reference_date`` defaults to nothing; without it we cannot tell overdue
    from merely waiting, so the item stays ``awaiting_response``.
    """
    if not date_sent:
        return "draft"
    if date_responded:
        return "responded"
    if not needs_response:
        return "no_response_needed"
    if reference_date is None:
        return "awaiting_response"
    due = compute_due_date(date_sent, response_due_days)
    if is_overdue(due, reference_date):
        return "overdue"
    return "awaiting_response"


# ── Explainable reports ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ResponseRateReport:
    """A response-rate figure alongside the components it was derived from."""

    sent_count: int
    responded_count: int
    outstanding_count: int
    rate: float
    percent: float
    explanation: str

    def as_dict(self) -> dict[str, object]:
        """Return a plain dict (JSON-friendly) view of the report."""
        return asdict(self)


@dataclass(frozen=True)
class ItemStatusReport:
    """A single item's derived status with the dates and deltas behind it."""

    status: str
    status_label: str
    type_label: str
    direction_label: str
    response_time_days: int | None
    days_until_due: int | None
    due_date: str | None
    explanation: str

    def as_dict(self) -> dict[str, object]:
        """Return a plain dict (JSON-friendly) view of the report."""
        return asdict(self)


def build_response_rate_report(
    responded_count: int,
    sent_count: int,
    language: str = DEFAULT_LANGUAGE,
) -> ResponseRateReport:
    """Compute the response rate and a one-line explainer in ``language``.

    The explainer names the raw components (answered, sent, outstanding) so
    the percentage is never a black box. An empty set reads as ``0%`` of
    nothing, which the sentence states plainly rather than hiding.
    """
    rate = response_rate(responded_count, sent_count)
    outstanding = sent_count - responded_count
    percent = round(rate * 100, 1)
    lang = normalize_language(language)
    templates = {
        "en": "Response rate {percent}%: {responded} of {sent} answered, {outstanding} outstanding.",
        "de": "Antwortquote {percent}%: {responded} von {sent} beantwortet, {outstanding} offen.",
        "ru": "Доля ответов {percent}%: отвечено {responded} из {sent}, без ответа {outstanding}.",
    }
    explanation = templates[lang].format(
        percent=_trim_number(percent),
        responded=responded_count,
        sent=sent_count,
        outstanding=outstanding,
    )
    return ResponseRateReport(
        sent_count=sent_count,
        responded_count=responded_count,
        outstanding_count=outstanding,
        rate=rate,
        percent=percent,
        explanation=explanation,
    )


def build_item_status_report(
    *,
    type_code: str,
    direction_code: str,
    date_sent: str | date | None,
    date_responded: str | date | None,
    reference_date: str | date | None = None,
    response_due_days: int = DEFAULT_RESPONSE_DUE_DAYS,
    needs_response: bool = True,
    language: str = DEFAULT_LANGUAGE,
) -> ItemStatusReport:
    """Summarise one correspondence item in plain language.

    Pulls together the derived status, the localised type / direction /
    status words, and the two time figures (turnaround if answered, days to
    or past the due date if still open) plus a single explanatory sentence.
    Every number is also returned as a structured field so a caller can build
    its own UI without re-parsing the sentence.
    """
    lang = normalize_language(language)
    status = derive_status(
        date_sent=date_sent,
        date_responded=date_responded,
        reference_date=reference_date,
        response_due_days=response_due_days,
        needs_response=needs_response,
    )

    turnaround: int | None = None
    if date_sent and date_responded:
        turnaround = response_time_days(date_sent, date_responded)

    due_iso: str | None = None
    until_due: int | None = None
    if date_sent and needs_response and not date_responded:
        due = compute_due_date(date_sent, response_due_days)
        due_iso = due.isoformat()
        if reference_date is not None:
            until_due = days_until_due(due, reference_date)

    type_label = localize_type(type_code, lang)
    direction_label = localize_direction(direction_code, lang)
    status_label = localize_status(status, lang)

    explanation = _explain_item(
        lang=lang,
        type_label=type_label,
        status=status,
        status_label=status_label,
        turnaround=turnaround,
        until_due=until_due,
        due_iso=due_iso,
    )

    return ItemStatusReport(
        status=status,
        status_label=status_label,
        type_label=type_label,
        direction_label=direction_label,
        response_time_days=turnaround,
        days_until_due=until_due,
        due_date=due_iso,
        explanation=explanation,
    )


def _explain_item(
    *,
    lang: str,
    type_label: str,
    status: str,
    status_label: str,
    turnaround: int | None,
    until_due: int | None,
    due_iso: str | None,
) -> str:
    """Build the one-line, plain-language sentence for an item report."""
    if status == "responded" and turnaround is not None:
        templates = {
            "en": "{type}: {status}. The reply took {days} day(s).",
            "de": "{type}: {status}. Die Antwort dauerte {days} Tag(e).",
            "ru": "{type}: {status}. Ответ занял {days} дн.",
        }
        return templates[lang].format(type=type_label, status=status_label, days=turnaround)

    if status == "overdue" and until_due is not None:
        overdue_by = -until_due
        templates = {
            "en": "{type}: {status} by {days} day(s); reply was due {due}.",
            "de": "{type}: {status} seit {days} Tag(en); Antwort war am {due} faellig.",
            "ru": "{type}: {status} на {days} дн.; ответ ожидался {due}.",
        }
        return templates[lang].format(type=type_label, status=status_label, days=overdue_by, due=due_iso)

    if status == "awaiting_response" and until_due is not None and due_iso is not None:
        templates = {
            "en": "{type}: {status}; {days} day(s) remain until {due}.",
            "de": "{type}: {status}; {days} Tag(e) verbleiben bis {due}.",
            "ru": "{type}: {status}; осталось {days} дн. до {due}.",
        }
        return templates[lang].format(type=type_label, status=status_label, days=until_due, due=due_iso)

    # Fallback for draft / no_response_needed / awaiting-without-reference.
    templates = {
        "en": "{type}: {status}.",
        "de": "{type}: {status}.",
        "ru": "{type}: {status}.",
    }
    return templates[lang].format(type=type_label, status=status_label)


def _trim_number(value: float) -> str:
    """Render a rounded number without a trailing ``.0`` for whole values."""
    if value == int(value):
        return str(int(value))
    return str(value)
