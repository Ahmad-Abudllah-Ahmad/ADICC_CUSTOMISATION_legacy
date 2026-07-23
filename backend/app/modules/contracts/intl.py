# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, jurisdiction-neutral contract money and date helpers.

This module is deliberately self-contained and stdlib-only (``decimal`` and
``datetime``) so it can be imported and unit-tested without a database, a
FastAPI app, or any config. It carries no hardcoded currency, tax rate, unit
of measure, or locale. Every jurisdiction-specific figure (retention
percentage, retention cap, payment-term days, defects-liability duration,
weekend handling) is a parameter with a documented, override-able default, so
the same functions fit a project anywhere in the world.

Design rules honoured here:
    * Money stays ``Decimal`` end to end; results are quantised to a fixed
      four-decimal minor unit (``MONEY_QUANTUM``) using round-half-up. There
      is never a binary ``float`` in the money path, so no rounding drift.
    * Amounts are never summed across different currency codes. Helpers that
      total money require a single currency and raise ``ValueError`` on a
      mix, rather than silently blending incompatible amounts.
    * Dates are ISO 8601 (``YYYY-MM-DD``) on the way in and out.
    * Bad input (non-numeric money, NaN/inf, a malformed date, a negative
      where only a non-negative makes sense) raises a clean ``ValueError``.
      No helper here can return ``NaN``, ``inf``, or raise a bare 500.
    * Every returned figure exposes its components and a one-line
      ``explanation`` so a quantity surveyor or client can check the maths by
      hand.

The plain-language helpers (:func:`explain_concept`, :func:`describe_status`)
turn contract jargon and status codes into a single clear sentence.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# A number that may arrive as Decimal, int, float, or a decimal string.
Number = Decimal | int | float | str

# ── Constants and documented defaults ─────────────────────────────────────

#: Smallest money step every result is rounded to. Four decimals keeps
#: percentage-derived figures exact enough that a chain of claims reconciles.
MONEY_QUANTUM = Decimal("0.0001")

DEC_ZERO = Decimal("0")
DEC_HUNDRED = Decimal("100")

#: Default retention percentage when a caller does not supply one. Five percent
#: is a common construction default, but it is only a default: pass any value
#: (including zero) to fit the contract at hand.
DEFAULT_RETENTION_PERCENT = Decimal("5")

#: Default net payment term in days from the invoice / certificate date.
DEFAULT_PAYMENT_TERM_DAYS = 30

#: Default defects-liability (maintenance / warranty) period length in months,
#: measured from the completion date.
DEFAULT_DEFECTS_LIABILITY_MONTHS = 12

#: How a computed payment due date that lands on a Saturday or Sunday is
#: handled. The default moves it to the next working day, which matches most
#: banking-day payment clauses; callers may choose otherwise.
WEEKEND_RULES = ("none", "next_business_day", "previous_business_day")
DEFAULT_WEEKEND_RULE = "next_business_day"

#: Default tiered retention-release schedule keyed by contract event. Values
#: are the percentage of the ORIGINAL retention released at each event. Pass a
#: custom schedule to match any jurisdiction or bespoke contract.
DEFAULT_RETENTION_RELEASE_SCHEDULE: dict[str, Decimal] = {
    "substantial_completion": Decimal("50"),
    "punch_list_complete": Decimal("50"),
    "defects_liability_end": Decimal("100"),
}

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


# ── Low-level guards (stdlib only) ─────────────────────────────────────────


def to_decimal(value: Number | None, field: str = "value") -> Decimal:
    """Parse ``value`` into a finite ``Decimal`` or raise ``ValueError``.

    ``None`` and empty string are treated as zero. A non-numeric value, or a
    ``NaN`` / infinity, is rejected with a clear message so callers never see a
    silent ``NaN`` leak into the money path.
    """
    if isinstance(value, Decimal):
        parsed = value
    else:
        if value is None or value == "":
            return DEC_ZERO
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"{field} must be a number, got {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return parsed


def quantize_money(value: Number | None, field: str = "amount") -> Decimal:
    """Round a money value to :data:`MONEY_QUANTUM` using round-half-up."""
    return to_decimal(value, field).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def require_non_negative(value: Number | None, field: str) -> Decimal:
    """Parse a money value and reject anything below zero."""
    parsed = to_decimal(value, field)
    if parsed < DEC_ZERO:
        raise ValueError(f"{field} must not be negative, got {parsed}")
    return parsed


def require_percent(value: Number | None, field: str) -> Decimal:
    """Parse a percentage and confine it to the inclusive range 0 to 100."""
    parsed = to_decimal(value, field)
    if parsed < DEC_ZERO or parsed > DEC_HUNDRED:
        raise ValueError(f"{field} must be between 0 and 100, got {parsed}")
    return parsed


def parse_iso_date(value: str | date, field: str = "date") -> date:
    """Parse an ISO 8601 ``YYYY-MM-DD`` string (or a ``date``) or raise."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO date (YYYY-MM-DD): {value!r}") from exc


# ── Currency safety ────────────────────────────────────────────────────────


def normalize_currency(code: str | None) -> str:
    """Normalise a currency code to a trimmed, upper-case string.

    An empty or missing code normalises to ``""`` (unknown / unset), which the
    platform treats as "the tenant's own currency" elsewhere. This helper does
    not validate against the ISO 4217 list, only cleans formatting.
    """
    return (code or "").strip().upper()


def ensure_single_currency(codes: Any, field: str = "currency") -> str:
    """Return the one currency shared by ``codes`` or raise on a mix.

    Empty / unset codes are ignored. When the remaining distinct codes number
    more than one, a ``ValueError`` is raised so money is never summed across
    currencies. Returns ``""`` when no concrete code is present.
    """
    distinct = {normalize_currency(c) for c in (codes or [])}
    distinct.discard("")
    if len(distinct) > 1:
        raise ValueError(f"cannot mix currencies in {field}: {sorted(distinct)}")
    return next(iter(distinct)) if distinct else ""


def total_in_single_currency(entries: Any) -> dict[str, Any]:
    """Sum ``(amount, currency)`` entries, refusing to blend currencies.

    ``entries`` is an iterable of either ``(amount, currency)`` pairs or dicts
    with ``amount`` and ``currency`` keys. All concrete currency codes must
    agree. Returns ``{"currency", "total", "count"}``; an empty input totals
    zero in an unset currency.
    """
    amounts: list[Decimal] = []
    codes: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            amount = entry.get("amount")
            currency = entry.get("currency")
        else:
            amount, currency = entry
        amounts.append(to_decimal(amount, "amount"))
        codes.append(normalize_currency(currency))
    currency = ensure_single_currency(codes)
    total = quantize_money(sum(amounts, DEC_ZERO))
    return {"currency": currency, "total": total, "count": len(amounts)}


# ── Retention ──────────────────────────────────────────────────────────────


def retention_on_certified(
    certified_amount: Number,
    *,
    retention_percent: Number = DEFAULT_RETENTION_PERCENT,
    retention_cap: Number | None = None,
    retention_already_held: Number = DEC_ZERO,
) -> dict[str, Any]:
    """Retention to hold on a newly certified amount, respecting a cap.

    Retention is a slice of each certified payment the client keeps back as
    security. ``retention_percent`` of ``certified_amount`` is the raw figure.
    When a ``retention_cap`` (the maximum total retention that may ever be
    held, often a share of the contract sum) is supplied, the amount held this
    time is trimmed so the running total never exceeds the cap. Once the cap is
    reached, further certifications hold nothing.

    All inputs are validated: a negative amount, a percent outside 0 to 100, or
    a negative cap raises ``ValueError``.

    Returns the held figure plus every component used to derive it, so the
    maths is checkable:
        ``certified_amount``, ``retention_percent``, ``retention_before_cap``,
        ``retention_held``, ``retention_cap``, ``retention_already_held``,
        ``cumulative_retention_held``, ``cap_reached``, ``explanation``.
    """
    certified = require_non_negative(certified_amount, "certified_amount")
    percent = require_percent(retention_percent, "retention_percent")
    already_held = require_non_negative(retention_already_held, "retention_already_held")
    raw = quantize_money(certified * percent / DEC_HUNDRED)

    cap: Decimal | None = None
    if retention_cap is not None:
        cap = require_non_negative(retention_cap, "retention_cap")

    if cap is None:
        held = raw
        cap_reached = False
    else:
        room = cap - already_held
        if room <= DEC_ZERO:
            held = DEC_ZERO
            cap_reached = True
        elif raw >= room:
            held = quantize_money(room)
            cap_reached = True
        else:
            held = raw
            cap_reached = False

    cumulative = quantize_money(already_held + held)
    if cap is not None and raw > held:
        explanation = (
            f"Retention capped: {percent}% of {certified} would be {raw}, but only {held} fits under the {cap} cap."
        )
    else:
        explanation = f"Held {percent}% of the {certified} certified this period = {held}."
    return {
        "certified_amount": quantize_money(certified),
        "retention_percent": percent,
        "retention_before_cap": raw,
        "retention_held": held,
        "retention_cap": None if cap is None else quantize_money(cap),
        "retention_already_held": quantize_money(already_held),
        "cumulative_retention_held": cumulative,
        "cap_reached": cap_reached,
        "explanation": explanation,
    }


def retention_release_amount(
    total_retention_held: Number,
    event: str,
    *,
    schedule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retention released at a contract event, from a tiered schedule.

    ``schedule`` maps an event name to the percentage of the retention held to
    release at that event; it defaults to
    :data:`DEFAULT_RETENTION_RELEASE_SCHEDULE`. An unknown event releases
    nothing. A non-positive held balance releases nothing. The percentage is
    confined to 0 to 100.

    Returns ``{"event", "percent_released", "amount_released", "remaining",
    "explanation"}``.
    """
    held = require_non_negative(total_retention_held, "total_retention_held")
    plan = schedule or DEFAULT_RETENTION_RELEASE_SCHEDULE
    if held <= DEC_ZERO:
        return {
            "event": event,
            "percent_released": DEC_ZERO,
            "amount_released": DEC_ZERO,
            "remaining": DEC_ZERO,
            "explanation": "No retention is being held, so nothing is released.",
        }
    percent = require_percent(plan.get(event, 0), "release_percent")
    amount = quantize_money(held * percent / DEC_HUNDRED)
    remaining = quantize_money(held - amount)
    if remaining < DEC_ZERO:
        remaining = DEC_ZERO
    return {
        "event": event,
        "percent_released": percent,
        "amount_released": amount,
        "remaining": remaining,
        "explanation": f"At {event}, release {percent}% of the {held} held = {amount}; {remaining} remains.",
    }


# ── Amount payable this period ─────────────────────────────────────────────


def amount_payable_this_period(
    certified_to_date: Number,
    *,
    retention_held_to_date: Number = DEC_ZERO,
    previously_paid: Number = DEC_ZERO,
) -> dict[str, Any]:
    """What is due to be paid now, with every component exposed.

    The payable figure is the certified value to date, less the retention held
    to date, less whatever has already been paid, floored at zero (a period can
    never produce a negative payment; an over-payment is surfaced by
    ``floored`` being true rather than by returning a negative number).

    All three inputs must be non-negative. Returns ``{"certified_to_date",
    "retention_held_to_date", "previously_paid", "net_before_floor",
    "amount_payable", "floored", "explanation"}``.
    """
    certified = require_non_negative(certified_to_date, "certified_to_date")
    retention = require_non_negative(retention_held_to_date, "retention_held_to_date")
    paid = require_non_negative(previously_paid, "previously_paid")
    net = quantize_money(certified - retention - paid)
    floored = net < DEC_ZERO
    payable = DEC_ZERO if floored else net
    explanation = f"Certified {certified} less retention {retention} less already-paid {paid} = {payable}."
    if floored:
        explanation += " Floored at zero: prior payments already exceed the net certified value."
    return {
        "certified_to_date": quantize_money(certified),
        "retention_held_to_date": quantize_money(retention),
        "previously_paid": quantize_money(paid),
        "net_before_floor": net,
        "amount_payable": payable,
        "floored": floored,
        "explanation": explanation,
    }


# ── Payment due date ───────────────────────────────────────────────────────


def _apply_weekend_rule(due: date, rule: str) -> tuple[date, bool]:
    """Shift ``due`` off a weekend per ``rule``; return (date, was_shifted)."""
    if rule == "none":
        return due, False
    step = 1 if rule == "next_business_day" else -1
    shifted = False
    while due.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        due = due + timedelta(days=step)
        shifted = True
    return due, shifted


def payment_due_date(
    invoice_date: str | date,
    *,
    net_days: int = DEFAULT_PAYMENT_TERM_DAYS,
    weekend_rule: str = DEFAULT_WEEKEND_RULE,
) -> dict[str, Any]:
    """Payment due date = invoice date plus ``net_days``, weekend-adjusted.

    ``net_days`` is the payment term (for example net 30). The raw due date is
    the invoice date plus that many calendar days. If it lands on a Saturday or
    Sunday, ``weekend_rule`` decides whether to leave it (``"none"``), move it
    to the next working day (``"next_business_day"``, the default), or the
    previous one (``"previous_business_day"``). Public holidays are not modelled
    here (they vary by country); callers with a holiday calendar can post-adjust.

    ``net_days`` must be a non-negative integer and ``weekend_rule`` must be one
    of :data:`WEEKEND_RULES`, else ``ValueError``.

    Returns ISO date strings plus the derivation: ``{"invoice_date", "net_days",
    "raw_due_date", "due_date", "shifted", "weekend_rule", "due_weekday",
    "explanation"}``.
    """
    start = parse_iso_date(invoice_date, "invoice_date")
    if not isinstance(net_days, int) or isinstance(net_days, bool):
        raise ValueError(f"net_days must be an integer, got {net_days!r}")
    if net_days < 0:
        raise ValueError(f"net_days must not be negative, got {net_days}")
    if weekend_rule not in WEEKEND_RULES:
        raise ValueError(f"weekend_rule must be one of {WEEKEND_RULES}, got {weekend_rule!r}")

    raw_due = start + timedelta(days=net_days)
    due, shifted = _apply_weekend_rule(raw_due, weekend_rule)
    explanation = f"Invoiced {start.isoformat()} plus net {net_days} days is due {due.isoformat()}."
    if shifted:
        explanation += f" Adjusted off the weekend via '{weekend_rule}'."
    return {
        "invoice_date": start.isoformat(),
        "net_days": net_days,
        "raw_due_date": raw_due.isoformat(),
        "due_date": due.isoformat(),
        "shifted": shifted,
        "weekend_rule": weekend_rule,
        "due_weekday": _WEEKDAY_NAMES[due.weekday()],
        "explanation": explanation,
    }


# ── Cumulative certified vs contract sum ───────────────────────────────────


def cumulative_certified_vs_contract_sum(
    certified_amounts: Any,
    contract_sum: Number,
) -> dict[str, Any]:
    """Compare total certified to date against the contract sum.

    ``certified_amounts`` is an iterable of same-currency certified figures
    (currency agreement is the caller's responsibility; keep to one currency).
    An empty iterable totals zero. Division-by-zero is guarded: when the
    contract sum is zero the percentage is reported as zero rather than raising.
    An over-certification (cumulative above the contract sum) is surfaced by
    ``over_certified`` and a negative ``remaining``.

    Returns ``{"cumulative_certified", "contract_sum", "remaining",
    "percent_certified", "over_certified", "count", "explanation"}``.
    """
    values = [require_non_negative(a, "certified_amount") for a in (certified_amounts or [])]
    cumulative = quantize_money(sum(values, DEC_ZERO))
    total = require_non_negative(contract_sum, "contract_sum")
    remaining = quantize_money(total - cumulative)
    if total <= DEC_ZERO:
        percent = DEC_ZERO
    else:
        percent = quantize_money(cumulative / total * DEC_HUNDRED)
    over = cumulative > total
    explanation = f"Certified {cumulative} of the {total} contract sum ({percent}%); {remaining} remaining."
    if over:
        explanation += " Over-certified: the cumulative certified value exceeds the contract sum."
    return {
        "cumulative_certified": cumulative,
        "contract_sum": quantize_money(total),
        "remaining": remaining,
        "percent_certified": percent,
        "over_certified": over,
        "count": len(values),
        "explanation": explanation,
    }


# ── Defects liability period ───────────────────────────────────────────────


def _add_months(start: date, months: int) -> date:
    """Add ``months`` calendar months to ``start``, clamping the day."""
    zero_based = start.month - 1 + months
    year = start.year + zero_based // 12
    month = zero_based % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def defects_liability_end(
    completion_date: str | date,
    *,
    months: int = DEFAULT_DEFECTS_LIABILITY_MONTHS,
    days: int | None = None,
) -> dict[str, Any]:
    """End date of the defects-liability period from a completion date.

    The defects-liability (maintenance / warranty) period runs from completion
    for a fixed span during which the contractor fixes defects at their own
    cost. Give the span either in whole ``months`` (the default, 12) or, when
    ``days`` is supplied, in calendar ``days`` (``days`` takes precedence).
    Month arithmetic clamps the day, so completion on the 31st maps to the last
    day of a shorter target month.

    ``months`` and ``days`` must be non-negative. Returns ``{"start_date",
    "basis", "months", "days", "end_date", "explanation"}``.
    """
    start = parse_iso_date(completion_date, "completion_date")
    if days is not None:
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ValueError(f"days must be a non-negative integer, got {days!r}")
        end = start + timedelta(days=days)
        basis = "days"
        span = days
    else:
        if not isinstance(months, int) or isinstance(months, bool) or months < 0:
            raise ValueError(f"months must be a non-negative integer, got {months!r}")
        end = _add_months(start, months)
        basis = "months"
        span = months
    return {
        "start_date": start.isoformat(),
        "basis": basis,
        "months": None if basis == "days" else span,
        "days": span if basis == "days" else None,
        "end_date": end.isoformat(),
        "explanation": (
            f"Defects liability runs {span} {basis} from completion {start.isoformat()} to {end.isoformat()}."
        ),
    }


# ── Composite: one payment certificate a client can verify ─────────────────


def build_payment_certificate(
    certified_to_date: Number,
    *,
    currency: str = "",
    retention_percent: Number = DEFAULT_RETENTION_PERCENT,
    retention_cap: Number | None = None,
    retention_already_held: Number = DEC_ZERO,
    previously_paid: Number = DEC_ZERO,
    invoice_date: str | date | None = None,
    net_days: int = DEFAULT_PAYMENT_TERM_DAYS,
    weekend_rule: str = DEFAULT_WEEKEND_RULE,
) -> dict[str, Any]:
    """Assemble a checkable interim-payment certificate in one currency.

    Ties the pieces together: retention on the certified value (capped),
    cumulative retention, the amount payable now, and, when an
    ``invoice_date`` is given, the payment due date. Everything stays in the
    single ``currency`` supplied; no cross-currency blending happens. Each
    sub-figure keeps its own ``explanation`` so a QS or client can audit the
    certificate line by line.

    Returns a dict with ``currency``, ``retention`` (the
    :func:`retention_on_certified` block), ``payable`` (the
    :func:`amount_payable_this_period` block), ``payment_due`` (the
    :func:`payment_due_date` block, or ``None``), and a top-level
    ``amount_payable`` for convenience.
    """
    code = normalize_currency(currency)
    retention = retention_on_certified(
        certified_to_date,
        retention_percent=retention_percent,
        retention_cap=retention_cap,
        retention_already_held=retention_already_held,
    )
    payable = amount_payable_this_period(
        certified_to_date,
        retention_held_to_date=retention["cumulative_retention_held"],
        previously_paid=previously_paid,
    )
    payment_due = (
        None if invoice_date is None else payment_due_date(invoice_date, net_days=net_days, weekend_rule=weekend_rule)
    )
    return {
        "currency": code,
        "retention": retention,
        "payable": payable,
        "payment_due": payment_due,
        "amount_payable": payable["amount_payable"],
    }


# ── Plain-language explainers ──────────────────────────────────────────────


#: One-line, jargon-free explanations of the contract concepts this module
#: works with. English is the built-in language; a caller with translations can
#: pass its own text. Kept intentionally short so the UI can show it inline.
CONCEPT_EXPLANATIONS: dict[str, str] = {
    "contract_sum": ("The agreed total price for the whole scope of work, before any change orders."),
    "contract_sum_to_date": ("The contract sum adjusted for the change orders approved so far."),
    "certified_value": ("The value of work the certifier agrees has been properly done up to a given date."),
    "retention": ("A percentage of each payment the client holds back as security until the work is proven complete."),
    "retention_held": "The running total of money currently held back as retention.",
    "retention_cap": ("The most retention that may ever be held, usually a set share of the contract sum."),
    "retention_release": ("Paying back held retention once an agreed point, such as completion, is reached."),
    "certified_amount": "The amount the certifier approves for payment in a period.",
    "amount_payable": ("What is owed this period: the certified value, less retention, less what was already paid."),
    "payment_due_date": ("The date payment must be made, counted as the net term in days after the invoice date."),
    "net_days": "The number of days after the invoice date within which payment is due.",
    "defects_liability_period": (
        "The period after completion in which the contractor must fix defects at their own cost."
    ),
    "liquidated_damages": ("A pre-agreed sum charged per day of late completion, capped at an agreed maximum."),
    "gmp_cap": ("The guaranteed maximum price the client will pay; the contractor carries costs above it."),
    "milestone_payment": "A payment released when a defined stage of the work is reached.",
    "gainshare": "Sharing the saving when the final cost comes in under the target cost.",
}


def explain_concept(concept: str, locale: str | None = None) -> str:
    """Return a one-line plain-language explanation of a contract concept.

    ``locale`` is accepted for forward compatibility; the built-in text is
    English. An unknown concept returns a safe generic sentence rather than
    raising, so a UI can always show something.
    """
    _ = locale  # reserved for future translation lookup
    text = CONCEPT_EXPLANATIONS.get(concept)
    if text is not None:
        return text
    readable = concept.replace("_", " ").strip()
    return f"{readable}: a contract term used in this module." if readable else "Unknown contract term."


#: Plain-language labels for the status codes used across the contracts module,
#: grouped by the entity ("kind") they belong to.
STATUS_LABELS: dict[str, dict[str, str]] = {
    "contract": {
        "draft": "Draft, not yet signed",
        "active": "Active and in force",
        "suspended": "Suspended, work paused",
        "completed": "Completed",
        "terminated": "Terminated before completion",
    },
    "claim": {
        "draft": "Draft, being prepared",
        "submitted": "Submitted, awaiting review",
        "approved": "Approved for certification",
        "certified": "Certified, cleared for payment",
        "paid": "Paid",
        "rejected": "Rejected",
    },
    "final_account": {
        "draft": "Draft, under preparation",
        "agreed": "Agreed by both parties",
        "disputed": "In dispute",
        "closed": "Closed and settled",
    },
    "eot": {
        "draft": "Draft, being prepared",
        "submitted": "Submitted, awaiting review",
        "under_review": "Under review",
        "granted": "Granted in full",
        "partially_granted": "Partially granted",
        "rejected": "Rejected",
        "withdrawn": "Withdrawn",
    },
    "milestone": {
        "pending": "Pending, not yet reached",
        "reached": "Reached",
        "invoiced": "Invoiced",
        "paid": "Paid",
    },
    "security": {
        "required": "Required, not yet provided",
        "received": "Received",
        "active": "Active and valid",
        "expired": "Expired",
        "released": "Released",
        "claimed": "Claimed against",
    },
}


def describe_status(kind: str, code: str, locale: str | None = None) -> str:
    """Return a plain-language label for a status ``code`` of a given ``kind``.

    ``kind`` is one of the keys in :data:`STATUS_LABELS` (for example
    ``"contract"`` or ``"claim"``). An unknown kind or code degrades to a
    title-cased version of the code, so the UI never shows a raw token or
    raises. ``locale`` is reserved for future translation.
    """
    _ = locale  # reserved for future translation lookup
    labels = STATUS_LABELS.get(kind, {})
    label = labels.get(code)
    if label is not None:
        return label
    return (code or "").replace("_", " ").strip().title() or "Unknown"
