# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, explainable safety-metric helpers (pure, DB-free).

This module adds a small layer of framework-independent helpers on top of the
safety module so the same site health and safety numbers read clearly for a
company on any national convention:

* OSHA-style frequency rates (TRIR, LTIFR) and a severity rate, each computed
  from an incident count and hours worked. The recognized hours base is an
  explicit parameter (TRIR uses 200000 hours, LTIFR commonly 1000000 hours),
  so a company reporting per 100000 or per 1000 workers can pass its own base
  without changing anything else.
* "Days since the last incident" from an explicit last-incident date and an
  explicit reference date, using ISO 8601 dates.
* Counts of incidents by severity and by type.
* Plain-language, one-line explainers for each rate.
* Localized incident/observation severity, type and status words for English,
  German and Russian, with an English fallback for any other language or any
  value outside the known vocabulary.

Everything here is a pure function or an immutable value object. There is no
database access, no I/O and no framework dependency, so the helpers are trivial
to unit test and safe to reuse from services, exports or reports.

Design guarantees for the rates:

* Division by zero is impossible: zero hours worked returns a defined result
  with ``value=None`` and ``status="no_exposure_data"``, never NaN, infinity
  or a crash.
* Negative counts, negative hours or a non-positive hours base raise a clean
  ``ValueError`` rather than producing a nonsense number.
* Every returned rate value is finite and rounded to two decimals.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Recognized hours bases (the "multiplier" in the frequency-rate formula).
#
# rate = incident_count / hours_worked * base_hours
#
# TRIR per 200000 hours is roughly 100 full-time workers over one year.
# LTIFR is commonly reported per 1000000 hours. Both are passed explicitly to
# the helpers below with these standard defaults, so any other convention
# (for example per 100000 hours) is supported by overriding one argument.
# ---------------------------------------------------------------------------
TRIR_BASE_HOURS = 200_000
LTIFR_BASE_HOURS = 1_000_000
SEVERITY_RATE_BASE_HOURS = 1_000_000

SUPPORTED_LANGUAGES = ("en", "de", "ru")

# Canonical vocabularies, mirrored from the safety schemas so counts and
# localization stay in step with what the API actually accepts.
CANONICAL_INCIDENT_SEVERITIES = ("minor", "moderate", "major", "severe", "critical")
CANONICAL_INCIDENT_TYPES = ("injury", "near_miss", "property_damage", "environmental", "fire")
CANONICAL_INCIDENT_STATUSES = ("reported", "investigating", "corrective_action", "closed")
CANONICAL_OBSERVATION_TYPES = ("positive", "unsafe_act", "unsafe_condition", "near_miss")
CANONICAL_OBSERVATION_STATUSES = ("open", "in_progress", "closed")
CANONICAL_TREATMENT_TYPES = ("first_aid", "medical", "hospital", "fatality")


# ---------------------------------------------------------------------------
# Rate result value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RateResult:
    """An explainable safety-rate result.

    Attributes:
        value: The rate rounded to two decimals, or ``None`` when it cannot be
            computed because no exposure hours were provided.
        formula: The derivation as a human-readable formula string.
        explainer: A one-line, plain-language description of the metric.
        count: The numerator (incident/injury/lost-day count) used.
        hours_worked: The exposure hours (denominator) used.
        base_hours: The hours base (multiplier) applied.
        status: ``"ok"`` when a rate was computed, otherwise
            ``"no_exposure_data"``.
    """

    value: float | None
    formula: str
    explainer: str
    count: float
    hours_worked: float
    base_hours: float
    status: str

    @property
    def components(self) -> dict[str, float]:
        """Return the rate inputs as a plain dict for reports and exports."""
        return {
            "count": self.count,
            "hours_worked": self.hours_worked,
            "base_hours": self.base_hours,
        }


def _fmt_hours(base_hours: float) -> str:
    """Format an hours base with thousands separators, for example 200,000."""
    return f"{base_hours:,.0f}"


def incident_rate(
    count: float,
    hours_worked: float,
    *,
    base_hours: float,
    label: str = "incident_rate",
    numerator_name: str = "incident_count",
    explainer: str | None = None,
) -> RateResult:
    """Compute a generic OSHA-style frequency rate.

    The formula is ``count / hours_worked * base_hours``. ``base_hours`` is the
    recognized multiplier (200000 for TRIR, 1000000 for LTIFR) and is required
    so the caller is always explicit about the convention in use.

    Args:
        count: Non-negative numerator (number of incidents, injuries or days).
        hours_worked: Non-negative exposure hours (the denominator).
        base_hours: Positive hours base / multiplier.
        label: Short metric label used in the formula string.
        numerator_name: Name of the numerator used in the formula string.
        explainer: Optional plain-language description; a generic one is built
            when omitted.

    Returns:
        A :class:`RateResult`. When ``hours_worked`` is zero the result carries
        ``value=None`` and ``status="no_exposure_data"`` instead of dividing by
        zero.

    Raises:
        ValueError: If ``count`` or ``hours_worked`` is negative, or if
            ``base_hours`` is not positive.
    """
    if count < 0:
        raise ValueError("count must not be negative")
    if hours_worked < 0:
        raise ValueError("hours_worked must not be negative")
    if base_hours <= 0:
        raise ValueError("base_hours must be positive")

    formula = f"{label} = {numerator_name} / hours_worked * {_fmt_hours(base_hours)}"
    if explainer is None:
        explainer = (
            f"{label}: {numerator_name.replace('_', ' ')} per {_fmt_hours(base_hours)} hours worked. Lower is better."
        )

    if hours_worked == 0:
        return RateResult(
            value=None,
            formula=formula,
            explainer=explainer,
            count=float(count),
            hours_worked=float(hours_worked),
            base_hours=float(base_hours),
            status="no_exposure_data",
        )

    value = round(count / hours_worked * base_hours, 2)
    return RateResult(
        value=value,
        formula=formula,
        explainer=explainer,
        count=float(count),
        hours_worked=float(hours_worked),
        base_hours=float(base_hours),
        status="ok",
    )


def trir(
    recordable_count: int,
    hours_worked: float,
    *,
    base_hours: float = TRIR_BASE_HOURS,
) -> RateResult:
    """Total Recordable Incident Rate.

    Recordable injuries per ``base_hours`` hours worked (200000 by default,
    roughly 100 full-time workers over one year).
    """
    explainer = (
        "Total Recordable Incident Rate: recordable injuries per "
        f"{_fmt_hours(base_hours)} hours worked. Lower is better."
    )
    return incident_rate(
        recordable_count,
        hours_worked,
        base_hours=base_hours,
        label="TRIR",
        numerator_name="recordable_incidents",
        explainer=explainer,
    )


def ltifr(
    lost_time_count: int,
    hours_worked: float,
    *,
    base_hours: float = LTIFR_BASE_HOURS,
) -> RateResult:
    """Lost Time Injury Frequency Rate.

    Injuries that caused at least one lost day, per ``base_hours`` hours worked
    (1000000 by default).
    """
    explainer = (
        "Lost Time Injury Frequency Rate: injuries causing at least one lost "
        f"day, per {_fmt_hours(base_hours)} hours worked. Lower is better."
    )
    return incident_rate(
        lost_time_count,
        hours_worked,
        base_hours=base_hours,
        label="LTIFR",
        numerator_name="lost_time_injuries",
        explainer=explainer,
    )


def severity_rate(
    days_lost: int,
    hours_worked: float,
    *,
    base_hours: float = SEVERITY_RATE_BASE_HOURS,
) -> RateResult:
    """Severity rate: lost days per ``base_hours`` hours worked.

    Shows how serious injuries are, not only how often they happen (1000000
    hours base by default).
    """
    explainer = (
        "Severity rate: lost days per "
        f"{_fmt_hours(base_hours)} hours worked, showing how serious injuries "
        "are, not only how often they happen. Lower is better."
    )
    return incident_rate(
        days_lost,
        hours_worked,
        base_hours=base_hours,
        label="severity_rate",
        numerator_name="days_lost",
        explainer=explainer,
    )


# One-line, plain-language explainers keyed by metric, for direct UI use.
EXPLAINERS: dict[str, str] = {
    "trir": (
        "Total Recordable Incident Rate: recordable injuries per 200,000 hours "
        "worked (about 100 full-time workers over one year). Lower is better."
    ),
    "ltifr": (
        "Lost Time Injury Frequency Rate: injuries causing at least one lost "
        "day, per 1,000,000 hours worked. Lower is better."
    ),
    "severity_rate": (
        "Severity rate: lost days per 1,000,000 hours worked, showing how "
        "serious injuries are, not only how often they happen. Lower is better."
    ),
    "days_since_last_incident": (
        "Days since the last recorded incident, counted from the last incident "
        "date to the reference date. Higher is better."
    ),
}


def explain(metric: str) -> str:
    """Return the one-line explainer for a metric key, or an empty string."""
    return EXPLAINERS.get(metric, "")


# ---------------------------------------------------------------------------
# Counts by severity and by type
# ---------------------------------------------------------------------------
def _resolve(item: Any, key: str) -> Any:
    """Read ``key`` from a dict or an object attribute."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _count_by(items: Iterable[Any], key: str, canonical_order: tuple[str, ...]) -> dict[str, int]:
    """Count ``items`` by a string field, ordered by canonical vocabulary.

    Values that are missing or blank fall into an ``"unknown"`` bucket. Known
    values appear first in canonical order, then any extra values sorted
    alphabetically, then ``"unknown"`` last. An empty input yields an empty
    dict.
    """
    tally: dict[str, int] = {}
    for item in items:
        raw = _resolve(item, key)
        value = str(raw).strip() if raw not in (None, "") else "unknown"
        if not value:
            value = "unknown"
        tally[value] = tally.get(value, 0) + 1

    ordered: dict[str, int] = {}
    for name in canonical_order:
        if name in tally:
            ordered[name] = tally.pop(name)
    unknown = tally.pop("unknown", None)
    for name in sorted(tally):
        ordered[name] = tally[name]
    if unknown is not None:
        ordered["unknown"] = unknown
    return ordered


def counts_by_severity(incidents: Iterable[Any], *, key: str = "severity") -> dict[str, int]:
    """Count incidents by severity (dicts or objects), canonical order first."""
    return _count_by(incidents, key, CANONICAL_INCIDENT_SEVERITIES)


def counts_by_type(incidents: Iterable[Any], *, key: str = "incident_type") -> dict[str, int]:
    """Count incidents by type (dicts or objects), canonical order first."""
    return _count_by(incidents, key, CANONICAL_INCIDENT_TYPES)


# ---------------------------------------------------------------------------
# Days since last incident
# ---------------------------------------------------------------------------
def _as_date(value: date | str, field: str) -> date:
    """Coerce an ISO 8601 string or date into a ``date``."""
    if isinstance(value, date):
        return value
    text = value.strip()
    try:
        # Accept a full ISO date or the date part of an ISO datetime.
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO 8601 date: {value!r}") from exc


def days_since_last_incident(
    last_incident_date: date | str | None,
    reference_date: date | str,
) -> int | None:
    """Return whole days between the last incident and a reference date.

    Both dates are ISO 8601 (``date`` objects or ``YYYY-MM-DD`` strings). The
    result is never negative: a last-incident date after the reference date is
    clamped to zero, matching the "days since" reading of a same-day incident.

    Args:
        last_incident_date: The most recent incident date, or ``None`` when the
            project has had no incident.
        reference_date: The date to measure up to (for example today).

    Returns:
        The non-negative day count, or ``None`` when ``last_incident_date`` is
        ``None`` (no incident to measure from).

    Raises:
        ValueError: If either date string cannot be parsed as ISO 8601.
    """
    if last_incident_date is None:
        return None
    last = _as_date(last_incident_date, "last_incident_date")
    reference = _as_date(reference_date, "reference_date")
    return max(0, (reference - last).days)


# ---------------------------------------------------------------------------
# Localization of vocabulary words (en / de / ru, English fallback)
# ---------------------------------------------------------------------------
_LOCALIZATIONS: dict[str, dict[str, dict[str, str]]] = {
    "incident_type": {
        "en": {
            "injury": "Injury",
            "near_miss": "Near miss",
            "property_damage": "Property damage",
            "environmental": "Environmental incident",
            "fire": "Fire",
        },
        "de": {
            "injury": "Verletzung",
            "near_miss": "Beinaheunfall",
            "property_damage": "Sachschaden",
            "environmental": "Umweltvorfall",
            "fire": "Brand",
        },
        "ru": {
            "injury": "Травма",
            "near_miss": "Почти несчастный случай",
            "property_damage": "Материальный ущерб",
            "environmental": "Экологический инцидент",
            "fire": "Пожар",
        },
    },
    "incident_severity": {
        "en": {
            "minor": "Minor",
            "moderate": "Moderate",
            "major": "Major",
            "severe": "Severe",
            "critical": "Critical",
        },
        "de": {
            "minor": "Gering",
            "moderate": "Mittel",
            "major": "Erheblich",
            "severe": "Schwer",
            "critical": "Kritisch",
        },
        "ru": {
            "minor": "Незначительная",
            "moderate": "Умеренная",
            "major": "Значительная",
            "severe": "Тяжёлая",
            "critical": "Критическая",
        },
    },
    "incident_status": {
        "en": {
            "reported": "Reported",
            "investigating": "Investigating",
            "corrective_action": "Corrective action",
            "closed": "Closed",
        },
        "de": {
            "reported": "Gemeldet",
            "investigating": "In Untersuchung",
            "corrective_action": "Korrekturmaßnahme",
            "closed": "Geschlossen",
        },
        "ru": {
            "reported": "Зарегистрирован",
            "investigating": "Расследуется",
            "corrective_action": "Корректирующие меры",
            "closed": "Закрыт",
        },
    },
    "observation_type": {
        "en": {
            "positive": "Positive",
            "unsafe_act": "Unsafe act",
            "unsafe_condition": "Unsafe condition",
            "near_miss": "Near miss",
        },
        "de": {
            "positive": "Positiv",
            "unsafe_act": "Unsichere Handlung",
            "unsafe_condition": "Unsicherer Zustand",
            "near_miss": "Beinaheunfall",
        },
        "ru": {
            "positive": "Положительное",
            "unsafe_act": "Опасное действие",
            "unsafe_condition": "Опасное условие",
            "near_miss": "Почти несчастный случай",
        },
    },
    "observation_status": {
        "en": {
            "open": "Open",
            "in_progress": "In progress",
            "closed": "Closed",
        },
        "de": {
            "open": "Offen",
            "in_progress": "In Bearbeitung",
            "closed": "Geschlossen",
        },
        "ru": {
            "open": "Открыто",
            "in_progress": "В работе",
            "closed": "Закрыто",
        },
    },
    "treatment_type": {
        "en": {
            "first_aid": "First aid",
            "medical": "Medical treatment",
            "hospital": "Hospitalization",
            "fatality": "Fatality",
        },
        "de": {
            "first_aid": "Erste Hilfe",
            "medical": "Ärztliche Behandlung",
            "hospital": "Krankenhaus",
            "fatality": "Todesfall",
        },
        "ru": {
            "first_aid": "Первая помощь",
            "medical": "Медицинская помощь",
            "hospital": "Госпитализация",
            "fatality": "Смертельный исход",
        },
    },
}


def _humanize(value: str) -> str:
    """Turn a snake_case code into a readable English fallback label."""
    return value.replace("_", " ").strip().capitalize()


def _normalize_lang(lang: str | None) -> str:
    """Reduce a locale tag to a lower-case two-letter language code."""
    if not lang:
        return "en"
    return lang.split("-")[0].split("_")[0].strip().lower()


def localize(category: str, value: str, lang: str = "en") -> str:
    """Localize a vocabulary word, falling back to English then a humanized code.

    Args:
        category: One of the localization categories, for example
            ``"incident_severity"`` or ``"observation_status"``.
        value: The canonical code to translate, for example ``"near_miss"``.
        lang: Target language tag; anything outside en/de/ru falls back to
            English.

    Returns:
        The localized label. Unknown categories or values fall back to an
        English humanized form of ``value`` so nothing ever renders blank.
    """
    if value is None:
        return ""
    table = _LOCALIZATIONS.get(category)
    if table is None:
        return _humanize(str(value))

    english = table["en"]
    if value not in english:
        return _humanize(str(value))

    code = _normalize_lang(lang)
    lang_map = table.get(code, english)
    return lang_map.get(value, english[value])


def localize_incident_type(value: str, lang: str = "en") -> str:
    """Localize an incident type code."""
    return localize("incident_type", value, lang)


def localize_incident_severity(value: str, lang: str = "en") -> str:
    """Localize an incident severity code."""
    return localize("incident_severity", value, lang)


def localize_incident_status(value: str, lang: str = "en") -> str:
    """Localize an incident status code."""
    return localize("incident_status", value, lang)


def localize_observation_type(value: str, lang: str = "en") -> str:
    """Localize an observation type code."""
    return localize("observation_type", value, lang)


def localize_observation_status(value: str, lang: str = "en") -> str:
    """Localize an observation status code."""
    return localize("observation_status", value, lang)


def localize_treatment_type(value: str, lang: str = "en") -> str:
    """Localize an incident treatment type code."""
    return localize("treatment_type", value, lang)
