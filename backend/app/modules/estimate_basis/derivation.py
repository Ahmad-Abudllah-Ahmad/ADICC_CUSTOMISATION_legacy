# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure derivation engine for the basis-of-estimate.

Turns the finished estimate contents (a flat list of BOQ position dicts) into a
structured, editable basis-of-estimate: the inclusions, exclusions and
assumptions that qualify what an estimate does and does not cover.

The engine is deliberately stdlib-only - no ORM, no app imports - so it loads on
a bare interpreter and can be unit tested without a database or the FastAPI
dependency graph. The service layer feeds it plain dicts and persists whatever
it returns.

Two derivations happen here:

* :func:`derive_trades` reads which work sections (trades) are present, absent or
  flagged in the estimate. A trade is keyed on the DIN 276 main cost group
  (an open classification standard already used across the platform); a position
  with no classification is matched on its description keywords as a fallback so
  a BOQ imported without cost codes still yields useful coverage.
* :func:`draft_basis` turns that coverage into the three qualification lists. A
  present trade becomes an inclusion, an expected-but-absent trade becomes an
  exclusion, and each quality flag (unpriced lines, missing quantities,
  provisional sums, work marked "by others") becomes an assumption. A fixed set
  of standard estimate qualifications is always drafted so the document reads
  like one an estimator would hand a client.

Every drafted line carries a deterministic id so a regenerate is stable and the
UI can key, reorder and toggle items without server round-trips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ── Trade taxonomy (DIN 276 main cost groups) ───────────────────────────────
#
# The main groups of DIN 276:2018-12, used here as an open, language-neutral
# work-section taxonomy. ``core`` marks the groups a normal building estimate is
# expected to carry (building construction + technical systems, matching the
# platform's DIN276 completeness rule); their absence is a meaningful exclusion
# rather than simply "not applicable". ``keywords`` drive the description
# fallback for positions that arrive without a cost code - kept conservative so
# a stray word does not misfile a line.


@dataclass(frozen=True)
class Trade:
    """One work section in the basis-of-estimate taxonomy."""

    code: str
    label: str
    core: bool
    keywords: tuple[str, ...]


TRADE_TAXONOMY: tuple[Trade, ...] = (
    Trade(
        "100",
        "Site and land",
        core=False,
        keywords=("site acquisition", "land purchase", "plot", "grundstück"),
    ),
    Trade(
        "200",
        "Site preparation and servicing",
        core=False,
        keywords=(
            "site clearance",
            "demolition",
            "earthwork",
            "excavation",
            "servicing",
            "utilities connection",
            "enabling works",
        ),
    ),
    Trade(
        "300",
        "Building construction works",
        core=True,
        keywords=(
            "concrete",
            "reinforcement",
            "rebar",
            "formwork",
            "masonry",
            "brickwork",
            "blockwork",
            "structure",
            "structural",
            "wall",
            "slab",
            "roof",
            "foundation",
            "beton",
            "screed",
            "plaster",
            "facade",
            "cladding",
        ),
    ),
    Trade(
        "400",
        "Building services and technical systems",
        core=True,
        keywords=(
            "hvac",
            "heating",
            "ventilation",
            "cooling",
            "plumbing",
            "sanitary",
            "electrical",
            "wiring",
            "lighting",
            "mechanical",
            "fire alarm",
            "sprinkler",
            "lift",
            "elevator",
            "ductwork",
            "pipework",
        ),
    ),
    Trade(
        "500",
        "External and landscaping works",
        core=False,
        keywords=(
            "external works",
            "landscap",
            "paving",
            "fencing",
            "planting",
            "car park",
            "drainage",
            "kerb",
        ),
    ),
    Trade(
        "600",
        "Furniture, fixtures and equipment",
        core=False,
        keywords=(
            "furniture",
            "furnishing",
            "fitting",
            "equipment",
            "appliance",
            "signage",
            "loose furniture",
        ),
    ),
    Trade(
        "700",
        "Ancillary and professional costs",
        core=False,
        keywords=(
            "professional fee",
            "design fee",
            "consultant",
            "supervision",
            "permit",
            "insurance",
            "survey fee",
        ),
    ),
    Trade(
        "800",
        "Financing costs",
        core=False,
        keywords=("financing", "interest", "loan", "finance charge"),
    ),
)

_TRADE_BY_CODE: dict[str, Trade] = {t.code: t for t in TRADE_TAXONOMY}

# Description markers for quality flags. Substring-matched on a folded
# (lower-cased) description, so partial and cased forms all hit.
_PROVISIONAL_MARKERS: tuple[str, ...] = (
    "provisional",
    "prov sum",
    "provisional sum",
    "pc sum",
    "p.c. sum",
    "prime cost",
    "allowance",
    "to be confirmed",
    "tbc",
)
_BY_OTHERS_MARKERS: tuple[str, ...] = (
    "by others",
    "by client",
    "by separate contract",
    "not included",
    "excluded",
    "n.i.c",
    "not in contract",
)

_CENTS = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    """Parse a money/quantity value into a Decimal, degrading to zero.

    Accepts the Decimal-as-string the wire carries, a real number, ``None`` or
    junk. Never raises: an unparseable or non-finite value collapses to ``0`` so
    a single bad row can never break a rollup.
    """
    if value is None or value == "":
        return Decimal("0")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    if not parsed.is_finite():
        return Decimal("0")
    return parsed


def fmt_decimal(value: Decimal) -> str:
    """Render a Decimal money value as a plain 2dp string (never scientific)."""
    return str(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


def normalize_din276_main_group(raw: object) -> str:
    """Return the DIN 276 main cost group (``N00``) of a classification code.

    Folds the dotted CAD forms (``"330.10"`` -> ``"330"``) and reduces any valid
    3+ digit numeric KG code to its top-level hundred (``"331"`` -> ``"300"``).
    Returns ``""`` when the input is not a usable numeric KG code.
    """
    code = str(raw or "").strip()
    if not code:
        return ""
    head = code.split(".", 1)[0].strip()
    if len(head) >= 3 and head[:3].isdigit():
        first = head[0]
        if first != "0":
            return f"{first}00"
    return ""


def _fold(text: object) -> str:
    """Lower-case a description for case-insensitive keyword matching."""
    return str(text or "").strip().lower()


def _match_trade_by_keyword(description: str) -> Trade | None:
    """Assign a trade from description keywords, or ``None`` when none match."""
    folded = _fold(description)
    if not folded:
        return None
    for trade in TRADE_TAXONOMY:
        if any(kw in folded for kw in trade.keywords):
            return trade
    return None


# ── Coverage model ──────────────────────────────────────────────────────────


@dataclass
class TradePresence:
    """A trade that appears in the estimate, with its rollup."""

    code: str
    label: str
    core: bool
    position_count: int = 0
    total: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class TradeCoverage:
    """The present / absent / flagged picture derived from the estimate."""

    present: list[TradePresence] = field(default_factory=list)
    absent_core: list[Trade] = field(default_factory=list)
    total_positions: int = 0
    classified_positions: int = 0
    unclassified_positions: int = 0
    zero_rate_positions: int = 0
    missing_quantity_positions: int = 0
    provisional_positions: int = 0
    by_others_positions: int = 0


def derive_trades(positions: list[dict]) -> TradeCoverage:
    """Derive trade coverage and quality flags from BOQ position dicts.

    Args:
        positions: Flat list of position dicts. Each may carry
            ``classification`` (``{"din276": "330"}``), ``description``,
            ``quantity``, ``unit_rate`` and ``total``. All keys are optional and
            defended - a sparse dict is handled, not assumed.

    Returns:
        A :class:`TradeCoverage` with present trades (ordered by descending
        rolled-up total), the expected trades that are absent, and the counts
        that seed the assumptions.
    """
    presence: dict[str, TradePresence] = {}
    coverage = TradeCoverage()

    for pos in positions:
        classification = pos.get("classification") or {}
        din_raw = classification.get("din276", "") if isinstance(classification, dict) else ""
        description = pos.get("description", "")
        main_group = normalize_din276_main_group(din_raw)

        trade: Trade | None
        if main_group and main_group in _TRADE_BY_CODE:
            trade = _TRADE_BY_CODE[main_group]
            coverage.classified_positions += 1
        else:
            trade = _match_trade_by_keyword(description)
            if trade is None:
                coverage.unclassified_positions += 1

        coverage.total_positions += 1

        rate = to_decimal(pos.get("unit_rate"))
        qty = to_decimal(pos.get("quantity"))
        if rate <= 0:
            coverage.zero_rate_positions += 1
        if qty <= 0:
            coverage.missing_quantity_positions += 1

        folded = _fold(description)
        if any(marker in folded for marker in _PROVISIONAL_MARKERS):
            coverage.provisional_positions += 1
        if any(marker in folded for marker in _BY_OTHERS_MARKERS):
            coverage.by_others_positions += 1

        if trade is not None:
            entry = presence.get(trade.code)
            if entry is None:
                entry = TradePresence(code=trade.code, label=trade.label, core=trade.core)
                presence[trade.code] = entry
            entry.position_count += 1
            entry.total += to_decimal(pos.get("total"))

    # Present trades, richest first (a tie falls back to the taxonomy order).
    order = {t.code: i for i, t in enumerate(TRADE_TAXONOMY)}
    coverage.present = sorted(
        presence.values(),
        key=lambda p: (-p.total, order.get(p.code, 99)),
    )

    present_codes = set(presence)
    coverage.absent_core = [t for t in TRADE_TAXONOMY if t.core and t.code not in present_codes]
    return coverage


# ── Drafted basis-of-estimate ───────────────────────────────────────────────


@dataclass
class Qualification:
    """One editable line of the basis-of-estimate."""

    id: str
    category: str  # "inclusion" | "exclusion" | "assumption"
    text: str
    trade_code: str | None = None
    trade_label: str | None = None
    basis: str = ""  # why the line was drafted: "present" | "absent" | "flag" | "standard"
    source: str = "auto"  # "auto" (drafted) | "manual" (user-added)
    enabled: bool = True

    def to_dict(self) -> dict:
        """Serialise to the JSON shape stored on the model / returned to the UI."""
        return {
            "id": self.id,
            "category": self.category,
            "text": self.text,
            "trade_code": self.trade_code,
            "trade_label": self.trade_label,
            "basis": self.basis,
            "source": self.source,
            "enabled": self.enabled,
        }


@dataclass
class BasisDraft:
    """The three drafted qualification lists."""

    inclusions: list[Qualification] = field(default_factory=list)
    exclusions: list[Qualification] = field(default_factory=list)
    assumptions: list[Qualification] = field(default_factory=list)


# Standard estimate qualifications, drafted on every basis so the document reads
# like a real one. Described by function only - never a brand or product.
_STANDARD_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("vat", "Value added tax and any other sales taxes, unless separately stated."),
    ("permits", "Statutory permits, authority fees and connection charges."),
    ("land-finance", "Land acquisition, legal costs and financing charges."),
    ("escalation", "Price escalation and inflation beyond the stated base date."),
    ("by-others", "Any work described as by others or provided under a separate contract."),
    (
        "ground",
        "Abnormal ground conditions, contamination, dewatering and rock excavation, unless stated.",
    ),
    ("loose-ffe", "Loose furniture, fittings and operational equipment, unless itemised."),
    ("prof-fees", "Professional, design and supervision fees, unless itemised."),
)

_STANDARD_ASSUMPTIONS: tuple[tuple[str, str], ...] = (
    (
        "quantities",
        "Quantities are measured from the information available at the time of estimate "
        "and are subject to confirmation at detailed design.",
    ),
    (
        "workmanship",
        "Normal working hours, standard access and unrestricted site conditions are assumed.",
    ),
    (
        "market",
        "Rates reflect competitive market conditions at the stated base date.",
    ),
)


# ── Sibling estimating-module assumptions ───────────────────────────────────
#
# The basis is deepened with what the sibling estimating modules assumed, so a
# reviewer sees them without opening each tool: the allowances / contingency
# register, the preliminaries (general-conditions) roll-up, and the date the
# priced rates are current to. The service reads each source and hands this
# engine plain values; every block degrades gracefully, contributing no line
# when the project has no data for it.

# Human labels for the allowance types the register carries (an open
# vocabulary; an unknown value folds to spaced words rather than raising).
_ALLOWANCE_TYPE_LABELS: dict[str, str] = {
    "provisional_sum": "provisional sum",
    "pc_sum": "prime cost sum",
    "contingency": "contingency",
}


def _allowance_type_label(raw: object) -> str:
    """Return a human label for an allowance type code.

    Args:
        raw: The stored type code (``provisional_sum`` / ``pc_sum`` /
            ``contingency``) or any other value.

    Returns:
        The mapped label, or the code with underscores spaced out when unknown;
        an empty value yields ``"allowance"``.
    """
    key = str(raw or "").strip().lower()
    if key in _ALLOWANCE_TYPE_LABELS:
        return _ALLOWANCE_TYPE_LABELS[key]
    return key.replace("_", " ") or "allowance"


def _money_phrase(amount: Decimal, currency: object = "") -> str:
    """Render a money amount as ``"1234.56 EUR"`` (the currency code optional)."""
    text = fmt_decimal(amount)
    code = str(currency or "").strip()
    return f"{text} {code}" if code else text


def _draft_allowance_assumptions(allowances: list[dict]) -> list[Qualification]:
    """Draft one assumption per allowance plus a contingency-inclusion note.

    Each allowance the estimate carries - a provisional sum, a prime-cost sum or
    a contingency - becomes a line naming it, its held amount and its type, so a
    reviewer sees what has been allowed for ahead of firm measurement. A closing
    note states whether a contingency is included in the estimate total, and (for
    a single currency) how much.

    Args:
        allowances: Allowance dicts, each optionally carrying ``id``, ``label``,
            ``allowance_type``, ``held_amount`` and ``currency``. All keys are
            defended - a sparse dict is handled, not assumed.

    Returns:
        The drafted assumption lines, in input order, with the contingency note
        last. An empty input yields an empty list (no note is invented).
    """
    if not allowances:
        return []

    lines: list[Qualification] = []
    contingency_total = Decimal("0")
    contingency_currencies: set[str] = set()
    has_contingency = False

    for index, allowance in enumerate(allowances):
        raw_type = str(allowance.get("allowance_type") or "").strip().lower()
        type_label = _allowance_type_label(raw_type)
        label = str(allowance.get("label") or "").strip()
        name = label or type_label.capitalize()
        amount = to_decimal(allowance.get("held_amount"))
        currency = str(allowance.get("currency") or "").strip()
        ident = str(allowance.get("id") or index)
        phrase = _money_phrase(amount, currency)
        lines.append(
            Qualification(
                id=f"asm-allowance-{ident}",
                category="assumption",
                text=f"Allowance included: {name} - {phrase} ({type_label}).",
                basis="allowance",
            )
        )
        if raw_type == "contingency":
            has_contingency = True
            contingency_total += amount
            contingency_currencies.add(currency)

    if not has_contingency:
        note = "Contingency is not included in the estimate total."
    elif len(contingency_currencies) == 1:
        phrase = _money_phrase(contingency_total, next(iter(contingency_currencies)))
        note = f"Contingency of {phrase} is included in the estimate total."
    else:
        note = "Contingency is included in the estimate total."
    lines.append(
        Qualification(
            id="asm-contingency",
            category="assumption",
            text=note,
            basis="allowance",
        )
    )
    return lines


def _draft_preliminaries_assumption(preliminaries: dict) -> Qualification | None:
    """Draft the preliminaries summary assumption, or ``None`` when there is none.

    Args:
        preliminaries: The pre-computed roll-up the service builds from
            ``preliminaries.prelim_math`` - ``grand_total``,
            ``time_related_total``, ``item_count`` and an optional ``currency``.

    Returns:
        A single assumption line naming the preliminaries total, the item count
        and the time-related portion, or ``None`` when no items were priced.
    """
    try:
        item_count = int(preliminaries.get("item_count") or 0)
    except (TypeError, ValueError):
        item_count = 0
    if item_count <= 0:
        return None

    currency = preliminaries.get("currency", "")
    total_phrase = _money_phrase(to_decimal(preliminaries.get("grand_total")), currency)
    time_phrase = _money_phrase(to_decimal(preliminaries.get("time_related_total")), currency)
    item_word = "item" if item_count == 1 else "items"
    return Qualification(
        id="asm-preliminaries",
        category="assumption",
        text=(f"Preliminaries assumed: {total_phrase} ({item_count} {item_word}, {time_phrase} time-related)."),
        basis="preliminaries",
    )


def _draft_pricing_base_date_assumption(pricing_base_date: str | None) -> Qualification | None:
    """Draft the pricing-base-date assumption, or ``None`` when no date is known.

    Args:
        pricing_base_date: The date the priced rates are current to, as a string
            (the service derives it from the freshest cost-item price date, or the
            estimate's stated base date).

    Returns:
        A single assumption line stating the price currency date and that
        escalation beyond it is excluded, or ``None`` when no date is available.
    """
    date_text = str(pricing_base_date or "").strip()
    if not date_text:
        return None
    return Qualification(
        id="asm-pricing-date",
        category="assumption",
        text=(f"Prices are current as of {date_text}; escalation beyond this date is excluded unless stated."),
        basis="pricing-date",
    )


def draft_basis(
    coverage: TradeCoverage,
    *,
    currency: str = "",
    base_date: str | None = None,
    allowances: list[dict] | None = None,
    preliminaries: dict | None = None,
    pricing_base_date: str | None = None,
) -> BasisDraft:
    """Draft the inclusions, exclusions and assumptions from trade coverage.

    Args:
        coverage: The derived :class:`TradeCoverage`.
        currency: Optional ISO currency code, woven into a money assumption.
        base_date: Optional base date string, woven into an escalation assumption.
        allowances: Optional allowance dicts from the allowances / contingency
            register; each drafts an assumption and the set drafts a contingency
            note (see :func:`_draft_allowance_assumptions`).
        preliminaries: Optional pre-computed preliminaries roll-up; drafts one
            summary assumption (see :func:`_draft_preliminaries_assumption`).
        pricing_base_date: Optional date the priced rates are current to; drafts
            a price-currency assumption (see
            :func:`_draft_pricing_base_date_assumption`).

    Returns:
        A :class:`BasisDraft` of deterministic, editable qualification lines.
    """
    draft = BasisDraft()

    # Inclusions - one per present trade, richest first.
    for trade in coverage.present:
        count = trade.position_count
        item_word = "item" if count == 1 else "items"
        draft.inclusions.append(
            Qualification(
                id=f"inc-trade-{trade.code}",
                category="inclusion",
                text=f"{trade.label} is included ({count} {item_word}).",
                trade_code=trade.code,
                trade_label=trade.label,
                basis="present",
            )
        )

    # Exclusions - expected trades that are absent, then the standard set.
    for trade in coverage.absent_core:
        draft.exclusions.append(
            Qualification(
                id=f"exc-trade-{trade.code}",
                category="exclusion",
                text=f"{trade.label} is not included in this estimate.",
                trade_code=trade.code,
                trade_label=trade.label,
                basis="absent",
            )
        )
    for key, text in _STANDARD_EXCLUSIONS:
        draft.exclusions.append(
            Qualification(
                id=f"exc-{key}",
                category="exclusion",
                text=text,
                basis="standard",
            )
        )

    # Assumptions - one per raised quality flag, then the standard set.
    if coverage.zero_rate_positions:
        count = coverage.zero_rate_positions
        item_word = "item carries" if count == 1 else "items carry"
        draft.assumptions.append(
            Qualification(
                id="asm-unpriced",
                category="assumption",
                text=(
                    f"{count} {item_word} no unit rate and is treated as a provisional "
                    "allowance to be priced before award."
                ),
                basis="flag",
            )
        )
    if coverage.missing_quantity_positions:
        count = coverage.missing_quantity_positions
        item_word = "item has" if count == 1 else "items have"
        draft.assumptions.append(
            Qualification(
                id="asm-missing-qty",
                category="assumption",
                text=(f"{count} {item_word} no measured quantity and is assumed to be confirmed at detailed design."),
                basis="flag",
            )
        )
    if coverage.provisional_positions:
        draft.assumptions.append(
            Qualification(
                id="asm-provisional",
                category="assumption",
                text=(
                    "Provisional sums and allowances are included as noted and are to be adjusted against actual cost."
                ),
                basis="flag",
            )
        )
    if coverage.unclassified_positions:
        count = coverage.unclassified_positions
        item_word = "item is" if count == 1 else "items are"
        draft.assumptions.append(
            Qualification(
                id="asm-unclassified",
                category="assumption",
                text=(
                    f"{count} {item_word} not mapped to a cost group; trade coverage above "
                    "is assessed from item descriptions."
                ),
                basis="flag",
            )
        )

    # Sibling estimating-module assumptions - allowances / contingency, the
    # preliminaries roll-up and the pricing base date. Each degrades gracefully:
    # an absent source contributes no line.
    draft.assumptions.extend(_draft_allowance_assumptions(allowances or []))
    prelim_line = _draft_preliminaries_assumption(preliminaries or {})
    if prelim_line is not None:
        draft.assumptions.append(prelim_line)
    pricing_line = _draft_pricing_base_date_assumption(pricing_base_date)
    if pricing_line is not None:
        draft.assumptions.append(pricing_line)

    if base_date:
        draft.assumptions.append(
            Qualification(
                id="asm-base-date",
                category="assumption",
                text=f"Rates are based on a base date of {base_date}.",
                basis="standard",
            )
        )
    if currency.strip():
        draft.assumptions.append(
            Qualification(
                id="asm-currency",
                category="assumption",
                text=f"All amounts are expressed in {currency.strip()}.",
                basis="standard",
            )
        )
    for key, text in _STANDARD_ASSUMPTIONS:
        draft.assumptions.append(
            Qualification(
                id=f"asm-{key}",
                category="assumption",
                text=text,
                basis="standard",
            )
        )

    return draft
