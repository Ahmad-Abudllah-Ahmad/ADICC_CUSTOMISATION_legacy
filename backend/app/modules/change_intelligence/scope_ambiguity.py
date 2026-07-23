# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure pre-construction scope-ambiguity scoring for BOQ line items.

Which lines of a bill of quantities are vague enough to breed a change later,
and exactly why, so a user can clarify the scope *before* the work is priced and
ordered rather than argue about it afterwards. The industry data behind the
"Change & AI" roadmap is blunt: a large share of variations trace back to scope
that was ambiguous from day one - a "provisional" allowance no one ever firmed
up, a line with no quantity, a description that just says "as required". This
engine reads each BOQ line and turns those tell-tale signals into a ranked,
explainable ambiguity score, so the soft spots surface while they are still
cheap to fix.

It is a *reading* engine, not a re-derivation engine: it adds no facts and
touches no other module. The integrator gathers a project's BOQ lines from the
DB, maps each into a :class:`ScopeLine`, and feeds them in; the engine names what
is missing or vague and grades it. Identical lines always yield an identical
result.

No database, no ORM, no ``app.*`` imports and no clock or randomness - standard
library only, with :class:`~decimal.Decimal` for any quantity / rate maths so no
money or measure ever flows through a float. It unit-tests on the local Python
3.11 runner exactly like the clarifier and delay-risk engines.

Scope note: signal detection is keyword / pattern based, so it reads a topic
being mentioned, not its polarity, in the same spirit as the change clarifier. A
description that says "no allowance needed" still trips the allowance signal
because the word "allowance" is present; the engine deliberately errs toward
"this line is talking about an allowance" and leaves the author to confirm. Low
scores on clean, fully-specified lines are honest, not a failure to detect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

# --------------------------------------------------------------------------- #
# Ambiguity-band thresholds (inclusive lower bounds) on the 0-100 score scale.
# Matched to the delay-risk engine's three-band shape so a UI can theme a row
# without re-deriving the cut points.
# --------------------------------------------------------------------------- #

BAND_HIGH = "high"
BAND_ELEVATED = "elevated"
BAND_LOW = "low"

#: At or above HIGH_THRESHOLD -> "high"; at or above ELEVATED_THRESHOLD (but
#: below high) -> "elevated"; anything lower -> "low". Inclusive lower bounds on
#: the 0-100 ambiguity scale.
HIGH_THRESHOLD = 60
ELEVATED_THRESHOLD = 30

# --------------------------------------------------------------------------- #
# Stable reason codes. score_line() returns these alongside human labels so a UI
# can label / theme / filter each reason without parsing prose. Codes are stable
# tokens; labels are display text.
# --------------------------------------------------------------------------- #

REASON_VAGUE_LANGUAGE = "vague_language"
REASON_PROVISIONAL_SUM = "provisional_sum"
REASON_MISSING_QUANTITY = "missing_quantity"
REASON_MISSING_UNIT = "missing_unit"
REASON_UNDERSPECIFIED = "underspecified_description"

#: Human-readable label for each reason code.
REASON_LABELS: dict[str, str] = {
    REASON_VAGUE_LANGUAGE: "Vague or placeholder wording",
    REASON_PROVISIONAL_SUM: "Provisional sum or allowance",
    REASON_MISSING_QUANTITY: "Missing or zero quantity",
    REASON_MISSING_UNIT: "Missing unit of measure",
    REASON_UNDERSPECIFIED: "Under-specified description",
}

# --------------------------------------------------------------------------- #
# Per-signal score weights. Each signal contributes its weight (capped at 100 in
# total) so any one signal raises the score and several stack. Provisional sums
# and vague wording are the strongest predictors of a downstream variation, so
# they carry the most weight; a missing unit alone is a smaller gap than a
# missing quantity.
# --------------------------------------------------------------------------- #

WEIGHT_VAGUE_LANGUAGE = 40
WEIGHT_PROVISIONAL_SUM = 45
WEIGHT_MISSING_QUANTITY = 30
WEIGHT_MISSING_UNIT = 20
WEIGHT_UNDERSPECIFIED = 25

#: The maximum a line can score. Stacked signals are capped here.
MAX_SCORE = 100

# --------------------------------------------------------------------------- #
# Signal vocabulary.
# --------------------------------------------------------------------------- #

#: Placeholder / vague wording. Each entry is matched case-insensitively and
#: whole-phrase (word-boundary aware) so "approx" does not fire inside
#: "approximation" and a substring of a real word never trips a false signal.
#: Multi-word phrases are matched as a unit. The literal "???" is handled
#: separately because it carries no word characters for ``\b`` to anchor to.
_VAGUE_PHRASES: tuple[str, ...] = (
    "tbd",
    "tbc",
    "to be confirmed",
    "to be advised",
    "to be determined",
    "to be agreed",
    "approx",
    "approximately",
    "around",
    "circa",
    "allowance",
    "provisional",
    "by others",
    "as required",
    "as directed",
    "as necessary",
    "as appropriate",
    "etc",
    "misc",
    "miscellaneous",
    "sundry",
    "sundries",
    "similar",
    "or equal",
    "or similar",
    "or equivalent",
    "nominal",
    "assumed",
    "unknown",
    "tba",
)

#: Whole-phrase vague vocabulary. ``\b`` anchors keep each phrase from matching
#: inside a larger word.
_VAGUE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _VAGUE_PHRASES) + r")\b",
    re.IGNORECASE,
)

#: The bare "???" placeholder, which has no word boundary to anchor on.
_QUESTION_MARKS_RE = re.compile(r"\?\?\?")

#: The subset of vague vocabulary that specifically signals a provisional sum or
#: an open-ended allowance (as opposed to merely loose wording). Kept separate so
#: the provisional-sum signal can fire on the description alone, independent of
#: the ``is_provisional_sum`` flag.
_PROVISIONAL_PHRASES: tuple[str, ...] = (
    "provisional",
    "provisional sum",
    "allowance",
    "prime cost",
    "pc sum",
    "p.c. sum",
    "dayworks",
    "daywork",
)

_PROVISIONAL_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _PROVISIONAL_PHRASES) + r")\b",
    re.IGNORECASE,
)

#: A description with fewer than this many meaningful words (after stripping
#: noise tokens) is treated as too thin to price confidently.
_MIN_MEANINGFUL_WORDS = 3

#: Tokens that do not count toward the meaningful-word total: pure punctuation,
#: bare numbers, and a few near-empty filler words. Kept deliberately small so
#: the engine reads "too short" rather than trying to judge quality.
_NOISE_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "to",
        "and",
        "or",
        "for",
        "in",
        "on",
        "at",
        "as",
        "etc",
        "item",
        "items",
        "works",
        "work",
    }
)

#: A token counts as meaningful only if it carries at least one letter (so bare
#: numbers and punctuation are ignored) and is not in the noise list.
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class ScopeLine:
    """One BOQ line as the integrator presents it to the engine.

    Every field is a plain primitive (or :class:`~decimal.Decimal`) so the engine
    stays ORM-free and 3.11-testable.

    Attributes
    ----------
    line_id:
        Stable identifier of the BOQ line, echoed onto the result and used as the
        tie-break for ordering.
    description:
        The line's scope text. Read for vague wording, provisional-sum language
        and under-specification. May be empty.
    unit:
        Unit of measure (for example ``m2`` / ``nr`` / ``item``). A blank unit on
        a non-heading line is a gap.
    quantity:
        The measured quantity, as a :class:`~decimal.Decimal`. ``None`` or a
        non-positive value on a non-heading line is a gap.
    rate:
        The unit rate, as a :class:`~decimal.Decimal`. Carried for completeness;
        not itself scored (an un-rated line is a pricing state, not a scope
        ambiguity).
    is_provisional_sum:
        ``True`` when the line is flagged in the source as a provisional sum or
        allowance. Fires the provisional-sum signal directly, independent of the
        wording.
    is_heading:
        ``True`` for a section heading / sub-total row that carries no measure of
        its own. Heading lines are exempt from the missing-quantity, missing-unit
        and under-specified signals (a heading is meant to be short and
        unmeasured); they are still read for vague and provisional wording.
    """

    line_id: str
    description: str
    unit: str = ""
    quantity: Decimal | None = None
    rate: Decimal | None = None
    is_provisional_sum: bool = False
    is_heading: bool = False


@dataclass(frozen=True)
class LineAmbiguity:
    """The graded scope ambiguity of one BOQ line.

    Attributes
    ----------
    line_id:
        Carried through from the input for display and stable ordering.
    score:
        The blended ambiguity in ``[0, 100]`` (100 == most ambiguous), capped at
        :data:`MAX_SCORE`.
    band:
        ``low`` / ``elevated`` / ``high`` per :func:`band_for_score`.
    reasons:
        Stable reason codes that fired, in a fixed, documented order. Empty for a
        clean line.
    labels:
        The human-readable label for each fired reason, aligned one-to-one with
        ``reasons``.
    """

    line_id: str
    score: int
    band: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    labels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScopeAmbiguityReport:
    """Project-level scope-ambiguity summary over a set of BOQ lines.

    Attributes
    ----------
    lines:
        Every line's :class:`LineAmbiguity`, ordered by ``score`` descending
        (ties broken by ``line_id`` ascending) so the worst offenders are first.
    counts_by_band:
        Number of lines in each band, always carrying all three keys
        (``high`` / ``elevated`` / ``low``) even when zero.
    ambiguity_index:
        The mean line score over the assessed lines, on the same 0-100 scale,
        rounded to 2 dp. ``0.0`` for an empty input. (An equal-weighted mean; the
        ``weight`` hook on :func:`assess` lets a caller bias it by line value.)
    top_reasons:
        The reason codes that fired, most frequent first (ties broken by the
        fixed reason order), so a UI can show the dominant drivers across the
        project.
    """

    lines: tuple[LineAmbiguity, ...] = field(default_factory=tuple)
    counts_by_band: dict[str, int] = field(default_factory=dict)
    ambiguity_index: float = 0.0
    top_reasons: tuple[str, ...] = field(default_factory=tuple)


# Fixed reason order. score_line() emits fired reasons in this order, and it is
# the stable tie-break for top-reason ranking (an earlier reason wins a tie).
_REASON_SPECS: tuple[tuple[str, int], ...] = (
    (REASON_PROVISIONAL_SUM, WEIGHT_PROVISIONAL_SUM),
    (REASON_VAGUE_LANGUAGE, WEIGHT_VAGUE_LANGUAGE),
    (REASON_MISSING_QUANTITY, WEIGHT_MISSING_QUANTITY),
    (REASON_MISSING_UNIT, WEIGHT_MISSING_UNIT),
    (REASON_UNDERSPECIFIED, WEIGHT_UNDERSPECIFIED),
)


def band_for_score(score: int) -> str:
    """Classify a ``[0, 100]`` ambiguity score into a band.

    ``score >= HIGH_THRESHOLD`` -> :data:`BAND_HIGH`;
    ``score >= ELEVATED_THRESHOLD`` -> :data:`BAND_ELEVATED`;
    otherwise :data:`BAND_LOW`. Thresholds are inclusive lower bounds on the
    0-100 scale.
    """
    if score >= HIGH_THRESHOLD:
        return BAND_HIGH
    if score >= ELEVATED_THRESHOLD:
        return BAND_ELEVATED
    return BAND_LOW


def _has_vague_language(description: str) -> bool:
    """True when the description carries placeholder / vague wording.

    Whole-phrase, case-insensitive; also fires on the bare ``???`` placeholder.
    """
    return bool(_VAGUE_RE.search(description) or _QUESTION_MARKS_RE.search(description))


def _has_provisional_language(description: str) -> bool:
    """True when the description names a provisional sum or open allowance."""
    return bool(_PROVISIONAL_RE.search(description))


def _meaningful_word_count(description: str) -> int:
    """Count the words in *description* that carry scope meaning.

    A token counts only if it contains at least one letter (bare numbers and
    punctuation are ignored) and is not a noise / filler word. Used to judge
    whether a description is too thin to price.
    """
    count = 0
    for token in _WORD_RE.findall(description.lower()):
        if token in _NOISE_WORDS:
            continue
        count += 1
    return count


def _quantity_is_missing(quantity: Decimal | None) -> bool:
    """True when the quantity is absent or non-positive.

    ``None`` and any value at or below zero count as missing; a positive
    Decimal does not.
    """
    if quantity is None:
        return True
    return quantity <= Decimal(0)


def score_line(line: ScopeLine) -> LineAmbiguity:
    """Grade one BOQ line's scope ambiguity into a :class:`LineAmbiguity`.

    Each detection signal contributes its weight to a 0-100 score, capped at
    :data:`MAX_SCORE`, and names a stable reason code plus a human label. The
    signals:

    * provisional sum / allowance - the ``is_provisional_sum`` flag, or
      provisional / allowance wording in the description;
    * vague / placeholder wording - any phrase from the vague vocabulary, or
      ``???``;
    * missing quantity - ``None`` or a non-positive quantity on a non-heading
      line;
    * missing unit - a blank unit on a non-heading line;
    * under-specified description - fewer than
      :data:`_MIN_MEANINGFUL_WORDS` meaningful words on a non-heading line.

    Heading lines are exempt from the quantity / unit / under-specification
    signals (a heading carries no measure of its own) but are still read for
    vague and provisional wording. Pure and deterministic: identical input always
    yields an identical result. Reasons are returned in the fixed
    :data:`_REASON_SPECS` order.
    """
    description = line.description or ""

    fired: dict[str, int] = {}

    # Provisional sum / allowance: the explicit flag, or the wording.
    if line.is_provisional_sum or _has_provisional_language(description):
        fired[REASON_PROVISIONAL_SUM] = WEIGHT_PROVISIONAL_SUM

    # Vague / placeholder wording.
    if _has_vague_language(description):
        fired[REASON_VAGUE_LANGUAGE] = WEIGHT_VAGUE_LANGUAGE

    # The remaining signals do not apply to heading / sub-total rows, which carry
    # no measure or full description of their own by design.
    if not line.is_heading:
        if _quantity_is_missing(line.quantity):
            fired[REASON_MISSING_QUANTITY] = WEIGHT_MISSING_QUANTITY
        if not line.unit.strip():
            fired[REASON_MISSING_UNIT] = WEIGHT_MISSING_UNIT
        if _meaningful_word_count(description) < _MIN_MEANINGFUL_WORDS:
            fired[REASON_UNDERSPECIFIED] = WEIGHT_UNDERSPECIFIED

    # Emit reasons / labels in the fixed order, and sum the weights (capped).
    reasons: list[str] = []
    labels: list[str] = []
    total = 0
    for reason, weight in _REASON_SPECS:
        if reason in fired:
            reasons.append(reason)
            labels.append(REASON_LABELS[reason])
            total += weight

    score = total if total < MAX_SCORE else MAX_SCORE

    return LineAmbiguity(
        line_id=line.line_id,
        score=score,
        band=band_for_score(score),
        reasons=tuple(reasons),
        labels=tuple(labels),
    )


def _empty_band_counts() -> dict[str, int]:
    """A band-count dict with all three bands present and zeroed."""
    return {BAND_HIGH: 0, BAND_ELEVATED: 0, BAND_LOW: 0}


def assess(lines: list[ScopeLine]) -> ScopeAmbiguityReport:
    """Score every BOQ line and summarise the project's scope ambiguity.

    Grades each line with :func:`score_line`, then returns a
    :class:`ScopeAmbiguityReport`:

    * ``lines`` ordered by score descending (ties broken by ``line_id``
      ascending) so the worst offenders surface first;
    * ``counts_by_band`` with all three bands present (zero when none);
    * ``ambiguity_index`` - the mean line score over the assessed lines, rounded
      to 2 dp, on the 0-100 scale;
    * ``top_reasons`` - the fired reason codes, most frequent first (ties broken
      by the fixed reason order).

    Pure and deterministic. An empty input yields an empty report with a 0.0
    index and zeroed band counts.
    """
    graded = [score_line(line) for line in lines]

    counts = _empty_band_counts()
    for line in graded:
        counts[line.band] += 1

    if graded:
        # Integer scores summed then divided; rounded to 2 dp for display. No
        # money flows through this average (it is a 0-100 ambiguity scale), so a
        # plain mean is the right transform.
        index = round(sum(line.score for line in graded) / len(graded), 2)
    else:
        index = 0.0

    # Count reason frequency, then rank most-frequent first with the fixed reason
    # order as the stable tie-break.
    reason_counts: dict[str, int] = {}
    for line in graded:
        for reason in line.reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    reason_order = {reason: position for position, (reason, _weight) in enumerate(_REASON_SPECS)}
    top_reasons = tuple(
        sorted(
            reason_counts,
            key=lambda reason: (-reason_counts[reason], reason_order.get(reason, len(reason_order))),
        )
    )

    ordered = tuple(sorted(graded, key=lambda line: (-line.score, line.line_id)))

    return ScopeAmbiguityReport(
        lines=ordered,
        counts_by_band=counts,
        ambiguity_index=index,
        top_reasons=top_reasons,
    )


__all__ = [
    "BAND_HIGH",
    "BAND_ELEVATED",
    "BAND_LOW",
    "HIGH_THRESHOLD",
    "ELEVATED_THRESHOLD",
    "REASON_VAGUE_LANGUAGE",
    "REASON_PROVISIONAL_SUM",
    "REASON_MISSING_QUANTITY",
    "REASON_MISSING_UNIT",
    "REASON_UNDERSPECIFIED",
    "REASON_LABELS",
    "WEIGHT_VAGUE_LANGUAGE",
    "WEIGHT_PROVISIONAL_SUM",
    "WEIGHT_MISSING_QUANTITY",
    "WEIGHT_MISSING_UNIT",
    "WEIGHT_UNDERSPECIFIED",
    "MAX_SCORE",
    "ScopeLine",
    "LineAmbiguity",
    "ScopeAmbiguityReport",
    "band_for_score",
    "score_line",
    "assess",
]
