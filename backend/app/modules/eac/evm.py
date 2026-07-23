# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Earned Value Management (EVM) forecasting - pure, database-free functions.

Estimate At Completion (EAC) is the earned-value forecast of what a project
will finally cost once all remaining work is done. This module gathers the
standard, open EVM forecasting maths in one place so any country, currency
or unit system can reuse it. There is nothing here that depends on a
database, an HTTP request, a locale, a calendar convention or a specific
currency. Money stays exact through :class:`decimal.Decimal`; dimensionless
ratios (CPI, SPI, TCPI) are plain ``float``.

International robustness
------------------------
* No hardcoded currency. Callers pass an ISO 4217 code (for example "EUR",
  "USD", "JPY", "INR") purely as a label; the maths never assumes one.
* No hardcoded minor-unit count. Money is rounded to a caller-supplied
  ``quantum`` that defaults to two decimal places but can be set to
  ``Decimal("1")`` for zero-decimal currencies (for example JPY) or
  ``Decimal("0.001")`` for three-decimal currencies (for example KWD).
* Dates are ISO 8601 strings, never a localized format.

Vocabulary (plain-language glossary in :data:`METRIC_GLOSSARY`)
--------------------------------------------------------------
* PV  - Planned Value: budgeted cost of the work that should be done by now.
* EV  - Earned Value: budgeted cost of the work actually done so far.
* AC  - Actual Cost: money actually spent so far.
* BAC - Budget At Completion: the total approved budget.
* CPI - Cost Performance Index = EV / AC (value earned per unit spent).
* SPI - Schedule Performance Index = EV / PV (progress against the plan).
* SV  - Schedule Variance = EV - PV (ahead if positive, behind if negative).
* CV  - Cost Variance = EV - AC (under budget if positive, over if negative).
* EAC - Estimate At Completion: forecast final cost of the whole project.
* ETC - Estimate To Complete = EAC - AC: forecast cost of remaining work.
* VAC - Variance At Completion = BAC - EAC (surplus if positive, overrun if
  negative).
* TCPI - To Complete Performance Index: the cost efficiency the remaining
  work must hit to still land on a target (BAC or EAC).

Forecasting formulas (each documented on its function)
------------------------------------------------------
* EAC (remaining as planned) = AC + (BAC - EV)
* EAC (cost trend continues)  = BAC / CPI
* EAC (cost and schedule)     = AC + (BAC - EV) / (CPI * SPI)

Edge-case policy
----------------
Two layers, on purpose:

* Low-level ``compute_*`` helpers are permissive: a division that would be
  by zero returns ``None`` (a well-defined "undefined / not started yet"
  value) instead of raising, and they never return NaN or infinity. This
  matches the way the metrics behave before a project has any actuals.
* The high-level :func:`forecast` and :func:`aggregate_elements` entry
  points validate their inputs and raise a clear :class:`ValueError` for
  genuinely invalid data (negative money, an empty dataset, an unknown
  method). Nothing here ever surfaces as a 500 or a NaN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

# Default money rounding step: two decimal places (most currencies). Override
# per call for zero-decimal (Decimal("1")) or three-decimal (Decimal("0.001"))
# currencies so the module never assumes a currency has 2 minor digits.
CENTS = Decimal("0.01")

Number = Decimal | int | float | str


# ── Coercion ─────────────────────────────────────────────────────────────


def to_decimal(value: Number) -> Decimal:
    """Coerce a money value to :class:`Decimal` without float rounding drift.

    Ints, Decimals and numeric strings convert exactly. Floats are routed
    through ``str`` first so ``0.1`` does not smuggle in binary noise. Raises
    :class:`ValueError` with a clear message when the value is not a number
    so bad input never becomes a NaN downstream.
    """
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        msg = f"Not a valid money value: {value!r}. Provide a number like 1200.50."
        raise ValueError(msg) from exc


def _round_money(value: Decimal, quantum: Decimal) -> Decimal:
    """Round a money amount to the currency's minor unit (default 2 places)."""
    return value.quantize(quantum)


# ── Performance indices (dimensionless floats, guarded) ──────────────────


def compute_cpi(ev: Decimal, ac: Decimal) -> float | None:
    """Cost Performance Index = EV / AC (value earned for each unit spent).

    Above 1.0 means under budget, below 1.0 means over budget. Returns
    ``None`` when AC is zero (no money spent yet, so cost efficiency is not
    defined) instead of dividing by zero. Callers read ``None`` as
    "project not started / undefined".
    """
    if ac == 0:
        return None
    return float(ev / ac)


def compute_spi(ev: Decimal, pv: Decimal) -> float | None:
    """Schedule Performance Index = EV / PV (progress against the plan).

    Above 1.0 means ahead of schedule, below 1.0 means behind. Returns
    ``None`` when PV is zero (nothing was planned to be done yet).
    """
    if pv == 0:
        return None
    return float(ev / pv)


def compute_sv(ev: Decimal, pv: Decimal) -> Decimal:
    """Schedule Variance = EV - PV. Positive is ahead, negative is behind."""
    return ev - pv


def compute_cv(ev: Decimal, ac: Decimal) -> Decimal:
    """Cost Variance = EV - AC. Positive is under budget, negative is over."""
    return ev - ac


# ── EAC / ETC / VAC forecasting ──────────────────────────────────────────


def compute_eac_remaining(ac: Decimal, bac: Decimal, ev: Decimal) -> Decimal:
    """EAC = AC + (BAC - EV): finish the remaining work at the planned rate.

    Use when the cost overrun so far is a one-off (for example a fixed price
    change) and the rest of the work is still expected to run to budget.
    """
    return ac + (bac - ev)


def compute_eac_cpi(
    bac: Decimal,
    cpi: float | None,
    *,
    quantum: Decimal = CENTS,
) -> Decimal | None:
    """EAC = BAC / CPI: assume the current cost trend continues to the end.

    Use when the cost performance seen so far is the best predictor of the
    rest of the project. Returns ``None`` when CPI is undefined (AC=0) or
    exactly zero (no value earned yet), never infinity.
    """
    if cpi is None or cpi == 0.0:
        return None
    return _round_money(bac / Decimal(str(cpi)), quantum)


def compute_eac_combined(
    ac: Decimal,
    bac: Decimal,
    ev: Decimal,
    cpi: float | None,
    spi: float | None,
    *,
    quantum: Decimal = CENTS,
) -> Decimal | None:
    """EAC = AC + (BAC - EV) / (CPI * SPI): weigh both cost and schedule.

    Use when being behind schedule is expected to keep pushing cost up, so
    both indices should shape the forecast of the remaining work. Returns
    ``None`` when either index is undefined or their product is zero.
    """
    if cpi is None or spi is None:
        return None
    product = cpi * spi
    if product == 0.0:
        return None
    return _round_money(ac + (bac - ev) / Decimal(str(product)), quantum)


def compute_etc(eac: Decimal | None, ac: Decimal) -> Decimal | None:
    """ETC = EAC - AC: forecast cost of the work still to do.

    Returns ``None`` when EAC is undefined.
    """
    if eac is None:
        return None
    return eac - ac


def compute_vac(bac: Decimal, eac: Decimal | None) -> Decimal | None:
    """VAC = BAC - EAC: forecast surplus (positive) or overrun (negative).

    Returns ``None`` when EAC is undefined.
    """
    if eac is None:
        return None
    return bac - eac


# ── To Complete Performance Index (TCPI) ─────────────────────────────────


def compute_tcpi_bac(bac: Decimal, ev: Decimal, ac: Decimal) -> float | None:
    """TCPI to BAC = (BAC - EV) / (BAC - AC).

    The cost efficiency the remaining work must reach to still finish inside
    the original budget. Above 1.0 means the team has to be more efficient
    than planned to recover. Returns ``None`` when the budget is already
    fully spent (BAC - AC = 0), never infinity.
    """
    denominator = bac - ac
    if denominator == 0:
        return None
    return float((bac - ev) / denominator)


def compute_tcpi_eac(
    bac: Decimal,
    ev: Decimal,
    ac: Decimal,
    eac: Decimal | None,
) -> float | None:
    """TCPI to EAC = (BAC - EV) / (EAC - AC).

    The cost efficiency the remaining work must reach to finish at the
    forecast EAC. Returns ``None`` when EAC is undefined or equals AC (no
    remaining spend forecast).
    """
    if eac is None:
        return None
    denominator = eac - ac
    if denominator == 0:
        return None
    return float((bac - ev) / denominator)


# ── Plain-language glossary (label the cryptic codes) ────────────────────

METRIC_GLOSSARY: dict[str, tuple[str, str]] = {
    "PV": (
        "Planned Value",
        "Budgeted cost of the work that should be finished by now.",
    ),
    "EV": (
        "Earned Value",
        "Budgeted cost of the work actually finished so far.",
    ),
    "AC": (
        "Actual Cost",
        "Money actually spent so far.",
    ),
    "BAC": (
        "Budget At Completion",
        "The total approved budget for the whole project.",
    ),
    "CPI": (
        "Cost Performance Index",
        "Value earned per unit of money spent (EV / AC). Above 1.0 is under budget, below 1.0 is over budget.",
    ),
    "SPI": (
        "Schedule Performance Index",
        "Progress against the plan (EV / PV). Above 1.0 is ahead of schedule, below 1.0 is behind.",
    ),
    "SV": (
        "Schedule Variance",
        "How far ahead or behind the plan you are in money terms (EV - PV). Positive is ahead, negative is behind.",
    ),
    "CV": (
        "Cost Variance",
        "How far under or over budget you are so far (EV - AC). Positive is under budget, negative is over.",
    ),
    "EAC": (
        "Estimate At Completion",
        "Forecast of what the whole project will finally cost.",
    ),
    "ETC": (
        "Estimate To Complete",
        "Forecast cost of the work that is still left to do (EAC - AC).",
    ),
    "VAC": (
        "Variance At Completion",
        "Forecast surplus or overrun against the budget (BAC - EAC). Positive "
        "means you finish under budget, negative means over.",
    ),
    "TCPI": (
        "To Complete Performance Index",
        "The cost efficiency the remaining work must reach to still hit a target (the budget or the forecast).",
    ),
}


def explain_metric(code: str) -> str:
    """Return a one-line plain-language explanation of an EVM code.

    ``code`` is case-insensitive (for example "cpi" or "CPI"). Raises
    :class:`ValueError` listing the known codes when the code is unknown, so
    a typo is a clear input error and never a silent blank.
    """
    key = code.strip().upper()
    entry = METRIC_GLOSSARY.get(key)
    if entry is None:
        known = ", ".join(sorted(METRIC_GLOSSARY))
        msg = f"Unknown EVM code {code!r}. Known codes: {known}."
        raise ValueError(msg)
    return entry[1]


def metric_label(code: str) -> str:
    """Return the full human name for an EVM code (for example CPI -> Cost
    Performance Index). Raises :class:`ValueError` for an unknown code.
    """
    key = code.strip().upper()
    entry = METRIC_GLOSSARY.get(key)
    if entry is None:
        known = ", ".join(sorted(METRIC_GLOSSARY))
        msg = f"Unknown EVM code {code!r}. Known codes: {known}."
        raise ValueError(msg)
    return entry[0]


# ── High-level forecast (validated, explainable) ─────────────────────────

# The EAC formula variants a caller can pick, keyed by a short method name.
EAC_METHODS: tuple[str, ...] = ("auto", "remaining", "cpi", "combined")


@dataclass(frozen=True)
class EvmForecast:
    """A complete, self-describing EVM forecast.

    Every money field is a :class:`Decimal`. Every ratio is a ``float`` or
    ``None``. ``currency`` and ``units`` make each number's meaning explicit
    so a value is never ambiguous across regions. ``drivers`` explains, in
    plain language, why the forecast came out the way it did, so a user can
    trust and check it.
    """

    # Inputs (echoed back so the forecast is self-contained).
    bac: Decimal
    pv: Decimal
    ev: Decimal
    ac: Decimal

    # Performance to date.
    cpi: float | None
    spi: float | None
    sv: Decimal
    cv: Decimal

    # Forecast.
    method: str
    eac: Decimal | None
    etc: Decimal | None
    vac: Decimal | None
    tcpi_bac: float | None
    tcpi_eac: float | None

    # All EAC variants side by side, so the choice is transparent.
    eac_variants: dict[str, Decimal | None]

    # Explicit meaning of each number (international robustness).
    currency: str | None = None
    as_of: str | None = None
    money_unit: str = "currency amount"
    drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Render as a JSON-serialisable dict (Decimals become strings).

        Money is emitted as a string to preserve exact precision on the way
        to JSON; ratios stay as numbers. This is safe for any currency.
        """

        def money(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "currency": self.currency,
            "as_of": self.as_of,
            "money_unit": self.money_unit,
            "inputs": {
                "bac": money(self.bac),
                "pv": money(self.pv),
                "ev": money(self.ev),
                "ac": money(self.ac),
            },
            "performance": {
                "cpi": self.cpi,
                "spi": self.spi,
                "sv": money(self.sv),
                "cv": money(self.cv),
            },
            "forecast": {
                "method": self.method,
                "eac": money(self.eac),
                "etc": money(self.etc),
                "vac": money(self.vac),
                "tcpi_bac": self.tcpi_bac,
                "tcpi_eac": self.tcpi_eac,
            },
            "eac_variants": {k: money(v) for k, v in self.eac_variants.items()},
            "drivers": list(self.drivers),
        }


def _validate_non_negative_money(name: str, value: Decimal) -> None:
    """Raise a clear :class:`ValueError` when a money input is negative."""
    if value < 0:
        msg = f"{name} cannot be negative (got {value}). {name} is a money amount and must be zero or more."
        raise ValueError(msg)


def _build_drivers(
    *,
    cpi: float | None,
    spi: float | None,
    vac: Decimal | None,
    currency: str | None,
) -> list[str]:
    """Compose plain-language sentences explaining the forecast."""
    unit = f" {currency}" if currency else ""
    drivers: list[str] = []

    if cpi is None:
        drivers.append(
            "No actual cost recorded yet, so cost performance (CPI) is not "
            "defined and cost-trend forecasts are unavailable."
        )
    elif cpi > 1:
        drivers.append(
            f"Cost performance (CPI) is {cpi:.3f}: work is being delivered "
            "for less than budgeted, so the project is running under budget."
        )
    elif cpi < 1:
        drivers.append(
            f"Cost performance (CPI) is {cpi:.3f}: each unit of budget is "
            "costing more than planned, so the project is running over budget."
        )
    else:
        drivers.append("Cost performance (CPI) is exactly 1.0: spend is on budget.")

    if spi is None:
        drivers.append("Nothing was planned to be done yet, so schedule performance (SPI) is not defined.")
    elif spi > 1:
        drivers.append(f"Schedule performance (SPI) is {spi:.3f}: ahead of plan.")
    elif spi < 1:
        drivers.append(f"Schedule performance (SPI) is {spi:.3f}: behind plan.")
    else:
        drivers.append("Schedule performance (SPI) is exactly 1.0: on plan.")

    if vac is not None:
        if vac < 0:
            drivers.append(f"Forecast overrun of {abs(vac)}{unit} against the budget (VAC is negative).")
        elif vac > 0:
            drivers.append(f"Forecast surplus of {vac}{unit} against the budget (VAC is positive).")
        else:
            drivers.append("Forecast to land exactly on budget (VAC is zero).")

    return drivers


def _select_eac(
    method: str,
    variants: dict[str, Decimal | None],
) -> tuple[str, Decimal | None]:
    """Pick the EAC value for ``method``, resolving "auto" to the richest
    variant whose inputs are defined (combined, then cpi, then remaining).
    """
    if method == "auto":
        for candidate in ("combined", "cpi", "remaining"):
            value = variants.get(candidate)
            if value is not None:
                return candidate, value
        return "remaining", variants["remaining"]
    return method, variants[method]


def forecast(
    bac: Number,
    pv: Number,
    ev: Number,
    ac: Number,
    *,
    method: str = "auto",
    currency: str | None = None,
    as_of: str | None = None,
    quantum: Decimal = CENTS,
) -> EvmForecast:
    """Compute a full, explainable EVM forecast from the four base inputs.

    Args:
        bac: Budget At Completion (total approved budget). Money.
        pv: Planned Value to date. Money.
        ev: Earned Value to date. Money.
        ac: Actual Cost to date. Money.
        method: Which EAC variant to headline - one of ``EAC_METHODS``.
            "auto" (default) picks the richest variant whose inputs are
            defined: combined (CPI and SPI), else cost-trend (CPI), else
            remaining-as-planned.
        currency: ISO 4217 code used only as a label (for example "EUR").
            No default, so no currency is ever assumed.
        as_of: ISO 8601 date string of the data cutoff. Defaults to today
            in ISO 8601 when omitted.
        quantum: Money rounding step. Default two decimals; pass
            ``Decimal("1")`` for zero-decimal currencies.

    Returns:
        An :class:`EvmForecast` with performance indices, all EAC variants,
        the selected EAC / ETC / VAC / TCPI, per-number units and a
        plain-language ``drivers`` explanation.

    Raises:
        ValueError: if ``method`` is unknown, or any money input is negative.
    """
    if method not in EAC_METHODS:
        allowed = ", ".join(EAC_METHODS)
        msg = f"Unknown method {method!r}. Choose one of: {allowed}."
        raise ValueError(msg)

    bac_d = to_decimal(bac)
    pv_d = to_decimal(pv)
    ev_d = to_decimal(ev)
    ac_d = to_decimal(ac)
    for name, value in (("BAC", bac_d), ("PV", pv_d), ("EV", ev_d), ("AC", ac_d)):
        _validate_non_negative_money(name, value)

    cpi = compute_cpi(ev_d, ac_d)
    spi = compute_spi(ev_d, pv_d)
    sv = compute_sv(ev_d, pv_d)
    cv = compute_cv(ev_d, ac_d)

    variants: dict[str, Decimal | None] = {
        "remaining": compute_eac_remaining(ac_d, bac_d, ev_d),
        "cpi": compute_eac_cpi(bac_d, cpi, quantum=quantum),
        "combined": compute_eac_combined(ac_d, bac_d, ev_d, cpi, spi, quantum=quantum),
    }

    chosen_method, eac = _select_eac(method, variants)
    etc = compute_etc(eac, ac_d)
    vac = compute_vac(bac_d, eac)
    tcpi_bac = compute_tcpi_bac(bac_d, ev_d, ac_d)
    tcpi_eac = compute_tcpi_eac(bac_d, ev_d, ac_d, eac)

    drivers = _build_drivers(cpi=cpi, spi=spi, vac=vac, currency=currency)

    return EvmForecast(
        bac=bac_d,
        pv=pv_d,
        ev=ev_d,
        ac=ac_d,
        cpi=cpi,
        spi=spi,
        sv=sv,
        cv=cv,
        method=chosen_method,
        eac=eac,
        etc=etc,
        vac=vac,
        tcpi_bac=tcpi_bac,
        tcpi_eac=tcpi_eac,
        eac_variants=variants,
        currency=currency,
        as_of=as_of if as_of is not None else date.today().isoformat(),
        drivers=drivers,
    )


# Keys read from each element when aggregating a dataset into totals.
_ELEMENT_FIELDS: tuple[str, ...] = ("bac", "pv", "ev", "ac")


def aggregate_elements(elements: list[dict[str, Number]]) -> dict[str, Decimal]:
    """Sum per-element BAC / PV / EV / AC into project totals.

    Each element is a mapping with numeric ``bac``, ``pv``, ``ev`` and ``ac``
    (missing keys count as zero). Money is summed exactly with
    :class:`Decimal`. The returned totals feed straight into :func:`forecast`.

    Raises:
        ValueError: when ``elements`` is empty (nothing to forecast) or an
            element carries a non-numeric value.
    """
    if not elements:
        msg = "Cannot forecast an empty dataset: provide at least one element."
        raise ValueError(msg)

    totals = {name: Decimal("0") for name in _ELEMENT_FIELDS}
    for index, element in enumerate(elements):
        for name in _ELEMENT_FIELDS:
            raw = element.get(name, 0)
            try:
                totals[name] += to_decimal(raw)
            except ValueError as exc:
                msg = f"Element {index} has an invalid {name}: {raw!r}."
                raise ValueError(msg) from exc
    return totals


__all__ = [
    "CENTS",
    "EAC_METHODS",
    "METRIC_GLOSSARY",
    "EvmForecast",
    "aggregate_elements",
    "compute_cpi",
    "compute_cv",
    "compute_eac_cpi",
    "compute_eac_combined",
    "compute_eac_remaining",
    "compute_etc",
    "compute_spi",
    "compute_sv",
    "compute_tcpi_bac",
    "compute_tcpi_eac",
    "compute_vac",
    "explain_metric",
    "forecast",
    "metric_label",
    "to_decimal",
]
