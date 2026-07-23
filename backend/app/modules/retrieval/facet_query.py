# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Claim-grade faceted retrieval - the pure, IO-free query layer.

This module ranks and filters candidate records that an integrator has
already gathered from the per-module vector adapters (correspondence, rfi,
submittals, documents, erp_chat and friends).  It performs no IO, no
embedding, and never reads the wall clock: any reference time used for
recency scoring is passed in explicitly via ``as_of``.

The output is intended to be "claim-reconstruction grade": every result
carries a provenance dict naming the owning module, record type, record id
and the date the underlying event occurred, so a downstream reconstruct
screen can rebuild the chain of evidence without a second database trip.

Design rules:

* Deterministic.  The same records plus the same query plus the same
  ``as_of`` always produce the same ordering, including tie-breaks.
* Standard library only.  No third-party imports, no ``app.database``.
* Scoring is a documented linear blend of four signals on top of the
  upstream relevance (``base_score``), clamped to ``[0, 1]``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Scoring weights.  These are deliberately exposed as module constants so the
# blend is auditable and tunable.  base_score is the upstream vector-adapter
# relevance (already 0..1); the four facet signals add on top of it, and the
# final value is clamped into [0, 1].
# ---------------------------------------------------------------------------

#: Weight applied to the upstream relevance carried on the record.
WEIGHT_BASE: float = 0.50
#: Weight applied to the fraction of query terms found in the record text.
WEIGHT_TEXT: float = 0.25
#: Weight applied to the fraction of queried entity refs the record matches.
WEIGHT_ENTITY: float = 0.15
#: Weight applied when the record's party is one of the queried parties.
WEIGHT_PARTY: float = 0.05
#: Weight applied to recency (newer ``occurred_at`` relative to ``as_of``).
WEIGHT_RECENCY: float = 0.05

#: Recency horizon in days.  An event ``RECENCY_HORIZON_DAYS`` or more before
#: ``as_of`` contributes nothing; one exactly on ``as_of`` contributes fully.
RECENCY_HORIZON_DAYS: int = 365

#: Minimum length for a query term to be considered (single chars are noise).
MIN_TERM_LEN: int = 2


@dataclass(frozen=True)
class RetrievableRecord:
    """A single candidate record gathered from an upstream vector adapter.

    ``base_score`` is the relevance the upstream adapter already assigned
    (expected in ``[0, 1]``); the rest of the fields drive faceted filtering
    and the additional scoring signals.  Frozen and hashable so result sets
    can be deduplicated or placed in sets by the integrator.
    """

    record_type: str
    record_id: str
    title: str
    body: str
    source_module: str
    party: str = ""
    occurred_at: str = ""  # ISO-8601 date or datetime, or "" when unknown.
    entity_refs: tuple[str, ...] = ()
    base_score: float = 0.0


@dataclass(frozen=True)
class FacetQuery:
    """A faceted retrieval query.

    Every facet is optional; an empty facet is inactive and does not filter.
    ``text`` is free text (whitespace tokenised); the remaining facets are
    exact-ish membership / intersection / range constraints.
    """

    text: str = ""
    parties: frozenset[str] = frozenset()
    date_from: str = ""
    date_to: str = ""
    entity_refs: frozenset[str] = frozenset()
    record_types: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RankedResult:
    """A record that survived filtering, with its score and provenance.

    ``matched_facets`` records which facets caused or boosted the match -
    useful both for UI highlighting and for explaining a ranking.  The
    ``provenance`` dict always contains ``module``, ``record_type``,
    ``record_id`` and ``occurred_at``.
    """

    record: RetrievableRecord
    score: float
    matched_facets: tuple[str, ...]
    provenance: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure helpers - all deterministic, stdlib-only.
# ---------------------------------------------------------------------------


def _date_key(s: str) -> str:
    """Return the leading 10-char ISO date (``YYYY-MM-DD``) of ``s``.

    ISO-8601 dates and datetimes sort correctly lexicographically once
    truncated to the date component, so callers can compare the returned
    keys with plain string comparison.  An empty or short string yields ""
    so it can be treated as "unknown".
    """
    if not s:
        return ""
    head = s[:10]
    # Guard against values shorter than a full date; treat as unknown.
    if len(head) < 10:
        return ""
    return head


def _in_window(date: str, lo: str, hi: str) -> bool:
    """Return whether ``date`` falls within ``[lo, hi]`` inclusive.

    Each bound is compared on its 10-char date key; an empty bound means
    that side of the window is open.  An empty ``date`` is never in a
    bounded window (callers exclude unknown-date records when a date facet
    is active).
    """
    dk = _date_key(date)
    if not dk:
        return False
    lo_k = _date_key(lo)
    hi_k = _date_key(hi)
    if lo_k and dk < lo_k:
        return False
    if hi_k and dk > hi_k:
        return False
    return True


def _terms(text: str) -> tuple[str, ...]:
    """Tokenise ``text`` into lowercased terms of length >= ``MIN_TERM_LEN``.

    De-duplicates while preserving first-seen order so overlap fractions are
    computed against distinct query terms.
    """
    seen: dict[str, None] = {}
    for raw in text.lower().split():
        token = raw.strip()
        if len(token) >= MIN_TERM_LEN and token not in seen:
            seen[token] = None
    return tuple(seen.keys())


def _overlap_fraction(query_terms: tuple[str, ...], haystack: str) -> float:
    """Fraction of ``query_terms`` that appear as substrings in ``haystack``.

    ``haystack`` is matched case-insensitively.  Returns 0.0 when there are
    no query terms so the caller can treat "no text facet" as no signal.
    """
    if not query_terms:
        return 0.0
    hay = haystack.lower()
    hits = sum(1 for term in query_terms if term in hay)
    return hits / len(query_terms)


def _norm_refs(refs: Iterable[str]) -> frozenset[str]:
    """Lowercase and trim a collection of entity refs, dropping blanks."""
    out: set[str] = set()
    for r in refs:
        key = r.strip().lower()
        if key:
            out.add(key)
    return frozenset(out)


def _recency_weight(occurred_at: str, as_of: str) -> float:
    """Recency signal in ``[0, 1]``: newer events score higher.

    Linear decay across ``RECENCY_HORIZON_DAYS``.  An event on ``as_of``
    scores 1.0; one ``RECENCY_HORIZON_DAYS`` or more before it scores 0.0.
    Future events (after ``as_of``) are clamped to 1.0.  When ``as_of`` or
    the record date is empty, recency contributes nothing.
    """
    if not as_of:
        return 0.0
    dk = _date_key(occurred_at)
    ak = _date_key(as_of)
    if not dk or not ak:
        return 0.0
    delta = _days_between(dk, ak)
    if delta is None:
        return 0.0
    # delta = as_of - occurred_at, in days.  Negative => event is in the
    # future relative to as_of; treat as fully recent.
    if delta <= 0:
        return 1.0
    if delta >= RECENCY_HORIZON_DAYS:
        return 0.0
    return 1.0 - (delta / RECENCY_HORIZON_DAYS)


def _days_between(earlier_key: str, later_key: str) -> int | None:
    """Whole days from ``earlier_key`` to ``later_key`` (both ``YYYY-MM-DD``).

    Returns ``later - earlier`` (positive when ``later`` is after
    ``earlier``).  Returns ``None`` if either key cannot be parsed.  Uses a
    proleptic-Gregorian day count so no ``datetime`` / timezone handling is
    needed and the result stays deterministic.
    """
    e = _ordinal_of(earlier_key)
    l = _ordinal_of(later_key)
    if e is None or l is None:
        return None
    return l - e


def _ordinal_of(date_key: str) -> int | None:
    """Day ordinal for a ``YYYY-MM-DD`` string, or ``None`` if malformed."""
    parts = date_key.split("-")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
    except ValueError:
        return None
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return _to_ordinal(year, month, day)


# Cumulative days before the first of each month in a non-leap year.
_DAYS_BEFORE_MONTH = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _to_ordinal(year: int, month: int, day: int) -> int:
    """Proleptic-Gregorian ordinal day number (year 1 = 1).

    Mirrors ``datetime.date.toordinal`` arithmetic without importing it, so
    the engine has zero stdlib-clock surface.  Only used for day differences,
    so the absolute epoch is irrelevant as long as it is consistent.
    """
    y = year - 1
    days = y * 365 + y // 4 - y // 100 + y // 400
    days += _DAYS_BEFORE_MONTH[month]
    if month > 2 and _is_leap(year):
        days += 1
    days += day
    return days


def _clamp01(value: float) -> float:
    """Clamp ``value`` into the closed interval ``[0.0, 1.0]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _haystack(record: RetrievableRecord) -> str:
    """Text used for term matching: title + body + entity refs joined."""
    return " ".join((record.title, record.body, " ".join(record.entity_refs)))


def _provenance_of(record: RetrievableRecord) -> dict:
    """Build the provenance dict carried on every result."""
    return {
        "module": record.source_module,
        "record_type": record.record_type,
        "record_id": record.record_id,
        "occurred_at": record.occurred_at,
    }


def _sort_key(result: RankedResult) -> tuple:
    """Deterministic sort key: score desc, date desc (empty last), id asc.

    We negate the score for descending order.  For the date we want newer
    first with empty dates sorting last; we achieve a descending string sort
    that still puts "" last by mapping the date key into a value that is
    larger for newer dates and smallest for unknown dates.
    """
    dk = _date_key(result.record.occurred_at)
    # "" -> sorts after any real date when we want empty LAST in a desc sort.
    # We build a tuple where the first element flags presence (0 = has date,
    # 1 = no date) so known dates always precede unknown ones; within known
    # dates, reverse lexicographic order gives newest-first.
    has_date = 0 if dk else 1
    # For reverse-lexicographic on the date string we invert each character.
    # Simpler and still deterministic: sort ascending on the original key but
    # negate ordering by using the key's "complement". Lexicographic reverse
    # is most robustly done by sorting on the raw key and reversing the field
    # sense via a wrapper. To keep a single sorted() call we encode newest
    # first by mapping the date to its negative ordinal.
    ordinal = _ordinal_of(dk) if dk else None
    neg_ordinal = -ordinal if ordinal is not None else 0
    return (
        -result.score,
        has_date,
        neg_ordinal,
        result.record.record_id,
    )


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def run_query(
    records: Iterable[RetrievableRecord],
    query: FacetQuery,
    *,
    as_of: str = "",
) -> tuple[RankedResult, ...]:
    """Filter, score and rank ``records`` against ``query``.

    Filtering uses AND semantics across active facets; an empty facet is
    inactive.  Scoring is the documented linear blend of base relevance,
    text overlap, entity-ref overlap, party match and recency, clamped to
    ``[0, 1]``.  Results are sorted by score descending, then by
    ``occurred_at`` descending (unknown dates last), then by ``record_id``
    ascending - a total, stable ordering.

    When the query has no active facets and no text, every record is
    returned ranked by its base score then recency (an "everything" browse).
    """
    # Pre-compute query-side derived values once.
    query_terms = _terms(query.text)
    has_text_facet = bool(query_terms)
    query_entities = _norm_refs(query.entity_refs)
    has_entity_facet = bool(query_entities)
    parties_lower = frozenset(p.strip().lower() for p in query.parties if p.strip())
    has_party_facet = bool(parties_lower)
    has_type_facet = bool(query.record_types)
    has_date_facet = bool(_date_key(query.date_from) or _date_key(query.date_to))

    any_facet_active = has_text_facet or has_entity_facet or has_party_facet or has_type_facet or has_date_facet

    results: list[RankedResult] = []

    for record in records:
        # ---- "Everything" browse: no facet, no text. -------------------
        if not any_facet_active:
            score = _clamp01(
                WEIGHT_BASE * _clamp01(record.base_score) + WEIGHT_RECENCY * _recency_weight(record.occurred_at, as_of)
            )
            results.append(
                RankedResult(
                    record=record,
                    score=score,
                    matched_facets=(),
                    provenance=_provenance_of(record),
                )
            )
            continue

        matched: list[str] = []

        # ---- record_types facet ---------------------------------------
        if has_type_facet:
            if record.record_type not in query.record_types:
                continue
            matched.append("type")

        # ---- parties facet (case-insensitive) -------------------------
        party_hit = False
        if has_party_facet:
            if record.party.strip().lower() not in parties_lower:
                continue
            party_hit = True
            matched.append("party")

        # ---- date window facet ----------------------------------------
        if has_date_facet:
            if not _in_window(record.occurred_at, query.date_from, query.date_to):
                continue
            matched.append("date")

        # ---- entity_refs facet (case-insensitive intersection) --------
        entity_fraction = 0.0
        if has_entity_facet:
            record_entities = _norm_refs(record.entity_refs)
            overlap = query_entities & record_entities
            if not overlap:
                continue
            entity_fraction = len(overlap) / len(query_entities)
            for ref in sorted(overlap):
                matched.append("entity:" + ref)

        # ---- text facet ------------------------------------------------
        text_fraction = 0.0
        if has_text_facet:
            text_fraction = _overlap_fraction(query_terms, _haystack(record))
            if text_fraction <= 0.0:
                continue
            matched.append("text")

        # ---- score ----------------------------------------------------
        recency = _recency_weight(record.occurred_at, as_of)
        score = (
            WEIGHT_BASE * _clamp01(record.base_score)
            + WEIGHT_TEXT * text_fraction
            + WEIGHT_ENTITY * entity_fraction
            + (WEIGHT_PARTY if party_hit else 0.0)
            + WEIGHT_RECENCY * recency
        )

        results.append(
            RankedResult(
                record=record,
                score=_clamp01(score),
                matched_facets=tuple(matched),
                provenance=_provenance_of(record),
            )
        )

    results.sort(key=_sort_key)
    return tuple(results)
