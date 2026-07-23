# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Minimal cron-expression parser for scheduled reports.

We avoid pulling in ``croniter`` (and its transitive deps) for the
narrow slice of cron that reports use in practice: daily, weekly and
monthly recurrence with an optional specific minute/hour.

Supported fields (5-field POSIX cron):
    minute      0-59    or ``*``
    hour        0-23    or ``*``
    day-of-mo   1-31    or ``*``
    month       1-12    or ``*``  (always ``*`` in practice for reports)
    day-of-wk   0-6     or ``*``  (0 = Sunday)

Each field supports:
    - ``*``         - any value
    - ``N``         - single value (e.g. ``9``)
    - ``N,M,...``   - list of values (e.g. ``1,15``)
    - ``N-M``       - inclusive range (e.g. ``1-5``)
    - ``*/N``       - every N (e.g. ``*/15`` for every 15 minutes)

We explicitly don't support nicknames (``@daily``), alternative day
names (``MON``), step within a range, or overflow correction - users
who need that can file an issue and we upgrade to croniter.

``next_occurrence(expr, after)`` returns the next UTC datetime that
matches ``expr`` and is strictly later than ``after``. Uses a minute-
by-minute walk bounded at 366 days to guarantee termination on
pathological inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class CronParseError(ValueError):
    """Raised when a cron expression cannot be interpreted.

    Callers should catch this and surface a user-friendly error; the UI
    is expected to show the offending expression next to the input box.
    """


def _parse_field(raw: str, *, lo: int, hi: int) -> set[int]:
    """Parse one of five cron fields into the set of matching integers."""
    raw = raw.strip()
    if raw == "*":
        return set(range(lo, hi + 1))

    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronParseError(f"Empty cron sub-expression in '{raw}'")
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError as exc:
                raise CronParseError(f"Bad step value in '{part}'") from exc
            if step <= 0:
                raise CronParseError(f"Step must be positive in '{part}'")
            out.update(range(lo, hi + 1, step))
            continue
        if "-" in part:
            left_raw, right_raw = part.split("-", 1)
            try:
                left = int(left_raw)
                right = int(right_raw)
            except ValueError as exc:
                raise CronParseError(f"Bad range in '{part}'") from exc
            if left > right:
                raise CronParseError(f"Inverted range '{part}'")
            for value in range(left, right + 1):
                if not lo <= value <= hi:
                    raise CronParseError(f"Value {value} out of range [{lo},{hi}]")
                out.add(value)
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise CronParseError(f"Invalid value '{part}'") from exc
        if not lo <= value <= hi:
            raise CronParseError(f"Value {value} out of range [{lo},{hi}]")
        out.add(value)
    return out


def parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse a 5-field cron expression into (minutes, hours, doms, months, dows).

    Raises :class:`CronParseError` on malformed input.
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        raise CronParseError(f"Expected 5 whitespace-separated cron fields, got {len(fields)}")
    minute, hour, dom, month, dow = fields
    return (
        _parse_field(minute, lo=0, hi=59),
        _parse_field(hour, lo=0, hi=23),
        _parse_field(dom, lo=1, hi=31),
        _parse_field(month, lo=1, hi=12),
        _parse_field(dow, lo=0, hi=6),
    )


def _field_is_wildcard(raw: str) -> bool:
    """Return True when a cron field is the unrestricted wildcard ``*``.

    POSIX/Vixie cron treats day-of-month and day-of-week specially: when
    BOTH are restricted (neither is ``*``) a timestamp matches if EITHER
    field matches (logical OR), not both (AND). We need to know whether
    each field was the literal wildcard to make that choice - the parsed
    integer set alone can't tell ``*`` apart from an explicit ``0-6`` /
    ``1-31`` range.
    """
    return raw.strip() == "*"


def next_occurrence(expr: str, after: datetime) -> datetime:
    """Return the first UTC datetime strictly after ``after`` matching ``expr``.

    ``after`` MUST be timezone-aware. The returned datetime is also
    timezone-aware and in UTC. Raises :class:`CronParseError` on bad
    input, ``ValueError`` on naive ``after``.
    """
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")
    after_utc = after.astimezone(UTC)

    minutes, hours, doms, months, dows = parse_cron(expr)

    # POSIX day-of-month / day-of-week OR semantics: when both fields are
    # restricted (neither is ``*``), a date matches if EITHER the day-of-
    # month OR the day-of-week matches. When one (or both) is the
    # wildcard the wildcard field is satisfied trivially and the result
    # is the same as ANDing them. We must inspect the raw fields because
    # the parsed integer set can't distinguish ``*`` from an explicit
    # full-range expression.
    fields = expr.strip().split()
    dom_is_wild = _field_is_wildcard(fields[2])
    dow_is_wild = _field_is_wildcard(fields[4])
    both_day_fields_restricted = not dom_is_wild and not dow_is_wild

    def _day_matches(probe: datetime) -> bool:
        # cron dow: 0 = Sunday; Python weekday() 0 = Monday, so convert.
        dom_match = probe.day in doms
        dow_match = ((probe.weekday() + 1) % 7) in dows
        if both_day_fields_restricted:
            return dom_match or dow_match
        return dom_match and dow_match

    # Start from the next minute boundary so we never return ``after`` itself.
    probe = (after_utc + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # Upper bound: 1 year of minutes - covers any realistic cron expr.
    # Worst case: "0 0 29 2 *" (only Feb 29) lands within ~4 years,
    # so we bump to 5 years for paranoia. Still fast (tens of ms).
    deadline = probe + timedelta(days=5 * 366)

    # Common case: daily / weekly / monthly hit within ~31 days. We
    # advance one minute at a time - trivially correct, negligible cost.
    while probe <= deadline:
        if probe.minute in minutes and probe.hour in hours and probe.month in months and _day_matches(probe):
            return probe
        # Skip ahead by hours / days when coarser fields don't match -
        # keeps the worst-case (year-long search) bounded in ms, not s.
        if probe.hour not in hours:
            probe = (probe + timedelta(hours=1)).replace(minute=0)
            continue
        if probe.month not in months or not _day_matches(probe):
            probe = (probe + timedelta(days=1)).replace(minute=0, hour=0)
            continue
        probe += timedelta(minutes=1)

    raise CronParseError(f"Cron expression '{expr}' has no occurrence within 5 years")
