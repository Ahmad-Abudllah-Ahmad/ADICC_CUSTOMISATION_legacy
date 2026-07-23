# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure input guards for ESG entries - validation as a first-class step.

These functions enforce the ESG data-quality rules before the service touches
the database:

* ``metric_key`` must be one of the catalogue metrics (a closed vocabulary);
* every ``value`` (and ``target``) must be zero or greater;
* any percentage metric (unit ``%``) must be in the range 0..100.

Each guard raises a plain :class:`ValueError` with a clear, plain-language
message; the service catches it and re-raises an HTTP 400 so the caller sees the
exact reason rather than a 500. Keeping the rules here (pure, importing only the
catalogue) means they can be unit-tested without a database and reused from a
router, a service or a validator.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.modules.esg.catalogue import PERCENT_UNIT, get_metric, is_percent_metric, metric_keys

# Lower bound shared by every metric: a period reading can never be negative.
MIN_VALUE = Decimal("0")
# Upper bound for percentage metrics.
PERCENT_MAX = Decimal("100")


def _as_decimal(field: str, value: object) -> Decimal:
    """Coerce ``value`` to a finite :class:`~decimal.Decimal`.

    Accepts a ``Decimal`` (the usual case - Pydantic hands the service a
    ``Decimal``), an ``int``/``float`` or a numeric string. Rejects anything
    non-numeric, as well as NaN / Infinity, with a clear ``ValueError`` so a
    poisoned value never reaches the database or an arithmetic path.
    """
    if isinstance(value, Decimal):
        candidate = value
    else:
        try:
            candidate = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a number, got {value!r}.") from exc
    if not candidate.is_finite():
        raise ValueError(f"{field} must be a finite number, got {value!r}.")
    return candidate


def validate_metric_key(metric_key: str) -> str:
    """Return the trimmed key if it is in the catalogue, else raise ``ValueError``.

    The error lists the allowed keys so the caller can correct the request
    without guessing.
    """
    key = (metric_key or "").strip()
    if not key:
        raise ValueError("metric_key is required.")
    if get_metric(key) is None:
        allowed = ", ".join(metric_keys())
        raise ValueError(f"Unknown metric_key '{metric_key}'. Allowed metrics: {allowed}")
    return key


def validate_reading(metric_key: str, field: str, value: object) -> Decimal:
    """Validate a single numeric reading (a value or a target) for ``metric_key``.

    Enforces ``>= 0`` for every metric and ``0..100`` for percentage metrics.
    Returns the coerced ``Decimal`` so the caller can persist a normalised value.
    Assumes ``metric_key`` is already known (call :func:`validate_metric_key`
    first); an unknown key simply skips the percentage bound.
    """
    number = _as_decimal(field, value)
    if number < MIN_VALUE:
        raise ValueError(f"{field} for '{metric_key}' must be zero or greater, got {number}.")
    if is_percent_metric(metric_key) and number > PERCENT_MAX:
        raise ValueError(
            f"{field} for percentage metric '{metric_key}' must be between 0 and "
            f"{PERCENT_MAX} ({PERCENT_UNIT}), got {number}.",
        )
    return number


def validate_entry(metric_key: str, value: object, target: object | None = None) -> str:
    """Validate a whole ESG entry: key in catalogue, value and target in range.

    Args:
        metric_key: The metric being recorded.
        value: The period reading (required).
        target: Optional target for the metric; range-checked when present.

    Returns:
        The validated, trimmed ``metric_key``.

    Raises:
        ValueError: If the key is unknown or a reading is out of range.
    """
    key = validate_metric_key(metric_key)
    validate_reading(key, "value", value)
    if target is not None:
        validate_reading(key, "target", target)
    return key
