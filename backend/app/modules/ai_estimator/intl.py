# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, database-free estimating helpers for the AI Estimate Builder.

These are pure functions (no DB, no HTTP, no AI key, no currency assumptions).
They exist so the same money and confidence logic the service uses can be reused
and unit-tested in isolation, and so a reviewer can read a plain-language
explanation of every estimating concept the builder produces.

Design rules, mirrored from the rest of the module:

* Money is Decimal end-to-end and never rounds through float. Currencies are
  never blended: a base estimate returns a per-currency subtotal map, never one
  merged number across currency codes.
* No hardcoded currency, unit or locale. Every line carries its own explicit
  currency; contingency and markup are percentage parameters with documented
  defaults.
* Bad input surfaces as a clean ``ValueError`` (never a 500, never a NaN or an
  inf). Empty inputs return a well-defined zero, not an error.
* AI proposes, the human confirms. :func:`describe_confidence` always exposes a
  confidence band and a note that the figure is a suggestion awaiting review; it
  never presents a number as auto-applied.

The confidence-band cutoffs are imported from :mod:`service` so there is one
source of truth: the API contract, the service matchers and these helpers all
read the same two thresholds.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.modules.ai_estimator.service import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
)

# Two-decimal money quantum (mirrors the service's ``_Q2``); totals round to the
# minor unit with banker-neutral half-up so the sum a user sees is stable.
_CENTS = Decimal("0.01")

# Documented percentage defaults. They are plain parameters, not policy: a caller
# always passes the project's own contingency and markup. The defaults exist only
# so a bare call has clear, conservative behaviour (10% contingency, 0% markup so
# markup is opt-in and never silently inflates a figure).
DEFAULT_CONTINGENCY_PCT: Decimal = Decimal("10")
DEFAULT_MARKUP_PCT: Decimal = Decimal("0")

# The confidence bands, plainest-first. ``none`` means "no score to rate", not
# "zero confidence": an unmatched line has no confidence at all.
CONFIDENCE_BANDS: tuple[str, ...] = ("none", "low", "medium", "high")

# Plain one-line labels per band, per language. English is the fallback for any
# language not in the table. Cyrillic / umlaut letters are ordinary Unicode text,
# not smart punctuation.
_BAND_LABELS: dict[str, dict[str, str]] = {
    "en": {"high": "High", "medium": "Medium", "low": "Low", "none": "Not rated"},
    "de": {"high": "Hoch", "medium": "Mittel", "low": "Niedrig", "none": "Nicht bewertet"},
    "ru": {"high": "Высокая", "medium": "Средняя", "low": "Низкая", "none": "Нет оценки"},
}

# One-line, plain-language explanation of every estimating concept the builder
# surfaces, per language. Keep each to a single clear sentence a site engineer or
# estimator understands in a few seconds.
_CONCEPT_EXPLANATIONS: dict[str, dict[str, str]] = {
    "en": {
        "line_total": "Line total is the quantity multiplied by the unit rate for one work item.",
        "base_estimate": (
            "Base estimate is the sum of all line totals before contingency or markup, kept separate per currency."
        ),
        "contingency": ("Contingency is a percentage added to the base estimate to cover unforeseen work."),
        "markup": ("Markup is a percentage added for overhead and profit on top of the base estimate."),
        "confidence_band": (
            "Confidence band groups the numeric match confidence into low, medium or high "
            "so a reviewer can scan it quickly."
        ),
        "suggestion": (
            "This figure is an AI suggestion, not a final price. A human reviews and confirms it before it is used."
        ),
    },
    "de": {
        "line_total": ("Die Positionssumme ist die Menge multipliziert mit dem Einheitspreis einer Arbeitsposition."),
        "base_estimate": (
            "Die Basisschaetzung ist die Summe aller Positionssummen vor Wagnis und Zuschlag, "
            "je Waehrung getrennt gehalten."
        ),
        "contingency": (
            "Wagnis ist ein Prozentsatz, der zur Basisschaetzung addiert wird, um unvorhergesehene Arbeiten abzudecken."
        ),
        "markup": ("Zuschlag ist ein Prozentsatz fuer Gemeinkosten und Gewinn zusaetzlich zur Basisschaetzung."),
        "confidence_band": (
            "Das Konfidenzband fasst die numerische Trefferkonfidenz in niedrig, mittel oder "
            "hoch zusammen, damit ein Pruefer sie schnell erfassen kann."
        ),
        "suggestion": (
            "Diese Zahl ist ein KI-Vorschlag, kein Endpreis. Ein Mensch prueft und bestaetigt sie vor der Verwendung."
        ),
    },
    "ru": {
        "line_total": ("Сумма позиции это количество, умноженное на единичную расценку для одной работы."),
        "base_estimate": ("Базовая оценка это сумма всех позиций до резерва и наценки, отдельно по каждой валюте."),
        "contingency": ("Резерв это процент, добавляемый к базовой оценке для покрытия непредвиденных работ."),
        "markup": "Наценка это процент на накладные расходы и прибыль сверх базовой оценки.",
        "confidence_band": (
            "Полоса уверенности группирует числовую уверенность совпадения в низкую, среднюю "
            "или высокую для быстрой проверки."
        ),
        "suggestion": (
            "Эта цифра это предложение ИИ, а не окончательная цена. Человек проверяет и "
            "подтверждает её перед использованием."
        ),
    },
}


# ── Internal coercion (strict: junk raises, never silently zeroes) ────────────


def _to_decimal(value: object, *, field: str) -> Decimal:
    """Coerce a number-like value to a finite :class:`Decimal` or raise.

    Unlike the service's forgiving ``_dec`` (which defaults junk to zero for the
    display path), this is strict on purpose: a caller-supplied quantity or rate
    that is not a real finite number is a clean input error, not a silent zero.

    Args:
        value: A ``Decimal``, ``int``, ``float`` or numeric ``str``.
        field: The field name, used only for a clear error message.

    Returns:
        The value as a finite ``Decimal``.

    Raises:
        ValueError: If the value is a bool, a non-numeric type, an unparseable
            string, or a non-finite number (NaN / infinity).
    """
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, (int, float, str)):
        try:
            dec = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field} is not a valid number: {value!r}") from exc
    else:
        raise ValueError(f"{field} must be a number, got {type(value).__name__}")
    if not dec.is_finite():
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return dec


def _to_percent(value: object, *, field: str) -> Decimal:
    """Coerce a percentage to a finite, non-negative ``Decimal`` or raise.

    Args:
        value: The percentage (for example ``10`` for ten percent).
        field: The field name for error messages.

    Returns:
        The percentage as a non-negative ``Decimal``.

    Raises:
        ValueError: If the value is not a finite number or is negative.
    """
    pct = _to_decimal(value, field=field)
    if pct < 0:
        raise ValueError(f"{field} must not be negative, got {value!r}")
    return pct


def _normalise_currency(value: object) -> str:
    """Return an upper-cased, non-empty currency code or raise.

    Every line must name its own currency so currencies are never blended by
    accident. There is no default currency (the platform is international).

    Raises:
        ValueError: If the currency is missing or blank.
    """
    code = str(value or "").strip().upper()
    if not code:
        raise ValueError("each line must carry an explicit currency code")
    return code


def _field(line: Any, key: str) -> Any:
    """Read ``key`` from a mapping line or an object line (helper for lines)."""
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _money(value: Decimal) -> Decimal:
    """Quantize a Decimal to the two-decimal minor unit, half-up."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


# ── Money helpers (Decimal-exact, currency-safe) ──────────────────────────────


def line_total(quantity: object, unit_rate: object) -> Decimal:
    """Return ``quantity * unit_rate`` as an exact ``Decimal``.

    This is the single work-item line total: how much one measured position
    costs at its unit rate. The result is exact (not rounded) so a downstream
    rollup can quantize once at the end.

    Args:
        quantity: The measured quantity (any non-negative finite number). Zero is
            allowed and yields ``Decimal("0")``.
        unit_rate: The rate per unit (any non-negative finite number). Zero is
            allowed and yields ``Decimal("0")``.

    Returns:
        The exact line total as a ``Decimal``.

    Raises:
        ValueError: If either input is non-finite, non-numeric or negative.
    """
    qty = _to_decimal(quantity, field="quantity")
    rate = _to_decimal(unit_rate, field="unit_rate")
    if qty < 0:
        raise ValueError(f"quantity must not be negative, got {quantity!r}")
    if rate < 0:
        raise ValueError(f"unit_rate must not be negative, got {unit_rate!r}")
    return qty * rate


def base_estimate(lines: Any) -> dict[str, Decimal]:
    """Sum line totals into a per-currency subtotal map (never blends currencies).

    Each line is a mapping (or object) carrying ``quantity``, ``unit_rate`` and an
    explicit ``currency``. Lines are grouped by currency code and summed within
    each group; currencies are never added together. An empty line list returns an
    empty map (a well-defined zero, not an error).

    Args:
        lines: An iterable of line mappings/objects, each with ``quantity``,
            ``unit_rate`` and ``currency``.

    Returns:
        A ``{currency_code: subtotal}`` map of exact ``Decimal`` subtotals.

    Raises:
        ValueError: If a line has a non-numeric/negative quantity or rate, or a
            missing/blank currency.
    """
    subtotals: dict[str, Decimal] = {}
    for line in lines or []:
        currency = _normalise_currency(_field(line, "currency"))
        total = line_total(_field(line, "quantity"), _field(line, "unit_rate"))
        subtotals[currency] = subtotals.get(currency, Decimal("0")) + total
    return subtotals


def contingency_amount(base: object, contingency_pct: object = DEFAULT_CONTINGENCY_PCT) -> Decimal:
    """Return the contingency money for a base amount at a percentage.

    Args:
        base: The base estimate amount (non-negative finite number).
        contingency_pct: The contingency percentage (for example ``10``).
            Defaults to :data:`DEFAULT_CONTINGENCY_PCT`.

    Returns:
        The contingency amount, quantized to the two-decimal minor unit.

    Raises:
        ValueError: If ``base`` is non-finite/negative or the percentage is
            non-finite/negative.
    """
    base_dec = _to_decimal(base, field="base")
    if base_dec < 0:
        raise ValueError(f"base must not be negative, got {base!r}")
    pct = _to_percent(contingency_pct, field="contingency_pct")
    return _money(base_dec * pct / Decimal("100"))


def markup_amount(base: object, markup_pct: object = DEFAULT_MARKUP_PCT) -> Decimal:
    """Return the markup money for a base amount at a percentage.

    Args:
        base: The base estimate amount (non-negative finite number).
        markup_pct: The markup percentage. Defaults to :data:`DEFAULT_MARKUP_PCT`.

    Returns:
        The markup amount, quantized to the two-decimal minor unit.

    Raises:
        ValueError: If ``base`` is non-finite/negative or the percentage is
            non-finite/negative.
    """
    base_dec = _to_decimal(base, field="base")
    if base_dec < 0:
        raise ValueError(f"base must not be negative, got {base!r}")
    pct = _to_percent(markup_pct, field="markup_pct")
    return _money(base_dec * pct / Decimal("100"))


def estimate_with_contingency(
    lines: Any,
    contingency_pct: object = DEFAULT_CONTINGENCY_PCT,
    markup_pct: object = DEFAULT_MARKUP_PCT,
) -> dict[str, dict[str, Decimal]]:
    """Build a per-currency base / contingency / markup / total breakdown.

    Contingency and markup are both computed from the base (not compounded on one
    another) so the arithmetic stays obvious: ``total = base + contingency +
    markup``. Currencies are never blended; each currency gets its own block.

    Args:
        lines: An iterable of line mappings/objects (see :func:`base_estimate`).
        contingency_pct: The contingency percentage. Defaults to
            :data:`DEFAULT_CONTINGENCY_PCT`.
        markup_pct: The markup percentage. Defaults to :data:`DEFAULT_MARKUP_PCT`.

    Returns:
        A ``{currency: {"base", "contingency", "markup", "total"}}`` map. Every
        value is a two-decimal ``Decimal``. An empty line list yields an empty map.

    Raises:
        ValueError: On any invalid line, quantity, rate, currency or percentage.
    """
    bases = base_estimate(lines)
    # Validate the percentages once, up front, so an empty line list still rejects
    # a negative percentage (fail fast, never a silent pass).
    cont_pct = _to_percent(contingency_pct, field="contingency_pct")
    mkp_pct = _to_percent(markup_pct, field="markup_pct")

    breakdown: dict[str, dict[str, Decimal]] = {}
    for currency, base in bases.items():
        cont = _money(base * cont_pct / Decimal("100"))
        mkp = _money(base * mkp_pct / Decimal("100"))
        base_money = _money(base)
        breakdown[currency] = {
            "base": base_money,
            "contingency": cont,
            "markup": mkp,
            "total": base_money + cont + mkp,
        }
    return breakdown


# ── Confidence helpers (real score or None; out of range is an error) ─────────


def confidence_to_band(score: float | int | None) -> str:
    """Map a real confidence in ``[0, 1]`` (or ``None``) to a plain band.

    ``None`` means "no score to rate" and maps to ``none``. A real score maps to
    ``low`` / ``medium`` / ``high`` using the same thresholds the service and API
    contract use, so the band shown here always matches the rest of the module. A
    score outside ``[0, 1]`` (or a non-numeric value) is a caller error, surfaced
    as ``ValueError`` rather than silently clamped to a fake value.

    Args:
        score: A confidence in ``[0, 1]``, or ``None`` when unmatched.

    Returns:
        One of ``none`` / ``low`` / ``medium`` / ``high``.

    Raises:
        ValueError: If the score is non-numeric, non-finite, or outside ``[0, 1]``.
    """
    if score is None:
        return "none"
    if isinstance(score, bool):
        raise ValueError("confidence must be a number, not a boolean")
    try:
        value = float(score)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"confidence must be a number, got {score!r}") from exc
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"confidence must be within [0, 1], got {score!r}")
    if value >= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if value >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def band_label(band: str, lang: str = "en") -> str:
    """Return the localized plain label for a confidence band.

    Args:
        band: One of ``none`` / ``low`` / ``medium`` / ``high``.
        lang: A two-letter language code (``en`` / ``de`` / ``ru``). Any other
            language falls back to English.

    Returns:
        The localized label (for example ``"Medium"`` / ``"Mittel"``).

    Raises:
        ValueError: If ``band`` is not a known band.
    """
    if band not in CONFIDENCE_BANDS:
        raise ValueError(f"band must be one of {list(CONFIDENCE_BANDS)}, got {band!r}")
    table = _BAND_LABELS.get(lang, _BAND_LABELS["en"])
    return table[band]


def describe_confidence(score: float | int | None, lang: str = "en") -> dict[str, Any]:
    """Turn a numeric confidence into a review-ready, suggestion-framed summary.

    The result always carries the band, its localized label, and a note that the
    figure is an AI suggestion awaiting human confirmation. It never presents the
    number as auto-applied (the platform rule: AI proposes, human confirms).

    Args:
        score: A confidence in ``[0, 1]``, or ``None`` when unmatched.
        lang: A two-letter language code (``en`` / ``de`` / ``ru``).

    Returns:
        A dict with ``score`` (the input, unchanged), ``band``, ``label`` and a
        plain-language ``note``.

    Raises:
        ValueError: If the score is out of range or non-numeric.
    """
    band = confidence_to_band(score)
    return {
        "score": score,
        "band": band,
        "label": band_label(band, lang),
        "note": explain("suggestion", lang),
    }


def explain(concept: str, lang: str = "en") -> str:
    """Return a one-line, plain-language explanation of an estimating concept.

    Args:
        concept: One of ``line_total`` / ``base_estimate`` / ``contingency`` /
            ``markup`` / ``confidence_band`` / ``suggestion``.
        lang: A two-letter language code (``en`` / ``de`` / ``ru``). Any other
            language falls back to English.

    Returns:
        A single clear sentence explaining the concept.

    Raises:
        ValueError: If ``concept`` is not a known concept.
    """
    table = _CONCEPT_EXPLANATIONS.get(lang, _CONCEPT_EXPLANATIONS["en"])
    if concept not in table:
        known = list(_CONCEPT_EXPLANATIONS["en"])
        raise ValueError(f"concept must be one of {known}, got {concept!r}")
    return table[concept]
