# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure event-reconciliation correlation engine.

A project's record of an event scatters across modules and channels: a single
site instruction surfaces as an inbound email, a request for information, a
change order and an entry in a daily diary, each in its own table with its own
identifier. The recurring question is which of these heterogeneous records are
really about the *same* underlying event, so the trail can be stitched back
together for a claim, an audit, or a coordination view. This engine answers it
by scoring every candidate pair and emitting explainable, deduplicated links.

It is a *correlation* engine, not a store: it owns no records and decides
nothing on its own. The integrator gathers rows from the change family,
correspondence, RFIs, NCRs, the diary and so on, projects each onto a uniform
:class:`CandidateRecord`, and feeds the set in. Each emitted :class:`ScoredLink`
carries a confidence in ``[0, 1]`` and a tuple of human-readable ``reasons``
naming exactly which signals fired, so a reviewer can confirm or reject a link
on the evidence rather than on a black-box number.

No database, no ORM, no ``app.*`` imports, no network - stdlib only - so it
unit-tests on the local Python 3.11 runner exactly like the sibling change /
cost engines. It is deterministic and reads no clock: any sense of "now" is
implicit in the records' own ``occurred_at`` values, and the date-proximity
signal decays purely as a function of the gap between two records. Identical
input always yields an identical, stably ordered result.

Signals and the confidence blend
--------------------------------
A pair's confidence is a saturating blend of independent weighted signals. Each
signal contributes a fraction in ``[0, 1]`` of how strongly it fires, scaled by
its weight; the weighted contributions are summed and the total is clamped to
``[0, 1]`` (so two strong signals reinforce each other up to full confidence
without any single signal being able to exceed it). The signals are:

* **shared entity reference** (weight :data:`W_SHARED_REF`, the strongest
  signal). Two records that both cite the same tracked code - ``RFI-123``,
  ``CO-014``, ``MoC-7``, ``VO-3``, ``NCR-9`` and the like - are almost certainly
  about the same event. Codes are parsed out of the subject and body with
  :data:`_CODE_RE` and unioned with the explicit ``refs`` tuple each record
  carries; the signal fires (fully) when the two records share at least one
  normalized code. A single shared code is enough on its own to clear the
  default threshold.
* **normalized-subject match** (weight :data:`W_SUBJECT`). Reply / forward
  prefixes (``Re:`` / ``Fwd:`` / ``Fw:`` / ``Aw:``) are stripped, whitespace is
  collapsed and the text lowercased (see :func:`normalize_subject`); when two
  records reduce to the same non-empty subject the signal fires fully. An empty
  subject never matches another empty subject - blank is not evidence.
* **party match with date proximity** (weight :data:`W_PARTY_TIME`). The same
  responsible party raising two records close together in time is corroborating
  evidence; far apart it is weak. This signal fires only when the parties match
  (non-blank, case-insensitively equal) AND both records are dated, and its
  strength is the date-proximity decay below - so a party match decays to zero
  as the records drift :data:`MAX_WINDOW_DAYS` apart, and contributes nothing
  beyond that window or when either date is missing.
* **embedding similarity** (weight :data:`W_SIMILARITY`, optional). When the
  caller supplies a ``similarity_fn(left, right) -> float`` the engine folds its
  clamped ``[0, 1]`` return in as a signal; when it is ``None`` the signal is
  skipped entirely and the engine calls no model and touches no network. The
  function is invoked at most once per pair.

Date-proximity decay
--------------------
:func:`date_proximity` turns the absolute gap between two ``occurred_at`` values
into a closeness fraction in ``[0, 1]``: ``1.0`` for simultaneous records,
decaying **linearly** to ``0.0`` at :data:`MAX_WINDOW_DAYS` and staying at
``0.0`` beyond it. Linear (rather than exponential) decay is used so the
falloff is transparent and easy to reason about from the constant alone; the
gap is measured in whole-second resolution so sub-day proximity still ranks.

Relations
---------
Every link is undirected and carries the single relation
:data:`RELATION_SAME_EVENT`; the constant exists so a UI and the persistence
layer can switch on a stable token rather than a bare string, and so the
vocabulary can grow later without changing call sites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Sequence

# --------------------------------------------------------------------------- #
# Signal weights (transparent blend). Larger == more decisive. A shared tracked
# code is by far the strongest single signal - two records citing the same
# RFI / CO / NCR are almost always the same event - so it alone clears the
# default threshold. The remaining signals corroborate but do not, individually,
# assert a link.
# --------------------------------------------------------------------------- #

#: Weight of a shared tracked entity reference (the dominant signal).
W_SHARED_REF = 0.60

#: Weight of a normalized-subject match.
W_SUBJECT = 0.30

#: Weight of a same-party match scaled by date proximity.
W_PARTY_TIME = 0.20

#: Weight of the optional embedding-similarity signal.
W_SIMILARITY = 0.25

# --------------------------------------------------------------------------- #
# Decay / threshold calibration.
# --------------------------------------------------------------------------- #

#: The date-proximity window. Two records exactly this many days apart (or more)
#: contribute nothing from the party-and-time signal; closer than this the
#: signal ramps linearly up to full strength at zero gap. A standard month is a
#: defensible default for "close enough in time to plausibly be the same event".
MAX_WINDOW_DAYS = 30.0

#: Seconds in a day, used to express the date gap as a fraction of the window
#: at whole-second resolution (so sub-day proximity still differentiates pairs).
_SECONDS_PER_DAY = 86400.0

#: Default minimum confidence for :func:`find_links` to keep a pair. Set just
#: below the lone-shared-reference contribution (:data:`W_SHARED_REF`) so a
#: single shared code is sufficient on its own, while a bare subject or a bare
#: party-and-time match (each individually weaker) is not - those need to
#: combine with another signal to surface.
DEFAULT_THRESHOLD = 0.5

# --------------------------------------------------------------------------- #
# Relation vocabulary.
# --------------------------------------------------------------------------- #

#: The one relation this engine emits: the two records describe the same event.
RELATION_SAME_EVENT = "same_event"

# --------------------------------------------------------------------------- #
# Reason tokens. Each appears in a link's ``reasons`` tuple when its signal
# fired, in this fixed order, so the explanation is stable and machine-readable.
# --------------------------------------------------------------------------- #

REASON_SHARED_REF = "shared_reference"
REASON_SUBJECT = "subject_match"
REASON_PARTY_TIME = "party_and_date_proximity"
REASON_SIMILARITY = "embedding_similarity"

# --------------------------------------------------------------------------- #
# Text parsing.
# --------------------------------------------------------------------------- #

#: Leading reply / forward marker on a subject line, stripped repeatedly so a
#: chain such as ``Re: Fwd: Aw: ...`` collapses to its bare subject. ``Aw:`` is
#: the German reply prefix, included so cross-locale correspondence folds
#: together. Matched case-insensitively. Mirrors the correspondence digest.
_SUBJECT_PREFIX_RE = re.compile(r"^\s*(re|fw|fwd|aw)\s*:\s*", re.IGNORECASE)

#: Run of whitespace inside a subject, collapsed to a single plain space.
_WHITESPACE_RE = re.compile(r"\s+")

#: Tracked entity-code pattern: a known prefix, an optional separator (hyphen,
#: space or underscore) and a run of digits - e.g. ``RFI-123``, ``CO 14``,
#: ``MoC_7``, ``VO-3``, ``NCR-9``. The prefix set is deliberately explicit (not
#: "any letters + digits") so ordinary tokens like ``ISO 9001`` or a date are
#: not mistaken for a tracked reference. Matched case-insensitively; a word
#: boundary in front keeps it from firing inside a larger token. Codes are
#: normalized to ``PREFIX-NUMBER`` (uppercase, no leading zeros) before
#: comparison so ``co-014`` and ``CO-14`` are recognised as the same code.
_CODE_PREFIXES = (
    "RFI",
    "CO",
    "VO",
    "VR",
    "VN",
    "MOC",
    "NCR",
    "PCO",
    "CR",
    "EOT",
    "DN",
    "SI",
    "EWN",
    "CE",
)

_CODE_RE = re.compile(
    r"\b(" + "|".join(_CODE_PREFIXES) + r")[-_ ]?(\d+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CandidateRecord:
    """One heterogeneous record projected onto a uniform shape for correlation.

    The integrator builds one of these per source row (an inbound email, an
    RFI, a change order, an NCR, a diary entry, ...) so records of every type
    can be compared on the same footing. Every field is a plain primitive so the
    engine stays ORM-free and 3.11-testable.

    Attributes
    ----------
    record_type:
        Source-type token (e.g. ``"rfi"``, ``"change_order"``, ``"email"``).
        Carried through to the link and used, with ``record_id``, as the stable
        identity for dedup and ordering.
    record_id:
        Stable identifier of the row within its type.
    project_id:
        The project the record belongs to. Only records sharing a project are
        ever compared - the engine never links across projects.
    subject:
        The record's subject / title line. Normalized for the subject signal
        and scanned (with ``body``) for tracked codes. May be blank.
    body:
        The record's free-text body, scanned for tracked codes. May be blank.
    party:
        The responsible / originating party, if known. ``None`` or blank means
        no party is recorded and the party-and-time signal cannot fire for this
        record. Compared case-insensitively after trimming.
    occurred_at:
        When the underlying event happened (or the record was raised). ``None``
        when undated, in which case the date-proximity signal cannot fire. The
        engine reads no clock; this is the only time source.
    refs:
        Explicit tracked references already extracted upstream (e.g. a foreign
        key rendered as ``"CO-014"``). Unioned with the codes parsed from
        ``subject`` and ``body`` before the shared-reference signal is computed,
        and normalized the same way, so an upstream-provided code and an
        in-text mention of the same code are treated as one.
    """

    record_type: str
    record_id: str
    project_id: str
    subject: str = ""
    body: str = ""
    party: str | None = None
    occurred_at: datetime | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredLink:
    """A scored, explainable correlation between two records.

    The link is undirected; the two endpoints are stored in a canonical order
    (the smaller ``(record_type, record_id)`` tuple as the *left*) so the same
    pair is never emitted twice with the endpoints swapped. ``confidence`` is the
    blended score in ``[0, 1]`` and ``reasons`` names every signal that fired,
    in the fixed :data:`REASON_*` order.

    Attributes
    ----------
    left_type / left_id:
        The canonical-left record's type and id.
    right_type / right_id:
        The canonical-right record's type and id.
    relation:
        Always :data:`RELATION_SAME_EVENT`.
    confidence:
        Blended confidence in ``[0, 1]`` (see the module docstring).
    reasons:
        Tuple of :data:`REASON_*` tokens for the signals that fired, ordered
        shared-reference, subject, party-and-time, similarity. Empty only for a
        pair with zero confidence (which :func:`find_links` filters out).
    """

    left_type: str
    left_id: str
    right_type: str
    right_id: str
    relation: str
    confidence: float
    reasons: tuple[str, ...]


def normalize_subject(subject: str) -> str:
    """Reduce *subject* to a stable comparison key.

    Strips every leading ``re:`` / ``fw:`` / ``fwd:`` / ``aw:`` prefix in turn,
    collapses internal runs of whitespace to a single space, strips the ends and
    lowercases. ``"Re: Fwd: Site access"`` becomes ``"site access"``. A subject
    that is blank or only punctuation / whitespace reduces to ``""``; an empty
    key never matches another empty key in the subject signal.
    """
    text = subject or ""
    while True:
        stripped = _SUBJECT_PREFIX_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.lower()


def _normalize_code(prefix: str, number: str) -> str:
    """Canonicalise a parsed code to ``PREFIX-NUMBER`` (upper, no leading zeros).

    So ``co-014``, ``CO 14`` and ``CO_14`` all normalise to ``CO-14`` and are
    recognised as the same tracked reference. A code that is all zeros keeps a
    single ``0`` rather than collapsing to the empty string.
    """
    digits = number.lstrip("0") or "0"
    return f"{prefix.upper()}-{digits}"


def extract_codes(*texts: str) -> frozenset[str]:
    """Parse tracked entity codes from *texts*, normalized and de-duplicated.

    Scans each text with :data:`_CODE_RE`, normalises every hit with
    :func:`_normalize_code`, and returns the set of distinct codes. Recognises
    only the explicit :data:`_CODE_PREFIXES` so ordinary tokens are not mistaken
    for references. A blank or ``None`` text contributes nothing.
    """
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _CODE_RE.finditer(text):
            found.add(_normalize_code(match.group(1), match.group(2)))
    return frozenset(found)


def _normalize_refs(refs: Sequence[str]) -> frozenset[str]:
    """Normalise an explicit ``refs`` tuple to the same code vocabulary.

    Each entry is run through the code parser so an upstream-provided reference
    such as ``"CO-014"`` lands in the same normalized form as one parsed from
    text (``CO-14``). An entry that is not a recognisable tracked code is dropped
    rather than guessed at, keeping the shared-reference signal precise.
    """
    found: set[str] = set()
    for ref in refs:
        found |= extract_codes(ref)
    return frozenset(found)


def record_codes(record: CandidateRecord) -> frozenset[str]:
    """All tracked codes for *record*: parsed from subject + body, plus refs.

    The union of the codes found in the subject and body text and the normalized
    explicit ``refs`` tuple, so an in-text mention and an upstream foreign key of
    the same code count once.
    """
    return extract_codes(record.subject, record.body) | _normalize_refs(record.refs)


def _clamp_fraction(value: float) -> float:
    """Clamp a value into the inclusive ``[0.0, 1.0]`` range."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def date_proximity(
    left: datetime | None,
    right: datetime | None,
    *,
    max_window_days: float = MAX_WINDOW_DAYS,
) -> float:
    """Closeness of two timestamps as a fraction in ``[0, 1]`` (1 == same moment).

    Decays linearly with the absolute gap between *left* and *right*: ``1.0`` at
    a zero gap, reaching ``0.0`` at *max_window_days* and staying there beyond
    it. Returns ``0.0`` when either timestamp is ``None`` (an undated record has
    no proximity). The gap is measured at whole-second resolution so records
    hours apart still rank above records weeks apart.

    Naive and aware datetimes are not mixed: if exactly one side is timezone
    aware the comparison is impossible to do safely, so the function returns
    ``0.0`` rather than raise. Two naive or two aware datetimes compare directly.
    """
    if left is None or right is None:
        return 0.0
    if (left.tzinfo is None) != (right.tzinfo is None):
        return 0.0
    if max_window_days <= 0.0:
        # Degenerate window: only an exact match counts as proximate.
        return 1.0 if left == right else 0.0
    gap_seconds = abs((left - right).total_seconds())
    window_seconds = max_window_days * _SECONDS_PER_DAY
    if gap_seconds >= window_seconds:
        return 0.0
    return _clamp_fraction(1.0 - gap_seconds / window_seconds)


def _parties_match(left: str | None, right: str | None) -> bool:
    """True when both parties are present and equal (trimmed, case-insensitive).

    A blank or ``None`` party on either side is not a match - an absent party is
    not evidence of a shared one.
    """
    a = (left or "").strip().lower()
    b = (right or "").strip().lower()
    return bool(a) and a == b


def _subjects_match(left: str, right: str) -> bool:
    """True when both subjects normalise to the same non-empty key."""
    a = normalize_subject(left)
    b = normalize_subject(right)
    return bool(a) and a == b


def _identity(record: CandidateRecord) -> tuple[str, str]:
    """Stable identity tuple ``(record_type, record_id)`` for ordering / dedup."""
    return (record.record_type, record.record_id)


def score_pair(
    a: CandidateRecord,
    b: CandidateRecord,
    *,
    similarity_fn: Callable[[CandidateRecord, CandidateRecord], float] | None = None,
) -> ScoredLink:
    """Score the correlation between records *a* and *b* into a :class:`ScoredLink`.

    Blends the four signals described in the module docstring into a confidence
    in ``[0, 1]`` and records, in fixed order, which signals fired. The endpoints
    are stored in canonical order (smaller ``(record_type, record_id)`` first) so
    the same pair always produces an identical link regardless of argument order.

    ``similarity_fn`` is optional; when supplied it is called exactly once with
    the records in canonical order and its return is clamped to ``[0, 1]`` before
    being folded in. When ``None`` the similarity signal is skipped and nothing
    external is called. Pure and deterministic for a deterministic
    ``similarity_fn``.
    """
    # Canonical orientation so the link is orientation-independent. The
    # similarity_fn is called with this same stable ordering.
    if _identity(b) < _identity(a):
        a, b = b, a

    contribution = 0.0
    reasons: list[str] = []

    # Shared tracked reference - the strongest signal. Fires fully on any one
    # shared normalized code.
    if record_codes(a) & record_codes(b):
        contribution += W_SHARED_REF
        reasons.append(REASON_SHARED_REF)

    # Normalized-subject match.
    if _subjects_match(a.subject, b.subject):
        contribution += W_SUBJECT
        reasons.append(REASON_SUBJECT)

    # Same party scaled by date proximity: fires only when the parties match and
    # both records are dated, decaying to zero across the window.
    if _parties_match(a.party, b.party):
        proximity = date_proximity(a.occurred_at, b.occurred_at)
        if proximity > 0.0:
            contribution += W_PARTY_TIME * proximity
            reasons.append(REASON_PARTY_TIME)

    # Optional embedding similarity.
    if similarity_fn is not None:
        sim = _clamp_fraction(similarity_fn(a, b))
        if sim > 0.0:
            contribution += W_SIMILARITY * sim
            reasons.append(REASON_SIMILARITY)

    confidence = _clamp_fraction(contribution)

    return ScoredLink(
        left_type=a.record_type,
        left_id=a.record_id,
        right_type=b.record_type,
        right_id=b.record_id,
        relation=RELATION_SAME_EVENT,
        confidence=round(confidence, 6),
        reasons=tuple(reasons),
    )


def find_links(
    records: Iterable[CandidateRecord],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    similarity_fn: Callable[[CandidateRecord, CandidateRecord], float] | None = None,
) -> list[ScoredLink]:
    """Score every same-project pair and return the links at or above *threshold*.

    Considers each unordered pair of records that share a ``project_id`` exactly
    once (no self-pairs, no cross-project pairs, no symmetric duplicates), scores
    it with :func:`score_pair`, and keeps those whose confidence is at least
    *threshold*. The result is sorted by descending confidence, then by the
    canonical left ``(type, id)`` and right ``(type, id)`` tuples, so ordering is
    fully deterministic and stable. Empty or single-record input yields an empty
    list.

    ``similarity_fn`` is forwarded to :func:`score_pair`; when ``None`` no
    similarity is computed and nothing external is called.
    """
    items = list(records)
    links: list[ScoredLink] = []

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a = items[i]
            b = items[j]
            if a.project_id != b.project_id:
                continue
            link = score_pair(a, b, similarity_fn=similarity_fn)
            if link.confidence >= threshold:
                links.append(link)

    links.sort(
        key=lambda link: (
            -link.confidence,
            link.left_type,
            link.left_id,
            link.right_type,
            link.right_id,
        )
    )
    return links


__all__ = [
    "W_SHARED_REF",
    "W_SUBJECT",
    "W_PARTY_TIME",
    "W_SIMILARITY",
    "MAX_WINDOW_DAYS",
    "DEFAULT_THRESHOLD",
    "RELATION_SAME_EVENT",
    "REASON_SHARED_REF",
    "REASON_SUBJECT",
    "REASON_PARTY_TIME",
    "REASON_SIMILARITY",
    "CandidateRecord",
    "ScoredLink",
    "normalize_subject",
    "extract_codes",
    "record_codes",
    "date_proximity",
    "score_pair",
    "find_links",
]
