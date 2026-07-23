# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure evidence-pack assembly engine for claims and disputes.

This module turns a flat list of heterogeneous source records into a single,
deterministic, ordered evidence pack. It is dependency-free: it imports only
the Python standard library (dataclasses, datetime, hashlib, typing), so the
ordering / grouping / digest contract can be unit-tested in isolation and on
the local Python 3.11 runner. The service layer feeds primitive values pulled
off the ORM rows (each becomes an :class:`EvidenceEntry`) and gets back an
:class:`EvidencePack` it can persist, render or hand to another party for
independent verification.

Determinism is the whole point of the engine. Given the same *set* of entries
in any input order, :func:`assemble_pack` produces the same section ordering,
the same per-section entry ordering and the same :attr:`EvidencePack.content_digest`.
Nothing here reads the wall clock or uses randomness; every input is explicit.

Section model
-------------
Each entry is routed into exactly one canonical section by :func:`section_for`,
which keys off ``source_module`` first and then ``kind``. The canonical order
is fixed by :data:`SECTION_ORDER`; only non-empty sections appear in a pack,
and within a section entries keep the global chronological order.

Chronology
----------
Entries are sorted by their parsed ``occurred_at`` ascending. Entries whose
``occurred_at`` is missing or unparseable sort *last* (they still belong in the
pack, just after everything that has a date). Ties - including all the
undated entries - are broken by ``(source_module, ref_id)`` so the order is
total and reproducible.

Content digest
--------------
:attr:`EvidencePack.content_digest` is the SHA-256 hex over the newline-joined
canonical lines ``ref_id|source_module|kind|occurred_at`` of the final ordered
entries. It changes when an entry is added, removed or reordered into a
different chronological position, and is stable across input permutations. The
digest of an empty pack is the SHA-256 of the empty string.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = [
    "SECTION_ORDER",
    "EvidenceEntry",
    "EvidenceSection",
    "EvidencePack",
    "parse_iso",
    "section_for",
    "assemble_pack",
]


# Canonical, fixed section order. A pack only ever lists the subset of these
# that actually has entries, but always in this relative order.
SECTION_ORDER: list[str] = [
    "notices",
    "correspondence",
    "rfis",
    "variations",
    "approvals",
    "delay",
    "timeline",
    "other",
]

# The bucket every unrecognised entry falls into. Must be a member of
# SECTION_ORDER (and, by convention, its last element).
_FALLBACK_SECTION = "other"


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 date or datetime into an aware UTC ``datetime``.

    The parser is deliberately forgiving and never raises - it returns
    ``None`` for anything it cannot understand, because a single malformed
    timestamp on one source row must not abort assembly of an entire pack.

    Handling rules:

    * A trailing ``Z`` (Zulu / UTC) is accepted and treated as ``+00:00``.
    * A full datetime (with or without an offset) is parsed; a naive value is
      assumed to be UTC, an aware value is converted to UTC.
    * A date-only string (``YYYY-MM-DD``) falls back to midnight UTC.
    * ``None``, empty / whitespace-only strings and unparseable input return
      ``None``.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    # Normalise a trailing Zulu marker into an explicit UTC offset, since
    # datetime.fromisoformat on 3.11 does not accept the bare "Z" suffix.
    candidate = text
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None

    # Date-only fallback: interpret as midnight UTC.
    if parsed is None:
        try:
            day = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
        return day.replace(tzinfo=UTC)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class EvidenceEntry:
    """A single source record considered for inclusion in an evidence pack.

    Attributes
    ----------
    ref_id:
        Identifier of the source record, unique within its ``source_module``.
    source_module:
        The originating module / record family (for example ``"notices"``,
        ``"correspondence"``, ``"changeorders"``, ``"timeline"``). Drives
        section routing and, together with ``ref_id``, identity for dedupe.
    kind:
        A finer-grained record type within the module (for example
        ``"delay_notice"``, ``"email"``, ``"rfi"``, ``"variation"``). Used as
        a secondary routing signal.
    title:
        Short human-readable label for the entry.
    occurred_at:
        The event time as an ISO-8601 string, or ``None`` when undated.
        Stored as the original string; chronology uses :func:`parse_iso`.
    actor_id:
        Optional identifier of the party associated with the record.
    summary:
        Optional free-text summary; carried through for rendering only.
    """

    ref_id: str
    source_module: str
    kind: str
    title: str
    occurred_at: str | None
    actor_id: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class EvidenceSection:
    """A named, ordered group of entries within a pack."""

    name: str
    entries: list[EvidenceEntry] = field(default_factory=list)


@dataclass(frozen=True)
class EvidencePack:
    """The assembled, deterministic evidence pack for a subject.

    Attributes
    ----------
    subject_ref:
        Identifier of the claim / dispute / variation the pack supports.
    basis:
        The basis the pack is assembled under (for example ``"dispute"``).
    entry_count:
        Number of entries after dedupe (the total across all sections).
    date_from:
        Original ``occurred_at`` string of the earliest dated entry, or
        ``None`` when no entry has a parseable date.
    date_to:
        Original ``occurred_at`` string of the latest dated entry, or
        ``None`` when no entry has a parseable date.
    sections:
        Non-empty sections in :data:`SECTION_ORDER` order.
    content_digest:
        SHA-256 hex over the canonical lines of the final ordered entries.
    """

    subject_ref: str
    basis: str
    entry_count: int
    date_from: str | None
    date_to: str | None
    sections: list[EvidenceSection]
    content_digest: str


# Routing tables for section_for.
#
# A record is routed by its source_module first; only when the module is not
# recognised do we fall back to inspecting its kind. This lets a generic
# "timeline" feed still land RFI- or notice-shaped rows in the right section
# via their kind, while a record that explicitly comes from the notices module
# is always treated as a notice regardless of how its kind is spelled.
#
# Every value on the right-hand side is a member of SECTION_ORDER.
_MODULE_TO_SECTION: dict[str, str] = {
    "notices": "notices",
    "notice": "notices",
    "correspondence": "correspondence",
    "letters": "correspondence",
    "email": "correspondence",
    "emails": "correspondence",
    "transmittals": "correspondence",
    "rfis": "rfis",
    "rfi": "rfis",
    "variations": "variations",
    "variation": "variations",
    "changeorders": "variations",
    "change_orders": "variations",
    "approvals": "approvals",
    "approval": "approvals",
    "approval_routes": "approvals",
    "delay": "delay",
    "delays": "delay",
    "delay_analysis": "delay",
    "forensic_delay": "delay",
    "timeline": "timeline",
    "activity_log": "timeline",
    "activitylog": "timeline",
}

# Substrings tested against a lower-cased kind when the module is unknown.
# Order matters: the first matching pair wins, so the more specific signals
# (notice, rfi, variation) are checked before the broad ones.
_KIND_KEYWORDS: list[tuple[str, str]] = [
    ("notice", "notices"),
    ("rfi", "rfis"),
    ("variation", "variations"),
    ("change_order", "variations"),
    ("changeorder", "variations"),
    ("approval", "approvals"),
    ("approved", "approvals"),
    ("delay", "delay"),
    ("eot", "delay"),
    ("letter", "correspondence"),
    ("email", "correspondence"),
    ("correspond", "correspondence"),
    ("transmittal", "correspondence"),
]


def section_for(entry: EvidenceEntry) -> str:
    """Return the canonical section name an entry belongs to.

    Routing precedence:

    1. ``source_module`` is matched (case-insensitively) against
       :data:`_MODULE_TO_SECTION`. A hit wins outright.
    2. Otherwise the ``kind`` is scanned for the keyword substrings in
       :data:`_KIND_KEYWORDS`, first match wins.
    3. Anything still unmatched is routed to ``"other"``.

    The returned value is always a member of :data:`SECTION_ORDER`.
    """
    module_key = (entry.source_module or "").strip().lower()
    mapped = _MODULE_TO_SECTION.get(module_key)
    if mapped is not None:
        return mapped

    kind_key = (entry.kind or "").strip().lower()
    if kind_key:
        for needle, section in _KIND_KEYWORDS:
            if needle in kind_key:
                return section

    return _FALLBACK_SECTION


def _dedupe_key(entry: EvidenceEntry) -> tuple[str, str]:
    """Identity used to drop duplicate source records: module + ref id."""
    return (entry.source_module, entry.ref_id)


def _tiebreak_key(entry: EvidenceEntry) -> tuple[str, str]:
    """Deterministic tiebreaker for entries that compare equal on date."""
    return (entry.source_module, entry.ref_id)


def _digest_line(entry: EvidenceEntry) -> str:
    """Canonical one-line representation of an entry for hashing."""
    occurred = entry.occurred_at if entry.occurred_at is not None else ""
    return f"{entry.ref_id}|{entry.source_module}|{entry.kind}|{occurred}"


def _content_digest(ordered: list[EvidenceEntry]) -> str:
    """SHA-256 hex over the newline-joined canonical lines of ``ordered``."""
    blob = "\n".join(_digest_line(entry) for entry in ordered)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def assemble_pack(
    subject_ref: str,
    entries: list[EvidenceEntry],
    *,
    basis: str = "dispute",
) -> EvidencePack:
    """Assemble a deterministic :class:`EvidencePack` from source ``entries``.

    Pipeline:

    1. **Dedupe** by ``(source_module, ref_id)``, keeping the first occurrence
       in input order.
    2. **Sort** chronologically by parsed ``occurred_at`` ascending. Undated /
       unparseable entries sort last; ties (and all undated entries) break by
       ``(source_module, ref_id)``.
    3. **Group** the ordered entries into sections following
       :data:`SECTION_ORDER`, emitting only non-empty sections and preserving
       the chronological order within each.
    4. **Span** ``date_from`` / ``date_to`` from the earliest / latest dated
       entries, carried as their original ``occurred_at`` strings (``None``
       when nothing parses).
    5. **Digest** the final ordered entries (step 2 order) into
       ``content_digest``.

    ``entry_count`` is the number of entries surviving dedupe.
    """
    # 1. Dedupe, preserving first-seen order.
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceEntry] = []
    for entry in entries:
        key = _dedupe_key(entry)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    # 2. Chronological sort with undated entries last and a total tiebreak.
    # We pair each entry with its parsed datetime once, then sort on a key of
    # (has_no_date_flag, sort_datetime, tiebreak). The flag forces None-dated
    # entries to the end; the datetime placeholder is only consulted for dated
    # entries so it never needs to be comparable against None.
    decorated: list[tuple[bool, datetime, tuple[str, str], EvidenceEntry]] = []
    epoch = datetime(1, 1, 1, tzinfo=UTC)
    for entry in deduped:
        parsed = parse_iso(entry.occurred_at)
        has_no_date = parsed is None
        sort_dt = parsed if parsed is not None else epoch
        decorated.append((has_no_date, sort_dt, _tiebreak_key(entry), entry))
    decorated.sort(key=lambda item: (item[0], item[1], item[2]))
    ordered = [item[3] for item in decorated]

    # 3. Group into canonical sections, keeping the global order within each.
    buckets: dict[str, list[EvidenceEntry]] = {name: [] for name in SECTION_ORDER}
    for entry in ordered:
        buckets[section_for(entry)].append(entry)
    sections = [EvidenceSection(name=name, entries=bucket) for name in SECTION_ORDER if (bucket := buckets[name])]

    # 4. Date span from the dated entries only (ordered already has dated
    # entries first, in ascending order, so the first/last dated ones bound
    # the span). Use the original occurred_at strings.
    dated = [entry for entry in ordered if parse_iso(entry.occurred_at) is not None]
    date_from = dated[0].occurred_at if dated else None
    date_to = dated[-1].occurred_at if dated else None

    # 5. Content digest over the final ordering.
    content_digest = _content_digest(ordered)

    return EvidencePack(
        subject_ref=subject_ref,
        basis=basis,
        entry_count=len(deduped),
        date_from=date_from,
        date_to=date_to,
        sections=sections,
        content_digest=content_digest,
    )
