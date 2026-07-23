# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure roll-up of AI feedback verdicts.

The accuracy scoreboard scores agent *runs*; this rolls up the generic
thumbs-up / down verdicts recorded against AI surfaces that have no run row
(the AI Estimator result, a match suggestion, an advisor answer). Until this
read existed the ``oe_ai_feedback`` table was write-only, so the trust loop the
verdicts feed was invisible.

Pure and dependency-free (no DB, no I/O) so it is cheap to unit test: the
service layer reads the rows and hands them here. A correct rate is ``None``
when a surface has no verdicts yet, never a misleading zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackItem:
    """One recorded verdict: which surface, and whether the AI output was right."""

    surface: str
    correct: bool


@dataclass(frozen=True)
class SurfaceSummary:
    """Verdict rollup for one AI surface."""

    surface: str
    total: int
    correct: int
    incorrect: int
    # Fraction in [0, 1], or None when the surface has no verdicts (undefined,
    # never a misleading 0).
    correct_rate: float | None


@dataclass(frozen=True)
class FeedbackSummary:
    """Overall verdict rollup plus a per-surface breakdown."""

    total: int
    correct: int
    incorrect: int
    correct_rate: float | None
    by_surface: list[SurfaceSummary]


def _rate(correct: int, total: int) -> float | None:
    """Correct fraction rounded to 4 dp, or None when there is nothing to divide."""
    return round(correct / total, 4) if total else None


def summarize_feedback(items: list[FeedbackItem]) -> FeedbackSummary:
    """Roll a flat list of verdicts up into overall + per-surface summaries.

    Surfaces are returned in alphabetical order for a stable response. An empty
    input yields zero counts and a ``None`` rate (not 0.0), so the caller can
    tell "no feedback yet" apart from "all wrong".
    """
    # surface -> [correct_count, total_count]
    buckets: dict[str, list[int]] = {}
    total = 0
    correct_total = 0
    for item in items:
        total += 1
        won = 1 if item.correct else 0
        correct_total += won
        bucket = buckets.setdefault(item.surface, [0, 0])
        bucket[0] += won
        bucket[1] += 1

    by_surface = [
        SurfaceSummary(
            surface=surface,
            total=count,
            correct=hit,
            incorrect=count - hit,
            correct_rate=_rate(hit, count),
        )
        for surface, (hit, count) in sorted(buckets.items())
    ]
    return FeedbackSummary(
        total=total,
        correct=correct_total,
        incorrect=total - correct_total,
        correct_rate=_rate(correct_total, total),
        by_surface=by_surface,
    )
