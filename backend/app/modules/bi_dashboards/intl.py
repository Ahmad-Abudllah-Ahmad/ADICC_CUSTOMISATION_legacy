# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""International, Decimal-exact aggregation helpers for BI dashboards.

Every function here is a PURE helper: no database, no I/O, no global
state. They exist so a KPI, a dashboard widget or a report can turn a
raw numeric series into a clear, localizable figure that behaves the
same for a site engineer in Berlin, Sao Paulo or Shanghai.

Design rules (mirrors the platform principles):

    * International by default. Nothing here hardcodes a currency, a unit
      or a locale. Money stays Decimal-exact and is NEVER blended across
      currency codes - amounts in different currencies are grouped, never
      summed into one meaningless scalar.
    * Percentages are ratios. A period-over-period change of "plus ten
      percent" is carried as the fraction ``Decimal("0.1")``; the percent
      sign is only ever added for human-facing text.
    * Edge cases are explicit. Division by zero, empty series, non-finite
      inputs (NaN / Infinity) and invalid negatives raise a clean
      ``ValueError`` (or a well-defined value such as ``0`` for a sum),
      never a 500, a NaN or an Infinity leaking into a response.
    * Explainable. Each aggregate documents how it is derived and there
      are one-line, localized explainers for a KPI, an aggregate and a
      period-over-period delta, with an English fallback for any locale.

Labels are provided in English, German and Russian (the platform's three
canonical message locales) and fall back to English for any other locale
so the helpers never return a raw key.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

__all__ = [
    "AGGREGATION_METHODS",
    "CurrencyMismatchError",
    "PeriodDelta",
    "aggregate_series",
    "aggregation_label",
    "explain_aggregate",
    "explain_delta",
    "explain_kpi",
    "format_ratio_as_percent",
    "group_aggregate",
    "group_money_by_currency",
    "period_over_period_delta",
    "series_average",
    "series_count",
    "series_max",
    "series_min",
    "series_sum",
    "sum_single_currency",
    "unit_label",
]

# Supported aggregation methods over a numeric series. ``last`` / ``first``
# are label-only (they are positional selections a caller resolves, not a
# reduction this module computes) but carry localized labels + explainers so
# a widget configured with them still reads clearly.
AGGREGATION_METHODS: tuple[str, ...] = ("sum", "average", "min", "max", "count", "last", "first")

_ENGLISH = "en"


class CurrencyMismatchError(ValueError):
    """Raised when amounts in different currencies would be blended.

    A subclass of :class:`ValueError` so callers that only guard against
    ``ValueError`` still catch it, while callers that care specifically
    about mixed currencies can catch this narrower type.
    """


# ── Numeric coercion ───────────────────────────────────────────────────


def _to_finite_decimal(value: Any) -> Decimal:
    """Coerce ``value`` to a finite :class:`~decimal.Decimal`.

    Accepts ``Decimal``, ``int``, ``float`` and numeric strings. Booleans,
    ``None``, non-numeric text and non-finite floats (``NaN`` / ``inf``)
    raise :class:`ValueError` so a bad input never becomes a silent zero or
    an ``inf`` / ``NaN`` that would poison an aggregate.

    Args:
        value: The raw value to coerce.

    Returns:
        A finite ``Decimal``.

    Raises:
        ValueError: If ``value`` is not a finite number.
    """
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a numeric value: {value!r}")
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"not a finite number: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"value must be finite, got {value!r}")
    return dec


def _decimal_series(values: Iterable[Any]) -> list[Decimal]:
    """Coerce every element of ``values`` to a finite ``Decimal``."""
    return [_to_finite_decimal(v) for v in values]


# ── Series aggregation ─────────────────────────────────────────────────


def series_sum(values: Iterable[Any]) -> Decimal:
    """Return the exact sum of a numeric series.

    An empty series sums to ``Decimal("0")`` - a total of nothing is a
    well-defined zero, so this never raises on empty input.
    """
    total = Decimal("0")
    for dec in _decimal_series(values):
        total += dec
    return total


def series_count(values: Iterable[Any]) -> int:
    """Return the number of elements in the series (``0`` for empty)."""
    return len(list(values))


def series_average(values: Iterable[Any]) -> Decimal:
    """Return the exact arithmetic mean of a numeric series.

    The mean is ``sum / count``; the ``count`` guard makes the division by
    zero impossible - an empty series has no mean, so this raises
    ``ValueError`` rather than inventing a value or dividing by zero.

    Raises:
        ValueError: If the series is empty.
    """
    decimals = _decimal_series(values)
    if not decimals:
        raise ValueError("cannot average an empty series")
    return sum(decimals, Decimal("0")) / Decimal(len(decimals))


def series_min(values: Iterable[Any]) -> Decimal:
    """Return the smallest value in the series.

    Raises:
        ValueError: If the series is empty (an empty set has no minimum).
    """
    decimals = _decimal_series(values)
    if not decimals:
        raise ValueError("cannot take the minimum of an empty series")
    return min(decimals)


def series_max(values: Iterable[Any]) -> Decimal:
    """Return the largest value in the series.

    Raises:
        ValueError: If the series is empty (an empty set has no maximum).
    """
    decimals = _decimal_series(values)
    if not decimals:
        raise ValueError("cannot take the maximum of an empty series")
    return max(decimals)


def aggregate_series(values: Iterable[Any], method: str) -> Decimal:
    """Aggregate a numeric series by ``method`` and return a ``Decimal``.

    Dispatches to the matching ``series_*`` helper. ``count`` is returned as
    a ``Decimal`` so every method has one return type. ``sum`` and ``count``
    are defined on the empty series (both ``0``); ``average`` / ``min`` /
    ``max`` raise ``ValueError`` on the empty series.

    Args:
        values: The numeric series.
        method: One of ``sum``, ``average``, ``min``, ``max``, ``count``.

    Returns:
        The aggregated value as ``Decimal``.

    Raises:
        ValueError: For an unknown method, a non-finite input, or an empty
            series under ``average`` / ``min`` / ``max``.
    """
    normalized = (method or "").strip().lower()
    if normalized == "sum":
        return series_sum(values)
    if normalized == "count":
        return Decimal(series_count(values))
    if normalized == "average":
        return series_average(values)
    if normalized in ("min", "minimum"):
        return series_min(values)
    if normalized in ("max", "maximum"):
        return series_max(values)
    raise ValueError(f"unknown aggregation method: {method!r}")


def group_aggregate(
    rows: Iterable[Mapping[str, Any]],
    *,
    key: str,
    value: str,
    method: str = "sum",
) -> dict[str, Decimal]:
    """Group rows by a key field and aggregate a numeric field per group.

    A row whose ``key`` is missing or empty is bucketed under an explicit
    ``"UNKNOWN"`` group so its value is never silently dropped. A row whose
    ``value`` field is missing counts as ``0`` for ``sum`` / ``average`` and
    is still counted for ``count`` (the row exists).

    Args:
        rows: An iterable of mapping rows.
        key: The field name to group by.
        value: The numeric field name to aggregate.
        method: The per-group aggregation (see :func:`aggregate_series`).

    Returns:
        A ``{group_key: Decimal}`` map. Empty input yields an empty map.

    Raises:
        ValueError: For an unknown method or a non-finite value in any row.
    """
    buckets: dict[str, list[Any]] = {}
    for row in rows:
        raw_key = row.get(key)
        group = str(raw_key).strip() if raw_key not in (None, "") else "UNKNOWN"
        buckets.setdefault(group, []).append(row.get(value, 0))
    return {group: aggregate_series(series, method) for group, series in buckets.items()}


# ── Money (currency-safe) ──────────────────────────────────────────────


def group_money_by_currency(entries: Iterable[tuple[Any, Any]]) -> dict[str, Decimal]:
    """Group money amounts by ISO currency code, summing within each code.

    Amounts are NEVER blended across currencies: each ``(amount, code)`` is
    added only to its own code's bucket, so a mixed-currency portfolio comes
    back as ``{"EUR": ..., "USD": ...}`` and the caller can present each
    subtotal instead of a meaningless cross-currency sum. An entry with a
    missing / empty code is bucketed under ``"UNKNOWN"`` rather than dropped.

    Args:
        entries: Iterable of ``(amount, currency_code)`` pairs.

    Returns:
        A ``{CODE: Decimal}`` map with each currency's exact subtotal.

    Raises:
        ValueError: If any amount is not a finite number.
    """
    buckets: dict[str, Decimal] = {}
    for amount, code in entries:
        dec = _to_finite_decimal(amount)
        norm = str(code).strip().upper() if code not in (None, "") else "UNKNOWN"
        buckets[norm] = buckets.get(norm, Decimal("0")) + dec
    return buckets


def sum_single_currency(entries: Iterable[tuple[Any, Any]]) -> tuple[Decimal, str]:
    """Sum money that must all share one currency, exactly.

    Use this where a single scalar total is genuinely wanted (for example
    within one project's own base currency). If more than one distinct
    non-empty currency code appears, a :class:`CurrencyMismatchError` is
    raised rather than blending them.

    Args:
        entries: Iterable of ``(amount, currency_code)`` pairs.

    Returns:
        A ``(total, currency_code)`` pair. The code is ``""`` when no entry
        carried one; the total of an empty input is ``Decimal("0")``.

    Raises:
        ValueError: If any amount is not a finite number.
        CurrencyMismatchError: If two or more currencies are present.
    """
    total = Decimal("0")
    codes: set[str] = set()
    for amount, code in entries:
        total += _to_finite_decimal(amount)
        norm = str(code).strip().upper() if code not in (None, "") else ""
        if norm:
            codes.add(norm)
    if len(codes) > 1:
        raise CurrencyMismatchError(f"refusing to blend currencies: {sorted(codes)}")
    return total, next(iter(codes)) if codes else ""


# ── Period-over-period delta ───────────────────────────────────────────


@dataclass(frozen=True)
class PeriodDelta:
    """A period-over-period change, currency- and unit-neutral.

    Attributes:
        current: The current period value.
        prior: The prior period value.
        absolute: ``current - prior`` (always defined).
        ratio: The fractional change ``(current - prior) / prior`` as a
            ratio (``0.1`` means plus ten percent), or ``None`` when the
            prior value is zero and the ratio is therefore undefined.
        direction: ``"up"``, ``"down"`` or ``"flat"`` from the sign of
            ``absolute`` (always defined, even when ``ratio`` is ``None``).
        prior_zero: ``True`` when the prior value was zero, so the change
            cannot be expressed as a percentage.
    """

    current: Decimal
    prior: Decimal
    absolute: Decimal
    ratio: Decimal | None
    direction: str
    prior_zero: bool


def period_over_period_delta(current: Any, prior: Any) -> PeriodDelta:
    """Compute a period-over-period delta with a zero-prior guard.

    The percentage change is a ratio, ``(current - prior) / prior``. When
    ``prior`` is zero that ratio is undefined (division by zero), so
    ``ratio`` is returned as ``None`` and ``prior_zero`` as ``True`` instead
    of raising or producing an Infinity. The absolute change and the
    direction stay well-defined in every case.

    Args:
        current: The current period value (coerced to Decimal).
        prior: The prior period value (coerced to Decimal).

    Returns:
        A :class:`PeriodDelta`.

    Raises:
        ValueError: If either input is not a finite number.
    """
    cur = _to_finite_decimal(current)
    pri = _to_finite_decimal(prior)
    absolute = cur - pri
    if absolute > 0:
        direction = "up"
    elif absolute < 0:
        direction = "down"
    else:
        direction = "flat"
    if pri == 0:
        return PeriodDelta(
            current=cur,
            prior=pri,
            absolute=absolute,
            ratio=None,
            direction=direction,
            prior_zero=True,
        )
    return PeriodDelta(
        current=cur,
        prior=pri,
        absolute=absolute,
        ratio=absolute / pri,
        direction=direction,
        prior_zero=False,
    )


def format_ratio_as_percent(ratio: Any, places: int = 1) -> str:
    """Render a ratio as a human percent string, e.g. ``0.125`` -> ``12.5%``.

    Keeps the value exact via ``Decimal`` and rounds only for display. This
    is the one place a percent sign is added: everywhere else a percentage
    is carried as a ratio.

    Args:
        ratio: The fractional change (``0.1`` is ten percent).
        places: Decimal places to show (``>= 0``).

    Returns:
        A percent string with a sign for positive values (``"+12.5%"``).

    Raises:
        ValueError: If ``ratio`` is not finite or ``places`` is negative.
    """
    if places < 0:
        raise ValueError("places must be >= 0")
    dec = _to_finite_decimal(ratio) * Decimal("100")
    quantum = Decimal(1) if places == 0 else Decimal(1).scaleb(-places)
    shown = dec.quantize(quantum)
    sign = "+" if shown > 0 else ""
    return f"{sign}{shown}%"


# ── Localized labels ───────────────────────────────────────────────────

_AGG_LABELS: dict[str, dict[str, str]] = {
    "sum": {"en": "Total", "de": "Summe", "ru": "Сумма"},
    "average": {"en": "Average", "de": "Durchschnitt", "ru": "Среднее"},
    "min": {"en": "Minimum", "de": "Minimum", "ru": "Минимум"},
    "max": {"en": "Maximum", "de": "Maximum", "ru": "Максимум"},
    "count": {"en": "Count", "de": "Anzahl", "ru": "Количество"},
    "last": {"en": "Latest", "de": "Letzter", "ru": "Последнее"},
    "first": {"en": "First", "de": "Erster", "ru": "Первое"},
}

_UNIT_LABELS: dict[str, dict[str, str]] = {
    "ratio": {"en": "ratio", "de": "Verhaeltnis", "ru": "коэффициент"},
    "percent": {"en": "percent", "de": "Prozent", "ru": "процент"},
    "currency": {"en": "currency", "de": "Waehrung", "ru": "валюта"},
    "days": {"en": "days", "de": "Tage", "ru": "дней"},
    "count": {"en": "count", "de": "Anzahl", "ru": "количество"},
}

_DIRECTION_LABELS: dict[str, dict[str, str]] = {
    "up": {"en": "up", "de": "hoch", "ru": "рост"},
    "down": {"en": "down", "de": "runter", "ru": "падение"},
    "flat": {"en": "unchanged", "de": "unveraendert", "ru": "без изменений"},
}

_AGG_EXPLAIN: dict[str, dict[str, str]] = {
    "sum": {
        "en": "Adds every value in the series into one total.",
        "de": "Addiert jeden Wert der Reihe zu einer Summe.",
        "ru": "Складывает все значения ряда в одну сумму.",
    },
    "average": {
        "en": "Divides the total of the series by the number of values.",
        "de": "Teilt die Summe der Reihe durch die Anzahl der Werte.",
        "ru": "Делит сумму ряда на количество значений.",
    },
    "min": {
        "en": "The smallest value in the series.",
        "de": "Der kleinste Wert der Reihe.",
        "ru": "Наименьшее значение ряда.",
    },
    "max": {
        "en": "The largest value in the series.",
        "de": "Der groesste Wert der Reihe.",
        "ru": "Наибольшее значение ряда.",
    },
    "count": {
        "en": "The number of values in the series.",
        "de": "Die Anzahl der Werte in der Reihe.",
        "ru": "Количество значений в ряду.",
    },
    "last": {
        "en": "The most recent value in the series.",
        "de": "Der neueste Wert der Reihe.",
        "ru": "Самое последнее значение ряда.",
    },
    "first": {
        "en": "The earliest value in the series.",
        "de": "Der frueheste Wert der Reihe.",
        "ru": "Самое раннее значение ряда.",
    },
}

# One-line delta phrasings. ``{pct}`` is the formatted percent, ``{dir}`` the
# localized direction word. The ``prior_zero`` variant is used when there is
# no prior value to divide by.
_DELTA_PHRASES: dict[str, dict[str, str]] = {
    "change": {
        "en": "{dir} {pct} versus the prior period.",
        "de": "{dir} {pct} gegenueber der Vorperiode.",
        "ru": "{dir} {pct} по сравнению с прошлым периодом.",
    },
    "flat": {
        "en": "Unchanged versus the prior period.",
        "de": "Unveraendert gegenueber der Vorperiode.",
        "ru": "Без изменений по сравнению с прошлым периодом.",
    },
    "prior_zero": {
        "en": "New this period; no prior value to compare as a percentage.",
        "de": "Neu in dieser Periode; kein Vorwert fuer einen Prozentvergleich.",
        "ru": "Впервые в этом периоде; нет прошлого значения для сравнения в процентах.",
    },
}

_KPI_EXPLAIN_TEMPLATE: dict[str, str] = {
    "en": "{name}, measured in {unit}.",
    "de": "{name}, gemessen in {unit}.",
    "ru": "{name}, измеряется в {unit}.",
}


def _localize(table: dict[str, dict[str, str]], key: str, lang: str) -> str:
    """Look up ``key`` in ``table`` for ``lang`` with an English fallback.

    Returns the key itself if it is unknown, so a caller always gets a
    printable string rather than a crash on an unmapped code.
    """
    entry = table.get((key or "").strip().lower())
    if entry is None:
        return key
    normalized = (lang or _ENGLISH).strip().lower()
    return entry.get(normalized) or entry.get(_ENGLISH) or key


def aggregation_label(method: str, lang: str = _ENGLISH) -> str:
    """Return a localized label for an aggregation method (English fallback)."""
    return _localize(_AGG_LABELS, method, lang)


def unit_label(unit: str, lang: str = _ENGLISH) -> str:
    """Return a localized label for a KPI unit (English fallback)."""
    return _localize(_UNIT_LABELS, unit, lang)


# ── One-line explainers ────────────────────────────────────────────────


def explain_kpi(name: str, unit: str, lang: str = _ENGLISH) -> str:
    """Return a one-line, localized explainer for a KPI.

    Args:
        name: The KPI display name (already localized by the caller).
        unit: The KPI unit code (``ratio`` / ``percent`` / ``currency`` /
            ``days`` / ``count``); localized here for the sentence.
        lang: Target locale; falls back to English.

    Returns:
        A single plain-language sentence.
    """
    normalized = (lang or _ENGLISH).strip().lower()
    template = _KPI_EXPLAIN_TEMPLATE.get(normalized) or _KPI_EXPLAIN_TEMPLATE[_ENGLISH]
    return template.format(name=name, unit=unit_label(unit, lang))


def explain_aggregate(method: str, lang: str = _ENGLISH) -> str:
    """Return a one-line, localized explainer of how an aggregate is derived.

    Falls back to a generic English sentence for an unknown method so the
    UI always has something honest to show.
    """
    entry = _AGG_EXPLAIN.get((method or "").strip().lower())
    if entry is None:
        return f"Aggregated using '{method}'."
    normalized = (lang or _ENGLISH).strip().lower()
    return entry.get(normalized) or entry.get(_ENGLISH) or entry["en"]


def explain_delta(delta: PeriodDelta, lang: str = _ENGLISH) -> str:
    """Return a one-line, localized explainer for a period-over-period delta.

    Handles the three real cases plainly: no prior value to compare
    (``prior_zero``), an unchanged value, and an up / down change rendered
    as a percent. Percentages are only ever rendered here, from the ratio.

    Args:
        delta: The :class:`PeriodDelta` to describe.
        lang: Target locale; falls back to English.

    Returns:
        A single plain-language sentence.
    """
    normalized = (lang or _ENGLISH).strip().lower()

    def _phrase(kind: str) -> str:
        entry = _DELTA_PHRASES[kind]
        return entry.get(normalized) or entry[_ENGLISH]

    if delta.prior_zero:
        return _phrase("prior_zero")
    if delta.ratio is None or delta.direction == "flat":
        return _phrase("flat")
    direction_word = _localize(_DIRECTION_LABELS, delta.direction, lang)
    # ``format_ratio_as_percent`` signs positive values; the direction word
    # already carries up / down, so present the magnitude only.
    pct = format_ratio_as_percent(abs(delta.ratio))
    return _phrase("change").format(dir=direction_word, pct=pct)
