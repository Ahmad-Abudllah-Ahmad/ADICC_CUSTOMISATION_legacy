# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure ownership hand-off chain + dwell-time for a single change record.

Answers the accountability question the project team cannot answer today: as a
change moves through approval, who has held the ball, in what order, and for how
long did each holder keep it. The change modules store ``ball_in_court`` as a
single mutable string with no history; the service layer records every change of
that field as an activity-log row (``action="ownership_handoff"``) carrying the
old holder, the new holder, when it happened, who recorded it, and why. This
engine reconstructs the timeline from those rows.

Given the hand-off rows for one change it builds an :class:`OwnershipChain`:

* ``segments`` - one :class:`OwnershipSegment` per successive holder, in time
  order, each with the interval it held the ball and the ``dwell_days`` it
  accrued. The final segment is open (``to_ts is None``) and dwells up to
  ``now``.
* ``dwell_by_party`` - total days each party held the ball, summed across all
  of its (possibly non-contiguous) segments.
* ``current_holder`` - who holds the ball right now (``None`` if nobody does).
* ``ownership_ambiguous`` - a single flag the caller can act on: the chain
  cannot say who is accountable. It is true when there is no current holder, or
  the holder did not change across a recorded status transition (the change
  advanced but nobody picked it up), or the recorded chain is internally
  inconsistent (a hand-off starts from someone other than the prior holder, so
  there is a gap / overlap in the custody record).

Plus the granular signals the ambiguity flag is derived from
(``has_unrecorded_origin``, ``chain_inconsistent``,
``unchanged_across_transition``) so a UI can explain *why* it is ambiguous.

No database, no ORM, no ``app.*`` imports - stdlib + datetime only - so it
unit-tests on the local Python 3.11 runner exactly like the cycle-time and
clarifier engines. The dwell-time it produces is the precise per-holder figure
that :mod:`app.modules.change_intelligence.cycle_time` flagged as a later
refinement; the thin service layer reads the hand-off rows and feeds them in.

Units: ``dwell_days`` is a float day count (seconds / 86400, rounded to two
decimals) to match the cycle-time board's age figures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class HandoffRow:
    """One recovered ownership hand-off for a change.

    Mirrors an ``oe_activity_log`` row with ``action="ownership_handoff"``.
    ``from_party`` is the holder the ball moved away from (the prior
    ball-in-court, ``None`` when the change had no holder before this hand-off);
    ``to_party`` is the new holder (``None`` is allowed - it records the ball
    being explicitly dropped / un-assigned). ``at`` is when the hand-off
    happened. ``set_by`` and ``reason`` are carried through for display and are
    not used in the dwell math.
    """

    at: datetime
    from_party: str | None
    to_party: str | None
    set_by: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class OwnershipSegment:
    """A single uninterrupted stretch during which one party held the ball.

    ``to_ts`` is ``None`` for the current / open segment, which dwells up to the
    ``now`` passed to :func:`build_ownership_chain`. ``is_open`` mirrors that for
    convenience. ``set_by`` / ``reason`` are the metadata of the hand-off that
    *started* this segment (i.e. the hand-off that put the ball in this party's
    court).
    """

    party: str | None
    from_ts: datetime
    to_ts: datetime | None
    dwell_days: float
    is_open: bool
    set_by: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PartyDwell:
    """Total time one party held the ball across all of its segments."""

    party: str | None
    dwell_days: float
    segment_count: int


@dataclass(frozen=True)
class OwnershipChain:
    """The full reconstructed ownership history for one change."""

    as_of: datetime
    segments: list[OwnershipSegment]
    dwell_by_party: list[PartyDwell]
    current_holder: str | None
    ownership_ambiguous: bool
    # Granular signals behind ``ownership_ambiguous`` (for explainability).
    has_current_holder: bool
    has_unrecorded_origin: bool
    chain_inconsistent: bool
    unchanged_across_transition: bool
    total_handoffs: int
    ambiguity_reasons: list[str] = field(default_factory=list)


# Stable tokens for the reasons that can drive ``ownership_ambiguous``.
REASON_NO_HOLDER = "no_current_holder"
REASON_UNCHANGED_ACROSS_TRANSITION = "holder_unchanged_across_status_transition"
REASON_CHAIN_INCONSISTENT = "chain_inconsistent"


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to aware UTC; ``None`` passes through.

    A naive datetime is assumed to already be UTC (the store persists UTC), so
    it is stamped rather than shifted.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _days_between(start: datetime, end: datetime) -> float:
    """Whole-and-fractional day count between two aware datetimes.

    Clamped at zero so a later-sorted equal/earlier boundary never yields a
    negative dwell. Rounded to two decimals to match the cycle-time board.
    """
    seconds = (end - start).total_seconds()
    if seconds < 0:
        seconds = 0.0
    return round(seconds / 86400.0, 2)


def _sorted_handoffs(handoffs: list[HandoffRow]) -> list[HandoffRow]:
    """Return the hand-offs in stable chronological order (UTC-normalized).

    Out-of-order input is sorted by timestamp; rows sharing a timestamp keep
    their original relative order (stable sort) so a deterministic chain results
    regardless of how the caller gathered the rows.
    """
    indexed = list(enumerate(handoffs))
    indexed.sort(key=lambda pair: (_as_utc(pair[1].at), pair[0]))  # type: ignore[arg-type]
    return [row for _, row in indexed]


def build_ownership_chain(
    handoffs: list[HandoffRow],
    *,
    now: datetime,
    status_transition_times: list[datetime] | None = None,
) -> OwnershipChain:
    """Reconstruct the ordered ownership chain + dwell-time for one change.

    Parameters
    ----------
    handoffs:
        Recovered ``ownership_handoff`` rows for a single change, in any order.
    now:
        The "as of" instant the open (current) segment dwells up to.
    status_transition_times:
        Optional timestamps at which the change's *status* advanced. Used only
        to detect the ambiguity case where the change moved forward but the ball
        did not change hands (nobody picked it up for the new phase).

    Returns
    -------
    OwnershipChain
        Ordered segments, per-party total dwell (descending by dwell), the
        current holder, and the ``ownership_ambiguous`` flag with its granular
        signals and human-stable reasons.

    Notes
    -----
    Segment model: each hand-off puts the ball in ``to_party``'s court at
    ``at``; that party holds it until the next hand-off (or ``now``). The very
    first hand-off's ``from_party`` is whoever held the ball *before* any
    recorded hand-off, but the store has no timestamp for when they received it,
    so no segment is fabricated for that pre-history; instead it is surfaced via
    ``has_unrecorded_origin``. Determinism: the result depends only on the input
    rows and ``now``.
    """
    now_utc = _as_utc(now) or now
    ordered = _sorted_handoffs(handoffs)

    # Build one segment per hand-off: to_party holds from this hand-off's time
    # until the next hand-off's time (or now for the last one).
    segments: list[OwnershipSegment] = []
    for i, row in enumerate(ordered):
        from_ts = _as_utc(row.at) or now_utc
        is_open = i == len(ordered) - 1
        to_ts = None if is_open else (_as_utc(ordered[i + 1].at) or now_utc)
        end = to_ts if to_ts is not None else now_utc
        segments.append(
            OwnershipSegment(
                party=row.to_party,
                from_ts=from_ts,
                to_ts=to_ts,
                dwell_days=_days_between(from_ts, end),
                is_open=is_open,
                set_by=row.set_by,
                reason=row.reason,
            )
        )

    # Per-party dwell, summed across (possibly non-contiguous) segments.
    dwell_totals: dict[str | None, float] = {}
    seg_counts: dict[str | None, int] = {}
    order_seen: list[str | None] = []
    for seg in segments:
        if seg.party not in dwell_totals:
            dwell_totals[seg.party] = 0.0
            seg_counts[seg.party] = 0
            order_seen.append(seg.party)
        dwell_totals[seg.party] = round(dwell_totals[seg.party] + seg.dwell_days, 2)
        seg_counts[seg.party] += 1

    dwell_by_party = [
        PartyDwell(party=party, dwell_days=dwell_totals[party], segment_count=seg_counts[party]) for party in order_seen
    ]
    # Most-dwell first; ties broken by first-appearance order for determinism.
    appearance = {party: idx for idx, party in enumerate(order_seen)}
    dwell_by_party.sort(key=lambda pd: (-pd.dwell_days, appearance[pd.party]))

    # Current holder = the last hand-off's destination (None => dropped / none).
    current_holder = ordered[-1].to_party if ordered else None
    has_current_holder = current_holder is not None

    # An origin is "unrecorded" when the first hand-off names a prior holder we
    # never have a received-timestamp for. That is a known gap, not an error,
    # so it informs the chain but does NOT by itself set ambiguity.
    has_unrecorded_origin = bool(ordered) and ordered[0].from_party is not None

    # Chain inconsistency: a hand-off whose from_party does not match the holder
    # the prior hand-off left the ball with => a gap / overlap in custody.
    chain_inconsistent = False
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        if curr.from_party != prev.to_party:
            chain_inconsistent = True
            break

    # Holder unchanged across a status transition: the change advanced (a status
    # transition fell strictly inside a holder's segment) yet the ball never
    # moved. Only meaningful when transitions are supplied.
    unchanged_across_transition = _transition_without_handoff(segments, status_transition_times, now_utc)

    reasons: list[str] = []
    if not has_current_holder:
        reasons.append(REASON_NO_HOLDER)
    if unchanged_across_transition:
        reasons.append(REASON_UNCHANGED_ACROSS_TRANSITION)
    if chain_inconsistent:
        reasons.append(REASON_CHAIN_INCONSISTENT)

    return OwnershipChain(
        as_of=now_utc,
        segments=segments,
        dwell_by_party=dwell_by_party,
        current_holder=current_holder,
        ownership_ambiguous=bool(reasons),
        has_current_holder=has_current_holder,
        has_unrecorded_origin=has_unrecorded_origin,
        chain_inconsistent=chain_inconsistent,
        unchanged_across_transition=unchanged_across_transition,
        total_handoffs=len(ordered),
        ambiguity_reasons=reasons,
    )


def _transition_without_handoff(
    segments: list[OwnershipSegment],
    status_transition_times: list[datetime] | None,
    now_utc: datetime,
) -> bool:
    """True when a status transition fell inside a holder's segment.

    A transition strictly after a segment's start and strictly before its end
    (``now`` for the open segment) means the change advanced while the ball
    stayed in the same court - the ambiguity the report calls out (nobody picked
    the change up for its new phase). A transition landing exactly on a segment
    boundary lines up with a hand-off and is not ambiguous.
    """
    if not status_transition_times or not segments:
        return False
    transitions = [t for t in (_as_utc(t) for t in status_transition_times) if t is not None]
    for seg in segments:
        seg_end = seg.to_ts if seg.to_ts is not None else now_utc
        for t in transitions:
            if seg.from_ts < t < seg_end:
                return True
    return False


__all__ = [
    "REASON_CHAIN_INCONSISTENT",
    "REASON_NO_HOLDER",
    "REASON_UNCHANGED_ACROSS_TRANSITION",
    "HandoffRow",
    "OwnershipChain",
    "OwnershipSegment",
    "PartyDwell",
    "build_ownership_chain",
]
