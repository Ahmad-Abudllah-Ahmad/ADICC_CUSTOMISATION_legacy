# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure compute for schedule real-time collaboration and field capture (T3.4).

This module holds the correctness core with zero application imports, so it
unit-tests on the local Python 3.11 runner without the ORM or the database:

  * optimistic-concurrency revision arithmetic - a monotonic per-activity
    revision int decides whether a guarded write applies, is a stale
    lost-update that must be rejected, or is an idempotent no-op;
  * field-submission well-formedness and normalisation - clamp the percent,
    floor the remaining duration, treat a recorded finish as completion, and
    require at least one mutating field;
  * an idempotent-replay predicate mirroring the field sync ledger so a retried
    offline submission is short-circuited instead of being applied twice.

Everything here is deterministic and side-effect free. The service layer
(realtime_service and the field sync service) calls it and owns all I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

# ----- optimistic concurrency -------------------------------------------------


class MergeOutcome(StrEnum):
    """How a guarded write resolves against the server's current revision."""

    APPLY = "apply"  # client base == server head -> write, revision becomes head + 1
    STALE = "stale"  # client base < server head -> reject, return current state
    NOOP = "noop"  # base == head but nothing changed -> idempotent success
    INVALID = "invalid"  # base is wrong-shape, negative, or ahead of the server


@dataclass(frozen=True)
class RevisionCheck:
    """The verdict for one guarded write attempt."""

    outcome: MergeOutcome
    current_revision: int
    next_revision: int
    reason: str = ""

    @property
    def should_write(self) -> bool:
        """Only an APPLY verdict authorises a persisted mutation."""
        return self.outcome is MergeOutcome.APPLY


def check_revision(
    *,
    client_base_revision: int | None,
    server_revision: int,
    has_changes: bool,
) -> RevisionCheck:
    """Decide whether a guarded activity write may proceed.

    ``client_base_revision`` is the revision the client believed it was editing.
    ``None`` is the documented force / first-write escape hatch (the client did
    not track a base, for example a brand-new activity or an admin override): it
    applies at ``server_revision + 1``.

    Invariants:
      * a write applies only when the client base equals the server head, and
        the new revision is strictly ``head + 1`` (the lost-update guard);
      * an equal base with no changes is a NOOP that does NOT bump the revision
        (a double-submitted unchanged form is idempotent, not a conflict);
      * a base below the head is STALE (reject and hand back the current state);
      * a malformed, negative, or ahead-of-server base is INVALID.
    """
    cur = server_revision
    if client_base_revision is None:
        return RevisionCheck(MergeOutcome.APPLY, cur, cur + 1, "forced (no client base)")
    # bool is a subclass of int; reject it so a stray True is never read as 1.
    if isinstance(client_base_revision, bool) or not isinstance(client_base_revision, int):
        return RevisionCheck(MergeOutcome.INVALID, cur, cur, "base is not an integer")
    if client_base_revision < 0:
        return RevisionCheck(MergeOutcome.INVALID, cur, cur, "base is negative")
    if client_base_revision > cur:
        return RevisionCheck(MergeOutcome.INVALID, cur, cur, "base is ahead of the server")
    if client_base_revision < cur:
        return RevisionCheck(MergeOutcome.STALE, cur, cur, "base is behind the server head")
    # client_base_revision == cur
    if has_changes:
        return RevisionCheck(MergeOutcome.APPLY, cur, cur + 1, "")
    return RevisionCheck(MergeOutcome.NOOP, cur, cur, "no changes")


def bump_revision(current: int) -> int:
    """Return the next revision, flooring a stray negative input at zero."""
    return max(current, 0) + 1


# ----- field submission -------------------------------------------------------


@dataclass(frozen=True)
class FieldProgressSubmission:
    """One field-captured progress update against a single schedule activity."""

    activity_id: str
    client_op_id: str
    percent_complete: float | None = None
    remaining_duration: int | None = None
    installed_units: str | None = None  # Decimal-as-string quantity, opaque here
    actual_start_iso: str | None = None
    actual_finish_iso: str | None = None
    captured_at_iso: str | None = None


@dataclass(frozen=True)
class SubmissionValidation:
    """Result of validating and normalising a field submission."""

    ok: bool
    normalized: FieldProgressSubmission | None = None
    errors: tuple[str, ...] = ()


_MUTATING_FIELDS = (
    "percent_complete",
    "remaining_duration",
    "installed_units",
    "actual_start_iso",
    "actual_finish_iso",
)


def _is_iso_date_shape(value: str) -> bool:
    """Light, version-stable ISO check: the first ten chars parse as a date.

    Accepts a bare ``YYYY-MM-DD`` and the date head of a full timestamp
    (``YYYY-MM-DDTHH:MM:SS...``) without relying on full ISO-8601 parsing, which
    differs across Python versions.
    """
    if len(value) < 10:
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def validate_field_submission(sub: FieldProgressSubmission) -> SubmissionValidation:
    """Validate and normalise a field progress submission.

    On success ``normalized`` carries a clamped copy: percent clamped to
    [0, 100], a negative remaining duration floored at 0, and a recorded finish
    coerced to 100 percent complete when the client left percent unset. On
    failure ``errors`` lists every problem and ``normalized`` is ``None``.
    """
    errors: list[str] = []

    if not any(getattr(sub, name) is not None for name in _MUTATING_FIELDS):
        errors.append("submission has no mutating field")

    for name in ("actual_start_iso", "actual_finish_iso", "captured_at_iso"):
        raw = getattr(sub, name)
        if raw is not None and not _is_iso_date_shape(raw):
            errors.append(f"{name} is not an ISO date")

    pct = sub.percent_complete
    # A recorded finish means the activity is complete; an explicit sub-100
    # percent alongside a finish is contradictory and is rejected outright.
    if sub.actual_finish_iso is not None and pct is not None and pct < 100:
        errors.append("actual_finish recorded but percent_complete is below 100")

    if errors:
        return SubmissionValidation(ok=False, normalized=None, errors=tuple(errors))

    norm_pct = pct
    if norm_pct is not None:
        norm_pct = float(min(100.0, max(0.0, norm_pct)))
    elif sub.actual_finish_iso is not None:
        norm_pct = 100.0

    norm_remaining = sub.remaining_duration
    if norm_remaining is not None and norm_remaining < 0:
        norm_remaining = 0

    normalized = FieldProgressSubmission(
        activity_id=sub.activity_id,
        client_op_id=sub.client_op_id,
        percent_complete=norm_pct,
        remaining_duration=norm_remaining,
        installed_units=sub.installed_units,
        actual_start_iso=sub.actual_start_iso,
        actual_finish_iso=sub.actual_finish_iso,
        captured_at_iso=sub.captured_at_iso,
    )
    return SubmissionValidation(ok=True, normalized=normalized, errors=())


# ----- idempotent replay ------------------------------------------------------


def dedupe_decision(
    *,
    seen_result_id: str | None,
    seen_result_type: str | None,
    expected_type: str,
) -> bool:
    """Return True when a ledger hit should short-circuit as a known replay.

    A previously-recorded op with a matching ``result_type`` is an idempotent
    replay (short-circuit and return the prior result). An unseen op, or a hit
    whose recorded type differs from ``expected_type``, is treated as new work.
    """
    if seen_result_id is None:
        return False
    return seen_result_type == expected_type
