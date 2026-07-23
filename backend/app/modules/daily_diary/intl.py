# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, unit-safe rollup helpers for the daily site diary.

These are pure functions (no database, no network, stdlib only) so they
can be unit tested in isolation and reused by the service, the PDF
export, or any subscriber.

Design goals:

* No hidden locale, unit, currency, or working-day assumptions. A diary
  is filled in worldwide, so temperatures may arrive in Celsius or
  Fahrenheit, labour and plant hours always carry an explicit hour unit,
  dates are ISO 8601, and the "working day lost to weather" rule is
  driven by a caller-supplied threshold rather than one country's
  climate.
* Canonical storage. Temperatures are normalised to Celsius (matching
  ``WeatherRecord.temperature_c``) before they are stored; the original
  unit is only a display concern.
* Clarity. Every diary concept (labour hours, plant working vs idle
  hours, weather delay, lost time) has a one-line plain-language
  explanation, and status / condition codes get a plain label.
* Safety. Division by zero (zero crew, zero hours), empty inputs, and
  negative counts are turned into clean ValueErrors or well-defined
  values; the helpers never return NaN or infinity and never raise a
  bare 500.
* Explainability. Each rollup returns its components so a reviewer can
  see exactly how the headline number was derived.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

# ── Numeric guards ────────────────────────────────────────────────────────


def _as_finite_number(value: Any, field: str) -> float:
    """Coerce ``value`` to a finite float or raise ValueError.

    Rejects ``None``, non-numeric input, NaN and infinity so a bad cell
    on a site form becomes a clean input error instead of a NaN that
    silently poisons every downstream rollup.
    """
    if value is None:
        raise ValueError(f"{field} is required (got None)")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return number


def _non_negative_number(value: Any, field: str) -> float:
    """Coerce to a finite, non-negative float or raise ValueError."""
    number = _as_finite_number(value, field)
    if number < 0:
        raise ValueError(f"{field} cannot be negative, got {number}")
    return number


def _non_negative_int(value: Any, field: str) -> int:
    """Coerce to a non-negative integer count or raise ValueError.

    Accepts whole-number floats (e.g. ``5.0``) since site forms often
    submit counts as strings or floats, but rejects fractional people.
    """
    number = _as_finite_number(value, field)
    if number < 0:
        raise ValueError(f"{field} cannot be negative, got {number}")
    if number != int(number):
        raise ValueError(f"{field} must be a whole count, got {number}")
    return int(number)


def _get(source: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an attribute on an object."""
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


# ── Temperature: accept C or F, store canonical Celsius ───────────────────


_CELSIUS_UNITS = {"c", "celsius", "degc", "°c"}
_FAHRENHEIT_UNITS = {"f", "fahrenheit", "degf", "°f"}


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return _as_finite_number(celsius, "celsius") * 9.0 / 5.0 + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (_as_finite_number(fahrenheit, "fahrenheit") - 32.0) * 5.0 / 9.0


def normalize_temperature(value: Any, unit: str = "C") -> float:
    """Return the canonical Celsius value for a temperature reading.

    Args:
        value: The numeric reading in the given unit.
        unit: The unit the reading was recorded in. Accepts C / Celsius
            or F / Fahrenheit, case-insensitive. Canonical storage is
            always Celsius, so a Fahrenheit reading is converted.

    Raises:
        ValueError: If the unit is unknown or the value is not a finite
            number.
    """
    number = _as_finite_number(value, "temperature")
    key = (unit or "").strip().lower()
    if key in _CELSIUS_UNITS:
        return round(number, 4)
    if key in _FAHRENHEIT_UNITS:
        return round(fahrenheit_to_celsius(number), 4)
    raise ValueError(
        f"Unknown temperature unit {unit!r}; use C/Celsius or F/Fahrenheit",
    )


def format_temperature(celsius: float, unit: str = "C") -> str:
    """Format a canonical Celsius value for display in C or F.

    The stored value is Celsius; a site in a Fahrenheit-using region can
    display it in F without any change to storage.
    """
    number = _as_finite_number(celsius, "celsius")
    key = (unit or "").strip().lower()
    if key in _CELSIUS_UNITS:
        return f"{round(number, 1)} C"
    if key in _FAHRENHEIT_UNITS:
        return f"{round(celsius_to_fahrenheit(number), 1)} F"
    raise ValueError(
        f"Unknown temperature unit {unit!r}; use C/Celsius or F/Fahrenheit",
    )


# ── Labour rollup: headcount and total labour hours ───────────────────────


def labour_rollup(lines: list[Any]) -> dict[str, Any]:
    """Roll a day's labour lines up into headcount and total labour hours.

    Each line is a mapping or object carrying:

        * ``headcount``: number of workers on that line (whole count).
        * ``hours``: hours worked per worker on that line (the explicit
          hour unit; there is no assumed shift length).

    Total labour hours are ``sum(headcount * hours)`` across the lines,
    which is the person-hours worked on site that day. The per-line
    contribution is echoed back under ``components`` so the headline is
    auditable.

    An empty list is valid and yields zeros. Negative or fractional
    counts, and negative or non-finite hours, raise ValueError.
    """
    total_headcount = 0
    total_labour_hours = 0.0
    components: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        headcount = _non_negative_int(_get(line, "headcount", 0), f"lines[{index}].headcount")
        hours = _non_negative_number(_get(line, "hours", 0), f"lines[{index}].hours")
        line_hours = headcount * hours
        total_headcount += headcount
        total_labour_hours += line_hours
        components.append(
            {
                "label": str(_get(line, "label", "") or _get(line, "company", "") or ""),
                "headcount": headcount,
                "hours_per_worker": round(hours, 4),
                "labour_hours": round(line_hours, 4),
            },
        )
    return {
        "total_headcount": total_headcount,
        "total_labour_hours": round(total_labour_hours, 4),
        "hour_unit": "hours",
        "components": components,
        "explanation": (
            "total_labour_hours is the sum over every labour line of "
            "headcount times hours worked per worker (person-hours)."
        ),
    }


def average_labour_hours_per_worker(total_labour_hours: float, headcount: int) -> float:
    """Mean hours worked per worker, guarded against a zero crew.

    With no crew on site the mean is undefined; rather than divide by
    zero we return a well-defined ``0.0`` (no crew means no hours per
    worker to report).
    """
    hours = _non_negative_number(total_labour_hours, "total_labour_hours")
    crew = _non_negative_int(headcount, "headcount")
    if crew == 0:
        return 0.0
    return round(hours / crew, 4)


# ── Plant (equipment) utilization: working vs idle hours ──────────────────


def plant_utilization(working_hours: float, idle_hours: float) -> dict[str, Any]:
    """Split a plant item's day into working vs idle and give utilization.

    Utilization is ``working_hours / (working_hours + idle_hours)``,
    i.e. the share of the on-site hours that the plant was actually
    productive. If the plant logged no hours at all the total is zero;
    rather than divide by zero we report utilization ``0.0`` and flag it
    so the caller can see it was simply not used, not a data error.

    Negative or non-finite hours raise ValueError.
    """
    working = _non_negative_number(working_hours, "working_hours")
    idle = _non_negative_number(idle_hours, "idle_hours")
    total = working + idle
    if total == 0:
        utilization = 0.0
    else:
        utilization = round(working / total, 4)
    return {
        "working_hours": round(working, 4),
        "idle_hours": round(idle, 4),
        "total_hours": round(total, 4),
        "utilization": utilization,
        "utilization_pct": round(utilization * 100, 1),
        "hour_unit": "hours",
        "has_hours": total > 0,
        "explanation": (
            "utilization is working_hours divided by the sum of working "
            "and idle hours; with zero total hours it is reported as 0.0."
        ),
    }


# ── Weather delay: data-driven, not hardcoded to one climate ──────────────


@dataclass(frozen=True)
class WeatherDelayThreshold:
    """Per-project weather limits that make a working day lost.

    Every field is optional. A field left as ``None`` means "no limit on
    this measure", so a hot-climate site can set only ``max_temp_c`` and
    ``max_precipitation_mm`` while a cold-climate site sets ``min_temp_c``.
    This keeps the lost-day rule data-driven instead of baking in one
    country's climate.
    """

    min_temp_c: float | None = None
    max_temp_c: float | None = None
    max_precipitation_mm: float | None = None
    max_wind_speed_kmh: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the threshold as a plain dict for reports and payloads."""
        return {
            "min_temp_c": self.min_temp_c,
            "max_temp_c": self.max_temp_c,
            "max_precipitation_mm": self.max_precipitation_mm,
            "max_wind_speed_kmh": self.max_wind_speed_kmh,
        }


# A neutral starting point, meant to be overridden per project or region.
# These are generic site limits, not tied to any single climate.
DEFAULT_WEATHER_DELAY_THRESHOLD = WeatherDelayThreshold(
    min_temp_c=-15.0,
    max_temp_c=45.0,
    max_precipitation_mm=25.0,
    max_wind_speed_kmh=60.0,
)


def weather_delay_assessment(
    *,
    temperature_c: Any = None,
    precipitation_mm: Any = None,
    wind_speed_kmh: Any = None,
    threshold: WeatherDelayThreshold = DEFAULT_WEATHER_DELAY_THRESHOLD,
) -> dict[str, Any]:
    """Decide whether the weather makes a working day lost, and say why.

    Only the measures that are supplied are checked, and only against the
    limits the threshold actually sets. A measure whose threshold is
    ``None`` is never a reason on its own. Inputs are expected to be
    canonical: temperature in Celsius, precipitation in millimetres over
    the day, wind speed in km/h.

    Returns a dict with ``lost`` (bool), ``reasons`` (plain-language
    strings), the ``components`` that were checked, and the ``threshold``
    that was applied, so the decision is fully explainable.
    """
    reasons: list[str] = []
    components: dict[str, float | None] = {
        "temperature_c": None,
        "precipitation_mm": None,
        "wind_speed_kmh": None,
    }

    if temperature_c is not None:
        temp = _as_finite_number(temperature_c, "temperature_c")
        components["temperature_c"] = round(temp, 4)
        if threshold.min_temp_c is not None and temp < threshold.min_temp_c:
            reasons.append(
                f"temperature {temp} C below the {threshold.min_temp_c} C lower limit",
            )
        if threshold.max_temp_c is not None and temp > threshold.max_temp_c:
            reasons.append(
                f"temperature {temp} C above the {threshold.max_temp_c} C upper limit",
            )

    if precipitation_mm is not None:
        precip = _non_negative_number(precipitation_mm, "precipitation_mm")
        components["precipitation_mm"] = round(precip, 4)
        if threshold.max_precipitation_mm is not None and precip > threshold.max_precipitation_mm:
            reasons.append(
                f"precipitation {precip} mm above the {threshold.max_precipitation_mm} mm limit",
            )

    if wind_speed_kmh is not None:
        wind = _non_negative_number(wind_speed_kmh, "wind_speed_kmh")
        components["wind_speed_kmh"] = round(wind, 4)
        if threshold.max_wind_speed_kmh is not None and wind > threshold.max_wind_speed_kmh:
            reasons.append(
                f"wind {wind} km/h above the {threshold.max_wind_speed_kmh} km/h limit",
            )

    return {
        "lost": bool(reasons),
        "reasons": reasons,
        "components": components,
        "threshold": threshold.as_dict(),
        "explanation": (
            "a working day is flagged lost when any supplied weather "
            "measure crosses the limit set for it; unset limits are ignored."
        ),
    }


# ── ISO 8601 date handling ────────────────────────────────────────────────


def to_iso_date(value: Any) -> str:
    """Normalise a date, datetime, or string to an ISO 8601 date string.

    Accepts a ``date``, a ``datetime`` (its date part is used), or a
    string that already starts with ``YYYY-MM-DD``. Raises ValueError on
    anything else, so a malformed date never flows into a summary line.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise ValueError(f"Not an ISO 8601 date: {value!r}") from exc
    raise ValueError(f"Cannot read a date from {value!r}")


# ── Plain-language labels and one-line explanations ───────────────────────


_CONCEPT_EXPLANATIONS: dict[str, str] = {
    "headcount": "Headcount is how many workers were on site that day.",
    "labour_hours": (
        "Labour hours are person-hours: workers times the hours each "
        "worked (10 workers for 8 hours is 80 labour hours)."
    ),
    "plant_hours": (
        "Plant hours are how long an item of equipment was on site, split into working hours and idle hours."
    ),
    "plant_working": "Plant working hours are the hours the equipment was actually in use.",
    "plant_idle": ("Plant idle hours are the hours the equipment was on site but standing, waiting, or not in use."),
    "utilization": ("Utilization is the share of on-site hours that plant spent working rather than idle."),
    "weather_delay": (
        "A weather delay is time when work had to stop because the weather crossed a limit set for the site."
    ),
    "lost_time": (
        "Lost time is productive hours the site could not use, for "
        "example because of weather, access, or waiting on materials."
    ),
}


def explain_concept(name: str) -> str:
    """Return a one-line plain-language explanation of a diary concept.

    Unknown names get a neutral fallback rather than raising, so a UI can
    call this for any label without a guard.
    """
    key = (name or "").strip().lower()
    return _CONCEPT_EXPLANATIONS.get(
        key,
        f"{humanize_code(name)} is a value recorded in the daily site diary.",
    )


def humanize_code(code: Any) -> str:
    """Turn a machine code like ``rain_heavy`` into ``Rain heavy``.

    Used as the safe fallback for any status or condition code so the UI
    never shows a raw snake_case token to a site user.
    """
    text = str(code or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").strip().capitalize()


_WEATHER_CONDITION_LABELS: dict[str, str] = {
    "clear": "Clear sky",
    "mainly_clear": "Mainly clear",
    "partly_cloudy": "Partly cloudy",
    "overcast": "Overcast",
    "fog": "Fog",
    "fog_rime": "Freezing fog",
    "drizzle_light": "Light drizzle",
    "drizzle_moderate": "Moderate drizzle",
    "drizzle_dense": "Heavy drizzle",
    "rain_light": "Light rain",
    "rain_moderate": "Moderate rain",
    "rain_heavy": "Heavy rain",
    "freezing_rain_light": "Light freezing rain",
    "freezing_rain_heavy": "Heavy freezing rain",
    "snow_light": "Light snow",
    "snow_moderate": "Moderate snow",
    "snow_heavy": "Heavy snow",
    "rain_showers_light": "Light rain showers",
    "rain_showers_moderate": "Moderate rain showers",
    "rain_showers_violent": "Violent rain showers",
    "snow_showers_light": "Light snow showers",
    "snow_showers_heavy": "Heavy snow showers",
    "thunderstorm": "Thunderstorm",
    "thunderstorm_hail_light": "Thunderstorm with light hail",
    "thunderstorm_hail_heavy": "Thunderstorm with heavy hail",
}


def describe_weather_condition(code: Any) -> str:
    """Return a plain label for a stored weather condition code."""
    key = str(code or "").strip().lower()
    if not key:
        return "Not recorded"
    return _WEATHER_CONDITION_LABELS.get(key, humanize_code(key))


_DELAY_CAUSE_LABELS: dict[str, str] = {
    "weather": "Weather",
    "access": "Site access",
    "design_change": "Design change",
    "materials": "Waiting on materials",
    "labour_shortage": "Labour shortage",
    "equipment_breakdown": "Equipment breakdown",
    "instruction": "Waiting on instruction",
    "permit": "Waiting on permit or approval",
    "utilities": "Utilities or services",
    "other": "Other",
}


def describe_delay_cause(code: Any) -> str:
    """Return a plain label for a delay-cause code."""
    key = str(code or "").strip().lower()
    if not key:
        return "Not recorded"
    return _DELAY_CAUSE_LABELS.get(key, humanize_code(key))


# ── Daily summary line ────────────────────────────────────────────────────


def daily_summary_line(
    *,
    diary_date: Any,
    headcount: Any = 0,
    labour_hours: Any = 0.0,
    plant: Mapping[str, Any] | None = None,
    weather_delay: Mapping[str, Any] | None = None,
) -> str:
    """Build one plain-language sentence summarising a diary day.

    Args:
        diary_date: The day, normalised to ISO 8601.
        headcount: Workers on site (whole count).
        labour_hours: Total person-hours worked.
        plant: Optional result of :func:`plant_utilization`.
        weather_delay: Optional result of :func:`weather_delay_assessment`.

    The sentence is deliberately simple so a site engineer reads it in a
    second. Invalid counts or hours raise ValueError.
    """
    day = to_iso_date(diary_date)
    crew = _non_negative_int(headcount, "headcount")
    hours = _non_negative_number(labour_hours, "labour_hours")
    worker_word = "worker" if crew == 1 else "workers"
    parts = [f"{day}: {crew} {worker_word} on site, {round(hours, 1)} labour hours"]

    if plant is not None and plant.get("has_hours"):
        parts.append(
            f"plant {plant['utilization_pct']}% utilized "
            f"({plant['working_hours']} h working / {plant['idle_hours']} h idle)",
        )

    if weather_delay is not None:
        if weather_delay.get("lost"):
            why = "; ".join(weather_delay.get("reasons", [])) or "weather over threshold"
            parts.append(f"weather: working day lost ({why})")
        else:
            parts.append("weather: within working limits")

    return ", ".join(parts) + "."
