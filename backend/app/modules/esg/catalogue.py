# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ESG Site Performance metric catalogue.

A fixed, code-defined vocabulary of *operational* site ESG metrics tracked per
reporting period (energy, water, waste, on-site CO2e, local labour, training,
safety, governance). This is deliberately a Python constant, not a database
table: the set of metrics is a curated standard that ships with the platform,
so it is versioned with the code and needs no migration to evolve.

This tracks what actually happens on the construction site each month. It is
distinct from *embodied* carbon (material life-cycle A1-A5), which lives in the
carbon / 6D module.

Pure module: it imports nothing from the database, SQLAlchemy or Pydantic, so it
is safe to import from a router, a service, a validator or a database-free test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricCategory(StrEnum):
    """The three ESG pillars a metric belongs to."""

    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    GOVERNANCE = "governance"


class MetricDirection(StrEnum):
    """Whether a lower or a higher reading is the good outcome.

    Drives the direction-aware good/bad colouring on the dashboard: for a
    ``lower_better`` metric (diesel, waste, incidents) a reading at or below its
    target is good; for a ``higher_better`` metric (recycling rate, local
    labour, training) a reading at or above its target is good.
    """

    LOWER_BETTER = "lower_better"
    HIGHER_BETTER = "higher_better"


# The unit that flags a percentage metric. A metric measured in this unit is
# range-checked to 0..100 by the service guard (see ``guard.is_percent_metric``).
PERCENT_UNIT = "%"


@dataclass(frozen=True)
class MetricDefinition:
    """One operational ESG metric definition.

    Attributes:
        key: Stable machine identifier, also the i18n key suffix
            (``esg.<key>`` on the frontend). Never change a shipped key.
        category: Which ESG pillar the metric belongs to.
        label: English default label; the UI localises it via i18n.
        unit: Human unit the reading is captured in (``L``, ``kWh``, ``%`` ...).
        direction: Whether lower or higher is the good outcome.
        description: One-line, plain-language explainer for a site engineer.
    """

    key: str
    category: MetricCategory
    label: str
    unit: str
    direction: MetricDirection
    description: str = ""


# ── The catalogue ─────────────────────────────────────────────────────────────
#
# Ordered environmental -> social -> governance so the dashboard renders the
# three pillars in a stable, familiar order.
METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    # Environmental
    MetricDefinition(
        key="energy_diesel_l",
        category=MetricCategory.ENVIRONMENTAL,
        label="Diesel consumed",
        unit="L",
        direction=MetricDirection.LOWER_BETTER,
        description="On-site diesel burned by plant, generators and vehicles in the period.",
    ),
    MetricDefinition(
        key="energy_grid_kwh",
        category=MetricCategory.ENVIRONMENTAL,
        label="Grid electricity",
        unit="kWh",
        direction=MetricDirection.LOWER_BETTER,
        description="Grid electricity drawn by the site in the period.",
    ),
    MetricDefinition(
        key="water_m3",
        category=MetricCategory.ENVIRONMENTAL,
        label="Water consumed",
        unit="m3",
        direction=MetricDirection.LOWER_BETTER,
        description="Mains and abstracted water used on site in the period.",
    ),
    MetricDefinition(
        key="waste_total_t",
        category=MetricCategory.ENVIRONMENTAL,
        label="Waste generated",
        unit="t",
        direction=MetricDirection.LOWER_BETTER,
        description="Total construction and demolition waste removed from site.",
    ),
    MetricDefinition(
        key="waste_recycled_pct",
        category=MetricCategory.ENVIRONMENTAL,
        label="Waste recycled",
        unit=PERCENT_UNIT,
        direction=MetricDirection.HIGHER_BETTER,
        description="Share of site waste diverted from landfill for reuse or recycling.",
    ),
    MetricDefinition(
        key="co2e_site_t",
        category=MetricCategory.ENVIRONMENTAL,
        label="Site CO2e emissions",
        unit="t CO2e",
        direction=MetricDirection.LOWER_BETTER,
        description="Operational carbon of running the site (fuel plus purchased energy).",
    ),
    # Social
    MetricDefinition(
        key="local_labour_pct",
        category=MetricCategory.SOCIAL,
        label="Local labour",
        unit=PERCENT_UNIT,
        direction=MetricDirection.HIGHER_BETTER,
        description="Share of the site workforce hired from the local area.",
    ),
    MetricDefinition(
        key="training_hours",
        category=MetricCategory.SOCIAL,
        label="Training delivered",
        unit="h",
        direction=MetricDirection.HIGHER_BETTER,
        description="Person-hours of training and toolbox instruction delivered on site.",
    ),
    MetricDefinition(
        key="apprentices",
        category=MetricCategory.SOCIAL,
        label="Apprentices on site",
        unit="count",
        direction=MetricDirection.HIGHER_BETTER,
        description="Number of apprentices or trainees working on site in the period.",
    ),
    MetricDefinition(
        key="incidents",
        category=MetricCategory.SOCIAL,
        label="Safety incidents",
        unit="count",
        direction=MetricDirection.LOWER_BETTER,
        description="Recordable health and safety incidents in the period.",
    ),
    MetricDefinition(
        key="near_misses",
        category=MetricCategory.SOCIAL,
        label="Near misses",
        unit="count",
        direction=MetricDirection.LOWER_BETTER,
        description="Near-miss events recorded in the period.",
    ),
    # Governance
    MetricDefinition(
        key="audits_passed_pct",
        category=MetricCategory.GOVERNANCE,
        label="Audits passed",
        unit=PERCENT_UNIT,
        direction=MetricDirection.HIGHER_BETTER,
        description="Share of quality, safety and environmental audits passed in the period.",
    ),
    MetricDefinition(
        key="compliance_findings_open",
        category=MetricCategory.GOVERNANCE,
        label="Open compliance findings",
        unit="count",
        direction=MetricDirection.LOWER_BETTER,
        description="Compliance or non-conformance findings still open at period end.",
    ),
    MetricDefinition(
        key="subcontractor_prequalified_pct",
        category=MetricCategory.GOVERNANCE,
        label="Subcontractors prequalified",
        unit=PERCENT_UNIT,
        direction=MetricDirection.HIGHER_BETTER,
        description="Share of active subcontractors that passed prequalification.",
    ),
)


# Fast lookup by key. Built once at import; the catalogue is immutable.
_BY_KEY: dict[str, MetricDefinition] = {definition.key: definition for definition in METRIC_DEFINITIONS}

# Canonical pillar order for grouped views.
CATEGORY_ORDER: tuple[str, ...] = tuple(category.value for category in MetricCategory)


def get_metric(key: str) -> MetricDefinition | None:
    """Return the metric definition for ``key``, or ``None`` if unknown.

    The match is exact and case-sensitive: metric keys are machine identifiers.
    """
    if not isinstance(key, str):
        return None
    return _BY_KEY.get(key.strip())


def metric_keys() -> list[str]:
    """Return every catalogue key in definition order."""
    return [definition.key for definition in METRIC_DEFINITIONS]


def is_percent_metric(key: str) -> bool:
    """Return ``True`` when ``key`` is a percentage metric (unit ``%``).

    Percentage metrics are range-checked to 0..100 by the service guard. An
    unknown key returns ``False`` (it is rejected earlier by the key check).
    """
    definition = get_metric(key)
    return definition is not None and definition.unit == PERCENT_UNIT


def metrics_by_category() -> dict[str, list[MetricDefinition]]:
    """Return the catalogue grouped by pillar, each pillar in definition order.

    Every canonical pillar is present as a key, even when it holds no metrics,
    so callers get a stable shape.
    """
    grouped: dict[str, list[MetricDefinition]] = {value: [] for value in CATEGORY_ORDER}
    for definition in METRIC_DEFINITIONS:
        grouped[definition.category.value].append(definition)
    return grouped
