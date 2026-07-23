# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

"""Pure engine that normalizes a raw phone-call / voice-note / verbal-instruction capture.

Why this exists: verbal, phone, and chat instructions on a construction project routinely go
unrecorded, and weeks later the parties dispute who said what. A site engineer is told on the
phone to change a detail, acts on it, and the instruction never makes it onto the record. This
module turns a raw, free-form capture (parties, a timestamp or two, and a transcript) into a
clean, structured, searchable record: a canonical direction and channel, a tidy party list, a
reliable duration, a short summary, and the instruction-bearing sentences pulled out of the
transcript. That way the verbal instruction is on the record and can be searched and cited later.

This module is pure and stdlib-only: no I/O, no database, no framework imports. Every public
function is independently testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Maximum number of parties we keep on a single call record. Beyond this it is almost certainly
# noise (a pasted distribution list rather than the people actually on the call).
_MAX_PARTIES = 20

# Summaries are meant to be a glanceable one-liner, so we hard-cap them.
_SUMMARY_MAX = 280

# Direction synonym map. Keys are matched case-insensitively against the trimmed raw hint. We map
# the many informal ways people describe call direction onto four canonical values. "us"/"team"
# read as an internal call between our own people.
_DIRECTION_SYNONYMS: dict[str, str] = {
    "in": "inbound",
    "inbound": "inbound",
    "incoming": "inbound",
    "received": "inbound",
    "from-them": "inbound",
    "out": "outbound",
    "outbound": "outbound",
    "outgoing": "outbound",
    "called": "outbound",
    "to-them": "outbound",
    "internal": "internal",
    "team": "internal",
    "us": "internal",
}

# Channel synonym map, matched case-insensitively against the trimmed raw hint.
_CHANNEL_SYNONYMS: dict[str, str] = {
    "phone": "phone",
    "call": "phone",
    "telephone": "phone",
    "voice": "voice_note",
    "voice_note": "voice_note",
    "voicenote": "voice_note",
    "voicemail": "voice_note",
    "audio": "voice_note",
    "chat": "chat",
    "im": "chat",
    "message": "chat",
    "sms": "chat",
    "whatsapp": "chat",
}

# Cue words and phrases that mark a sentence as an instruction or request. Matched
# case-insensitively with word boundaries so "add" does not fire inside "address". Multi-word
# cues such as "make sure" are matched as phrases. Kept deliberately broad: a false positive
# (keeping a borderline sentence) is far cheaper than dropping a real instruction from the record.
INSTRUCTION_CUES: frozenset[str] = frozenset(
    {
        "please",
        "need to",
        "needs to",
        "make sure",
        "ensure",
        "change",
        "add",
        "remove",
        "delete",
        "stop",
        "proceed",
        "confirm",
        "send",
        "hold",
        "revise",
        "update",
        "replace",
        "install",
        "demolish",
        "do not",
        "don't",
        "must",
        "should",
        "asap",
        "by tomorrow",
        "by friday",
    }
)

# Pre-compiled, word-boundary patterns for each cue. We build these once at import time. The
# boundary is relaxed at the edges of a cue when it starts/ends with a non-word character (for
# example "don't") so the apostrophe form still matches.
_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(
        (r"\b" if cue[:1].isalnum() else "") + re.escape(cue) + (r"\b" if cue[-1:].isalnum() else ""),
        re.IGNORECASE,
    )
    for cue in INSTRUCTION_CUES
)

# Sentence terminators used when carving a transcript into sentences.
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")

# Party separators: arrow, comma, semicolon, slash, pipe, and newlines.
_PARTY_SPLIT = re.compile(r"->|[,;/|\n]")

# Runs of whitespace, used to collapse internal spacing.
_WHITESPACE = re.compile(r"\s+")


@dataclass
class PhoneLogInput:
    """Raw, caller-supplied capture of a phone call, voice note, or verbal instruction."""

    raw_parties: str | list[str] = ""
    direction: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: int | None = None
    transcript: str = ""
    summary: str = ""
    channel: str = ""


@dataclass(frozen=True)
class NormalizedPhoneLog:
    """Cleaned, dispute-ready phone-log record derived from a PhoneLogInput."""

    parties: tuple[str, ...]
    direction: str
    channel: str
    duration_seconds: int | None
    summary: str
    instructions: tuple[str, ...]
    word_count: int


def normalize_direction(raw: str) -> str:
    """Map a free-text direction hint onto one of inbound / outbound / internal / unknown.

    Matching is case-insensitive on the trimmed value. Anything blank or unrecognised becomes
    "unknown".
    """
    key = (raw or "").strip().lower()
    if not key:
        return "unknown"
    return _DIRECTION_SYNONYMS.get(key, "unknown")


def normalize_channel(raw: str) -> str:
    """Map a free-text channel hint onto one of phone / voice_note / chat / other.

    A blank hint defaults to "phone": a phone call is the most common verbal-instruction channel
    on a site, so an unspecified capture is most safely treated as one. A non-blank value we do
    not recognise becomes "other" rather than being silently forced to phone.
    """
    key = (raw or "").strip().lower()
    if not key:
        return "phone"
    return _CHANNEL_SYNONYMS.get(key, "other")


def split_parties(raw: str | list[str]) -> tuple[str, ...]:
    """Normalize the parties into a clean, ordered, de-duplicated tuple (capped at 20).

    Accepts either a single free-text string or a list of strings. A string is split on the
    separators -> , ; / | and newlines. Each candidate is trimmed and its internal whitespace
    collapsed; empties are dropped. De-duplication is case-insensitive but keeps the FIRST spelling
    seen, because the first mention is usually the one the caller typed most carefully. Original
    order is preserved.
    """
    if isinstance(raw, list):
        candidates = list(raw)
    else:
        candidates = _PARTY_SPLIT.split(raw or "")

    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        name = _WHITESPACE.sub(" ", str(candidate).strip())
        if not name:
            continue
        marker = name.lower()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(name)
        if len(result) >= _MAX_PARTIES:
            break
    return tuple(result)


def derive_duration(started_at: str | None, ended_at: str | None, duration_seconds: int | None) -> int | None:
    """Return a non-negative call duration in seconds, or None when it cannot be determined.

    An explicit duration takes precedence over the timestamps: if the caller hands us a number we
    trust it (returning it when >= 0, else None) and never second-guess it from start/end. Only
    when no explicit duration is given do we compute it from two ISO-8601 timestamps. Any parse
    failure, a missing timestamp, or a negative span (end before start) yields None.
    """
    if duration_seconds is not None:
        return duration_seconds if duration_seconds >= 0 else None

    try:
        start = datetime.fromisoformat(started_at)  # type: ignore[arg-type]
        end = datetime.fromisoformat(ended_at)  # type: ignore[arg-type]
        span = int((end - start).total_seconds())
    except (ValueError, TypeError):
        return None
    return None if span < 0 else max(0, span)


def summarize(transcript: str, explicit_summary: str) -> str:
    """Produce a short summary (<= 280 chars) of the call.

    An explicit human summary always wins: it is returned trimmed and, if longer than 280 chars,
    truncated to 277 chars plus a trailing "..." so the result stays within the cap. With no
    explicit summary we fall back to the first sentence of the transcript; if there is no sentence
    break, or that first sentence is itself too long, we cap the transcript at 277 chars + "...".
    A blank transcript and blank summary yield "".
    """
    explicit = (explicit_summary or "").strip()
    if explicit:
        if len(explicit) > _SUMMARY_MAX:
            return explicit[: _SUMMARY_MAX - 3] + "..."
        return explicit

    text = (transcript or "").strip()
    if not text:
        return ""

    first = _SENTENCE_SPLIT.split(text, maxsplit=1)[0].strip()
    if first and len(first) <= _SUMMARY_MAX:
        return first
    return text[: _SUMMARY_MAX - 3] + "..."


def extract_instructions(transcript: str, limit: int = 10) -> tuple[str, ...]:
    """Pull instruction-bearing sentences out of a transcript.

    The transcript is split into sentences on . ! ? and newlines. A sentence is kept when it
    contains any cue from INSTRUCTION_CUES (case-insensitive, word-boundary aware). Kept sentences
    are trimmed and de-duplicated (case-insensitive, first spelling wins), order is preserved, and
    the result is capped at `limit`.
    """
    if not transcript:
        return ()

    seen: set[str] = set()
    result: list[str] = []
    for raw_sentence in _SENTENCE_SPLIT.split(transcript):
        sentence = _WHITESPACE.sub(" ", raw_sentence.strip())
        if not sentence:
            continue
        if not any(pattern.search(sentence) for pattern in _CUE_PATTERNS):
            continue
        marker = sentence.lower()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(sentence)
        if len(result) >= limit:
            break
    return tuple(result)


def normalize(item: PhoneLogInput) -> NormalizedPhoneLog:
    """Compose every rule above into a single clean NormalizedPhoneLog.

    word_count is the number of whitespace-separated tokens in the transcript.
    """
    return NormalizedPhoneLog(
        parties=split_parties(item.raw_parties),
        direction=normalize_direction(item.direction),
        channel=normalize_channel(item.channel),
        duration_seconds=derive_duration(item.started_at, item.ended_at, item.duration_seconds),
        summary=summarize(item.transcript, item.summary),
        instructions=extract_instructions(item.transcript),
        word_count=len((item.transcript or "").split()),
    )
