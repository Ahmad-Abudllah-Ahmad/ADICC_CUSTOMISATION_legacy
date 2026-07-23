# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, DB-free helpers for the project risk register.

This module is strictly additive. It contains only pure functions and small
immutable data holders so it can be imported and unit-tested without a
database, a network, or any app runtime. Nothing here changes existing
service / schema / router signatures; it complements them.

Design goals (aligned with ISO 31000 qualitative risk assessment):

International by construction
    No currency symbol, locale, or matrix size is hardcoded. Likelihood and
    impact live on a configurable 1..N scale (default 1-5). Money is handled
    with :class:`decimal.Decimal` and a currency is only ever an opaque code
    that travels next to the amount, never blended with a different code.
    Dates are formatted as ISO 8601 (YYYY-MM-DD).

Clarity
    Every derived figure has a one-line, plain-language explainer and its raw
    components are exposed, so a site engineer or estimator can see exactly
    how a number was produced. Status / category / severity / rating words are
    localized into English, German and Russian with an English fallback.

Robustness
    Empty sets, division by zero, out-of-range or negative inputs, and
    non-finite money (NaN / Infinity) all raise a clean ``ValueError`` or are
    guarded. No function returns NaN or infinity, and any normalized score
    stays within ``[0, 1]``.

Formulas
    risk score          = likelihood x impact            (1 .. scale*scale)
    normalized score    = (score - 1) / (scale*scale - 1) (0 .. 1)
    rating band         = first band whose upper cut-point >= normalized score
    monetary exposure   = probability (0..1) x cost impact (expected value)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.modules.risk.schemas import STATUS_VALUES

# ── Public constants ──────────────────────────────────────────────────────

#: Default qualitative scale. A 1-5 scale is the most widely taught matrix,
#: but every helper accepts ``scale`` so a 1-3, 1-4 or 1-10 matrix works too.
DEFAULT_SCALE: int = 5

#: Supported UI languages for term localization. English is always the
#: fallback, so an unknown language or an unknown term degrades gracefully
#: instead of raising or leaking a raw enum key.
SUPPORTED_LANGS: tuple[str, ...] = ("en", "de", "ru")

#: Risk category vocabulary. Mirrors the pattern accepted by
#: ``RiskCreate.category`` in schemas.py (kept in sync as a plain tuple here
#: so this module has no dependency on that private regex).
CATEGORY_VALUES: tuple[str, ...] = (
    "technical",
    "financial",
    "schedule",
    "regulatory",
    "environmental",
    "safety",
    "procurement",
)

#: Rating bands, low to critical. Reused as the default rating vocabulary and
#: as the tier names produced elsewhere in the module (service.py uses the
#: same four words for ``risk_tier``).
RATING_BANDS: tuple[str, ...] = ("low", "medium", "high", "critical")

#: Default band cut-points as fractions (0..1) of the normalized score, in
#: ascending order. A band matches when the normalized score is <= its
#: cut-point. Being expressed on the normalized 0..1 score makes them
#: independent of the matrix size, so the same thresholds are meaningful for a
#: 1-5 or a 1-10 matrix. Callers may pass their own ordered thresholds.
DEFAULT_BAND_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("low", 0.20),
    ("medium", 0.40),
    ("high", 0.70),
    ("critical", 1.00),
)

#: Money precision for exposure amounts (minor units / cents).
_MONEY_QUANT: Decimal = Decimal("0.01")

#: Upper magnitude bound for money, mirroring schemas._MONEY_MAX so a single
#: absurd input cannot overflow a downstream rollup. Kept local to avoid
#: importing a private symbol.
_MONEY_MAX: Decimal = Decimal("1e15")


# ── Localization tables ───────────────────────────────────────────────────
# English is the source of truth and the fallback. German and Russian are
# provided for the shared vocabularies. An unknown term returns a readable
# form of the key itself rather than raising.

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "identified": {"en": "Identified", "de": "Identifiziert", "ru": "Vyyavlen"},
    "assessed": {"en": "Assessed", "de": "Bewertet", "ru": "Otsenen"},
    "mitigating": {"en": "Mitigating", "de": "In Behandlung", "ru": "Snizhaetsya"},
    "monitoring": {"en": "Monitoring", "de": "Wird beobachtet", "ru": "Nablyudaetsya"},
    "mitigated": {"en": "Mitigated", "de": "Behandelt", "ru": "Snizhen"},
    "open": {"en": "Open", "de": "Offen", "ru": "Otkryt"},
    "closed": {"en": "Closed", "de": "Geschlossen", "ru": "Zakryt"},
    "occurred": {"en": "Occurred", "de": "Eingetreten", "ru": "Nastupil"},
}

_CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "technical": {"en": "Technical", "de": "Technisch", "ru": "Tekhnicheskiy"},
    "financial": {"en": "Financial", "de": "Finanziell", "ru": "Finansovyy"},
    "schedule": {"en": "Schedule", "de": "Terminplan", "ru": "Grafik"},
    "regulatory": {"en": "Regulatory", "de": "Regulatorisch", "ru": "Normativnyy"},
    "environmental": {"en": "Environmental", "de": "Umwelt", "ru": "Ekologicheskiy"},
    "safety": {"en": "Safety", "de": "Sicherheit", "ru": "Bezopasnost"},
    "procurement": {"en": "Procurement", "de": "Beschaffung", "ru": "Zakupki"},
}

_SEVERITY_LABELS: dict[str, dict[str, str]] = {
    "very_low": {"en": "Very low", "de": "Sehr gering", "ru": "Ochen nizkiy"},
    "low": {"en": "Low", "de": "Gering", "ru": "Nizkiy"},
    "medium": {"en": "Medium", "de": "Mittel", "ru": "Sredniy"},
    "high": {"en": "High", "de": "Hoch", "ru": "Vysokiy"},
    "critical": {"en": "Critical", "de": "Kritisch", "ru": "Kriticheskiy"},
}

# Rating bands share the severity words; keep a dedicated map so the two can
# diverge later without a breaking change.
_BAND_LABELS: dict[str, dict[str, str]] = {
    "low": {"en": "Low", "de": "Gering", "ru": "Nizkiy"},
    "medium": {"en": "Medium", "de": "Mittel", "ru": "Sredniy"},
    "high": {"en": "High", "de": "Hoch", "ru": "Vysokiy"},
    "critical": {"en": "Critical", "de": "Kritisch", "ru": "Kriticheskiy"},
}

_LABEL_TABLES: dict[str, dict[str, dict[str, str]]] = {
    "status": _STATUS_LABELS,
    "category": _CATEGORY_LABELS,
    "severity": _SEVERITY_LABELS,
    "band": _BAND_LABELS,
}


def _fallback_label(term: str) -> str:
    """Return a readable label for an unknown term (``very_low`` -> ``Very low``)."""
    cleaned = str(term).replace("_", " ").strip()
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def localize(term: str, kind: str, lang: str = "en") -> str:
    """Localize a controlled-vocabulary ``term`` into ``lang``.

    Args:
        term: The raw enum value, e.g. ``"monitoring"`` or ``"critical"``.
        kind: One of ``"status"``, ``"category"``, ``"severity"``, ``"band"``.
        lang: Target language code; falls back to English then to a readable
            form of the key. Never raises for an unknown language or term.

    Returns:
        A human-readable, plain-language label.
    """
    table = _LABEL_TABLES.get(kind)
    if table is None:
        return _fallback_label(term)
    entry = table.get(term)
    if entry is None:
        return _fallback_label(term)
    return entry.get(lang) or entry.get("en") or _fallback_label(term)


# ── Scale validation and scoring ──────────────────────────────────────────


def _coerce_int(value: object, name: str) -> int:
    """Coerce ``value`` to an int without silently truncating a real fraction."""
    if isinstance(value, bool):
        # bool is an int subclass; reject it so True/False cannot pose as 1/0.
        raise ValueError(f"{name} must be a whole number, got a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{name} must be a finite whole number")
        if not value.is_integer():
            raise ValueError(f"{name} must be a whole number, got {value}")
        return int(value)
    raise ValueError(f"{name} must be a whole number, got {type(value).__name__}")


def validate_scale(scale: int) -> int:
    """Validate a matrix scale (must be a whole number >= 1)."""
    scale_int = _coerce_int(scale, "scale")
    if scale_int < 1:
        raise ValueError(f"scale must be at least 1, got {scale_int}")
    return scale_int


def validate_scale_value(value: object, *, scale: int = DEFAULT_SCALE, name: str = "value") -> int:
    """Validate a likelihood or impact value against a 1..scale matrix.

    Raises:
        ValueError: If ``value`` is not a whole number in ``1..scale``
            (covers negative, zero, out-of-range and fractional inputs).
    """
    scale_int = validate_scale(scale)
    value_int = _coerce_int(value, name)
    if value_int < 1 or value_int > scale_int:
        raise ValueError(f"{name} must be between 1 and {scale_int}, got {value_int}")
    return value_int


def risk_score(likelihood: object, impact: object, *, scale: int = DEFAULT_SCALE) -> int:
    """Qualitative risk score = likelihood x impact.

    Both inputs are validated against the 1..scale matrix, so the result is
    always in ``1 .. scale*scale``. This is the ISO 31000 / PMBOK product
    used to rank risks.
    """
    scale_int = validate_scale(scale)
    likelihood_int = validate_scale_value(likelihood, scale=scale_int, name="likelihood")
    impact_int = validate_scale_value(impact, scale=scale_int, name="impact")
    return likelihood_int * impact_int


def normalized_score(likelihood: object, impact: object, *, scale: int = DEFAULT_SCALE) -> float:
    """Risk score rescaled to ``[0, 1]`` so any matrix size is comparable.

    Formula: ``(score - 1) / (scale*scale - 1)``. For a 1x1 matrix the
    denominator would be zero, so that degenerate case returns ``0.0`` instead
    of dividing by zero. The result is clamped to ``[0, 1]`` as defence in
    depth and is never NaN or infinity.
    """
    scale_int = validate_scale(scale)
    score = risk_score(likelihood, impact, scale=scale_int)
    span = scale_int * scale_int - 1
    if span <= 0:
        return 0.0
    normalized = (score - 1) / span
    return max(0.0, min(1.0, normalized))


def _validate_thresholds(
    thresholds: Sequence[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    """Validate band thresholds: non-empty, ascending, finite, within (0, 1]."""
    if not thresholds:
        raise ValueError("thresholds must not be empty")
    previous = 0.0
    cleaned: list[tuple[str, float]] = []
    for name, cut in thresholds:
        cut_f = float(cut)
        if cut_f != cut_f or cut_f in (float("inf"), float("-inf")):
            raise ValueError("threshold cut-point must be finite")
        if cut_f < previous:
            raise ValueError("threshold cut-points must be in ascending order")
        if cut_f > 1.0:
            raise ValueError("threshold cut-points are fractions and must be <= 1.0")
        cleaned.append((str(name), cut_f))
        previous = cut_f
    return tuple(cleaned)


def rating_band(
    likelihood: object,
    impact: object,
    *,
    scale: int = DEFAULT_SCALE,
    thresholds: Sequence[tuple[str, float]] = DEFAULT_BAND_THRESHOLDS,
) -> str:
    """Rating band for a risk from its likelihood and impact.

    The score is normalized to ``[0, 1]`` and matched against the ascending
    ``thresholds`` (fractions of the normalized score). The first band whose
    cut-point is >= the normalized score wins; if none do (thresholds below
    1.0), the last band is returned. Thresholds are a parameter so a project
    can tune where low / medium / high / critical fall for any matrix size.
    """
    validated = _validate_thresholds(thresholds)
    normalized = normalized_score(likelihood, impact, scale=scale)
    for name, cut in validated:
        if normalized <= cut:
            return name
    return validated[-1][0]


def rating_band_from_score(
    score: object,
    *,
    scale: int = DEFAULT_SCALE,
    thresholds: Sequence[tuple[str, float]] = DEFAULT_BAND_THRESHOLDS,
) -> str:
    """Rating band from a pre-computed product score (``1 .. scale*scale``).

    Convenience wrapper for callers that already hold the product (for
    instance a stored ``risk_score``) rather than the two factors.
    """
    scale_int = validate_scale(scale)
    score_int = _coerce_int(score, "score")
    max_score = scale_int * scale_int
    if score_int < 1 or score_int > max_score:
        raise ValueError(f"score must be between 1 and {max_score}, got {score_int}")
    validated = _validate_thresholds(thresholds)
    span = max_score - 1
    normalized = 0.0 if span <= 0 else max(0.0, min(1.0, (score_int - 1) / span))
    for name, cut in validated:
        if normalized <= cut:
            return name
    return validated[-1][0]


# ── Monetary exposure ─────────────────────────────────────────────────────


def _to_probability(probability: object) -> Decimal:
    """Coerce and validate a probability as a Decimal fraction in ``[0, 1]``."""
    try:
        prob = Decimal(str(probability))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"probability must be a number, got {probability!r}") from exc
    if not prob.is_finite():
        raise ValueError("probability must be a finite number (no NaN/Infinity)")
    if prob < 0 or prob > 1:
        raise ValueError(f"probability must be a fraction between 0 and 1, got {prob}")
    return prob


def _to_money(cost_impact: object, name: str = "cost impact") -> Decimal:
    """Coerce and validate a non-negative, finite, in-range money amount."""
    try:
        amount = Decimal(str(cost_impact))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a number, got {cost_impact!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"{name} must be a finite number (no NaN/Infinity)")
    if amount < 0:
        raise ValueError(f"{name} must not be negative, got {amount}")
    if amount >= _MONEY_MAX:
        raise ValueError(f"{name} is outside the supported range")
    return amount


@dataclass(frozen=True)
class MonetaryExposure:
    """Explainable monetary risk exposure (expected monetary value).

    Attributes:
        probability: The 0..1 likelihood fraction used.
        cost_impact: The Decimal cost impact if the risk occurs.
        amount: probability x cost_impact, quantized to minor units.
        currency: Opaque ISO currency code carried alongside the amount;
            empty string when unknown (the UI then renders a bare number
            rather than mislabelling the currency).
    """

    probability: Decimal
    cost_impact: Decimal
    amount: Decimal
    currency: str

    @property
    def formula(self) -> str:
        """Plain-language derivation of :attr:`amount`."""
        return f"exposure = probability {self.probability} x cost impact {self.cost_impact} = {self.amount}"


def monetary_exposure(
    probability: object,
    cost_impact: object,
    *,
    currency: str = "",
) -> MonetaryExposure:
    """Expected monetary exposure = probability (0..1) x cost impact.

    Decimal-exact and currency-safe: the amount is computed with Decimal and
    quantized to minor units (half-up). The ``currency`` code is only carried
    alongside the number, never used in arithmetic, so two different currency
    codes can never be blended by this function. Guards reject NaN / Infinity,
    negative money, out-of-range probability, and absurd magnitudes with a
    clean ValueError.
    """
    prob = _to_probability(probability)
    cost = _to_money(cost_impact)
    amount = (prob * cost).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return MonetaryExposure(
        probability=prob,
        cost_impact=cost,
        amount=amount,
        currency=str(currency or ""),
    )


def total_exposure(
    exposures: Iterable[MonetaryExposure],
) -> dict[str, Decimal]:
    """Sum exposures, keeping each currency separate.

    Heterogeneous currencies are never added together: the result maps each
    currency code (``""`` for unknown) to its own Decimal total. An empty
    input yields an empty map instead of raising or returning zero under a
    guessed currency.
    """
    totals: dict[str, Decimal] = {}
    for exposure in exposures:
        code = exposure.currency or ""
        running = totals.get(code, Decimal("0"))
        totals[code] = (running + exposure.amount).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return totals


# ── Aggregations ──────────────────────────────────────────────────────────


def _extract(item: object, key: str) -> object:
    """Read ``key`` from a Mapping or an attribute, else return the item itself."""
    if isinstance(item, Mapping):
        return item.get(key)
    if hasattr(item, key):
        return getattr(item, key)
    return item


def counts_by_status(
    items: Iterable[object],
    *,
    statuses: Sequence[str] = STATUS_VALUES,
) -> dict[str, int]:
    """Count risks by lifecycle status.

    Accepts an iterable of status strings, Mappings with a ``status`` key, or
    objects with a ``status`` attribute. The result is seeded with every known
    status at zero (stable keys for a dashboard); any status outside the known
    vocabulary is still counted under its own key so nothing is silently
    dropped. An empty input returns the all-zero baseline.
    """
    counts: dict[str, int] = dict.fromkeys(statuses, 0)
    for item in items:
        raw = _extract(item, "status")
        key = str(raw) if raw is not None else "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def counts_by_band(
    items: Iterable[object],
    *,
    scale: int = DEFAULT_SCALE,
    thresholds: Sequence[tuple[str, float]] = DEFAULT_BAND_THRESHOLDS,
    bands: Sequence[str] = RATING_BANDS,
) -> dict[str, int]:
    """Count risks by rating band.

    Each item may be a ``(likelihood, impact)`` pair, a Mapping with
    ``likelihood`` and ``impact`` keys, or an object with those attributes.
    Values are validated through :func:`rating_band`, so an out-of-range or
    negative factor raises a clean ValueError rather than being miscounted.
    The result is seeded with every band at zero. Empty input returns the
    all-zero baseline.
    """
    counts: dict[str, int] = dict.fromkeys(bands, 0)
    for item in items:
        if isinstance(item, Mapping):
            likelihood = item.get("likelihood")
            impact = item.get("impact")
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            likelihood, impact = item[0], item[1]
        else:
            likelihood = getattr(item, "likelihood", None)
            impact = getattr(item, "impact", None)
        band = rating_band(likelihood, impact, scale=scale, thresholds=thresholds)
        counts[band] = counts.get(band, 0) + 1
    return counts


# ── ISO 8601 dates ────────────────────────────────────────────────────────


def iso_date(value: date | datetime | str) -> str:
    """Format a date / datetime as an ISO 8601 date (YYYY-MM-DD).

    A ``datetime`` keeps only its date part; a string is validated by parsing
    it as ISO 8601. Anything unparseable raises a clean ValueError. This keeps
    every date the register emits locale-independent.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError as exc:
            raise ValueError(f"value is not an ISO 8601 date: {value!r}") from exc
    raise ValueError(f"value must be a date, datetime or ISO 8601 string, got {value!r}")


# ── Explainers and full breakdown ─────────────────────────────────────────


def explain_risk_score(
    likelihood: object,
    impact: object,
    *,
    scale: int = DEFAULT_SCALE,
    lang: str = "en",
) -> str:
    """One-line, localized explanation of a risk score."""
    score = risk_score(likelihood, impact, scale=scale)
    scale_int = validate_scale(scale)
    templates = {
        "en": (f"Risk score {score} = likelihood x impact on a 1-{scale_int} scale. Higher means a more urgent risk."),
        "de": (
            f"Risikowert {score} = Eintrittswahrscheinlichkeit x Auswirkung auf "
            f"einer 1-{scale_int}-Skala. Hoeher bedeutet dringlicher."
        ),
        "ru": (f"Otsenka riska {score} = veroyatnost x vozdeystvie po shkale 1-{scale_int}. Chem vyshe, tem srochnee."),
    }
    return templates.get(lang) or templates["en"]


def explain_rating_band(
    likelihood: object,
    impact: object,
    *,
    scale: int = DEFAULT_SCALE,
    thresholds: Sequence[tuple[str, float]] = DEFAULT_BAND_THRESHOLDS,
    lang: str = "en",
) -> str:
    """One-line, localized explanation of a rating band."""
    band = rating_band(likelihood, impact, scale=scale, thresholds=thresholds)
    label = localize(band, "band", lang)
    templates = {
        "en": f"Rating band: {label}. Derived by comparing the normalized score to the band thresholds.",
        "de": f"Bewertungsstufe: {label}. Aus dem normierten Wert und den Stufengrenzen abgeleitet.",
        "ru": f"Uroven otsenki: {label}. Poluchen sravneniem normirovannoy otsenki s porogami.",
    }
    return templates.get(lang) or templates["en"]


def explain_exposure(
    probability: object,
    cost_impact: object,
    *,
    currency: str = "",
    lang: str = "en",
) -> str:
    """One-line, localized explanation of monetary risk exposure."""
    exposure = monetary_exposure(probability, cost_impact, currency=currency)
    money = f"{exposure.amount} {exposure.currency}".strip()
    templates = {
        "en": (
            f"Monetary exposure {money} = probability {exposure.probability} x cost "
            f"impact {exposure.cost_impact} (expected value if the risk occurs)."
        ),
        "de": (
            f"Monetaeres Risiko {money} = Wahrscheinlichkeit {exposure.probability} x "
            f"Kostenauswirkung {exposure.cost_impact} (Erwartungswert bei Eintritt)."
        ),
        "ru": (
            f"Denezhnaya podverzhennost {money} = veroyatnost {exposure.probability} x "
            f"stoimostnoe vozdeystvie {exposure.cost_impact} (ozhidaemoe znachenie)."
        ),
    }
    return templates.get(lang) or templates["en"]


@dataclass(frozen=True)
class RiskAssessment:
    """Full, explainable qualitative + monetary assessment of one risk.

    Every derived figure is exposed alongside the components it came from, so
    the calculation is transparent end to end.
    """

    likelihood: int
    impact: int
    scale: int
    score: int
    normalized: float
    band: str
    exposure: MonetaryExposure | None

    def to_dict(self, *, lang: str = "en") -> dict[str, object]:
        """Serialize to a plain dict with localized labels and explainers."""
        result: dict[str, object] = {
            "likelihood": self.likelihood,
            "impact": self.impact,
            "scale": self.scale,
            "score": self.score,
            "normalized": self.normalized,
            "band": self.band,
            "band_label": localize(self.band, "band", lang),
            "score_formula": "likelihood x impact",
            "explain_score": explain_risk_score(self.likelihood, self.impact, scale=self.scale, lang=lang),
            "explain_band": explain_rating_band(self.likelihood, self.impact, scale=self.scale, lang=lang),
        }
        if self.exposure is not None:
            result["exposure_amount"] = self.exposure.amount
            result["exposure_currency"] = self.exposure.currency
            result["exposure_formula"] = self.exposure.formula
            result["explain_exposure"] = explain_exposure(
                self.exposure.probability,
                self.exposure.cost_impact,
                currency=self.exposure.currency,
                lang=lang,
            )
        return result


def assess_risk(
    likelihood: object,
    impact: object,
    *,
    scale: int = DEFAULT_SCALE,
    thresholds: Sequence[tuple[str, float]] = DEFAULT_BAND_THRESHOLDS,
    probability: object | None = None,
    cost_impact: object | None = None,
    currency: str = "",
) -> RiskAssessment:
    """Build a full :class:`RiskAssessment` from raw inputs.

    Qualitative scoring is always computed. Monetary exposure is added only
    when both ``probability`` and ``cost_impact`` are supplied; otherwise
    :attr:`RiskAssessment.exposure` is ``None``. All inputs are validated, so
    this never returns a NaN, an infinity, or an out-of-range score.
    """
    scale_int = validate_scale(scale)
    likelihood_int = validate_scale_value(likelihood, scale=scale_int, name="likelihood")
    impact_int = validate_scale_value(impact, scale=scale_int, name="impact")
    score = likelihood_int * impact_int
    normalized = normalized_score(likelihood_int, impact_int, scale=scale_int)
    band = rating_band(likelihood_int, impact_int, scale=scale_int, thresholds=thresholds)
    exposure: MonetaryExposure | None = None
    if probability is not None and cost_impact is not None:
        exposure = monetary_exposure(probability, cost_impact, currency=currency)
    return RiskAssessment(
        likelihood=likelihood_int,
        impact=impact_int,
        scale=scale_int,
        score=score,
        normalized=normalized,
        band=band,
        exposure=exposure,
    )
