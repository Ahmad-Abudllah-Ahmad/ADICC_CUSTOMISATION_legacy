# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure hours-saved estimation.

Answers the commercial question the construction-change survey keeps raising:
roughly half of practitioners spend eleven or more hours a week on
administration, and AI-embedded tooling is reported to give back about two
hours a week per project. We deliver those savings already - every assisted
action lands a row in the activity log - but until now we never quantified
them. This engine turns those activity rows into an honest, defensible
hours-saved figure.

The model is deliberately a transparent minute-factor lookup, not a
black box. Each estimated action maps to a small, conservative number of
minutes the manual alternative would have cost - drafting an RFI reply by
hand, hand-compiling a correspondence digest, assembling an evidence pack
from scattered files. The honesty of the number is the whole point, so the
defaults are intentionally low (we would rather under-claim than oversell),
every constant carries a one-line justification, and an unrecognised
``(module, action)`` pair contributes exactly zero - the engine never invents
a saving for work it cannot account for.

The defaults here are the seed values. The integrator layers a small
admin-editable table on top so an operator can tune any factor to their own
measured baseline; this module is the deterministic calculator those factors
feed into.

No database, no ORM, no ``app.*`` imports - stdlib plus Decimal / datetime
only - so it unit-tests on the local Python 3.11 runner exactly like the
other pure engines. The thin service layer (written separately) reads
``oe_activity_log`` rows, projects them onto :class:`ActivityEvent`, and calls
in here.

Time is reported in hours (minutes divided by sixty) and quantized to two
decimal places with half-up rounding so a dashboard total is stable and
reconciles with the per-row minutes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping

#: Two-decimal-place quantum for the hours figures we report.
TWOPLACES = Decimal("0.01")

#: Minutes in an hour, as Decimal so the division stays exact before rounding.
_MINUTES_PER_HOUR = Decimal("60")

# Grouping axes accepted by :func:`aggregate_hours`.
BY_USER = "user"
BY_PROJECT = "project"
BY_FEATURE = "feature"
BY_PERIOD = "period"

#: Period bucket granularities accepted by :func:`aggregate_hours`.
PERIOD_WEEK = "week"
PERIOD_MONTH = "month"

#: Bucket label for an event whose grouping key is missing (no actor, no
#: project, ...). Surfacing an "unknown" bucket is more honest than silently
#: dropping the saving or folding it into someone else's total.
UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Default minute factors
# ---------------------------------------------------------------------------
#
# Each entry is the number of minutes the MANUAL alternative to one assisted
# action would plausibly have cost a competent practitioner. Values are
# deliberately conservative - the low end of a believable range - because an
# hours-saved claim is only useful if a sceptical buyer accepts it. They are
# expressed as whole-minute ``Decimal`` so the arithmetic never touches float.
#
# An action absent from this map saves nothing. We only credit savings for
# work the platform genuinely performs in place of a person.
#
# Keys are ``(module, action)`` to match the ``module`` + ``action`` columns
# the activity log already records.
DEFAULT_FACTORS: dict[tuple[str, str], Decimal] = {
    # Answering an RFI by hand means reading the question, checking drawings /
    # specs and composing a written reply. 25 min is a modest single reply.
    ("rfi", "rfi_answered"): Decimal("25"),
    # Logging a change order from scratch - transcribing scope, cost and
    # schedule into the register. 20 min for the data entry alone.
    ("changeorders", "change_order_logged"): Decimal("20"),
    # Updating an existing change order (re-pricing, status, re-routing).
    # Lighter than first capture, so 10 min.
    ("changeorders", "change_order_updated"): Decimal("10"),
    # Compiling a correspondence digest by hand - skimming a thread and
    # summarising the open points. 30 min for a non-trivial thread.
    ("change_intelligence", "comms_digest_generated"): Decimal("30"),
    # Drafting the clarifying questions for an ambiguous change request -
    # spotting the gaps a person would otherwise miss. 15 min.
    ("change_intelligence", "change_request_clarified"): Decimal("15"),
    # Assembling an evidence pack manually - locating, ordering and collating
    # the contemporaneous records behind a claim. This is the heaviest admin
    # task we displace; 45 min is still conservative for a real pack.
    ("claims_evidence", "evidence_pack_assembled"): Decimal("45"),
    # Producing a first-pass estimate by hand from a takeoff. 40 min to price
    # a modest scope before review.
    ("ai_estimator", "ai_estimate_produced"): Decimal("40"),
    # Parsing a takeoff out of a drawing / model by hand - measuring and
    # listing quantities. 35 min for a single sheet's worth.
    ("takeoff", "takeoff_parsed"): Decimal("35"),
    # Detecting a schedule delay from field reports that a person would have to
    # read and cross-reference. 20 min of correlation work.
    ("change_intelligence", "delay_detected"): Decimal("20"),
}


@dataclass(frozen=True)
class ActivityEvent:
    """Present-state projection of one activity-log row for the engine.

    Mirrors the columns ``oe_activity_log`` already records: ``action`` and
    ``module`` identify what happened, ``at`` is the event timestamp
    (``created_at``), and ``actor_id`` / ``project_id`` are the optional
    user / project scope. ``units`` lets a single row stand for more than one
    unit of saved work (for example a batch import that answered five RFIs);
    it defaults to one. The engine treats ``actor_id`` and ``project_id`` as
    opaque strings - it never imports the ORM.
    """

    action: str
    module: str
    at: datetime
    actor_id: str | None = None
    project_id: str | None = None
    units: int = 1


@dataclass(frozen=True)
class SavedBucket:
    """Hours saved for one grouping key.

    ``key`` is the bucket label (a user id, project id, ``module/action``
    feature token, or period bucket like ``2026-W26`` / ``2026-06``).
    ``event_count`` is how many activity rows fell in the bucket (including
    zero-factor rows, so the denominator is honest), ``unit_count`` is the sum
    of their ``units``, ``minutes`` is the exact saved-minutes total, and
    ``hours`` is that total in hours, quantized to two places.
    """

    key: str
    event_count: int
    unit_count: int
    minutes: Decimal
    hours: Decimal


def minutes_to_hours(minutes: Decimal) -> Decimal:
    """Convert *minutes* to hours, quantized to two places half-up."""
    return (minutes / _MINUTES_PER_HOUR).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def merge_factors(
    overrides: Mapping[tuple[str, str], Decimal],
    base: Mapping[tuple[str, str], Decimal] = DEFAULT_FACTORS,
) -> dict[tuple[str, str], Decimal]:
    """Layer *overrides* on top of *base*, returning the effective factor map.

    The result is ``base`` with each overridden ``(module, action)`` pair
    replaced by its override value, so an admin who tuned only one factor still
    gets the documented defaults for every other action. ``base`` is never
    mutated. A pair present in *base* but not in *overrides* keeps its default;
    a pair present only in *overrides* (a tenant crediting an action the seed map
    does not) is added. This is the deterministic glue the service uses to turn a
    sparse table of tenant overrides into the full factor map the aggregation
    functions take - the engine stays the single place that defines what
    "effective factors" means.
    """
    effective = dict(base)
    effective.update(overrides)
    return effective


def estimate_saved_minutes(
    action: str,
    module: str,
    units: int = 1,
    factors: Mapping[tuple[str, str], Decimal] = DEFAULT_FACTORS,
) -> Decimal:
    """Estimated minutes saved by one assisted *action* in *module*.

    Looks the ``(module, action)`` pair up in *factors* and multiplies by
    *units*. An unrecognised pair returns ``Decimal("0")`` - the engine never
    credits a saving for work it cannot account for. A non-positive *units*
    also returns zero, since fewer than one unit of work cannot have saved
    time. The result is exact (no rounding); rounding happens only when minutes
    are converted to reported hours.
    """
    if units <= 0:
        return Decimal("0")
    factor = factors.get((module, action))
    if factor is None:
        return Decimal("0")
    return factor * Decimal(units)


def _period_key(moment: datetime, period: str) -> str:
    """Bucket label for *moment* at the requested *period* granularity.

    Weekly buckets use the ISO calendar (``YYYY-Www``, zero-padded week) so a
    week is unambiguous across year boundaries; monthly buckets use
    ``YYYY-MM``. Both are lexically sortable, which keeps a time series in
    order without extra date parsing downstream.
    """
    if period == PERIOD_WEEK:
        iso_year, iso_week, _ = moment.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"
    if period == PERIOD_MONTH:
        return f"{moment.year:04d}-{moment.month:02d}"
    raise ValueError(f"unknown period granularity: {period!r}")


def _bucket_key(
    event: ActivityEvent,
    by: str,
    period: str | None,
) -> str:
    """Resolve the grouping key for *event* on the *by* axis."""
    if by == BY_USER:
        return event.actor_id or UNKNOWN
    if by == BY_PROJECT:
        return event.project_id or UNKNOWN
    if by == BY_FEATURE:
        return f"{event.module}/{event.action}"
    if by == BY_PERIOD:
        if period is None:
            raise ValueError("period granularity is required when grouping by period")
        return _period_key(event.at, period)
    raise ValueError(f"unknown grouping axis: {by!r}")


def aggregate_hours(
    rows: Iterable[ActivityEvent],
    *,
    by: str,
    factors: Mapping[tuple[str, str], Decimal] = DEFAULT_FACTORS,
    period: str | None = None,
) -> tuple[SavedBucket, ...]:
    """Aggregate activity rows into hours saved, grouped on one axis.

    *by* is one of :data:`BY_USER`, :data:`BY_PROJECT`, :data:`BY_FEATURE`
    (``module/action``) or :data:`BY_PERIOD`. When grouping by period, *period*
    must be :data:`PERIOD_WEEK` or :data:`PERIOD_MONTH`. Every row contributes
    to its bucket's ``event_count`` and ``unit_count`` even when its factor is
    zero, so the saved-hours figure is reported against an honest denominator
    rather than only the rows that happened to save time.

    Buckets are returned sorted by descending saved hours, then ascending key,
    so the most valuable bucket leads and ties are stable. Empty input yields
    an empty tuple.
    """
    minutes_by_key: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    events_by_key: dict[str, int] = defaultdict(int)
    units_by_key: dict[str, int] = defaultdict(int)

    for event in rows:
        key = _bucket_key(event, by, period)
        # Count every event and its units, even zero-factor ones, so the
        # bucket's denominator reflects all the work, not just the credited
        # work. Clamp negative/zero units to zero for the unit tally to match
        # the minutes (estimate_saved_minutes already floors them).
        units = event.units if event.units > 0 else 0
        events_by_key[key] += 1
        units_by_key[key] += units
        minutes_by_key[key] += estimate_saved_minutes(
            event.action,
            event.module,
            event.units,
            factors,
        )

    buckets = tuple(
        SavedBucket(
            key=key,
            event_count=events_by_key[key],
            unit_count=units_by_key[key],
            minutes=minutes_by_key[key],
            hours=minutes_to_hours(minutes_by_key[key]),
        )
        for key in events_by_key
    )

    return tuple(sorted(buckets, key=lambda b: (-b.hours, b.key)))


def total_hours(
    rows: Iterable[ActivityEvent],
    factors: Mapping[tuple[str, str], Decimal] = DEFAULT_FACTORS,
) -> Decimal:
    """Total hours saved across *rows*, ignoring grouping.

    A convenience for a single headline figure (for example a personal "time
    you saved this month" widget). Sums the exact minutes first, then converts
    once, so the headline reconciles with the sum of the per-bucket minutes.
    """
    minutes = Decimal("0")
    for event in rows:
        minutes += estimate_saved_minutes(
            event.action,
            event.module,
            event.units,
            factors,
        )
    return minutes_to_hours(minutes)


__all__ = [
    "BY_FEATURE",
    "BY_PERIOD",
    "BY_PROJECT",
    "BY_USER",
    "DEFAULT_FACTORS",
    "PERIOD_MONTH",
    "PERIOD_WEEK",
    "TWOPLACES",
    "UNKNOWN",
    "ActivityEvent",
    "SavedBucket",
    "aggregate_hours",
    "estimate_saved_minutes",
    "merge_factors",
    "minutes_to_hours",
    "total_hours",
]
