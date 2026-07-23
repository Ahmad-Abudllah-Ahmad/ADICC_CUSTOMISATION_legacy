# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure provability scoring for a change / disputed event.

How strong is the contemporaneous record behind a change - could the project
actually *prove*, from documents it holds, who was responsible and that the
proper process was followed? The evidence-pack engine
(:mod:`app.modules.claims_evidence.evidence_pack`) already assembles and
digests the underlying records; this engine grades that body of evidence into a
single 0-100 :class:`ProvabilityScore` with transparent per-signal sub-scores
and a concrete list of weaknesses to cure. The industry signal it operates on
is blunt: when the record is easy to find and complete, confidence in proving
responsibility roughly doubles, and far more cost gets recovered. A graded
score turns the audit trail from a pile of documents into an asset the
commercial team can manage up.

No database, no ORM, no ``app.*`` imports - stdlib plus ``datetime`` only - so
it unit-tests on the local Python 3.11 runner exactly like the evidence-pack,
ownership-chain and cost-recovery engines. A thin service layer (written
separately by the integrator) gathers the evidence entries already assembled
for a subject plus a handful of stored signals, packs them into a
:class:`ProvabilitySignals`, and feeds it in.

Inputs are explicit dataclasses defined here on purpose - the engine never
imports the ORM. The integrator maps real rows onto these fields:

* notice timeliness from the served-at vs contractual-due-at datetimes;
* acknowledgement / response presence as a bool;
* the count of linked governing instructions / contract clauses (from the
  clarifier or hard FK links);
* owner-transition continuity, consumed from the ownership-chain engine's
  ``ownership_ambiguous`` / ``chain_inconsistent`` flags;
* date completeness from the assembled entry count, the dated span and a
  caller-supplied chronology-gap indicator.

Scoring model
-------------
Five independent signals each own a fixed weight; the weights are module-level
constants that sum to :data:`MAX_SCORE` (100). Each signal yields a *fraction*
in ``[0, 1]`` of how well it is satisfied; its contribution is ``weight x
fraction``, rounded to a whole point. The overall :attr:`ProvabilityScore.score`
is the sum of contributions, clamped to ``[0, 100]``. Everything is
deterministic and reads no clock: identical signals always produce an identical
score, sub-scores and weakness list.

Weakness model
--------------
Whenever a signal is not fully satisfied the engine appends a
:class:`Weakness` carrying a stable ``token`` (safe to switch on / localize)
and a human-readable ``message`` describing the gap and, where useful, the
points it cost. Weaknesses are emitted in a fixed signal order so the list is
reproducible.

Bands
-----
:func:`band_for` classifies a score into ``weak`` / ``moderate`` / ``strong``
using documented inclusive thresholds, so a downstream dispute-exposure model
(item #7) can consume the band without re-deriving the cut points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# --------------------------------------------------------------------------- #
# Score scale + weighting table (transparent, deterministic, sums to 100).
# --------------------------------------------------------------------------- #

#: The maximum attainable provability score. Sub-scores are points out of this.
MAX_SCORE = 100

#: Weight of a contractual notice that is present AND was served on or before
#: its contractual due date. The single strongest evidentiary lever: a timely
#: notice on the record is what most often distinguishes a provable claim.
WEIGHT_NOTICE = 30

#: Weight of an acknowledgement / response being on the record - proof the
#: other party received the notice / instruction and engaged with it.
WEIGHT_ACK = 15

#: Weight of a linked governing instruction or contract clause - what ties the
#: change to its contractual basis rather than leaving it as a bare assertion.
WEIGHT_INSTRUCTION = 20

#: Weight of owner-transition continuity - an unambiguous, internally
#: consistent custody chain (consumed from the ownership-chain engine).
WEIGHT_OWNERSHIP = 15

#: Weight of date completeness - enough dated entries spanning the event with no
#: chronology holes, i.e. a genuinely contemporaneous record.
WEIGHT_DATES = 20

#: All weights, in the fixed order signals are evaluated and weaknesses emitted.
#: Kept as data so a test can assert the sum and the service can introspect it.
WEIGHTS: dict[str, int] = {
    "notice_timeliness": WEIGHT_NOTICE,
    "acknowledgement": WEIGHT_ACK,
    "linked_instruction": WEIGHT_INSTRUCTION,
    "ownership_continuity": WEIGHT_OWNERSHIP,
    "date_completeness": WEIGHT_DATES,
}

# --------------------------------------------------------------------------- #
# Band thresholds (inclusive lower bounds). Documented for downstream reuse.
# --------------------------------------------------------------------------- #

BAND_WEAK = "weak"
BAND_MODERATE = "moderate"
BAND_STRONG = "strong"

#: A score of STRONG_THRESHOLD or above is "strong"; at or above
#: MODERATE_THRESHOLD (but below strong) is "moderate"; anything lower is
#: "weak". Chosen so a single fully-missing major signal (notice or
#: instruction) drops a record out of "strong", and losing two major signals
#: drops it to "weak".
STRONG_THRESHOLD = 75
MODERATE_THRESHOLD = 50

# --------------------------------------------------------------------------- #
# Stable weakness tokens. Each maps to one unsatisfied (or partial) signal.
# --------------------------------------------------------------------------- #

WEAKNESS_NOTICE_MISSING = "notice_missing"
WEAKNESS_NOTICE_LATE = "notice_late"
WEAKNESS_NOTICE_DUE_UNKNOWN = "notice_due_date_unknown"
WEAKNESS_NO_ACKNOWLEDGEMENT = "no_acknowledgement"
WEAKNESS_NO_LINKED_INSTRUCTION = "no_linked_instruction"
WEAKNESS_NO_OWNERSHIP_CHAIN = "no_ownership_chain"
WEAKNESS_OWNERSHIP_AMBIGUOUS = "ownership_ambiguous"
WEAKNESS_OWNERSHIP_GAP = "ownership_gap"
WEAKNESS_NO_DATED_RECORD = "no_dated_record"
WEAKNESS_THIN_RECORD = "thin_record"
WEAKNESS_CHRONOLOGY_GAP = "chronology_gap"

#: A record with at least this many dated entries is treated as a substantive
#: contemporaneous trail; fewer earns a partial date-completeness score and a
#: "thin record" weakness. A deliberately low, defensible bar.
MIN_SUBSTANTIVE_ENTRIES = 3


@dataclass(frozen=True)
class ProvabilitySignals:
    """Everything the engine needs to grade one change / event.

    The integrator gathers these off the evidence already assembled for a
    subject (the :class:`~app.modules.claims_evidence.evidence_pack.EvidencePack`
    plus a few stored flags) and feeds one instance in. Every field is a plain
    primitive so the engine stays ORM-free and 3.11-testable.

    Attributes
    ----------
    notice_served_at:
        When the contractual notice was actually served, or ``None`` if no
        notice is on the record at all.
    notice_due_at:
        The contractual deadline the notice was due by, or ``None`` if unknown.
        Timeliness can only be proven when both this and ``notice_served_at``
        are present; a served notice with an unknown deadline scores partially.
    has_acknowledgement:
        Whether an acknowledgement / response to the notice or instruction is on
        the record (proof the counterparty received and engaged).
    linked_instruction_count:
        How many governing instructions / contract clauses are linked to the
        change. Zero means the change is unanchored to its contractual basis.
    ownership_chain_present:
        Whether any ownership hand-off record exists for the change at all (the
        ownership-chain engine returned at least one segment). When ``False``
        there is no custody record to grade, so the ownership signal earns
        nothing and flags a missing chain - distinct from a chain that exists
        but is ambiguous. Defaults to ``False`` so an unwired / empty subject
        is scored conservatively.
    ownership_ambiguous:
        From the ownership-chain engine (``OwnershipChain.ownership_ambiguous``):
        the custody chain cannot say who is accountable (no current holder, or
        holder unchanged across a status transition, or an internally
        inconsistent chain). Only consulted when ``ownership_chain_present``.
    ownership_chain_inconsistent:
        From the ownership-chain engine (``OwnershipChain.chain_inconsistent``):
        a hand-off started from someone other than the prior holder - a concrete
        gap / overlap in the custody record. A more specific signal than
        ``ownership_ambiguous`` and reported with its own weakness when set.
        Only consulted when ``ownership_chain_present``.
    entry_count:
        Number of dated, deduped evidence entries assembled for the subject
        (``EvidencePack.entry_count`` once undated rows are excluded by the
        caller, or simply the count of entries with a parseable date).
    date_from:
        Earliest dated entry's timestamp, or ``None`` when nothing is dated.
    date_to:
        Latest dated entry's timestamp, or ``None`` when nothing is dated.
    chronology_has_gap:
        Caller-supplied indicator that the dated record has a hole - a stretch
        inside the event's span with no contemporaneous entry. The engine does
        not infer this (it has no view of expected cadence); the service sets it
        from whatever gap rule it applies. Defaults to ``False``.
    """

    notice_served_at: datetime | None = None
    notice_due_at: datetime | None = None
    has_acknowledgement: bool = False
    linked_instruction_count: int = 0
    ownership_chain_present: bool = False
    ownership_ambiguous: bool = False
    ownership_chain_inconsistent: bool = False
    entry_count: int = 0
    date_from: datetime | None = None
    date_to: datetime | None = None
    chronology_has_gap: bool = False


@dataclass(frozen=True)
class Weakness:
    """A single named gap that held the provability score below maximum.

    ``token`` is a stable identifier (one of the ``WEAKNESS_*`` constants) safe
    to switch on or localize; ``message`` is a human-readable explanation;
    ``signal`` names the weighted signal the weakness belongs to (a key of
    :data:`WEIGHTS`); ``points_lost`` is how many points this signal's shortfall
    cost, out of that signal's weight.
    """

    token: str
    message: str
    signal: str
    points_lost: int


@dataclass(frozen=True)
class SubScore:
    """One weighted signal's contribution to the overall score.

    ``earned`` + (weight - ``earned``) reconstructs the weight; ``fraction`` is
    the ``earned / weight`` ratio in ``[0, 1]`` the contribution was derived
    from (1.0 for a fully-satisfied signal).
    """

    signal: str
    weight: int
    earned: int
    fraction: float


@dataclass(frozen=True)
class ProvabilityScore:
    """The graded provability of one change / event.

    Attributes
    ----------
    score:
        Integer 0-100. Sum of every sub-score's ``earned`` points, clamped to
        :data:`MAX_SCORE`.
    band:
        ``weak`` / ``moderate`` / ``strong`` per :func:`band_for`.
    sub_scores:
        Per-signal contributions, in :data:`WEIGHTS` order.
    weaknesses:
        Named gaps, in signal order, each with a stable token, a message and the
        points it cost. An empty list means a perfect record.
    """

    score: int
    band: str
    sub_scores: list[SubScore]
    weaknesses: list[Weakness] = field(default_factory=list)


def band_for(score: int) -> str:
    """Classify a 0-100 provability score into a band.

    ``score >= STRONG_THRESHOLD`` -> :data:`BAND_STRONG`;
    ``score >= MODERATE_THRESHOLD`` -> :data:`BAND_MODERATE`;
    otherwise :data:`BAND_WEAK`. Thresholds are inclusive lower bounds.
    """
    if score >= STRONG_THRESHOLD:
        return BAND_STRONG
    if score >= MODERATE_THRESHOLD:
        return BAND_MODERATE
    return BAND_WEAK


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to aware UTC; ``None`` passes through.

    A naive datetime is assumed to already be UTC (the store persists UTC), so
    it is stamped rather than shifted - matching the ownership-chain engine.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _earned(weight: int, fraction: float) -> int:
    """Whole points a signal earned: ``round(weight * fraction)``, clamped."""
    pts = round(weight * fraction)
    if pts < 0:
        return 0
    if pts > weight:
        return weight
    return pts


def _score_notice(
    signals: ProvabilitySignals,
) -> tuple[float, list[Weakness]]:
    """Notice-timeliness fraction + any notice weakness.

    Full credit only when a notice was served on or before a *known*
    contractual deadline. A served notice with an unknown deadline cannot be
    proven timely, so it earns partial credit (it is still better than no notice
    at all) and flags the unknown due date. A late notice earns partial credit
    scaled down further; no notice at all earns nothing.
    """
    weight = WEIGHT_NOTICE
    served = _as_utc(signals.notice_served_at)
    due = _as_utc(signals.notice_due_at)

    if served is None:
        return 0.0, [
            Weakness(
                token=WEAKNESS_NOTICE_MISSING,
                message="No contractual notice is on the record for this change.",
                signal="notice_timeliness",
                points_lost=weight,
            )
        ]

    if due is None:
        # Served, but we cannot prove it beat a deadline we do not hold.
        fraction = 0.6
        return fraction, [
            Weakness(
                token=WEAKNESS_NOTICE_DUE_UNKNOWN,
                message=(
                    "A notice was served but its contractual due date is not "
                    "recorded, so its timeliness cannot be proven."
                ),
                signal="notice_timeliness",
                points_lost=weight - _earned(weight, fraction),
            )
        ]

    if served <= due:
        # On time against a known deadline: full credit, no weakness.
        return 1.0, []

    # Late. Report how late, and award partial credit (a late notice still
    # carries evidentiary weight, just diminished).
    fraction = 0.3
    days_late = (served - due).total_seconds() / 86400.0
    days_late_int = int(days_late) if days_late == int(days_late) else round(days_late, 1)
    plural = "" if days_late_int == 1 else "s"
    return fraction, [
        Weakness(
            token=WEAKNESS_NOTICE_LATE,
            message=(f"Notice served {days_late_int} day{plural} after its contractual due date."),
            signal="notice_timeliness",
            points_lost=weight - _earned(weight, fraction),
        )
    ]


def _score_ack(signals: ProvabilitySignals) -> tuple[float, list[Weakness]]:
    """Acknowledgement-present fraction + weakness when absent (all-or-nothing)."""
    weight = WEIGHT_ACK
    if signals.has_acknowledgement:
        return 1.0, []
    return 0.0, [
        Weakness(
            token=WEAKNESS_NO_ACKNOWLEDGEMENT,
            message="No acknowledgement or response from the other party is on the record.",
            signal="acknowledgement",
            points_lost=weight,
        )
    ]


def _score_instruction(signals: ProvabilitySignals) -> tuple[float, list[Weakness]]:
    """Linked-instruction fraction + weakness when none is linked.

    Presence is what matters evidentially, so this is all-or-nothing: one or
    more linked governing instructions / clauses earns full credit, none earns
    nothing. A negative count is treated as none.
    """
    weight = WEIGHT_INSTRUCTION
    if signals.linked_instruction_count > 0:
        return 1.0, []
    return 0.0, [
        Weakness(
            token=WEAKNESS_NO_LINKED_INSTRUCTION,
            message=(
                "No governing instruction or contract clause is linked to this "
                "change, so it is not anchored to a contractual basis."
            ),
            signal="linked_instruction",
            points_lost=weight,
        )
    ]


def _score_ownership(signals: ProvabilitySignals) -> tuple[float, list[Weakness]]:
    """Owner-continuity fraction + weakness(es) from the ownership-chain flags.

    No chain on the record at all earns nothing and flags the absence (you
    cannot prove who was accountable without any custody record). When a chain
    exists: an internally inconsistent chain (a concrete custody gap / overlap)
    is the worse failure and earns nothing; a chain that is merely ambiguous -
    no current holder, or unchanged across a status transition - earns partial
    credit because some custody record still exists. A clean, present chain
    earns full credit. The inconsistency / ambiguity flags can co-occur; the
    inconsistency dominates the score but each sets its own weakness so the cure
    list is specific.
    """
    weight = WEIGHT_OWNERSHIP
    weaknesses: list[Weakness] = []

    if not signals.ownership_chain_present:
        return 0.0, [
            Weakness(
                token=WEAKNESS_NO_OWNERSHIP_CHAIN,
                message=(
                    "No ownership hand-off record exists for this change, so who was accountable cannot be traced."
                ),
                signal="ownership_continuity",
                points_lost=weight,
            )
        ]

    if signals.ownership_chain_inconsistent:
        fraction = 0.0
    elif signals.ownership_ambiguous:
        fraction = 0.5
    else:
        return 1.0, []

    earned = _earned(weight, fraction)
    lost = weight - earned

    if signals.ownership_chain_inconsistent:
        weaknesses.append(
            Weakness(
                token=WEAKNESS_OWNERSHIP_GAP,
                message=(
                    "The ownership chain is inconsistent - a hand-off starts "
                    "from a party other than the prior holder, leaving a gap in "
                    "the custody record."
                ),
                signal="ownership_continuity",
                # Attribute the full shortfall to the dominant (gap) weakness so
                # points_lost across this signal's weaknesses does not exceed
                # the weight when both flags are set.
                points_lost=lost,
            )
        )
    if signals.ownership_ambiguous:
        weaknesses.append(
            Weakness(
                token=WEAKNESS_OWNERSHIP_AMBIGUOUS,
                message=(
                    "Ownership is ambiguous between submission and approval - "
                    "the record cannot say who was accountable."
                ),
                signal="ownership_continuity",
                # If a gap weakness already claimed the shortfall, this softer
                # weakness reports zero points so the sum stays consistent.
                points_lost=0 if signals.ownership_chain_inconsistent else lost,
            )
        )

    return fraction, weaknesses


def _score_dates(signals: ProvabilitySignals) -> tuple[float, list[Weakness]]:
    """Date-completeness fraction + weakness(es) for a thin or holed record.

    Three nested conditions, worst first:

    * no dated entry at all (or no span) earns nothing;
    * a dated record thinner than :data:`MIN_SUBSTANTIVE_ENTRIES` earns half;
    * an explicit chronology gap costs a further quarter of the weight.

    A substantive, gap-free dated record earns full credit.
    """
    weight = WEIGHT_DATES
    weaknesses: list[Weakness] = []

    has_span = signals.date_from is not None and signals.date_to is not None
    count = signals.entry_count if signals.entry_count > 0 else 0

    if count <= 0 or not has_span:
        return 0.0, [
            Weakness(
                token=WEAKNESS_NO_DATED_RECORD,
                message="No dated contemporaneous record exists for this change.",
                signal="date_completeness",
                points_lost=weight,
            )
        ]

    fraction = 1.0
    if count < MIN_SUBSTANTIVE_ENTRIES:
        fraction -= 0.5
        weaknesses.append(
            Weakness(
                token=WEAKNESS_THIN_RECORD,
                message=(
                    f"Only {count} dated "
                    f"{'entry' if count == 1 else 'entries'} on the record; a "
                    f"substantive trail needs at least {MIN_SUBSTANTIVE_ENTRIES}."
                ),
                signal="date_completeness",
                points_lost=0,  # filled in below once the final fraction is known
            )
        )

    if signals.chronology_has_gap:
        fraction -= 0.25
        weaknesses.append(
            Weakness(
                token=WEAKNESS_CHRONOLOGY_GAP,
                message="The chronology has a gap - a stretch of the event has no contemporaneous record.",
                signal="date_completeness",
                points_lost=0,  # filled in below
            )
        )

    if fraction < 0.0:
        fraction = 0.0

    # Distribute the actual shortfall across the emitted weaknesses so their
    # points_lost reconstruct the lost points exactly (largest share to the
    # first weakness on any remainder).
    total_lost = weight - _earned(weight, fraction)
    if weaknesses:
        per = total_lost // len(weaknesses)
        remainder = total_lost - per * len(weaknesses)
        adjusted: list[Weakness] = []
        for idx, wk in enumerate(weaknesses):
            extra = 1 if idx < remainder else 0
            adjusted.append(
                Weakness(
                    token=wk.token,
                    message=wk.message,
                    signal=wk.signal,
                    points_lost=per + extra,
                )
            )
        weaknesses = adjusted

    return fraction, weaknesses


# Signal evaluators in the fixed, documented order. Keeping them as data lets
# compute_provability iterate deterministically and keeps the weakness order
# stable and aligned with WEIGHTS.
_SIGNAL_ORDER: list[tuple[str, int]] = [
    ("notice_timeliness", WEIGHT_NOTICE),
    ("acknowledgement", WEIGHT_ACK),
    ("linked_instruction", WEIGHT_INSTRUCTION),
    ("ownership_continuity", WEIGHT_OWNERSHIP),
    ("date_completeness", WEIGHT_DATES),
]


def compute_provability(signals: ProvabilitySignals) -> ProvabilityScore:
    """Grade how provable responsibility for a change / event is.

    Evaluates the five weighted signals (see module docstring) in fixed order,
    sums their earned points into a 0-100 score, classifies it into a band and
    returns the per-signal sub-scores plus an ordered list of named weaknesses.

    The computation is pure and deterministic: it reads no clock and uses no
    randomness, so identical ``signals`` always yield an identical result.
    """
    evaluators = {
        "notice_timeliness": _score_notice,
        "acknowledgement": _score_ack,
        "linked_instruction": _score_instruction,
        "ownership_continuity": _score_ownership,
        "date_completeness": _score_dates,
    }

    sub_scores: list[SubScore] = []
    weaknesses: list[Weakness] = []
    total = 0
    for signal, weight in _SIGNAL_ORDER:
        fraction, signal_weaknesses = evaluators[signal](signals)
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        earned = _earned(weight, fraction)
        total += earned
        sub_scores.append(SubScore(signal=signal, weight=weight, earned=earned, fraction=fraction))
        weaknesses.extend(signal_weaknesses)

    if total < 0:
        total = 0
    elif total > MAX_SCORE:
        total = MAX_SCORE

    return ProvabilityScore(
        score=total,
        band=band_for(total),
        sub_scores=sub_scores,
        weaknesses=weaknesses,
    )


# --------------------------------------------------------------------------- #
# Localization + action-planning helpers (additive, pure, deterministic).
#
# The scoring above is deliberately country-neutral (UTC dates, no currency, no
# locale). What was still English-only was the way a result is *presented*: the
# signal names and band words. These catalogues let a UI show them in the user's
# language without re-deriving anything. The dynamic weakness messages stay in
# their English default (they carry values like day counts); a UI that needs
# them translated switches on the stable ``token``.
# --------------------------------------------------------------------------- #

#: Short, human-readable name of each weighted signal, per language. English is
#: always present and is the fallback for any missing language or unknown signal.
SIGNAL_LABELS: dict[str, dict[str, str]] = {
    "notice_timeliness": {
        "en": "Notice timeliness",
        "de": "Rechtzeitigkeit der Anzeige",
        "ru": "Своевременность уведомления",
    },
    "acknowledgement": {
        "en": "Acknowledgement on record",
        "de": "Empfangsbestätigung vorhanden",
        "ru": "Подтверждение получения",
    },
    "linked_instruction": {
        "en": "Linked instruction or clause",
        "de": "Verknüpfte Anweisung oder Klausel",
        "ru": "Связанное указание или пункт договора",
    },
    "ownership_continuity": {
        "en": "Ownership continuity",
        "de": "Kontinuität der Zuständigkeit",
        "ru": "Непрерывность ответственности",
    },
    "date_completeness": {
        "en": "Dated record completeness",
        "de": "Vollständigkeit der datierten Nachweise",
        "ru": "Полнота датированных записей",
    },
}

#: The band words, per language. English is the fallback.
BAND_LABELS: dict[str, dict[str, str]] = {
    BAND_WEAK: {"en": "weak", "de": "schwach", "ru": "слабая"},
    BAND_MODERATE: {"en": "moderate", "de": "mittel", "ru": "средняя"},
    BAND_STRONG: {"en": "strong", "de": "stark", "ru": "высокая"},
}


def signal_label(signal: str, lang: str = "en") -> str:
    """Localized short name of a weighted signal.

    Falls back to English for an unknown language, and to the raw ``signal`` key
    for an unknown signal, so a caller never gets an empty string.
    """
    per_lang = SIGNAL_LABELS.get(signal)
    if per_lang is None:
        return signal
    return per_lang.get(lang) or per_lang["en"]


def band_label(band: str, lang: str = "en") -> str:
    """Localized band word (weak / moderate / strong), English as fallback."""
    per_lang = BAND_LABELS.get(band)
    if per_lang is None:
        return band
    return per_lang.get(lang) or per_lang["en"]


@dataclass(frozen=True)
class CureStep:
    """One prioritized action that would recover the most provability points.

    Derived from a :class:`ProvabilityScore` weakness. ``priority`` is 1 for the
    most valuable cure, 2 for the next and so on; ``points_recoverable`` is how
    many points curing it adds back (the weakness's ``points_lost``).
    """

    priority: int
    token: str
    signal: str
    points_recoverable: int
    message: str


def cure_plan(score: ProvabilityScore) -> list[CureStep]:
    """Rank a score's weaknesses into a "fix this first" action list.

    Orders by the points each cure recovers (largest first), breaking ties by
    the fixed signal order so the plan is reproducible. Weaknesses that recover
    no points (a softer duplicate already counted elsewhere) are omitted, since
    acting on them changes nothing. An empty list means a complete record.
    """
    signal_rank = {signal: idx for idx, (signal, _weight) in enumerate(_SIGNAL_ORDER)}
    curable = [wk for wk in score.weaknesses if wk.points_lost > 0]
    ordered = sorted(
        curable,
        key=lambda wk: (-wk.points_lost, signal_rank.get(wk.signal, len(_SIGNAL_ORDER))),
    )
    return [
        CureStep(
            priority=idx + 1,
            token=wk.token,
            signal=wk.signal,
            points_recoverable=wk.points_lost,
            message=wk.message,
        )
        for idx, wk in enumerate(ordered)
    ]


def score_summary(score: ProvabilityScore) -> str:
    """One-line plain-language summary of a provability result.

    States the band and score, then either confirms a complete record or names
    the single most valuable gap to cure and the points it would recover. Kept
    in English (it quotes the English weakness message); a UI wanting other
    languages uses :func:`signal_label` / :func:`band_label` and the token.
    """
    head = f"Provability is {band_label(score.band)} ({score.score}/{MAX_SCORE})."
    plan = cure_plan(score)
    if not plan:
        return f"{head} The record is complete, with no gaps to cure."
    top = plan[0]
    point_word = "point" if top.points_recoverable == 1 else "points"
    return f"{head} Biggest gap to cure: {top.message} (worth {top.points_recoverable} {point_word})."


__all__ = [
    "MAX_SCORE",
    "WEIGHT_NOTICE",
    "WEIGHT_ACK",
    "WEIGHT_INSTRUCTION",
    "WEIGHT_OWNERSHIP",
    "WEIGHT_DATES",
    "WEIGHTS",
    "BAND_WEAK",
    "BAND_MODERATE",
    "BAND_STRONG",
    "STRONG_THRESHOLD",
    "MODERATE_THRESHOLD",
    "MIN_SUBSTANTIVE_ENTRIES",
    "WEAKNESS_NOTICE_MISSING",
    "WEAKNESS_NOTICE_LATE",
    "WEAKNESS_NOTICE_DUE_UNKNOWN",
    "WEAKNESS_NO_ACKNOWLEDGEMENT",
    "WEAKNESS_NO_LINKED_INSTRUCTION",
    "WEAKNESS_NO_OWNERSHIP_CHAIN",
    "WEAKNESS_OWNERSHIP_AMBIGUOUS",
    "WEAKNESS_OWNERSHIP_GAP",
    "WEAKNESS_NO_DATED_RECORD",
    "WEAKNESS_THIN_RECORD",
    "WEAKNESS_CHRONOLOGY_GAP",
    "ProvabilitySignals",
    "Weakness",
    "SubScore",
    "ProvabilityScore",
    "band_for",
    "compute_provability",
    "SIGNAL_LABELS",
    "BAND_LABELS",
    "signal_label",
    "band_label",
    "CureStep",
    "cure_plan",
    "score_summary",
]
