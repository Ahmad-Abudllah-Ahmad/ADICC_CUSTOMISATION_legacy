# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure correspondence-thread consolidator.

A project accumulates a stream of correspondence - messages, requests for
information, notices - and the recurring question is which open topics are
still waiting on a reply, and from whom. This engine groups individual
messages into conversation threads and reports, per thread, who owes the next
move so the open items are visible at a glance.

Given every :class:`Message`, :func:`build_digest` produces a
:class:`CommsDigest`: one :class:`ThreadDigest` per conversation with its
participants, span, latest message, and a single ``awaiting`` verdict -
:data:`AWAITING_US` when the ball is in our court, :data:`AWAITING_THEM` when
it sits with the other party, or :data:`AWAITING_NONE` when nothing is
outstanding. A thread is open while it is awaiting anyone.

Messages are grouped by an explicit ``thread_key`` when one is set, otherwise
by their normalized subject (leading ``re:`` / ``fw:`` / ``fwd:`` prefixes
stripped, whitespace collapsed, lowercased) so a reply chain folds into one
thread regardless of how many times the subject was re-prefixed.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on
the local Python 3.11 runner exactly like the cycle-time and impact engines.
The engine is deterministic: the caller passes the current time in as ``now``
rather than the engine reading the clock. A thin service layer gathers the
correspondence rows and feeds them in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

#: The latest message asks for a reply and it came from the other party, so
#: the next move is ours.
AWAITING_US = "us"
#: The latest message asks for a reply and it went out from us, so we are
#: waiting on the other party.
AWAITING_THEM = "them"
#: Nothing is outstanding on the thread - the latest message wants no reply.
AWAITING_NONE = "none"

#: Direction of a message relative to us: an inbound message arrived from an
#: external party, an outbound one was sent by us.
DIRECTION_INBOUND = "inbound"
DIRECTION_OUTBOUND = "outbound"

#: Leading reply / forward marker on a subject line, stripped repeatedly so a
#: chain such as ``Re: Fwd: Re: ...`` collapses to its bare subject. Matched
#: case-insensitively.
_SUBJECT_PREFIX = re.compile(r"^\s*(re|fw|fwd)\s*:\s*", re.IGNORECASE)

#: Run of whitespace inside a subject, collapsed to a single plain space.
_WHITESPACE = re.compile(r"\s+")

#: Inert stand-in datetime for undated messages in a sort key. An undated row
#: is always ordered by a separate boolean flag first, so this value is never
#: actually compared against a real timestamp; it only keeps the sort key
#: well-typed (a tuple field cannot be ``None`` and a real datetime at once).
#: Aware so it never trips the naive-vs-aware comparison guard in
#: :func:`_sort_key`.
_EPOCH = datetime(1, 1, 1, tzinfo=UTC)


def _sort_key(value: datetime | None) -> datetime:
    """Map a parsed timestamp to a comparable, aware datetime for sorting.

    A naive datetime is read as UTC so naive and offset-aware ``sent_at``
    strings in the same thread can be ordered without a ``TypeError``; ``None``
    (undated) maps to :data:`_EPOCH`, which an undated boolean flag always
    orders separately so the substituted value is never the deciding key.
    """
    if value is None:
        return _EPOCH
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Message:
    """One piece of correspondence feeding the digest.

    ``sent_at`` is the raw stored string (ISO-8601 date or datetime) and is
    parsed defensively inside the engine; a blank or unparseable value is
    treated as undated and sorts after every dated message in its thread.
    ``direction`` is :data:`DIRECTION_INBOUND` for a message that arrived from
    an external party or :data:`DIRECTION_OUTBOUND` for one we sent.
    ``requires_reply`` marks a message that asks for a response.
    ``thread_key``, when non-empty, pins the message to a conversation
    explicitly and overrides subject-based grouping.
    """

    ref_id: str
    subject: str
    sender: str
    sent_at: str | None
    direction: str
    requires_reply: bool = False
    thread_key: str = ""


@dataclass(frozen=True)
class ThreadDigest:
    """Consolidated state of one conversation thread.

    ``subject`` is the human-readable subject of the earliest dated message
    (or the first message when none are dated), kept verbatim rather than
    normalized. ``participants`` is the sorted set of distinct senders.
    ``first_at`` / ``last_at`` are the earliest / latest ``sent_at`` strings
    present, or ``None`` when no message in the thread is dated.
    ``last_direction`` and ``last_sender`` come from the latest message in
    thread order. ``awaiting`` is one of :data:`AWAITING_US`,
    :data:`AWAITING_THEM`, or :data:`AWAITING_NONE`; ``is_open`` is true while
    ``awaiting`` is not :data:`AWAITING_NONE`.
    """

    thread_key: str
    subject: str
    message_count: int
    participants: tuple[str, ...]
    first_at: str | None
    last_at: str | None
    last_direction: str
    last_sender: str
    awaiting: str
    is_open: bool


@dataclass(frozen=True)
class CommsDigest:
    """Project-wide roll-up of every correspondence thread.

    ``threads`` is ordered open-first, then by most recent ``last_at`` (undated
    threads last), then by ``thread_key``. ``generated_at`` is the caller-
    supplied ``now`` rendered with :meth:`datetime.isoformat`.
    """

    generated_at: str
    thread_count: int
    open_count: int
    awaiting_us_count: int
    threads: tuple[ThreadDigest, ...]


def normalize_subject(subject: str) -> str:
    """Reduce *subject* to a stable grouping key.

    Strips every leading ``re:`` / ``fw:`` / ``fwd:`` prefix in turn, collapses
    internal runs of whitespace to a single space, strips the ends, and
    lowercases. For example ``"Re: Re: Site access"`` becomes ``"site access"``.
    """
    text = subject
    while True:
        stripped = _SUBJECT_PREFIX.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    text = _WHITESPACE.sub(" ", text).strip()
    return text.lower()


def parse_dt(value: str | None) -> datetime | None:
    """Best-effort ISO parse of a stored timestamp string.

    Accepts a date (``2026-07-01``) or a datetime (``2026-07-01T09:00:00`` with
    an optional offset or trailing ``Z``). Returns ``None`` for a blank or
    unparseable value and never raises, so an undated or garbage timestamp is
    simply treated as "no date" rather than aborting the digest.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text[:10])  # date-only fallback
        except ValueError:
            return None


def effective_key(message: Message) -> str:
    """Grouping key for *message*: its ``thread_key`` if set, else its subject.

    An explicit ``thread_key`` wins so callers can pin a conversation that
    spans differing subject lines; otherwise the normalized subject groups a
    reply chain together.
    """
    if message.thread_key:
        return message.thread_key
    return normalize_subject(message.subject)


def _awaiting_for(latest: Message) -> str:
    """Who owes the next reply given the latest message in a thread."""
    if not latest.requires_reply:
        return AWAITING_NONE
    if latest.direction == DIRECTION_INBOUND:
        return AWAITING_US
    return AWAITING_THEM


def _digest_thread(thread_key: str, messages: list[Message]) -> ThreadDigest:
    """Consolidate one thread's *messages* (already grouped) into a digest."""
    # Pair each message with its parsed timestamp once, preserving input order.
    paired = [(m, parse_dt(m.sent_at)) for m in messages]

    # Sort by sent_at ascending with undated messages last, stable. The undated
    # flag is the first key so a missing date never has to compare against a
    # real one; ``_sort_key`` coerces dated rows to aware UTC (and undated rows
    # to an inert stand-in their flag has already ordered last), and the
    # enumerate index keeps equal-timestamp and undated rows in input order.
    ordered_pairs = [
        pair
        for _, pair in sorted(
            enumerate(paired),
            key=lambda item: (item[1][1] is None, _sort_key(item[1][1]), item[0]),
        )
    ]
    ordered = [m for m, _ in ordered_pairs]

    dated = [(m, dt) for m, dt in ordered_pairs if dt is not None]
    # Headline subject: earliest dated message, or the first message overall
    # when none are dated. ``ordered`` already has the earliest dated row first.
    subject = dated[0][0].subject if dated else ordered[0].subject

    first_at = dated[0][0].sent_at if dated else None
    last_at = dated[-1][0].sent_at if dated else None

    latest = ordered[-1]
    awaiting = _awaiting_for(latest)
    participants = tuple(sorted({m.sender for m in messages}))

    return ThreadDigest(
        thread_key=thread_key,
        subject=subject,
        message_count=len(messages),
        participants=participants,
        first_at=first_at,
        last_at=last_at,
        last_direction=latest.direction,
        last_sender=latest.sender,
        awaiting=awaiting,
        is_open=awaiting != AWAITING_NONE,
    )


def build_digest(messages: Iterable[Message], now: datetime) -> CommsDigest:
    """Group *messages* into conversation threads and summarize each.

    Messages are bucketed by :func:`effective_key`. Within a thread they are
    ordered by ``sent_at`` ascending with undated messages last; the thread's
    headline ``subject`` is taken from the earliest dated message (or the first
    message when none are dated) and its ``awaiting`` verdict from the latest.
    Threads are ordered open-first, then by most recent ``last_at`` (undated
    last), then by ``thread_key``. ``now`` supplies ``generated_at`` and is the
    only time source - the engine never reads the clock itself.
    """
    grouped: dict[str, list[Message]] = {}
    for message in messages:
        grouped.setdefault(effective_key(message), []).append(message)

    threads = [_digest_thread(key, group) for key, group in grouped.items()]

    # Order open threads first, then by most recent last_at (undated last),
    # then thread_key ascending. Done as three stable passes from least to most
    # significant key so the date pass can run descending (reverse=True) without
    # flipping the open / undated booleans: every earlier pass breaks ties of
    # the next. Undated threads share the inert _sort_key stand-in and so keep
    # the order the thread_key pass gave them.
    threads.sort(key=lambda t: t.thread_key)
    threads.sort(key=lambda t: _sort_key(parse_dt(t.last_at)), reverse=True)
    threads.sort(key=lambda t: (not t.is_open, parse_dt(t.last_at) is None))

    return CommsDigest(
        generated_at=now.isoformat(),
        thread_count=len(threads),
        open_count=sum(1 for t in threads if t.is_open),
        awaiting_us_count=sum(1 for t in threads if t.awaiting == AWAITING_US),
        threads=tuple(threads),
    )


__all__ = [
    "AWAITING_NONE",
    "AWAITING_THEM",
    "AWAITING_US",
    "DIRECTION_INBOUND",
    "DIRECTION_OUTBOUND",
    "CommsDigest",
    "Message",
    "ThreadDigest",
    "build_digest",
    "effective_key",
    "normalize_subject",
    "parse_dt",
]
