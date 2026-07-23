# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, Decimal-exact fixed-asset finance helpers.

Pure functions for the fixed-asset / plant register that work the same in
every country. There is no hardcoded currency, no hardcoded locale and no
hardcoded unit system here. Money is always an exact ``Decimal`` paired
with an explicit ISO 4217-style currency code, and figures from different
currencies are never blended into one total. Dates are ISO 8601
(``YYYY-MM-DD``), which is unambiguous worldwide.

Everything is a pure function of its arguments (no DB, no I/O), so each
helper is trivially unit-tested and reused by the per-asset detail view,
the portfolio roll-up and any export.

Scope: straight-line and declining-balance depreciation to an as-of date,
net book value, register value totalled per currency, plain-language
one-line explainers, and localized status words (en / de / ru with an
English fallback). This module mirrors the depreciation conventions used
by the sibling equipment module but shares no imports with it, so the two
stay independent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

__all__ = [
    "METHOD_STRAIGHT_LINE",
    "METHOD_DECLINING_BALANCE",
    "DAYS_PER_YEAR",
    "MONEY_QUANT",
    "DepreciationResult",
    "to_decimal",
    "normalize_currency",
    "parse_iso_date",
    "quantize_money",
    "straight_line_depreciation",
    "declining_balance_depreciation",
    "net_book_value",
    "total_register_value_by_currency",
    "localize_status",
    "explain",
    "describe_depreciation",
]

# Method identifiers. Callers pass these (or their aliases) as parameters;
# nothing about the method is hardcoded per region.
METHOD_STRAIGHT_LINE = "straight_line"
METHOD_DECLINING_BALANCE = "declining_balance"

# Depreciation is measured in days for smooth, calendar-accurate accrual.
# A nominal 365-day accounting year is used, which is the common convention
# for a daily-prorated register; leap days round out over an asset life.
DAYS_PER_YEAR = 365

# Default money rounding: two fractional digits, half-up. Callers can pass a
# different quantum for currencies with zero or three minor units, so the
# minor-unit count is never hardcoded to one currency.
MONEY_QUANT = Decimal("0.01")


# --- Coercion and parsing --------------------------------------------------


def to_decimal(value: Any, *, field_name: str = "value") -> Decimal:
    """Coerce ``value`` to a finite ``Decimal`` or raise ``ValueError``.

    Floats are converted through ``str`` so that a value such as ``0.1``
    keeps its decimal meaning instead of its binary-float artifact. ``None``,
    empty strings, and non-finite results (NaN / infinity) are rejected with
    a clear message rather than silently producing a bad money figure.
    """
    if value is None:
        raise ValueError(f"{field_name} is required (got None)")
    if isinstance(value, bool):
        # bool is an int subclass; refuse it so True/False cannot masquerade
        # as an amount.
        raise ValueError(f"{field_name} must be a number, not a boolean")
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError(f"{field_name} is required (got empty string)")
        try:
            result = Decimal(raw)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field_name} is not a valid number: {value!r}") from exc
    elif isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(str(value))
    else:
        raise ValueError(f"{field_name} must be a number, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"{field_name} must be a finite number, got {value!r}")
    return result


def normalize_currency(code: Any) -> str:
    """Normalize a currency code to an upper-case token or raise ``ValueError``.

    Any non-empty alphabetic token is accepted and upper-cased, so no single
    currency is privileged. An empty or non-string code is rejected, because
    an amount without a currency cannot be totalled safely.
    """
    if not isinstance(code, str):
        raise ValueError(f"currency code must be a string, got {type(code).__name__}")
    token = code.strip().upper()
    if not token:
        raise ValueError("currency code is required")
    if not token.isalpha():
        raise ValueError(f"currency code must be alphabetic, got {code!r}")
    return token


def parse_iso_date(value: Any, *, field_name: str = "date") -> date:
    """Parse an ISO 8601 date (or datetime) into a ``date`` or raise.

    Accepts ``YYYY-MM-DD`` and full ``YYYY-MM-DDTHH:MM:SS`` timestamps, plus
    ``date`` / ``datetime`` objects. Unlike the incremental, human-entered
    lifecycle metadata, a depreciation calculation must have real dates, so
    a missing or malformed date raises instead of returning ``None``.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required as an ISO 8601 string")
    raw = value.strip().rstrip("Zz")
    head = raw.split("T", 1)[0].split(" ", 1)[0]
    try:
        return date.fromisoformat(head)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO 8601 date: {value!r}") from exc


def quantize_money(amount: Decimal, *, quant: Decimal = MONEY_QUANT) -> Decimal:
    """Round a Decimal amount to the given money quantum, half-up."""
    return amount.quantize(quant, rounding=ROUND_HALF_UP)


# --- Depreciation ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DepreciationResult:
    """Full, explainable output of a depreciation computation.

    Every component that goes into the figures is exposed so a user can see
    exactly how the net book value was derived. All money fields share the
    single ``currency`` code; nothing here mixes currencies.
    """

    method: str
    currency: str
    cost: Decimal
    salvage_value: Decimal
    useful_life_years: Decimal
    purchase_date: str
    as_of_date: str
    life_days: int
    elapsed_days: int
    depreciable_base: Decimal  # cost - salvage_value
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    fully_depreciated: bool
    annual_rate: Decimal | None = None  # only set for declining balance
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialize to plain JSON-friendly types (Decimals become strings)."""
        out = asdict(self)
        for key, value in out.items():
            if isinstance(value, Decimal):
                out[key] = str(value)
        return out


def _validate_common(
    cost: Any,
    salvage_value: Any,
    useful_life_years: Any,
    purchase_date: Any,
    as_of_date: Any,
    currency: Any,
) -> tuple[Decimal, Decimal, Decimal, date, date, str, int, int]:
    """Validate shared depreciation inputs; return normalized primitives.

    Guards every edge case up front so the method-specific code below can
    assume clean values: negative or zero-ish cost, negative salvage, salvage
    above cost, zero or negative useful life (division by zero), and an as-of
    date before purchase.
    """
    cost_d = to_decimal(cost, field_name="cost")
    if cost_d < 0:
        raise ValueError(f"cost must not be negative, got {cost_d}")
    salvage_d = to_decimal(salvage_value, field_name="salvage_value")
    if salvage_d < 0:
        raise ValueError(f"salvage_value must not be negative, got {salvage_d}")
    if salvage_d > cost_d:
        raise ValueError(f"salvage_value ({salvage_d}) must not exceed cost ({cost_d})")
    life_d = to_decimal(useful_life_years, field_name="useful_life_years")
    if life_d <= 0:
        raise ValueError(f"useful_life_years must be positive, got {life_d}")
    ccy = normalize_currency(currency)
    purchased = parse_iso_date(purchase_date, field_name="purchase_date")
    as_of = parse_iso_date(as_of_date, field_name="as_of_date")

    life_days = int((life_d * Decimal(DAYS_PER_YEAR)).to_integral_value(rounding=ROUND_HALF_UP))
    if life_days <= 0:
        raise ValueError("useful_life_years is too small to yield a positive life in days")

    raw_elapsed = (as_of - purchased).days
    elapsed_days = raw_elapsed if raw_elapsed > 0 else 0
    return cost_d, salvage_d, life_d, purchased, as_of, ccy, life_days, elapsed_days


def straight_line_depreciation(
    cost: Any,
    salvage_value: Any,
    useful_life_years: Any,
    purchase_date: Any,
    as_of_date: Any,
    currency: Any,
    *,
    quant: Decimal = MONEY_QUANT,
) -> DepreciationResult:
    """Straight-line depreciation accrued to ``as_of_date``.

    The depreciable base ``cost - salvage_value`` is spread evenly across the
    asset life and prorated by elapsed days, so the net book value declines in
    a straight line from ``cost`` on the purchase date to ``salvage_value`` at
    the end of ``useful_life_years``. Before the purchase date nothing is
    depreciated; after the life ends the value rests at salvage.

    Raises ``ValueError`` for negative cost or salvage, salvage above cost,
    non-positive useful life, or unparseable dates or currency.
    """
    cost_d, salvage_d, life_d, purchased, as_of, ccy, life_days, elapsed_days = _validate_common(
        cost, salvage_value, useful_life_years, purchase_date, as_of_date, currency
    )
    depreciable = cost_d - salvage_d
    notes: list[str] = []

    if as_of <= purchased:
        accumulated = Decimal("0")
        notes.append("as_of on or before purchase date; no depreciation yet")
    elif elapsed_days >= life_days:
        accumulated = depreciable
        notes.append("useful life fully elapsed; value rests at salvage")
    else:
        per_day = depreciable / Decimal(life_days)
        accumulated = per_day * Decimal(elapsed_days)

    accumulated = quantize_money(accumulated, quant=quant)
    if accumulated > depreciable:
        accumulated = quantize_money(depreciable, quant=quant)
    nbv = quantize_money(cost_d - accumulated, quant=quant)
    return DepreciationResult(
        method=METHOD_STRAIGHT_LINE,
        currency=ccy,
        cost=quantize_money(cost_d, quant=quant),
        salvage_value=quantize_money(salvage_d, quant=quant),
        useful_life_years=life_d,
        purchase_date=purchased.isoformat(),
        as_of_date=as_of.isoformat(),
        life_days=life_days,
        elapsed_days=elapsed_days,
        depreciable_base=quantize_money(depreciable, quant=quant),
        accumulated_depreciation=accumulated,
        net_book_value=nbv,
        fully_depreciated=elapsed_days >= life_days,
        notes=notes,
    )


def declining_balance_depreciation(
    cost: Any,
    salvage_value: Any,
    useful_life_years: Any,
    purchase_date: Any,
    as_of_date: Any,
    currency: Any,
    *,
    annual_rate: Any = None,
    quant: Decimal = MONEY_QUANT,
) -> DepreciationResult:
    """Declining-balance depreciation accrued to ``as_of_date``.

    Each year a fixed ``annual_rate`` is applied to the remaining net book
    value, so more depreciation falls in the early years. When ``annual_rate``
    is not given it defaults to double-declining (``2 / useful_life_years``).
    The final year switches to a straight-line bridge so the value lands
    exactly on ``salvage_value`` at the end of life, which is the standard
    GAAP / IFRS treatment. Net book value never drops below salvage.

    Raises ``ValueError`` for the same input problems as the straight-line
    helper, and additionally when ``annual_rate`` is outside ``(0, 1]``.
    """
    cost_d, salvage_d, life_d, purchased, as_of, ccy, life_days, elapsed_days = _validate_common(
        cost, salvage_value, useful_life_years, purchase_date, as_of_date, currency
    )
    depreciable = cost_d - salvage_d
    notes: list[str] = []

    if annual_rate is None:
        rate = Decimal("2") / life_d
    else:
        rate = to_decimal(annual_rate, field_name="annual_rate")
    if rate <= 0 or rate > 1:
        raise ValueError(f"annual_rate must be in (0, 1], got {rate}")

    if as_of <= purchased:
        nbv = cost_d
        notes.append("as_of on or before purchase date; no depreciation yet")
    elif elapsed_days >= life_days:
        nbv = salvage_d
        notes.append("useful life fully elapsed; value rests at salvage")
    else:
        elapsed_years_whole = elapsed_days // DAYS_PER_YEAR
        remainder_days = elapsed_days % DAYS_PER_YEAR
        # Threshold: the final year of life switches to a straight-line bridge.
        final_year_start = (life_days // DAYS_PER_YEAR) - 1

        nbv = cost_d
        for _ in range(int(elapsed_years_whole)):
            reduced = nbv - (nbv * rate)
            if reduced < salvage_d:
                reduced = salvage_d
                break
            nbv = reduced

        if elapsed_years_whole >= final_year_start:
            remaining_to_salvage = nbv - salvage_d
            per_day = remaining_to_salvage / Decimal(DAYS_PER_YEAR)
            nbv = nbv - (per_day * Decimal(remainder_days))
            notes.append("final-year straight-line bridge to salvage applied")
        else:
            year_depreciation = nbv * rate
            per_day = year_depreciation / Decimal(DAYS_PER_YEAR)
            nbv = nbv - (per_day * Decimal(remainder_days))

        if nbv < salvage_d:
            nbv = salvage_d

    nbv = quantize_money(nbv, quant=quant)
    accumulated = quantize_money(cost_d - nbv, quant=quant)
    return DepreciationResult(
        method=METHOD_DECLINING_BALANCE,
        currency=ccy,
        cost=quantize_money(cost_d, quant=quant),
        salvage_value=quantize_money(salvage_d, quant=quant),
        useful_life_years=life_d,
        purchase_date=purchased.isoformat(),
        as_of_date=as_of.isoformat(),
        life_days=life_days,
        elapsed_days=elapsed_days,
        depreciable_base=quantize_money(depreciable, quant=quant),
        accumulated_depreciation=accumulated,
        net_book_value=nbv,
        fully_depreciated=elapsed_days >= life_days,
        annual_rate=rate,
        notes=notes,
    )


def net_book_value(
    cost: Any,
    accumulated_depreciation: Any,
    *,
    quant: Decimal = MONEY_QUANT,
) -> Decimal:
    """Net book value: ``cost - accumulated_depreciation``, floored at zero.

    A small standalone helper for callers that already hold an accumulated
    figure and just need the carrying amount. Negative inputs are rejected;
    the result never goes below zero, since an asset cannot carry a negative
    book value.
    """
    cost_d = to_decimal(cost, field_name="cost")
    acc_d = to_decimal(accumulated_depreciation, field_name="accumulated_depreciation")
    if cost_d < 0:
        raise ValueError(f"cost must not be negative, got {cost_d}")
    if acc_d < 0:
        raise ValueError(f"accumulated_depreciation must not be negative, got {acc_d}")
    nbv = cost_d - acc_d
    if nbv < 0:
        nbv = Decimal("0")
    return quantize_money(nbv, quant=quant)


def total_register_value_by_currency(
    entries: Iterable[Any],
    *,
    quant: Decimal = MONEY_QUANT,
) -> dict[str, Decimal]:
    """Sum asset values grouped by currency, never blending currencies.

    ``entries`` is any iterable of items that each carry an amount and a
    currency. An item may be a ``(currency, amount)`` pair or a mapping with
    ``currency`` and one of ``net_book_value`` / ``amount`` / ``value``. The
    result maps each currency code to its exact Decimal total, sorted by code.
    An empty input yields an empty mapping.

    Because different currencies are kept in separate buckets, this never
    produces a meaningless mixed-currency sum.
    """
    totals: dict[str, Decimal] = {}
    for item in entries:
        currency, amount = _unpack_entry(item)
        ccy = normalize_currency(currency)
        amt = to_decimal(amount, field_name="amount")
        totals[ccy] = totals.get(ccy, Decimal("0")) + amt
    return {ccy: quantize_money(totals[ccy], quant=quant) for ccy in sorted(totals)}


def _unpack_entry(item: Any) -> tuple[Any, Any]:
    """Extract ``(currency, amount)`` from a pair or a mapping."""
    if isinstance(item, Mapping):
        currency = item.get("currency")
        for key in ("net_book_value", "amount", "value"):
            if key in item:
                return currency, item[key]
        raise ValueError("mapping entry needs one of: net_book_value, amount, value")
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return item[0], item[1]
    raise ValueError(f"cannot read currency and amount from entry: {item!r}")


# --- Plain-language explainers and localized status words ------------------

# One-line explainers, keyed by figure then language. English is the
# guaranteed fallback for any language not present.
_EXPLAINERS: dict[str, dict[str, str]] = {
    "asset_cost": {
        "en": "What the asset cost to acquire and make ready for use.",
        "de": "Anschaffungskosten, um den Vermoegenswert einsatzbereit zu machen.",
        "ru": "Stoimost priobreteniya aktiva i podgotovki ego k ekspluatatsii.",
    },
    "accumulated_depreciation": {
        "en": "The total value used up since purchase, spread over the asset life.",
        "de": "Der seit dem Kauf verbrauchte Wert, verteilt ueber die Nutzungsdauer.",
        "ru": "Obshchaya iznoshennaya stoimost s momenta pokupki za srok sluzhby.",
    },
    "net_book_value": {
        "en": "What the asset is still worth on the books: cost minus depreciation.",
        "de": "Aktueller Buchwert: Anschaffungskosten abzueglich Abschreibung.",
        "ru": "Ostatochnaya balansovaya stoimost: stoimost minus amortizatsiya.",
    },
    "useful_life": {
        "en": "How many years the asset is expected to be usable.",
        "de": "Erwartete Nutzungsdauer des Vermoegenswerts in Jahren.",
        "ru": "Ozhidaemyy srok poleznogo ispolzovaniya aktiva v godakh.",
    },
    "salvage_value": {
        "en": "The expected leftover value at the end of the useful life.",
        "de": "Erwarteter Restwert am Ende der Nutzungsdauer.",
        "ru": "Ozhidaemaya likvidatsionnaya stoimost v kontse sroka sluzhby.",
    },
}

# Localized asset status words. English is the fallback for missing languages
# and for any status not listed here.
_STATUS_LABELS: dict[str, dict[str, str]] = {
    # Warranty and maintenance share "ok" and "unknown".
    "ok": {"en": "OK", "de": "In Ordnung", "ru": "V poryadke"},
    "unknown": {"en": "Unknown", "de": "Unbekannt", "ru": "Neizvestno"},
    "expiring": {"en": "Expiring soon", "de": "Laeuft bald ab", "ru": "Skoro istekaet"},
    "expired": {"en": "Expired", "de": "Abgelaufen", "ru": "Istek"},
    "due": {"en": "Due soon", "de": "Bald faellig", "ru": "Skoro srok"},
    "overdue": {"en": "Overdue", "de": "Ueberfaellig", "ru": "Prosrocheno"},
    "operational": {"en": "Operational", "de": "In Betrieb", "ru": "V ekspluatatsii"},
    "under_maintenance": {"en": "Under maintenance", "de": "In Wartung", "ru": "Na obsluzhivanii"},
    "decommissioned": {"en": "Decommissioned", "de": "Stillgelegt", "ru": "Vyveden iz ekspluatatsii"},
    "retired": {"en": "Retired", "de": "Ausgemustert", "ru": "Spisan"},
}


def _lang_key(lang: Any) -> str:
    """Reduce a locale tag such as ``de-DE`` to its base language ``de``."""
    if not isinstance(lang, str) or not lang.strip():
        return "en"
    return lang.strip().lower().replace("_", "-").split("-", 1)[0]


def localize_status(term: Any, lang: str = "en") -> str:
    """Return a human status label in ``lang`` with an English fallback.

    Unknown terms are humanized (underscores to spaces, title case) so the
    caller always gets a readable word instead of a raw key.
    """
    key = term or ""
    key = key.strip().lower() if isinstance(key, str) else ""
    table = _STATUS_LABELS.get(key)
    if table is None:
        return key.replace("_", " ").title() if key else "Unknown"
    return table.get(_lang_key(lang)) or table["en"]


def explain(term: Any, lang: str = "en") -> str:
    """Return the one-line explainer for a figure in ``lang`` (English fallback).

    Recognised figures: ``asset_cost``, ``accumulated_depreciation``,
    ``net_book_value``, ``useful_life``, ``salvage_value``. An unrecognised
    term yields an empty string so callers can safely treat it as "no help".
    """
    key = term or ""
    key = key.strip().lower() if isinstance(key, str) else ""
    table = _EXPLAINERS.get(key)
    if table is None:
        return ""
    return table.get(_lang_key(lang)) or table["en"]


def describe_depreciation(result: DepreciationResult, lang: str = "en") -> dict[str, Any]:
    """Bundle a depreciation result with plain-language explainers.

    Returns the serialized components plus an ``explainers`` block, so a UI can
    show every figure next to a one-line description of what it means without
    any extra lookups. This is the explainability surface for the register.
    """
    return {
        "components": result.as_dict(),
        "explainers": {
            "asset_cost": explain("asset_cost", lang),
            "salvage_value": explain("salvage_value", lang),
            "useful_life": explain("useful_life", lang),
            "accumulated_depreciation": explain("accumulated_depreciation", lang),
            "net_book_value": explain("net_book_value", lang),
        },
    }
