# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, plain-language reporting helpers for subcontractors.

Pure, dependency-free helpers (Python standard library plus ``Decimal`` only,
no database, no framework, no I/O) that turn the raw counters and money rows of
the subcontractors module into clear, locale-aware, currency-safe figures.

Design goals:
    - International first. No hardcoded locale or currency. Money is kept
      Decimal-exact and is never blended across currency codes. Dates are
      rendered as ISO 8601 (YYYY-MM-DD).
    - Clarity. Every figure ships with a one-line, plain-language explainer and
      a documented derivation, so a site engineer or estimator understands it in
      under a minute. Status and compliance words localize to en / de / ru with
      an English fallback.
    - Safe edge cases. Division by zero, empty sets and negative counts are
      guarded: helpers return well-defined values or raise a clean ``ValueError``,
      never a 500, a ``NaN`` or an ``inf``. Rates stay inside [0, 1] (fraction)
      and [0, 100] (percent); scores stay inside [0, 100].

The status and compliance vocabularies mirror the real module vocabulary used in
``service.py`` and ``models.py`` (prequalification, payment, agreement, work
package and certificate states), so this file reads the same words the rest of
the module writes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ── Rounding quanta ─────────────────────────────────────────────────────────
# Fractions carry four decimals (0.0001 granularity); percent, money and score
# carry two. All rounding is ROUND_HALF_UP so figures are stable and auditable.
FRACTION_QUANTUM = Decimal("0.0001")
PERCENT_QUANTUM = Decimal("0.01")
MONEY_QUANTUM = Decimal("0.01")
SCORE_QUANTUM = Decimal("0.01")

# Default performance weights. These mirror ``DEFAULT_RATING_WEIGHTS`` in
# ``service.py`` (quality and HSE weighted highest for construction work) so a
# score computed here lines up with the module's stored rating. Weights need not
# sum to one; they are renormalised over the components actually supplied.
DEFAULT_PERFORMANCE_WEIGHTS: dict[str, Decimal] = {
    "quality": Decimal("0.30"),
    "hse": Decimal("0.30"),
    "schedule": Decimal("0.20"),
    "cost": Decimal("0.20"),
}

# Locales this module localizes into. Anything else falls back to English.
SUPPORTED_LOCALES = ("en", "de", "ru")
_FALLBACK_LOCALE = "en"

# Canonical status words drawn from the module state machines. One label per
# canonical word covers the overlaps (draft/submitted/rejected/completed appear
# in more than one state machine but mean the same thing to a reader).
_STATUS_LABELS: dict[str, dict[str, str]] = {
    # Prequalification lifecycle.
    "pending": {"en": "Pending", "de": "Ausstehend", "ru": "Ozhidaet"},
    "draft": {"en": "Draft", "de": "Entwurf", "ru": "Chernovik"},
    "submitted": {"en": "Submitted", "de": "Eingereicht", "ru": "Podano"},
    "under_review": {"en": "Under review", "de": "In Pruefung", "ru": "Na proverke"},
    "approved": {"en": "Approved", "de": "Genehmigt", "ru": "Odobreno"},
    "rejected": {"en": "Rejected", "de": "Abgelehnt", "ru": "Otkloneno"},
    "suspended": {"en": "Suspended", "de": "Gesperrt", "ru": "Priostanovleno"},
    # Payment application lifecycle.
    "foreman_approved": {
        "en": "Foreman approved",
        "de": "Vom Polier freigegeben",
        "ru": "Odobreno prorabom",
    },
    "finance_approved": {
        "en": "Finance approved",
        "de": "Von Finanzen freigegeben",
        "ru": "Odobreno finansami",
    },
    "paid": {"en": "Paid", "de": "Bezahlt", "ru": "Oplacheno"},
    # Agreement lifecycle.
    "active": {"en": "Active", "de": "Aktiv", "ru": "Aktivno"},
    "completed": {"en": "Completed", "de": "Abgeschlossen", "ru": "Zaversheno"},
    "terminated": {"en": "Terminated", "de": "Gekuendigt", "ru": "Prekrascheno"},
    # Work package lifecycle.
    "planned": {"en": "Planned", "de": "Geplant", "ru": "Zaplanirovano"},
    "in_progress": {"en": "In progress", "de": "In Arbeit", "ru": "V rabote"},
}

# Compliance and certificate vocabulary (certificate states plus derived flags).
_COMPLIANCE_LABELS: dict[str, dict[str, str]] = {
    "valid": {"en": "Valid", "de": "Gueltig", "ru": "Deystvitelno"},
    "expired": {"en": "Expired", "de": "Abgelaufen", "ru": "Prosrocheno"},
    "revoked": {"en": "Revoked", "de": "Widerrufen", "ru": "Otozvano"},
    "expiring_soon": {
        "en": "Expiring soon",
        "de": "Laeuft bald ab",
        "ru": "Skoro istekaet",
    },
    "compliant": {"en": "Compliant", "de": "Konform", "ru": "Sootvetstvuet"},
    "non_compliant": {
        "en": "Non compliant",
        "de": "Nicht konform",
        "ru": "Ne sootvetstvuet",
    },
    "blocked": {"en": "Blocked", "de": "Blockiert", "ru": "Zablokirovano"},
    # Certificate types.
    "insurance": {"en": "Insurance", "de": "Versicherung", "ru": "Strahovanie"},
    "license": {"en": "License", "de": "Lizenz", "ru": "Litsenziya"},
    "iso": {"en": "ISO certificate", "de": "ISO-Zertifikat", "ru": "ISO-sertifikat"},
    "safety": {"en": "Safety", "de": "Sicherheit", "ru": "Bezopasnost"},
    "bond": {"en": "Bond", "de": "Buergschaft", "ru": "Garantiya"},
}


def _normalise_locale(locale: str | None) -> str:
    """Return a supported locale code, defaulting to English.

    Args:
        locale: Requested locale (for example ``"de"`` or ``"de-DE"``). Only the
            leading language subtag is considered.

    Returns:
        One of ``SUPPORTED_LOCALES``; ``"en"`` when the request is unknown.
    """
    if not locale:
        return _FALLBACK_LOCALE
    tag = str(locale).strip().lower().replace("_", "-").split("-", 1)[0]
    return tag if tag in SUPPORTED_LOCALES else _FALLBACK_LOCALE


def _localize(term: str, locale: str | None, table: dict[str, dict[str, str]]) -> str:
    """Localize a single canonical term with an English fallback.

    Unknown terms degrade to plain language (underscores become spaces, first
    letter capitalised) so a caller never sees a raw snake_case key.
    """
    resolved = _normalise_locale(locale)
    labels = table.get(term)
    if labels is None:
        plain = term.replace("_", " ").strip()
        return plain[:1].upper() + plain[1:] if plain else term
    return labels.get(resolved) or labels[_FALLBACK_LOCALE]


def localize_status(status_value: str, locale: str | None = None) -> str:
    """Localize a workflow status word (prequal / payment / agreement / work package).

    Args:
        status_value: Canonical status, for example ``"finance_approved"``.
        locale: Target locale; unknown locales fall back to English.

    Returns:
        A human-readable label in the requested language.
    """
    return _localize(status_value, locale, _STATUS_LABELS)


def localize_compliance(term: str, locale: str | None = None) -> str:
    """Localize a compliance or certificate word (valid / expired / insurance / ...).

    Args:
        term: Canonical compliance or certificate word.
        locale: Target locale; unknown locales fall back to English.

    Returns:
        A human-readable label in the requested language.
    """
    return _localize(term, locale, _COMPLIANCE_LABELS)


# ── ISO 8601 dates ──────────────────────────────────────────────────────────


def format_iso_date(value: date | datetime | None) -> str | None:
    """Render a date or datetime as an ISO 8601 calendar date (YYYY-MM-DD).

    Times and time zones are dropped on purpose: subcontractor reporting speaks
    in calendar days, and a bare date reads the same in every country.

    Args:
        value: A ``date``, a ``datetime`` or ``None``.

    Returns:
        The ISO 8601 date string, or ``None`` when the input is ``None``.

    Raises:
        ValueError: If ``value`` is neither a date/datetime nor ``None``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise ValueError(f"not a date: {value!r}")


# ── Numeric coercion ────────────────────────────────────────────────────────


def _to_decimal(value: object, *, label: str) -> Decimal:
    """Coerce a value to ``Decimal`` exactly, raising a clean ValueError.

    Bools are rejected (``True``/``False`` are not amounts). Floats are routed
    through ``str`` so ``0.1`` stays ``0.1`` rather than its binary tail.
    ``NaN`` and infinities are rejected so no figure can carry them downstream.
    """
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number, got bool")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} is not a valid number: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite, got {value!r}")
    return result


def _require_count(value: object, *, label: str) -> int:
    """Coerce a value to a non-negative integer count, else raise ValueError."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer, got bool")
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not a valid integer: {value!r}") from exc
    if count < 0:
        raise ValueError(f"{label} must not be negative, got {count}")
    return count


def _normalise_currency(code: object) -> str:
    """Validate and normalise an ISO 4217 alpha-3 currency code to upper case.

    Raises:
        ValueError: For a missing or non alpha-3 code. A strict gate is what
            keeps amounts in different currencies from ever being blended.
    """
    text = str(code or "").strip().upper()
    if len(text) != 3 or not text.isalpha():
        raise ValueError(f"invalid ISO 4217 currency code: {code!r}")
    return text


# ── Rate results ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateResult:
    """A rate expressed both as a fraction [0, 1] and a percent [0, 100].

    Attributes:
        numerator: Favourable count (on-time deliveries, passed inspections).
        denominator: Total count the rate is measured over.
        fraction: ``numerator / denominator`` in [0, 1], or 0 when undefined.
        percent: The same value in [0, 100].
        defined: ``False`` when ``denominator`` is 0 (no data yet); the fraction
            and percent are then 0 by convention, not a measured zero.
        explanation: One-line, plain-language description of the figure.
    """

    numerator: int
    denominator: int
    fraction: Decimal
    percent: Decimal
    defined: bool
    explanation: str


def _rate(numerator: int, denominator: int, undefined_text: str, defined_text_fmt: str) -> RateResult:
    """Build a ``RateResult`` with zero-guarded fraction and percent."""
    if denominator == 0:
        return RateResult(
            numerator=numerator,
            denominator=0,
            fraction=Decimal("0"),
            percent=Decimal("0"),
            defined=False,
            explanation=undefined_text,
        )
    fraction = (Decimal(numerator) / Decimal(denominator)).quantize(
        FRACTION_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    percent = (fraction * Decimal("100")).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    return RateResult(
        numerator=numerator,
        denominator=denominator,
        fraction=fraction,
        percent=percent,
        defined=True,
        explanation=defined_text_fmt.format(
            numerator=numerator,
            denominator=denominator,
            percent=percent,
        ),
    )


def on_time_delivery_rate(on_time_jobs: object, total_jobs: object, *, locale: str | None = None) -> RateResult:
    """On-time delivery rate: on-time jobs divided by total jobs.

    Formula:
        rate = on_time_jobs / total_jobs, clamped implicitly to [0, 1] because
        ``0 <= on_time_jobs <= total_jobs`` is enforced.

    Edge cases:
        - ``total_jobs == 0`` returns a defined=False result (rate 0), never a
          division by zero.
        - Negative counts, or on-time exceeding total, raise ``ValueError``.

    Args:
        on_time_jobs: Count of jobs delivered on or before the due date.
        total_jobs: Count of jobs with a due date in the period.
        locale: Language for the explainer text.

    Returns:
        A ``RateResult``.
    """
    on_time = _require_count(on_time_jobs, label="on_time_jobs")
    total = _require_count(total_jobs, label="total_jobs")
    if on_time > total:
        raise ValueError(f"on_time_jobs ({on_time}) cannot exceed total_jobs ({total})")
    loc = _normalise_locale(locale)
    undefined = {
        "en": "No deliveries with a due date recorded yet.",
        "de": "Noch keine Lieferungen mit Faelligkeitsdatum erfasst.",
        "ru": "Postavki so srokom sdachi poka ne zafiksirovany.",
    }[loc]
    defined = {
        "en": "{numerator} of {denominator} deliveries were on time ({percent} percent).",
        "de": "{numerator} von {denominator} Lieferungen waren puenktlich ({percent} Prozent).",
        "ru": "{numerator} iz {denominator} postavok vypolneny v srok ({percent} protsentov).",
    }[loc]
    return _rate(on_time, total, undefined, defined)


def quality_pass_rate(
    passed_inspections: object, total_inspections: object, *, locale: str | None = None
) -> RateResult:
    """Quality pass rate: passed inspections divided by total inspections.

    Formula:
        rate = passed_inspections / total_inspections, with
        ``0 <= passed_inspections <= total_inspections`` enforced.

    Edge cases mirror :func:`on_time_delivery_rate`: zero inspections yields a
    defined=False result, and invalid counts raise ``ValueError``.

    Args:
        passed_inspections: Count of inspections / checks that passed.
        total_inspections: Count of inspections / checks carried out.
        locale: Language for the explainer text.

    Returns:
        A ``RateResult``.
    """
    passed = _require_count(passed_inspections, label="passed_inspections")
    total = _require_count(total_inspections, label="total_inspections")
    if passed > total:
        raise ValueError(f"passed_inspections ({passed}) cannot exceed total_inspections ({total})")
    loc = _normalise_locale(locale)
    undefined = {
        "en": "No inspections recorded yet.",
        "de": "Noch keine Pruefungen erfasst.",
        "ru": "Proverki poka ne zafiksirovany.",
    }[loc]
    defined = {
        "en": "{numerator} of {denominator} inspections passed ({percent} percent).",
        "de": "{numerator} von {denominator} Pruefungen bestanden ({percent} Prozent).",
        "ru": "{numerator} iz {denominator} proverok proydeny ({percent} protsentov).",
    }[loc]
    return _rate(passed, total, undefined, defined)


# ── Weighted performance score ──────────────────────────────────────────────


def _clamp_score(value: Decimal) -> Decimal:
    """Clamp a component rate to [0, 100] with two-decimal rounding."""
    if value < 0:
        value = Decimal("0")
    elif value > 100:
        value = Decimal("100")
    return value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ScoreComponent:
    """One weighted input to a performance score.

    Attributes:
        name: Component key (for example ``"quality"``).
        rate: The component rate after clamping to [0, 100].
        weight: The component's normalised weight in [0, 1] (weights sum to 1).
        contribution: ``rate * weight``, the points this component adds.
    """

    name: str
    rate: Decimal
    weight: Decimal
    contribution: Decimal


@dataclass(frozen=True)
class PerformanceScore:
    """A weighted performance score with a fully itemised derivation.

    Attributes:
        score: Overall score in [0, 100].
        components: Per-component rate, weight and contribution.
        explanation: One-line, plain-language summary.
    """

    score: Decimal
    components: tuple[ScoreComponent, ...]
    explanation: str


def weighted_performance_score(
    component_rates: Mapping[str, object],
    weights: Mapping[str, object] | None = None,
    *,
    locale: str | None = None,
) -> PerformanceScore:
    """Combine component rates into one weighted performance score in [0, 100].

    Formula:
        score = sum(clamp(rate_i) * w_i) / sum(w_i), where each ``w_i`` is the
        supplied weight for a component present in ``component_rates``. Weights
        are renormalised over exactly the components supplied, so the score is
        always a proper weighted average on the same [0, 100] scale as its parts.

    The weights are explicit and echoed back per component so the number is fully
    explainable: every point in the total is traceable to a component.

    Edge cases:
        - Empty ``component_rates`` raises ``ValueError`` (nothing to score).
        - A component with no matching weight, or a non-positive total weight,
          raises ``ValueError``.
        - Rates outside [0, 100] are clamped, never rejected.

    Args:
        component_rates: Map of component name to its rate on a [0, 100] scale.
        weights: Map of component name to a non-negative weight. Defaults to
            :data:`DEFAULT_PERFORMANCE_WEIGHTS`. Need not sum to one.
        locale: Language for the explainer text.

    Returns:
        A ``PerformanceScore``.
    """
    if not component_rates:
        raise ValueError("component_rates must not be empty")
    weight_source = weights if weights is not None else DEFAULT_PERFORMANCE_WEIGHTS

    resolved: list[tuple[str, Decimal, Decimal]] = []
    total_weight = Decimal("0")
    for name in component_rates:
        if name not in weight_source:
            raise ValueError(f"no weight supplied for component {name!r}")
        weight = _to_decimal(weight_source[name], label=f"weight[{name}]")
        if weight < 0:
            raise ValueError(f"weight[{name}] must not be negative, got {weight}")
        rate = _clamp_score(_to_decimal(component_rates[name], label=f"rate[{name}]"))
        resolved.append((name, rate, weight))
        total_weight += weight

    if total_weight <= 0:
        raise ValueError("sum of weights must be positive")

    components: list[ScoreComponent] = []
    score = Decimal("0")
    for name, rate, weight in resolved:
        normalised = (weight / total_weight).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        contribution = (rate * weight / total_weight).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
        score += rate * weight / total_weight
        components.append(
            ScoreComponent(name=name, rate=rate, weight=normalised, contribution=contribution),
        )

    final = _clamp_score(score)
    loc = _normalise_locale(locale)
    parts = ", ".join(f"{c.name} {c.rate}x{c.weight}" for c in components)
    explanation = {
        "en": f"Weighted score {final} of 100 from: {parts}.",
        "de": f"Gewichtete Bewertung {final} von 100 aus: {parts}.",
        "ru": f"Vzveshennaya otsenka {final} iz 100 iz: {parts}.",
    }[loc]
    return PerformanceScore(score=final, components=tuple(components), explanation=explanation)


# ── Spend grouped strictly per currency ─────────────────────────────────────


def _extract_amount_currency(entry: object) -> tuple[object, object]:
    """Pull an (amount, currency) pair from a tuple, mapping or object."""
    if isinstance(entry, Mapping):
        if "amount" not in entry or "currency" not in entry:
            raise ValueError("spend entry mapping needs 'amount' and 'currency' keys")
        return entry["amount"], entry["currency"]
    if isinstance(entry, (tuple, list)):
        if len(entry) != 2:
            raise ValueError("spend entry sequence must be (amount, currency)")
        return entry[0], entry[1]
    if hasattr(entry, "amount") and hasattr(entry, "currency"):
        return entry.amount, entry.currency  # type: ignore[attr-defined]
    raise ValueError(f"cannot read amount/currency from spend entry: {entry!r}")


@dataclass(frozen=True)
class SpendBreakdown:
    """Total spend grouped strictly per currency, never blended.

    Attributes:
        by_currency: Map of ISO 4217 code to an exact ``Decimal`` total. Each
            currency is summed independently; totals in different currencies are
            never added together, because that would be meaningless.
        explanation: One-line, plain-language summary.
    """

    by_currency: dict[str, Decimal]
    explanation: str


def spend_by_currency(entries: Iterable[object], *, locale: str | None = None) -> SpendBreakdown:
    """Sum spend per currency, keeping every currency code separate.

    Each entry may be an ``(amount, currency)`` pair, a mapping with ``amount``
    and ``currency`` keys, or any object exposing ``amount`` and ``currency``
    attributes (for example a payment application row).

    Amounts are summed with ``Decimal`` for exactness and rounded to two
    decimals per currency at the end. An empty input returns an empty breakdown
    rather than raising, so a subcontractor with no payments reports cleanly.

    Edge cases:
        - A missing or non alpha-3 currency code raises ``ValueError`` (this is
          the guard that prevents blending currencies).
        - A non-numeric or non-finite amount raises ``ValueError``.

    Args:
        entries: Iterable of spend entries.
        locale: Language for the explainer text.

    Returns:
        A ``SpendBreakdown``.
    """
    totals: dict[str, Decimal] = {}
    for entry in entries:
        raw_amount, raw_currency = _extract_amount_currency(entry)
        currency = _normalise_currency(raw_currency)
        amount = _to_decimal(raw_amount, label="amount")
        totals[currency] = totals.get(currency, Decimal("0")) + amount

    by_currency = {code: totals[code].quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) for code in sorted(totals)}

    loc = _normalise_locale(locale)
    if not by_currency:
        explanation = {
            "en": "No spend recorded yet.",
            "de": "Noch keine Ausgaben erfasst.",
            "ru": "Rashody poka ne zafiksirovany.",
        }[loc]
    else:
        rendered = ", ".join(f"{amount} {code}" for code, amount in by_currency.items())
        explanation = {
            "en": f"Spend by currency: {rendered}.",
            "de": f"Ausgaben nach Waehrung: {rendered}.",
            "ru": f"Rashody po valyute: {rendered}.",
        }[loc]
    return SpendBreakdown(by_currency=by_currency, explanation=explanation)


# ── Counts by status ────────────────────────────────────────────────────────


def counts_by_status(
    items: Iterable[object],
    *,
    attribute: str = "status",
    locale: str | None = None,
) -> dict[str, int]:
    """Count items grouped by their status value.

    Works over mappings (``item[attribute]``) and objects (``item.attribute``).
    Missing or empty status values are grouped under the ``"unknown"`` key so no
    item is silently dropped. The returned counts are always non-negative and the
    dictionary is ordered by descending count then status name for stable output.

    Args:
        items: Iterable of rows carrying a status.
        attribute: Name of the status field to group on. Defaults to ``"status"``.
        locale: Reserved for symmetry; counting is language independent. The
            status keys stay canonical so callers can localize with
            :func:`localize_status` at render time.

    Returns:
        Map of canonical status value to count.
    """
    tally: dict[str, int] = {}
    for item in items:
        if isinstance(item, Mapping):
            raw = item.get(attribute)
        else:
            raw = getattr(item, attribute, None)
        key = str(raw).strip() if raw not in (None, "") else "unknown"
        tally[key] = tally.get(key, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])))


# ── Composed, plain-language summary ────────────────────────────────────────


@dataclass(frozen=True)
class PerformanceSummary:
    """A clear, composed view of a subcontractor's headline figures.

    Attributes:
        on_time_delivery: On-time delivery rate result.
        quality_pass: Quality pass rate result.
        performance_score: Weighted score built from the two rates above.
        spend: Spend grouped per currency.
        status_counts: Counts of related records by status.
        narrative: A short, plain-language paragraph tying the figures together.
    """

    on_time_delivery: RateResult
    quality_pass: RateResult
    performance_score: PerformanceScore
    spend: SpendBreakdown
    status_counts: dict[str, int] = field(default_factory=dict)
    narrative: str = ""


def performance_summary(
    *,
    on_time_jobs: object,
    total_jobs: object,
    passed_inspections: object,
    total_inspections: object,
    spend_entries: Iterable[object] = (),
    status_items: Iterable[object] = (),
    status_attribute: str = "status",
    weights: Mapping[str, object] | None = None,
    locale: str | None = None,
) -> PerformanceSummary:
    """Compose the headline subcontractor figures into one explainable view.

    The performance score is a two-component weighted average of the on-time
    delivery rate and the quality pass rate (both re-expressed on the [0, 100]
    scale), using the ``quality`` and ``schedule`` slices of the default weights
    unless overridden. Undefined rates (no data) count as 0 in the score, which
    is stated plainly in the narrative so the reader is not misled.

    Args:
        on_time_jobs: On-time delivery count.
        total_jobs: Total jobs with a due date.
        passed_inspections: Passed inspection count.
        total_inspections: Total inspection count.
        spend_entries: Iterable of spend entries for :func:`spend_by_currency`.
        status_items: Iterable of rows for :func:`counts_by_status`.
        status_attribute: Status field name for the count.
        weights: Optional override for the two-component score weights. Keys used
            are ``"schedule"`` (delivery) and ``"quality"`` (inspections).
        locale: Language for all explainer text.

    Returns:
        A ``PerformanceSummary``.
    """
    loc = _normalise_locale(locale)
    delivery = on_time_delivery_rate(on_time_jobs, total_jobs, locale=loc)
    quality = quality_pass_rate(passed_inspections, total_inspections, locale=loc)

    score_weights = weights if weights is not None else DEFAULT_PERFORMANCE_WEIGHTS
    score = weighted_performance_score(
        {"schedule": delivery.percent, "quality": quality.percent},
        {
            "schedule": score_weights.get("schedule", DEFAULT_PERFORMANCE_WEIGHTS["schedule"]),
            "quality": score_weights.get("quality", DEFAULT_PERFORMANCE_WEIGHTS["quality"]),
        },
        locale=loc,
    )
    spend = spend_by_currency(spend_entries, locale=loc)
    status_counts = counts_by_status(status_items, attribute=status_attribute, locale=loc)

    narrative = {
        "en": (
            f"Performance score {score.score} of 100. {delivery.explanation} {quality.explanation} {spend.explanation}"
        ),
        "de": (
            f"Leistungsbewertung {score.score} von 100. "
            f"{delivery.explanation} {quality.explanation} {spend.explanation}"
        ),
        "ru": (
            f"Otsenka effektivnosti {score.score} iz 100. "
            f"{delivery.explanation} {quality.explanation} {spend.explanation}"
        ),
    }[loc]

    return PerformanceSummary(
        on_time_delivery=delivery,
        quality_pass=quality,
        performance_score=score,
        spend=spend,
        status_counts=status_counts,
        narrative=narrative.strip(),
    )
