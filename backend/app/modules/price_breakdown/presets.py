# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Presentation presets for a price breakdown.

The breakdown model is country-neutral. A preset is only a labelling and
grouping choice for output: which categories to show, in which order, under
which heading. The international preset is the default; the other presets lay
the same data out the way a given standard or market words it (German
procurement sheets, UK NRM/CESMM detailed rates, US bid cost breakdown, a
generic cost-plus sheet). Adding a country convention is one entry in
``PRESETS`` - no model change, the underlying ResourceKind values never fork.

Every preset also carries stable i18n keys (``price_breakdown.kind.<value>``
per category and ``price_breakdown.preset.<name>`` for its own label) so a
frontend can translate the headings later. The keys live here as data only; no
shared locale file is edited by this module.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.price_breakdown.model import (
    LINE_I18N_KEYS,
    PriceBreakdown,
    ResourceKind,
    kind_i18n_key,
)

_2P = Decimal("0.01")
_4P = Decimal("0.0001")


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    region: str
    # Heading shown per resource kind, in display order.
    kind_labels: tuple[tuple[ResourceKind, str], ...]

    @property
    def label_i18n_key(self) -> str:
        """Stable i18n key for this preset's own name."""
        return f"price_breakdown.preset.{self.name}"

    def to_dict(self) -> dict:
        """Machine-readable view a UI can render and translate.

        Each kind row exposes the canonical ``kind`` value, the English default
        ``label`` and the stable ``i18n_key``. The summary-line keys are added
        so the whole sheet (categories plus markup lines) is translatable.
        """
        return {
            "name": self.name,
            "label": self.label,
            "label_i18n_key": self.label_i18n_key,
            "region": self.region,
            "kinds": [
                {
                    "kind": kind.value,
                    "label": label,
                    "i18n_key": kind_i18n_key(kind),
                }
                for kind, label in self.kind_labels
            ],
            "line_i18n_keys": dict(LINE_I18N_KEYS),
        }


_INTERNATIONAL = Preset(
    name="international",
    label="Unit price analysis",
    region="international",
    kind_labels=(
        (ResourceKind.LABOUR, "Labour"),
        (ResourceKind.MATERIAL, "Material"),
        (ResourceKind.MACHINERY, "Machinery"),
        (ResourceKind.EQUIPMENT, "Equipment"),
        (ResourceKind.SUBCONTRACT, "Subcontract"),
        (ResourceKind.OTHER, "Other"),
    ),
)

# EFB (Einheitliche Formblaetter, German public procurement handbook). 221 is
# the own-labour sheet, 222 the subcontract sheet, 223 the material list; here
# they are one labelled view of the same categories.
_EFB = Preset(
    name="efb",
    label="EFB price sheets (221/222/223)",
    region="DE",
    kind_labels=(
        (ResourceKind.LABOUR, "Lohnkosten (221)"),
        (ResourceKind.MATERIAL, "Stoffkosten (223)"),
        (ResourceKind.MACHINERY, "Geraetekosten"),
        (ResourceKind.EQUIPMENT, "Vorhaltekosten"),
        (ResourceKind.SUBCONTRACT, "Nachunternehmerleistungen (222)"),
        (ResourceKind.OTHER, "Sonstige Kosten"),
    ),
)

# UK detailed rate build-up, wording shared by NRM (New Rules of Measurement)
# unit-rate analysis and CESMM (Civil Engineering Standard Method of
# Measurement). Plant is the UK term for machinery; a subcontract line is a
# domestic/nominated sub package.
_NRM = Preset(
    name="nrm",
    label="Detailed rate (NRM / CESMM)",
    region="UK",
    kind_labels=(
        (ResourceKind.LABOUR, "Labour"),
        (ResourceKind.MATERIAL, "Materials"),
        (ResourceKind.MACHINERY, "Plant"),
        (ResourceKind.EQUIPMENT, "Temporary works / hire"),
        (ResourceKind.SUBCONTRACT, "Sublet"),
        (ResourceKind.OTHER, "Other"),
    ),
)

# US bid cost breakdown wording (division of the unit price into the cost codes
# an estimator carries on a hard-bid). Equipment (US) is owned/operated plant,
# which the platform stores as machinery; small tools and rented gear map onto
# the equipment kind.
_US_BID = Preset(
    name="us_bid",
    label="Bid cost breakdown",
    region="US",
    kind_labels=(
        (ResourceKind.LABOUR, "Labor"),
        (ResourceKind.MATERIAL, "Material"),
        (ResourceKind.MACHINERY, "Equipment"),
        (ResourceKind.EQUIPMENT, "Small tools and consumables"),
        (ResourceKind.SUBCONTRACT, "Subcontractor"),
        (ResourceKind.OTHER, "Other direct cost"),
    ),
)

# Generic cost-plus sheet: neutral, market-agnostic wording for a build-up
# where a fee is added to measured cost. Useful as a plain fallback heading set.
_COST_PLUS = Preset(
    name="cost_plus",
    label="Cost-plus breakdown",
    region="international",
    kind_labels=(
        (ResourceKind.LABOUR, "Labour cost"),
        (ResourceKind.MATERIAL, "Material cost"),
        (ResourceKind.MACHINERY, "Machinery cost"),
        (ResourceKind.EQUIPMENT, "Equipment cost"),
        (ResourceKind.SUBCONTRACT, "Subcontract cost"),
        (ResourceKind.OTHER, "Other cost"),
    ),
)

PRESETS: dict[str, Preset] = {p.name: p for p in (_INTERNATIONAL, _EFB, _NRM, _US_BID, _COST_PLUS)}


def get_preset(name: str | None) -> Preset:
    return PRESETS.get((name or "").strip().lower(), _INTERNATIONAL)


def _q(value: Decimal) -> str:
    return str(Decimal(value).quantize(_2P, rounding=ROUND_HALF_UP))


def _qty(value: Decimal) -> str:
    return str(Decimal(value).quantize(_4P, rounding=ROUND_HALF_UP))


def efb_221_view(bd: PriceBreakdown) -> dict:
    """Group the components the way an EFB 221-style sheet does: totals per
    resource category plus the markup lines, keyed by category."""
    kt = bd.kind_totals
    preset = _EFB
    rows = [{"kind": kind.value, "label": label, "amount": _q(kt[kind])} for kind, label in preset.kind_labels]
    return {
        "position_ref": bd.position_ref,
        "unit": bd.unit,
        "currency": bd.currency,
        "rows": rows,
        "direct_unit_cost": _q(bd.direct_unit_cost),
        "overhead_amount": _q(bd.overhead_amount),
        "risk_amount": _q(bd.risk_amount),
        "profit_amount": _q(bd.profit_amount),
        "unit_rate": _q(bd.unit_rate),
    }


def render_markdown(bd: PriceBreakdown, *, preset: str = "international") -> str:
    """A compact, readable price-analysis table (works for any language later
    once the labels move to i18n; the numbers are the point)."""
    p = get_preset(preset)
    cur = bd.currency
    lines: list[str] = []
    lines.append(f"# {p.label}: {bd.position_ref} {bd.description}".rstrip())
    lines.append("")
    lines.append(f"Unit: {bd.unit}   Quantity: {bd.position_quantity}   Currency: {cur}")
    lines.append("")
    lines.append("| Resource | Description | Qty | Unit cost | Amount |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    label_by_kind = dict(p.kind_labels)
    for c in bd.components:
        lines.append(
            f"| {label_by_kind.get(c.kind, c.kind.value)} | {c.description} | "
            f"{c.quantity} | {_q(c.unit_cost)} | {_q(c.amount)} |"
        )
    lines.append("")
    lines.append(f"Direct cost per unit: {_q(bd.direct_unit_cost)} {cur}")
    if bd.overhead_pct:
        lines.append(f"Overhead ({bd.overhead_pct}%): {_q(bd.overhead_amount)} {cur}")
    if bd.risk_pct:
        lines.append(f"Risk ({bd.risk_pct}%): {_q(bd.risk_amount)} {cur}")
    if bd.profit_pct:
        lines.append(f"Profit ({bd.profit_pct}%): {_q(bd.profit_amount)} {cur}")
    lines.append(f"Unit rate: {_q(bd.unit_rate)} {cur}")
    lines.append(f"Position total: {_q(bd.position_total)} {cur}")
    return "\n".join(lines)


def render_csv(bd: PriceBreakdown, *, preset: str = "international") -> str:
    """Render the price analysis as spreadsheet-friendly CSV.

    Layout: a short title block (position, unit, quantity, currency), then one
    row per cost component with kind / description / unit / quantity / unit cost
    / amount, then the summary lines (direct, overhead, risk, profit, unit rate,
    position total). Money is 2dp and quantities 4dp, Decimal-exact. Fields are
    comma-separated with minimal quoting, so commas or quotes inside a
    description are escaped safely by the csv writer.
    """
    p = get_preset(preset)
    cur = bd.currency
    label_by_kind = dict(p.kind_labels)
    buf = io.StringIO()
    # Fixed line terminator so the output is deterministic across platforms.
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

    writer.writerow(["Price analysis", p.label])
    writer.writerow(["Position", bd.position_ref, bd.description])
    writer.writerow(["Unit", bd.unit, "Quantity", _qty(bd.position_quantity), "Currency", cur])
    writer.writerow([])
    writer.writerow(["Kind", "Description", "Unit", "Quantity", "Unit cost", "Amount"])
    for c in bd.components:
        writer.writerow(
            [
                label_by_kind.get(c.kind, c.kind.value),
                c.description,
                c.unit,
                _qty(c.quantity),
                _q(c.unit_cost),
                _q(c.amount),
            ]
        )
    writer.writerow([])
    writer.writerow(["Direct cost per unit", "", "", "", "", _q(bd.direct_unit_cost)])
    writer.writerow([f"Overhead ({bd.overhead_pct}%)", "", "", "", "", _q(bd.overhead_amount)])
    writer.writerow([f"Risk ({bd.risk_pct}%)", "", "", "", "", _q(bd.risk_amount)])
    writer.writerow([f"Profit ({bd.profit_pct}%)", "", "", "", "", _q(bd.profit_amount)])
    writer.writerow(["Unit rate", "", "", "", "", _q(bd.unit_rate)])
    writer.writerow(["Position total", "", "", "", "", _q(bd.position_total)])
    return buf.getvalue()
