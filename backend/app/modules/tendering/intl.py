# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, plain-language helpers for the tendering module.

This file is additive and dependency-free (Python standard library only). It
holds small, pure functions that make tender-level figures clear and safe for
a worldwide audience. Nothing here touches the database, the network or any
global state, so every helper is trivially testable in isolation.

What it covers:
- response rate: how many invited firms actually responded, with a guard so an
  empty invite list yields a well-defined zero instead of a division error;
- package coverage: which packages drew at least N responses and are therefore
  worth comparing, plus an overall coverage figure;
- late-response detection from an ISO 8601 deadline and a submission time, and
  a way to derive a deadline from an issue date plus a response window in days;
- award readiness: whether there are enough compliant responses (and, if the
  caller asks, whether the deadline has passed) to award the package;
- one-line explanations of each tender concept, and plain labels for the
  package / recipient / bid status codes used across the module.

Design rules honoured here (see the project and module instructions):
- No hardcoded currency, unit or locale. Currency codes are never summed
  across; ``sum_by_currency`` keeps each code in its own bucket and
  ``single_currency`` refuses a mixed set rather than inventing a rate.
- Money stays Decimal-exact; rates are computed in Decimal, not float.
- Dates and deadlines are ISO 8601. The response window is always a caller
  supplied number of days, never a constant baked into the code.
- Every division is guarded, so an empty invite list or an empty package set
  yields a clean zero, never a ZeroDivisionError, NaN or infinity.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

# ── Plain-language vocabulary ────────────────────────────────────────────────
# One-line explanations so a non-specialist (a site engineer, a new estimator,
# a subcontractor's office clerk anywhere in the world) understands each term
# without a glossary. Keep every line a single, plain sentence.
_CONCEPTS: dict[str, str] = {
    "bid_package": (
        "A bid package is a bundle of work put out to tender so subcontractors can price it and send back an offer."
    ),
    "invited": ("An invited firm is a subcontractor on the package's distribution list."),
    "responded": ("A firm has responded once it has submitted a bid for the package."),
    "response_rate": (
        "The response rate is how many invited firms sent back a bid, divided by how many firms were invited."
    ),
    "coverage": (
        "Package coverage is how many packages drew at least the required number "
        "of responses, so they can be compared fairly."
    ),
    "tender_deadline": ("The tender deadline is the latest date and time a firm may submit its bid."),
    "late_response": ("A late response is a bid submitted after the tender deadline has passed."),
    "award_readiness": (
        "Award readiness means there are enough compliant bids in hand (and, if "
        "required, the deadline has passed) to pick a winner."
    ),
    "compliant_response": (
        "A compliant response is a submitted bid that meets the tender rules and has not been disqualified."
    ),
}

# Plain labels for the status codes the module already uses. Unknown codes fall
# back to a readable form of the code itself, so a new status never crashes a UI.
_PACKAGE_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft (not yet sent out)",
    "issued": "Issued (sent to firms)",
    "collecting": "Collecting responses",
    "evaluating": "Evaluating responses",
    "awarded": "Awarded to a winner",
    "closed": "Closed",
}

_RECIPIENT_STATUS_LABELS: dict[str, str] = {
    "pending": "Not sent yet",
    "sent": "Invitation sent",
    "failed": "Sending failed",
    "skipped": "Skipped (already sent)",
}

_BID_STATUS_LABELS: dict[str, str] = {
    "pending": "Awaiting the firm's offer",
    "submitted": "Offer received",
    "accepted": "Accepted (winning offer)",
    "rejected": "Rejected",
}


def explain(concept: str) -> str:
    """Return a one-line plain-language explanation of a tender concept.

    Args:
        concept: One of the keys in ``list_concepts()`` (for example
            ``"response_rate"`` or ``"award_readiness"``).

    Returns:
        A single plain sentence describing the concept.

    Raises:
        ValueError: If ``concept`` is not a known concept key.
    """
    key = (concept or "").strip().lower()
    if key not in _CONCEPTS:
        known = ", ".join(sorted(_CONCEPTS))
        raise ValueError(f"Unknown tender concept {concept!r}; known concepts are: {known}")
    return _CONCEPTS[key]


def list_concepts() -> list[str]:
    """Return the sorted list of concept keys that ``explain`` understands."""
    return sorted(_CONCEPTS)


def package_status_label(code: str) -> str:
    """Return a plain-language label for a package status code.

    Unknown codes degrade to a readable form of the code itself (underscores to
    spaces, capitalised) so the function never raises on a future status.
    """
    return _lookup_label(code, _PACKAGE_STATUS_LABELS)


def recipient_status_label(code: str) -> str:
    """Return a plain-language label for a distribution recipient status code."""
    return _lookup_label(code, _RECIPIENT_STATUS_LABELS)


def bid_status_label(code: str) -> str:
    """Return a plain-language label for a bid status code."""
    return _lookup_label(code, _BID_STATUS_LABELS)


def _lookup_label(code: str, table: Mapping[str, str]) -> str:
    """Look a status code up in ``table``, with a safe readable fallback."""
    key = (code or "").strip().lower()
    if key in table:
        return table[key]
    if not key:
        return "Unknown"
    return key.replace("_", " ").replace("-", " ").capitalize()


# ── Response rate ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResponseRate:
    """How many invited firms responded, with the components spelled out.

    Attributes:
        invited: Number of firms invited (on the distribution list).
        responded: Number of invited firms that submitted a bid.
        outstanding: ``invited - responded``; firms still to respond.
        rate: Responded divided by invited, as an exact Decimal fraction
            between 0 and 1. Zero when nobody was invited.
        rate_pct: The same figure as a percent rounded to one decimal place,
            for display only.
        measurable: ``False`` when nobody was invited (the rate is not
            meaningful and is reported as zero), ``True`` otherwise.
        explanation: A plain sentence describing how the figure was derived.
    """

    invited: int
    responded: int
    outstanding: int
    rate: Decimal
    rate_pct: float
    measurable: bool
    explanation: str


def response_rate(invited: int, responded: int) -> ResponseRate:
    """Compute the share of invited firms that responded.

    The figure is ``responded / invited``. Division is guarded: when no firm
    has been invited the rate is a well-defined zero and ``measurable`` is
    ``False`` rather than raising ``ZeroDivisionError``.

    Args:
        invited: Number of firms invited. Must be zero or positive.
        responded: Number that responded. Must be zero or positive and not
            greater than ``invited``.

    Returns:
        A :class:`ResponseRate` with the rate and its components.

    Raises:
        ValueError: If either count is negative or ``responded > invited``.
    """
    if invited < 0:
        raise ValueError("invited count cannot be negative")
    if responded < 0:
        raise ValueError("responded count cannot be negative")
    if responded > invited:
        raise ValueError(f"responded ({responded}) cannot exceed invited ({invited})")

    outstanding = invited - responded
    if invited == 0:
        return ResponseRate(
            invited=0,
            responded=0,
            outstanding=0,
            rate=Decimal("0"),
            rate_pct=0.0,
            measurable=False,
            explanation=("No firms have been invited yet, so a response rate cannot be measured."),
        )

    rate = Decimal(responded) / Decimal(invited)
    rate_pct = round(float(rate) * 100.0, 1)
    return ResponseRate(
        invited=invited,
        responded=responded,
        outstanding=outstanding,
        rate=rate,
        rate_pct=rate_pct,
        measurable=True,
        explanation=(
            f"{responded} of {invited} invited firms responded ({rate_pct}%); {outstanding} still to respond."
        ),
    )


# ── Package coverage ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoverageItem:
    """One package's coverage status against the required response threshold."""

    package_id: str
    name: str
    responded: int
    covered: bool


@dataclass(frozen=True)
class PackageCoverage:
    """Which packages drew enough responses to be compared.

    Attributes:
        min_responses: The threshold N a package must reach to count as covered.
        total_packages: How many packages were considered.
        covered_count: How many reached the threshold.
        uncovered_count: How many fell short.
        coverage_rate: ``covered_count / total_packages`` as an exact Decimal
            fraction between 0 and 1. Zero when there are no packages.
        coverage_pct: The same figure as a percent rounded to one decimal place.
        items: Per-package coverage detail, in the order supplied.
        covered: Names of the covered packages.
        uncovered: Names of the packages still short of the threshold.
        explanation: A plain sentence describing how the figure was derived.
    """

    min_responses: int
    total_packages: int
    covered_count: int
    uncovered_count: int
    coverage_rate: Decimal
    coverage_pct: float
    items: list[CoverageItem] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    explanation: str = ""


def package_coverage(
    packages: Iterable[Mapping[str, object]],
    *,
    min_responses: int = 1,
) -> PackageCoverage:
    """Report which packages have at least ``min_responses`` responses.

    Each input item is a mapping describing one package. Recognised keys:
    ``package_id`` (or ``id``), ``name``, and ``responded`` (or
    ``responded_count`` / ``bid_count``). Missing keys are treated as empty or
    zero so partial data never crashes the computation.

    Args:
        packages: The packages to consider. May be empty.
        min_responses: The threshold N; a package is covered once it has at
            least this many responses. Must be one or greater.

    Returns:
        A :class:`PackageCoverage` summarising covered vs uncovered packages.

    Raises:
        ValueError: If ``min_responses`` is less than one, or a package's
            ``responded`` value is negative or not a whole number.
    """
    if min_responses < 1:
        raise ValueError("min_responses must be at least 1")

    items: list[CoverageItem] = []
    covered_names: list[str] = []
    uncovered_names: list[str] = []

    for idx, raw in enumerate(packages):
        pid = str(raw.get("package_id", raw.get("id", "")) or "")
        name = str(raw.get("name", "") or "") or (pid or f"package {idx + 1}")
        responded = _coerce_count(
            raw.get("responded", raw.get("responded_count", raw.get("bid_count", 0))),
            field_name=f"responded (package {name!r})",
        )
        is_covered = responded >= min_responses
        items.append(CoverageItem(package_id=pid, name=name, responded=responded, covered=is_covered))
        (covered_names if is_covered else uncovered_names).append(name)

    total = len(items)
    covered_count = len(covered_names)
    uncovered_count = total - covered_count

    if total == 0:
        return PackageCoverage(
            min_responses=min_responses,
            total_packages=0,
            covered_count=0,
            uncovered_count=0,
            coverage_rate=Decimal("0"),
            coverage_pct=0.0,
            items=[],
            covered=[],
            uncovered=[],
            explanation="No packages to measure, so coverage is zero.",
        )

    coverage_rate = Decimal(covered_count) / Decimal(total)
    coverage_pct = round(float(coverage_rate) * 100.0, 1)
    return PackageCoverage(
        min_responses=min_responses,
        total_packages=total,
        covered_count=covered_count,
        uncovered_count=uncovered_count,
        coverage_rate=coverage_rate,
        coverage_pct=coverage_pct,
        items=items,
        covered=covered_names,
        uncovered=uncovered_names,
        explanation=(
            f"{covered_count} of {total} packages have at least {min_responses} "
            f"response(s) ({coverage_pct}%); {uncovered_count} still need more."
        ),
    )


def _coerce_count(value: object, *, field_name: str) -> int:
    """Coerce a response count to a non-negative int, raising on bad input."""
    if isinstance(value, bool):
        # bool is an int subclass; treat it as a plain data error, not 0/1.
        raise ValueError(f"{field_name} must be a whole number, got a boolean")
    if value is None:
        return 0
    try:
        count = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a whole number, got {value!r}") from exc
    if count < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return count


# ── Deadlines and late responses ─────────────────────────────────────────────


def deadline_from_window(issued_at: str, response_window_days: int) -> str:
    """Derive an ISO 8601 tender deadline from an issue date plus a window.

    The response window is always supplied by the caller, never assumed. The
    returned deadline is the issue instant advanced by ``response_window_days``
    whole days, emitted as an ISO 8601 string in UTC.

    Args:
        issued_at: When the package was issued, as an ISO 8601 string. A
            date-only value (``YYYY-MM-DD``) is read as the start of that day.
        response_window_days: How many days firms are given to respond. Must be
            one or greater.

    Returns:
        The deadline as an ISO 8601 string (UTC).

    Raises:
        ValueError: If ``response_window_days`` is less than one or
            ``issued_at`` is not a parseable ISO 8601 value.
    """
    if response_window_days < 1:
        raise ValueError("response_window_days must be at least 1")
    issued = _parse_instant(issued_at, field_name="issued_at")
    return (issued + timedelta(days=response_window_days)).isoformat()


def is_late(deadline: str, submitted_at: str) -> bool:
    """Return whether a submission arrived after the tender deadline.

    A date-only deadline (``YYYY-MM-DD``) is treated as the very end of that
    day, so a bid submitted at any time on the deadline day counts as on time.

    Args:
        deadline: The tender deadline as an ISO 8601 string. Required.
        submitted_at: When the bid was submitted, as an ISO 8601 string.
            Required.

    Returns:
        ``True`` if the submission is strictly after the deadline, else
        ``False``.

    Raises:
        ValueError: If either value is empty or not parseable ISO 8601.
    """
    deadline_dt = _parse_deadline(deadline)
    submitted_dt = _parse_instant(submitted_at, field_name="submitted_at")
    return submitted_dt > deadline_dt


def _parse_instant(value: object, *, field_name: str) -> datetime:
    """Parse an ISO 8601 instant into a timezone-aware UTC datetime.

    A naive value (no offset) is read as UTC. A date-only value is read as the
    start of that day in UTC.
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required (ISO 8601 date or datetime)")
    normalised = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO 8601 value: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_deadline(value: object) -> datetime:
    """Parse a deadline, treating a date-only value as the end of that day."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("deadline is required (ISO 8601 date or datetime)")
    instant = _parse_instant(text, field_name="deadline")
    # Date-only strings carry no time part; read them as end of day so a bid
    # sent any time on the deadline day is on time.
    if "t" not in text.lower() and ":" not in text:
        return instant.replace(hour=23, minute=59, second=59, microsecond=999999)
    return instant


# ── Award readiness ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AwardReadiness:
    """Whether there are enough compliant responses to award the package.

    Attributes:
        ready: ``True`` when every readiness condition is met.
        responded: How many firms responded.
        compliant: How many of those responses are compliant (submitted and not
            disqualified).
        min_compliant: The minimum compliant responses required to award.
        shortfall: How many more compliant responses are still needed (zero
            once the minimum is met).
        deadline_passed: ``None`` when no deadline was supplied, otherwise
            whether the deadline has passed as of the check time.
        reasons: Plain sentences explaining why the package is or is not ready.
    """

    ready: bool
    responded: int
    compliant: int
    min_compliant: int
    shortfall: int
    deadline_passed: bool | None
    reasons: list[str] = field(default_factory=list)


def award_readiness(
    *,
    responded: int,
    compliant: int,
    min_compliant: int = 1,
    deadline: str | None = None,
    as_of: str | None = None,
    require_deadline_passed: bool = False,
) -> AwardReadiness:
    """Judge whether a package has enough compliant responses to award.

    The package is ready when the number of compliant responses reaches
    ``min_compliant``. When ``require_deadline_passed`` is ``True`` and a
    ``deadline`` is given, the deadline must also have passed.

    Args:
        responded: How many firms responded. Zero or positive.
        compliant: How many responses are compliant. Zero or positive and not
            greater than ``responded``.
        min_compliant: Minimum compliant responses required. One or greater.
        deadline: Optional tender deadline as an ISO 8601 string. Only used to
            report (and, if requested, enforce) whether it has passed.
        as_of: Optional ISO 8601 instant to check the deadline against;
            defaults to now (UTC).
        require_deadline_passed: When ``True``, the deadline must have passed
            for the package to be ready.

    Returns:
        An :class:`AwardReadiness` describing the decision and its reasons.

    Raises:
        ValueError: If any count is out of range, ``compliant > responded``, or
            a supplied date is not parseable ISO 8601.
    """
    if responded < 0:
        raise ValueError("responded count cannot be negative")
    if compliant < 0:
        raise ValueError("compliant count cannot be negative")
    if compliant > responded:
        raise ValueError(f"compliant ({compliant}) cannot exceed responded ({responded})")
    if min_compliant < 1:
        raise ValueError("min_compliant must be at least 1")

    shortfall = max(0, min_compliant - compliant)
    enough = compliant >= min_compliant

    deadline_passed: bool | None = None
    if deadline is not None and str(deadline).strip():
        now = _parse_instant(as_of, field_name="as_of") if as_of else datetime.now(UTC)
        deadline_passed = now > _parse_deadline(deadline)

    reasons: list[str] = []
    if enough:
        reasons.append(f"{compliant} compliant response(s) meet the required minimum of {min_compliant}.")
    else:
        reasons.append(
            f"Only {compliant} compliant response(s); {shortfall} more needed to reach the minimum of {min_compliant}."
        )

    ready = enough
    if require_deadline_passed:
        if deadline_passed is None:
            ready = False
            reasons.append("A deadline is required before awarding, but none was provided.")
        elif not deadline_passed:
            ready = False
            reasons.append("The tender deadline has not passed yet.")
        else:
            reasons.append("The tender deadline has passed.")
    elif deadline_passed is False:
        reasons.append("Note: the tender deadline has not passed yet; more responses may still arrive.")

    return AwardReadiness(
        ready=ready,
        responded=responded,
        compliant=compliant,
        min_compliant=min_compliant,
        shortfall=shortfall,
        deadline_passed=deadline_passed,
        reasons=reasons,
    )


# ── Currency safety (never sum across currencies) ────────────────────────────


def sum_by_currency(entries: Iterable[tuple[object, str]]) -> dict[str, Decimal]:
    """Total a set of amounts, keeping every currency in its own bucket.

    Amounts are summed exactly in Decimal. Amounts in different currencies are
    never added together; each normalised currency code maps to its own total.
    An empty or missing currency code is bucketed under ``""`` (unknown) so it
    is never silently folded into a real currency.

    Args:
        entries: Pairs of ``(amount, currency_code)``. The amount may be a
            Decimal, int, or a numeric string (parsed exactly, no float).

    Returns:
        A mapping of upper-cased currency code to its Decimal total.

    Raises:
        ValueError: If any amount cannot be parsed as an exact decimal number.
    """
    totals: dict[str, Decimal] = {}
    for amount, currency in entries:
        code = (currency or "").strip().upper()
        try:
            value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"amount {amount!r} is not a valid decimal number") from exc
        if not value.is_finite():
            raise ValueError(f"amount {amount!r} is not a finite number")
        totals[code] = totals.get(code, Decimal("0")) + value
    return totals


def single_currency(codes: Iterable[str]) -> str:
    """Return the one currency shared by ``codes``, or refuse a mixed set.

    Empty and whitespace codes are ignored. This is the guard to call before
    summing a set of bid totals: if they are not all in one currency the sum
    would be meaningless, so this raises instead of inventing a rate.

    Args:
        codes: Currency codes to reconcile.

    Returns:
        The single normalised (upper-cased) currency code shared by all
        non-empty entries.

    Raises:
        ValueError: If no non-empty code is present, or more than one distinct
            currency is found.
    """
    distinct = sorted({(c or "").strip().upper() for c in codes if (c or "").strip()})
    if not distinct:
        raise ValueError("no currency code available to reconcile")
    if len(distinct) > 1:
        joined = ", ".join(distinct)
        raise ValueError(f"cannot reconcile a mixed-currency set: {joined}")
    return distinct[0]
