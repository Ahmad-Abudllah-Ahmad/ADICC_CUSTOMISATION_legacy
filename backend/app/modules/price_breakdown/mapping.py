# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Map a stored BoQ position onto a :class:`PriceBreakdown`.

The platform already stores a per-position resource split under
``Position.metadata_["resources"]`` (a list of ``{type, name, unit, quantity,
unit_rate, total, currency}``), written both when a position is edited and when
an assembly is applied. This turns that split, plus the BoQ overhead/profit
markups, into the formal per-position price analysis. No new storage: it reads
what is already there.

Resource ``total`` is the amount for the whole position, so it is divided by
the position quantity to get the per-unit contribution to the unit rate. If a
position carries no resource split, the whole unit rate is shown as a single
"other" line so the analysis still renders.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.price_breakdown.model import PriceBreakdown, build_breakdown


def _dec(value: Any, default: str = "0") -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return Decimal(default)


def _markup_pct(markups: list[dict] | None, category: str) -> Decimal:
    """Sum the percentage markups of a given category (overhead/profit)."""
    total = Decimal("0")
    for m in markups or []:
        if str(m.get("category") or "").strip().lower() != category:
            continue
        if str(m.get("markup_type") or "percentage").strip().lower() != "percentage":
            continue
        total += _dec(m.get("percentage"))
    return total


def from_position(
    position: dict[str, Any],
    *,
    markups: list[dict] | None = None,
    overhead_pct: Any = None,
    profit_pct: Any = None,
    currency: str | None = None,
    basis: str = "position",
) -> PriceBreakdown:
    """Build a price analysis from a BoQ position dict.

    ``basis`` is ``"position"`` when resource ``total`` values are for the whole
    position (the platform default, divided by quantity here) or ``"unit"`` when
    they are already per unit. ``overhead_pct`` / ``profit_pct`` win over the
    values derived from ``markups``.
    """
    meta = position.get("metadata_") or position.get("metadata") or {}
    resources = meta.get("resources") or []
    qty = _dec(position.get("quantity"), "1")
    divisor = qty if (basis == "position" and qty != 0) else Decimal("1")
    cur = currency or position.get("currency") or (resources[0].get("currency") if resources else None) or "EUR"

    components: list[dict] = []
    for r in resources:
        total = _dec(r.get("total"))
        if not total:
            total = _dec(r.get("quantity"), "1") * _dec(r.get("unit_rate"))
        per_unit = total / divisor
        res_qty = _dec(r.get("quantity"), "1") / divisor
        components.append(
            {
                "kind": r.get("type") or r.get("resource_type"),
                "description": r.get("name") or r.get("description") or "-",
                "unit": r.get("unit") or "",
                "quantity": res_qty,
                "unit_cost": _dec(r.get("unit_rate")),
                "amount": per_unit,
            }
        )

    if not components:
        # No stored split: show the whole unit rate as one line so the sheet
        # is never empty and still reconciles to the position total.
        components.append(
            {
                "kind": "other",
                "description": position.get("description") or "Unit rate",
                "unit": position.get("unit") or "",
                "quantity": Decimal("1"),
                "unit_cost": _dec(position.get("unit_rate")),
                "amount": _dec(position.get("unit_rate")),
            }
        )

    oh = _dec(overhead_pct) if overhead_pct is not None else _markup_pct(markups, "overhead")
    pr = _dec(profit_pct) if profit_pct is not None else _markup_pct(markups, "profit")

    return build_breakdown(
        position_ref=str(position.get("ordinal") or position.get("reference_code") or ""),
        description=str(position.get("description") or ""),
        unit=str(position.get("unit") or ""),
        position_quantity=qty,
        components=components,
        overhead_pct=oh,
        profit_pct=pr,
        risk_pct=_dec(meta.get("risk_pct")),
        currency=str(cur or "EUR"),
    )
