# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Whole-life cost (ISO 15686-5) and B6 operational-carbon pure math.

This is the 6D Phase 2 engine layer. Every function here is pure and
import-light (standard library only: ``decimal`` + typing). It never imports
the app, the database, FastAPI or any ORM model, so it is unit-testable on
Python 3.11 while the rest of the app requires 3.12.

Two families of function live here:

* Whole-life cost per ISO 15686-5. The life-cycle cost of an element or
  system is ``capex + discounted opex + discounted replacements + discounted
  end-of-life``, where every future cost is brought to a present value with a
  real discount rate. Replacement cycles are keyed to a component service life
  and the study period (the same B4/B5 logic EN 15978 uses on the carbon side).

* B6 operational carbon. Recurring use-phase carbon is
  ``annual energy demand x grid emission factor``, integrated over the study
  period. This mirrors the embodied ``quantity x emission factor`` on the
  carbon side - the same multiply-and-roll-up operation, one stage later in
  the life cycle.

Money and quantities are ``Decimal`` end to end so a float regression cannot
silently corrupt a present-value calculation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Modelling defaults (documented, overridable per request)
# ---------------------------------------------------------------------------

# Typical building study period for a whole-life assessment (years).
DEFAULT_STUDY_PERIOD_YEARS: int = 60
# Real discount rate used to net-present-value future costs (3.5%), a common
# public-sector real rate. Callers override per study.
DEFAULT_DISCOUNT_RATE: str = "0.035"
# Annual operation + maintenance cost modelled as a share of capex when the
# asset carries no explicit opex figure (2% of capex per year).
DEFAULT_OPEX_RATE: str = "0.02"
# End-of-life / disposal cost modelled as a share of capex when the asset
# carries no explicit figure (10% of capex).
DEFAULT_EOL_RATE: str = "0.10"
# Fallback component service life when the asset register carries none (years).
DEFAULT_SERVICE_LIFE_YEARS: int = 30

# Property keys a converted BIM element / asset register may carry cost and
# service-life data under. Read in order; first positive value wins.
_CAPEX_KEYS: tuple[str, ...] = (
    "capex",
    "capital_cost",
    "construction_cost",
    "acquisition_cost",
    "initial_cost",
)
_OPEX_KEYS: tuple[str, ...] = (
    "annual_opex",
    "annual_operating_cost",
    "annual_maintenance_cost",
    "opex_per_year",
)
_REPLACEMENT_KEYS: tuple[str, ...] = (
    "replacement_cost",
    "renewal_cost",
)
_EOL_KEYS: tuple[str, ...] = (
    "eol_cost",
    "disposal_cost",
    "end_of_life_cost",
)
_SERVICE_LIFE_KEYS: tuple[str, ...] = (
    "service_life_years",
    "expected_service_life_years",
    "design_life_years",
    "replacement_interval_years",
    "service_life",
)
# Property keys carrying an explicit annual operational energy demand (kWh/yr).
_ENERGY_KEYS: tuple[str, ...] = (
    "annual_energy_kwh",
    "energy_kwh_per_year",
    "annual_energy_kwh_per_year",
    "operational_energy_kwh",
)
# Keys for a rated electrical power (W) and annual run hours, from which an
# annual energy demand is derived (power x hours / 1000).
_POWER_KEYS: tuple[str, ...] = ("power_rating_w", "rated_power_w", "power_w")
_HOURS_KEYS: tuple[str, ...] = (
    "annual_operating_hours",
    "operating_hours_per_year",
    "annual_run_hours",
)


def _dec(value: Any) -> Decimal:
    """Coerce any numeric-ish value to ``Decimal`` via ``str`` (no float path)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _read_positive(source: Any, keys: tuple[str, ...]) -> Decimal | None:
    """Return the first strictly-positive ``Decimal`` among ``keys`` in a dict."""
    if not isinstance(source, dict):
        return None
    for key in keys:
        raw = source.get(key)
        if raw is None:
            continue
        try:
            value = _dec(raw)
        except (ArithmeticError, ValueError, TypeError):
            continue
        if value > 0:
            return value
    return None


def _read_positive_int(source: Any, keys: tuple[str, ...]) -> int | None:
    """Return the first strictly-positive integer among ``keys`` in a dict."""
    value = _read_positive(source, keys)
    if value is None:
        return None
    return int(value)


# ---------------------------------------------------------------------------
# Present-value primitives
# ---------------------------------------------------------------------------


def net_present_value(
    future_cost: Any,
    discount_rate: Any,
    years: int,
) -> Decimal:
    """Present value of a single future cost ``years`` from now.

    ``PV = C / (1 + d) ** n`` (ISO 15686-5 discounting). A cost incurred now
    (``years == 0``) is returned unchanged.

    Args:
        future_cost: The nominal future cost ``C``.
        discount_rate: Real discount rate ``d`` (e.g. ``0.035`` for 3.5%).
        years: Whole years ``n`` from the present (must be >= 0).

    Returns:
        The discounted present value as a ``Decimal``.

    Raises:
        ValueError: ``years`` is negative or the discount rate is <= -1.
    """
    n = int(years)
    if n < 0:
        raise ValueError("years must be >= 0")
    cost = _dec(future_cost)
    rate = _dec(discount_rate)
    if rate <= Decimal("-1"):
        raise ValueError("discount_rate must be greater than -1")
    if n == 0 or rate == 0:
        return cost
    return cost / ((Decimal("1") + rate) ** n)


def present_value_annuity(
    annual_cost: Any,
    discount_rate: Any,
    years: int,
) -> Decimal:
    """Present value of a constant annual cost paid at the end of years 1..N.

    Computed as the explicit sum of per-year discounted costs so it stays
    identical, term for term, to discounting each year with
    :func:`net_present_value`. With a zero discount rate this is
    ``annual_cost * years``.

    Args:
        annual_cost: The recurring annual cost ``A``.
        discount_rate: Real discount rate ``d``.
        years: Number of annual payments ``N`` (<= 0 yields ``0``).

    Returns:
        The present value of the annuity as a ``Decimal``.
    """
    n = int(years)
    amount = _dec(annual_cost)
    if n <= 0 or amount == 0:
        return Decimal("0")
    rate = _dec(discount_rate)
    if rate == 0:
        return amount * n
    base = Decimal("1") + rate
    total = Decimal("0")
    for year in range(1, n + 1):
        total += amount / (base**year)
    return total


def replacement_years(service_life_years: int, study_period_years: int) -> list[int]:
    """Years within the study period at which a component is replaced.

    A component with service life ``L`` is replaced at years ``L, 2L, 3L, ...``
    for as long as that year is strictly inside the study period ``P`` (a
    replacement in the final year is not modelled - the asset is disposed of at
    end of life instead). The count equals ``ceil(P / L) - 1``.

    Args:
        service_life_years: Component service life ``L`` (years).
        study_period_years: Study period ``P`` (years).

    Returns:
        Ascending list of replacement years, empty when either input is <= 0
        or the service life outlasts the study period.
    """
    life = int(service_life_years)
    period = int(study_period_years)
    if life <= 0 or period <= 0:
        return []
    years: list[int] = []
    step = life
    while step < period:
        years.append(step)
        step += life
    return years


def replacement_present_value(
    replacement_cost: Any,
    service_life_years: int,
    study_period_years: int,
    discount_rate: Any,
) -> Decimal:
    """Present value of every in-period replacement of a component.

    Sums :func:`net_present_value` of ``replacement_cost`` at each year returned
    by :func:`replacement_years`.
    """
    cost = _dec(replacement_cost)
    if cost == 0:
        return Decimal("0")
    total = Decimal("0")
    for year in replacement_years(service_life_years, study_period_years):
        total += net_present_value(cost, discount_rate, year)
    return total


def residual_value(
    *,
    capex: Any,
    replacement_cost: Any,
    service_life_years: int,
    study_period_years: int,
) -> Decimal:
    """Straight-line residual value of a component at the study-period end.

    ISO 15686-5 credits the unexpired worth of a component still in service at
    the end of the study period back against the whole-life cost - otherwise a
    heating plant one year into a 20-year life at the study end is written off
    as if it were scrap. The component is installed at year 0 (funded by capex)
    and re-installed at each replacement year; the installation still live at
    the study end has consumed only part of its service life, and the remaining
    fraction is worth crediting back.

    The residual is pro-rated straight-line on the cost of the *last*
    installation: ``basis x remaining_life / service_life``, where ``basis`` is
    the replacement cost once at least one replacement has occurred, else the
    capex. The returned figure is a nominal value at the study end (year ``P``);
    the caller discounts it to a present value.

    Returns ``Decimal("0")`` when the service life is unknown (<= 0), when the
    last installation reaches exactly end of life at the study end (nothing
    unexpired), or when the basis cost is not positive.
    """
    life = int(service_life_years)
    period = int(study_period_years)
    if life <= 0 or period <= 0:
        return Decimal("0")
    repl_years = replacement_years(life, period)
    if repl_years:
        last_install = repl_years[-1]
        basis = _dec(replacement_cost)
    else:
        last_install = 0
        basis = _dec(capex)
    if basis <= 0:
        return Decimal("0")
    remaining_life = life - (period - last_install)
    if remaining_life <= 0:
        return Decimal("0")
    fraction = Decimal(remaining_life) / Decimal(life)
    # A component cannot be worth more than its installed cost, even if the
    # study period ends before its first anniversary.
    if fraction > 1:
        fraction = Decimal("1")
    return basis * fraction


def compute_life_cycle_cost(
    *,
    capex: Any,
    annual_opex: Any,
    replacement_cost: Any,
    service_life_years: int,
    eol_cost: Any,
    discount_rate: Any,
    study_period_years: int,
    include_residual_value: bool = True,
) -> dict[str, Any]:
    """Whole-life cost of one element or system per ISO 15686-5.

    ``LCC = capex + PV(opex) + PV(replacements) + PV(end-of-life)
    - PV(residual value)``. Capex is incurred at year 0 and is not discounted;
    every other term is brought to a present value with the real discount rate.
    The residual value is the unexpired worth of the component still in service
    at the study end and is credited back (a negative cash flow), per ISO
    15686-5; pass ``include_residual_value=False`` to reproduce the pre-residual
    figure.

    Args:
        capex: Initial construction / acquisition cost (year 0).
        annual_opex: Recurring annual operation + maintenance cost.
        replacement_cost: Cost of one like-for-like replacement (B4/B5).
        service_life_years: Component service life driving the replacement cycle.
        eol_cost: End-of-life / disposal cost incurred at the study end (C).
        discount_rate: Real discount rate used for present values.
        study_period_years: Study period ``P`` (years).
        include_residual_value: Credit the study-end residual value (default on).

    Returns:
        A dict of the present-value components (capex, opex, replacements,
        end-of-life and the residual-value credit), the replacement schedule,
        and the whole-life cost, all as ``Decimal`` (plus plain-int counts).
    """
    period = int(study_period_years)
    capex_pv = _dec(capex)
    opex_pv = present_value_annuity(annual_opex, discount_rate, period)
    repl_years = replacement_years(service_life_years, period)
    replacement_pv = Decimal("0")
    repl_cost = _dec(replacement_cost)
    for year in repl_years:
        replacement_pv += net_present_value(repl_cost, discount_rate, year)
    eol_pv = net_present_value(eol_cost, discount_rate, period)
    residual_nominal = (
        residual_value(
            capex=capex,
            replacement_cost=replacement_cost,
            service_life_years=service_life_years,
            study_period_years=period,
        )
        if include_residual_value
        else Decimal("0")
    )
    residual_pv = net_present_value(residual_nominal, discount_rate, period)
    whole_life_cost = capex_pv + opex_pv + replacement_pv + eol_pv - residual_pv
    return {
        "capex": capex_pv,
        "capex_pv": capex_pv,
        "annual_opex": _dec(annual_opex),
        "opex_pv": opex_pv,
        "replacement_cost": repl_cost,
        "replacement_pv": replacement_pv,
        "replacement_count": len(repl_years),
        "replacement_years": repl_years,
        "eol_cost": _dec(eol_cost),
        "eol_pv": eol_pv,
        "residual_value": residual_nominal,
        "residual_value_pv": residual_pv,
        "service_life_years": int(service_life_years),
        "discount_rate": _dec(discount_rate),
        "study_period_years": period,
        "whole_life_cost": whole_life_cost,
    }


# ---------------------------------------------------------------------------
# B6 operational carbon
# ---------------------------------------------------------------------------


def annual_operational_carbon(annual_energy_kwh: Any, grid_factor: Any) -> Decimal:
    """Annual B6 carbon = annual energy demand x grid emission factor.

    The same multiply as embodied ``quantity x emission factor``, one life-cycle
    stage later. ``grid_factor`` is in kgCO2e per kWh.
    """
    return _dec(annual_energy_kwh) * _dec(grid_factor)


def operational_carbon_over_period(
    annual_energy_kwh: Any,
    grid_factor: Any,
    study_period_years: int,
) -> dict[str, Any]:
    """Roll annual B6 operational carbon over the whole study period.

    Returns the annual figure and the period total (annual x years), so the
    period total can be booked as the B6 stage carbon alongside embodied A1-A5.
    """
    period = int(study_period_years)
    annual = annual_operational_carbon(annual_energy_kwh, grid_factor)
    return {
        "annual_carbon_kg": annual,
        "carbon_kg": annual * period,
        "study_period_years": period,
    }


def cost_of_carbon(carbon_kg: Any, price_per_tonne_co2e: Any) -> Decimal:
    """Monetise carbon: ``(carbon_kg / 1000) x price per tonne CO2e``.

    Lets a whole-life view surface the societal cost of the whole-life carbon
    next to the whole-life cost, without conflating the two rollups.
    """
    return (_dec(carbon_kg) / Decimal("1000")) * _dec(price_per_tonne_co2e)


def element_annual_energy_kwh(
    quantities: Any,
    asset_info: Any,
) -> tuple[Decimal, str] | None:
    """Read an element's annual operational energy demand (kWh/yr).

    Resolution order (first positive wins):

    1. An explicit annual-energy field on the asset register (``asset_info``).
    2. An explicit annual-energy field on the element geometry (``quantities``).
    3. A rated power (W) x annual run hours on the asset register, converted to
       kWh (``power x hours / 1000``).

    Returns ``(annual_kwh, source)`` where source is one of ``asset_info`` /
    ``element`` / ``asset_power_rating``, or ``None`` when the element carries no
    usable energy signal (the caller may then fall back to a modelled intensity
    at the building level).
    """
    from_asset = _read_positive(asset_info, _ENERGY_KEYS)
    if from_asset is not None:
        return from_asset, "asset_info"
    from_element = _read_positive(quantities, _ENERGY_KEYS)
    if from_element is not None:
        return from_element, "element"
    power = _read_positive(asset_info, _POWER_KEYS)
    hours = _read_positive(asset_info, _HOURS_KEYS)
    if power is not None and hours is not None:
        return (power * hours) / Decimal("1000"), "asset_power_rating"
    return None


def service_life_from_asset_info(
    asset_info: Any,
    properties: Any = None,
    default: int | None = None,
) -> int | None:
    """Read a component service life (years) from the asset register.

    Looks at ``asset_info`` first (ISO 19650 Asset Information Model), then the
    element ``properties``, then falls back to ``default``. Returns ``None`` when
    nothing usable is present and no default is given.
    """
    hit = _read_positive_int(asset_info, _SERVICE_LIFE_KEYS)
    if hit is None:
        hit = _read_positive_int(properties, _SERVICE_LIFE_KEYS)
    if hit is not None and hit > 0:
        return hit
    if default is not None and int(default) > 0:
        return int(default)
    return None


def _confidence_from_provenance(*, capex_from_asset: bool, service_life_from_asset: bool) -> str:
    """Map how much of an LCC input came from the asset register to a band."""
    if capex_from_asset and service_life_from_asset:
        return "high"
    if capex_from_asset or service_life_from_asset:
        return "medium"
    return "low"


def derive_lcc_inputs(
    *,
    asset_info: Any,
    properties: Any = None,
    default_capex: Any = None,
    opex_rate: Any = DEFAULT_OPEX_RATE,
    eol_rate: Any = DEFAULT_EOL_RATE,
    default_service_life_years: int = DEFAULT_SERVICE_LIFE_YEARS,
) -> dict[str, Any] | None:
    """Resolve the LCC cost inputs for one BIM element.

    Reads capex, annual opex, replacement cost, end-of-life cost and service
    life from the asset register where present; otherwise models them from
    capex (opex and end-of-life as a share of capex, replacement like-for-like)
    and from the supplied defaults. Service life is taken from the AIM asset
    register per the task, which is exactly what drives the B4/B5 replacement
    cycle.

    Returns the resolved inputs plus a ``confidence`` band and provenance flags,
    or ``None`` when no capex can be established at all (neither the asset
    register nor a modelled default), so the caller can skip the element.
    """
    capex = _read_positive(asset_info, _CAPEX_KEYS)
    if capex is None:
        capex = _read_positive(properties, _CAPEX_KEYS)
    capex_from_asset = capex is not None
    if capex is None:
        if default_capex is None:
            return None
        capex = _dec(default_capex)
        if capex <= 0:
            return None

    service_life_hit = service_life_from_asset_info(asset_info, properties, None)
    service_life_from_asset = service_life_hit is not None
    service_life = service_life_hit or int(default_service_life_years)

    annual_opex = _read_positive(asset_info, _OPEX_KEYS)
    if annual_opex is None:
        annual_opex = capex * _dec(opex_rate)

    replacement_cost = _read_positive(asset_info, _REPLACEMENT_KEYS)
    if replacement_cost is None:
        replacement_cost = capex

    eol_cost = _read_positive(asset_info, _EOL_KEYS)
    if eol_cost is None:
        eol_cost = capex * _dec(eol_rate)

    return {
        "capex": capex,
        "annual_opex": annual_opex,
        "replacement_cost": replacement_cost,
        "eol_cost": eol_cost,
        "service_life_years": service_life,
        "capex_from_asset": capex_from_asset,
        "service_life_from_asset": service_life_from_asset,
        "confidence": _confidence_from_provenance(
            capex_from_asset=capex_from_asset,
            service_life_from_asset=service_life_from_asset,
        ),
    }


# ---------------------------------------------------------------------------
# Whole-life rollups (carbon side by side with cost)
# ---------------------------------------------------------------------------


def whole_life_carbon(
    *,
    a1a3: Any,
    a4: Any,
    a5: Any,
    b_embodied: Any,
    b6_operational: Any,
    c_end_of_life: Any,
    d_beyond: Any = 0,
) -> dict[str, Any]:
    """Assemble the EN 15978 whole-life carbon breakdown A-B-C-D.

    ``B`` is the full use stage: embodied maintenance / replacement (B1-B5) plus
    B6 operational energy carbon. The whole-life total is ``A1-A5 + B + C``;
    module D (benefits beyond the system boundary) is reported separately and
    never folded into the headline total.
    """
    a1a3_d = _dec(a1a3)
    a4_d = _dec(a4)
    a5_d = _dec(a5)
    a1a5 = a1a3_d + a4_d + a5_d
    b_embodied_d = _dec(b_embodied)
    b6_d = _dec(b6_operational)
    b_total = b_embodied_d + b6_d
    c_d = _dec(c_end_of_life)
    return {
        "a1a3": a1a3_d,
        "a4": a4_d,
        "a5": a5_d,
        "a1a5": a1a5,
        "b_embodied": b_embodied_d,
        "b6_operational": b6_d,
        "b_total": b_total,
        "c_end_of_life": c_d,
        "d_beyond": _dec(d_beyond),
        "whole_life_total": a1a5 + b_total + c_d,
    }


def summarize_life_cycle_cost(entries: Any) -> dict[str, Any]:
    """Roll up capex / opex / replacement / end-of-life across LCC entries.

    Each entry may be an object or a dict carrying ``capex``, ``opex_pv``,
    ``replacement_pv``, ``eol_pv``, ``residual_value_pv`` and
    ``whole_life_cost``. Missing fields count as zero, so entries produced
    before residual value was modelled still roll up cleanly.
    """

    def _get(entry: Any, key: str) -> Decimal:
        raw = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
        if raw is None:
            return Decimal("0")
        try:
            return _dec(raw)
        except (ArithmeticError, ValueError, TypeError):
            return Decimal("0")

    def _has(entry: Any, key: str) -> bool:
        raw = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
        return raw is not None

    capex = Decimal("0")
    opex_pv = Decimal("0")
    replacement_pv = Decimal("0")
    eol_pv = Decimal("0")
    residual_value_pv = Decimal("0")
    whole_life_cost = Decimal("0")
    count = 0
    for entry in entries:
        c = _get(entry, "capex")
        o = _get(entry, "opex_pv")
        r = _get(entry, "replacement_pv")
        e = _get(entry, "eol_pv")
        wlc = _get(entry, "whole_life_cost")
        # Residual value is not a persisted column on the LCC row. A fresh
        # compute dict carries an explicit residual_value_pv and is used as is; a
        # persisted model row has no such attribute, so derive it from the ISO
        # 15686-5 identity whole_life_cost = capex + opex_pv + replacement_pv +
        # eol_pv - residual_value_pv (rows written before the residual credit have
        # whole_life_cost == the components and derive to 0). A partial or legacy
        # dict without the field carries no residual credit and stays 0, so it
        # never derives a spurious value from incomplete components.
        if _has(entry, "residual_value_pv"):
            resid = _get(entry, "residual_value_pv")
        elif isinstance(entry, dict):
            resid = Decimal("0")
        else:
            resid = c + o + r + e - wlc
        capex += c
        opex_pv += o
        replacement_pv += r
        eol_pv += e
        residual_value_pv += resid
        whole_life_cost += wlc
        count += 1
    return {
        "capex": capex,
        "opex_pv": opex_pv,
        "replacement_pv": replacement_pv,
        "eol_pv": eol_pv,
        "residual_value_pv": residual_value_pv,
        "whole_life_cost": whole_life_cost,
        "entry_count": count,
    }
