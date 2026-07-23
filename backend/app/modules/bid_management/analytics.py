# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Line-level bid parity and fairness analytics (pure, no I/O).

The single public entry point :func:`compute_bid_parity_analytics` takes the
side-by-side leveling matrix already produced by
``BidManagementService.leveling_matrix`` (rows = package line items, columns =
bidders, each cell carrying unit price, total price and inclusion status) and
turns it into the per-line, per-bid and overall fairness picture a reviewer
needs before an award:

1. Per line item: median, mean, min, max and spread of the competing unit
   prices, plus a per-cell outlier flag when a bid's unit price deviates more
   than a configurable threshold from the line median.
2. Per bid: a cost-driver ranking (the lines contributing the most to that
   bid's total), so a reviewer sees what drives each number.
3. Per bid: a structural health check (outlier lines, missing mandatory lines,
   abnormally low or high total) returning a soft verdict, never a hard reject.
4. An overall parity summary: how many lines carry high dispersion (a sign of
   scope ambiguity or strategic pricing) and which bid is the most consistent.

Design rules that keep it safe for every market:
    * Money stays :class:`~decimal.Decimal`, never float.
    * Every ratio guards against a zero denominator, so empty, single-bid and
      all-zero inputs return well-defined values, never NaN, inf or a crash.
    * The matrix is the single source of truth: nothing is re-queried, so the
      numbers can never drift from the leveling view the reviewer already sees.
    * The total-level screens reuse ``detect_bid_outliers`` and the ranking
      reuses ``rank_bids`` from the service, so parity and leveling stay aligned.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

# Inclusion statuses that represent a real, competitive bid on a line. Excluded
# and clarification_needed cells are not competing offers, so they take no part
# in the line median, spread or outlier maths (this mirrors the ``is_low`` rule
# used by ``leveling_matrix``).
_COMPETITIVE_STATUSES = ("included", "alternative", "noted")

# Soft health-check penalty weights (points off a 100 consistency score).
_PENALTY_PER_OUTLIER_LINE = Decimal("5")
_PENALTY_PER_MISSING_MANDATORY = Decimal("10")
_PENALTY_ABNORMAL_TOTAL = Decimal("15")


def _dec(value: Any) -> Decimal:
    """Coerce a scalar to :class:`Decimal`. Empty / None become ``0``."""
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_sqrt(value: Decimal) -> Decimal:
    """Square root of a non-negative Decimal via Newton's method.

    ``Decimal`` has no ``sqrt`` in stdlib arithmetic here, so we iterate. A zero
    or negative input returns ``0`` (variance is never negative in practice).
    """
    if value <= 0:
        return Decimal("0")
    x = value
    for _ in range(40):
        x = (x + value / x) / Decimal("2")
    return x


def _median(sorted_values: list[Decimal]) -> Decimal:
    """Median of an already-sorted, non-empty list of Decimals."""
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / Decimal("2")


def _reason_for(winner: SimpleNamespace, bids: list[dict[str, Any]]) -> str:
    """Plain, numbers-first sentence for why a bid is the most consistent."""
    health = next((b["health"] for b in bids if b["bidder_id"] == winner.id), None)
    if health is None:
        return "Most consistent line pricing across the field."
    if health["outlier_line_count"] == 0:
        outliers = "no outlier lines"
    else:
        outliers = f"{health['outlier_line_count']} outlier line(s)"
    if health["missing_mandatory_count"] == 0:
        mandatory = "full mandatory coverage"
    else:
        mandatory = f"{health['missing_mandatory_count']} missing mandatory line(s)"
    return f"Most consistent bid with {outliers} and {mandatory}."


def compute_bid_parity_analytics(
    matrix: dict[str, Any],
    *,
    unit_price_threshold_pct: Decimal | float | int | str = Decimal("20"),
    high_dispersion_cv_pct: Decimal | float | int | str = Decimal("30"),
    sigma_threshold: Decimal | float | int | str = Decimal("2"),
    top_drivers: int = 5,
    currency: str = "",
) -> dict[str, Any]:
    """Compute line-level parity and per-bid fairness analytics from a matrix.

    Args:
        matrix: The dict returned by ``BidManagementService.leveling_matrix``
            (keys ``package_id`` / ``rows``; each row has ``cells``).
        unit_price_threshold_pct: A cell is flagged as an outlier when its unit
            price deviates strictly more than this percentage from the line
            median (default 20). At exactly the threshold a cell is not flagged.
        high_dispersion_cv_pct: A line is flagged ``high_dispersion`` when its
            coefficient of variation exceeds this percentage (default 30).
        sigma_threshold: Sigma band for the total-level abnormally-low / high
            screen, delegated to ``detect_bid_outliers`` (default 2).
        top_drivers: How many top cost-driver lines to keep per bid (default 5).
        currency: Reporting currency code, echoed into the result for display.

    Returns:
        A dict with ``lines``, ``bids`` and ``summary`` sections, ready to drop
        into :class:`BidParityAnalyticsResponse`.

    Raises:
        ValueError: If a threshold is negative.
    """
    q_money = Decimal("0.01")
    q_pct = Decimal("0.01")
    q_ratio = Decimal("0.0001")

    unit_thr = _dec(unit_price_threshold_pct)
    disp_thr = _dec(high_dispersion_cv_pct)
    sigma_thr = _dec(sigma_threshold)
    if unit_thr < 0:
        raise ValueError("unit_price_threshold_pct cannot be negative")
    if disp_thr < 0:
        raise ValueError("high_dispersion_cv_pct cannot be negative")
    top_n = max(int(top_drivers), 0)

    rows = matrix.get("rows", []) or []

    # ── Per-bidder accumulators (keyed by bidder_id, insertion-ordered) ──
    name_by_bidder: dict[Any, str] = {}
    order: list[Any] = []
    total_by_bidder: dict[Any, Decimal] = {}
    contribs_by_bidder: dict[Any, list[dict[str, Any]]] = {}
    priced_count_by_bidder: dict[Any, int] = {}
    outlier_hi_by_bidder: dict[Any, int] = {}
    outlier_lo_by_bidder: dict[Any, int] = {}
    missing_by_bidder: dict[Any, list[str]] = {}

    def _seen(bidder_id: Any, name: str) -> None:
        if bidder_id not in name_by_bidder:
            name_by_bidder[bidder_id] = name or ""
            order.append(bidder_id)
            total_by_bidder[bidder_id] = Decimal("0")
            contribs_by_bidder[bidder_id] = []
            priced_count_by_bidder[bidder_id] = 0
            outlier_hi_by_bidder[bidder_id] = 0
            outlier_lo_by_bidder[bidder_id] = 0
            missing_by_bidder[bidder_id] = []
        elif name and not name_by_bidder[bidder_id]:
            name_by_bidder[bidder_id] = name

    lines_out: list[dict[str, Any]] = []
    outlier_cell_count = 0
    high_disp_codes: list[str] = []

    # ── One pass over the matrix: per-line stats + per-bidder rollups ──
    for row in rows:
        code = str(row.get("line_item_code", "") or "")
        is_mandatory = bool(row.get("is_mandatory", True))
        cells = row.get("cells", []) or []

        competitive: list[tuple[Any, str, Decimal]] = []
        for cell in cells:
            bidder_id = cell.get("bidder_id")
            name = str(cell.get("company_name", "") or "")
            _seen(bidder_id, name)
            unit = _dec(cell.get("unit_price", 0))
            total = _dec(cell.get("total_price", 0))
            status = str(cell.get("inclusion_status", "included") or "included")
            # Completeness rule (same as compute_completeness_score): a line is
            # priced when it carries a non-zero unit or total price.
            priced = unit > 0 or total > 0
            if is_mandatory and not priced:
                missing_by_bidder[bidder_id].append(code)
            is_competitive = status in _COMPETITIVE_STATUSES
            if is_competitive and total > 0:
                total_by_bidder[bidder_id] += total
                priced_count_by_bidder[bidder_id] += 1
                contribs_by_bidder[bidder_id].append(
                    {
                        "line_item_id": row.get("line_item_id"),
                        "line_item_code": code,
                        "description": str(row.get("description", "") or ""),
                        "total_price": total,
                    },
                )
            if is_competitive and unit > 0:
                competitive.append((bidder_id, name, unit))

        n = len(competitive)
        if n == 0:
            lines_out.append(
                {
                    "line_item_id": row.get("line_item_id"),
                    "line_item_code": code,
                    "description": str(row.get("description", "") or ""),
                    "unit": str(row.get("unit", "") or ""),
                    "is_mandatory": is_mandatory,
                    "bid_count": 0,
                    "median_unit_price": None,
                    "mean_unit_price": None,
                    "min_unit_price": None,
                    "max_unit_price": None,
                    "spread": None,
                    "spread_pct": None,
                    "cv_pct": None,
                    "max_over_median": None,
                    "high_dispersion": False,
                    "outlier_count": 0,
                    "cells": [],
                },
            )
            continue

        units = sorted(u for _, _, u in competitive)
        median = _median(units)
        low = units[0]
        high = units[-1]
        mean = sum(units, Decimal("0")) / Decimal(n)
        variance = sum(((u - mean) ** 2 for u in units), Decimal("0")) / Decimal(n)
        std = _decimal_sqrt(variance)
        spread = high - low
        spread_pct = (spread / median * Decimal("100")) if median > 0 else Decimal("0")
        cv_pct = (std / mean * Decimal("100")) if mean > 0 else Decimal("0")
        max_over_median = (high / median) if median > 0 else Decimal("0")
        high_dispersion = n >= 2 and cv_pct > disp_thr
        if high_dispersion:
            high_disp_codes.append(code)

        line_cells: list[dict[str, Any]] = []
        line_outliers = 0
        for bidder_id, name, unit in competitive:
            deviation = (abs(unit - median) / median * Decimal("100")) if median > 0 else Decimal("0")
            is_outlier = median > 0 and deviation > unit_thr
            if unit > median:
                direction = "above"
            elif unit < median:
                direction = "below"
            else:
                direction = "at"
            if is_outlier:
                line_outliers += 1
                outlier_cell_count += 1
                if direction == "above":
                    outlier_hi_by_bidder[bidder_id] += 1
                else:
                    outlier_lo_by_bidder[bidder_id] += 1
            line_cells.append(
                {
                    "bidder_id": bidder_id,
                    "company_name": name,
                    "unit_price": unit,
                    "deviation_pct": deviation.quantize(q_pct),
                    "direction": direction,
                    "is_outlier": is_outlier,
                },
            )

        lines_out.append(
            {
                "line_item_id": row.get("line_item_id"),
                "line_item_code": code,
                "description": str(row.get("description", "") or ""),
                "unit": str(row.get("unit", "") or ""),
                "is_mandatory": is_mandatory,
                "bid_count": n,
                "median_unit_price": median.quantize(q_money),
                "mean_unit_price": mean.quantize(q_money),
                "min_unit_price": low.quantize(q_money),
                "max_unit_price": high.quantize(q_money),
                "spread": spread.quantize(q_money),
                "spread_pct": spread_pct.quantize(q_pct),
                "cv_pct": cv_pct.quantize(q_pct),
                "max_over_median": max_over_median.quantize(q_ratio),
                "high_dispersion": high_dispersion,
                "outlier_count": line_outliers,
                "cells": line_cells,
            },
        )

    # ── Total-level abnormal screen (reuses the module's sigma helper) ──
    # Imported here (not at module top) so the service can import this module
    # without a circular import.
    from app.modules.bid_management.service import detect_bid_outliers, rank_bids

    aggs = [
        SimpleNamespace(
            id=bidder_id,
            company_name=name_by_bidder.get(bidder_id, ""),
            total_amount=total_by_bidder.get(bidder_id, Decimal("0")),
            total_score=Decimal("0"),
            normalized_total=total_by_bidder.get(bidder_id, Decimal("0")),
            rank=0,
        )
        for bidder_id in order
    ]
    outliers = detect_bid_outliers(aggs, sigma_threshold=sigma_thr)
    low_ids = {r["id"] for r in outliers["low_outliers"]}
    high_ids = {r["id"] for r in outliers["high_outliers"]}
    comparable = [t for t in total_by_bidder.values() if t > 0]
    have_field = len(comparable) >= 2

    # ── Per-bid: cost drivers + soft health verdict ──
    bids_out: list[dict[str, Any]] = []
    for bidder_id in order:
        total = total_by_bidder.get(bidder_id, Decimal("0"))
        ranked_contribs = sorted(
            contribs_by_bidder.get(bidder_id, []),
            key=lambda d: d["total_price"],
            reverse=True,
        )[:top_n]
        cost_drivers = [
            {
                "line_item_id": d["line_item_id"],
                "line_item_code": d["line_item_code"],
                "description": d["description"],
                "total_price": d["total_price"].quantize(q_money),
                "contribution_pct": (
                    (d["total_price"] / total * Decimal("100")).quantize(q_pct) if total > 0 else Decimal("0.00")
                ),
            }
            for d in ranked_contribs
        ]

        hi = outlier_hi_by_bidder.get(bidder_id, 0)
        lo = outlier_lo_by_bidder.get(bidder_id, 0)
        outlier_lines = hi + lo
        missing_codes = missing_by_bidder.get(bidder_id, [])
        sid = str(bidder_id)
        abnormal = "low" if sid in low_ids else "high" if sid in high_ids else "normal"

        penalty = (
            Decimal(outlier_lines) * _PENALTY_PER_OUTLIER_LINE
            + Decimal(len(missing_codes)) * _PENALTY_PER_MISSING_MANDATORY
            + (_PENALTY_ABNORMAL_TOTAL if abnormal != "normal" else Decimal("0"))
        )
        consistency = Decimal("100") - penalty
        if consistency < 0:
            consistency = Decimal("0")

        flags: list[str] = []
        if abnormal == "low":
            flags.append("abnormally_low_total")
        elif abnormal == "high":
            flags.append("abnormally_high_total")
        if missing_codes:
            flags.append("missing_mandatory")
        if outlier_lines > 0:
            flags.append("outlier_lines")

        if abnormal != "normal" or missing_codes:
            verdict = "attention"
        elif outlier_lines > 0:
            verdict = "review"
        else:
            verdict = "clean"

        bids_out.append(
            {
                "bidder_id": bidder_id,
                "company_name": name_by_bidder.get(bidder_id, ""),
                "bid_total": total.quantize(q_money),
                "priced_line_count": priced_count_by_bidder.get(bidder_id, 0),
                "cost_drivers": cost_drivers,
                "health": {
                    "outlier_line_count": outlier_lines,
                    "outlier_high_count": hi,
                    "outlier_low_count": lo,
                    "missing_mandatory_count": len(missing_codes),
                    "missing_mandatory_codes": missing_codes,
                    "abnormal_total": abnormal,
                    "consistency_score": consistency.quantize(q_pct),
                    "verdict": verdict,
                    "flags": flags,
                },
            },
        )

    # ── Most-consistent recommendation (reuses rank_bids) ──
    # Rank the priced bids by consistency score (higher is better); the lower
    # total breaks ties. rank_bids sorts in place and stamps ``rank``.
    rank_rows = [
        SimpleNamespace(
            id=b["bidder_id"],
            company_name=b["company_name"],
            total_amount=b["bid_total"],
            total_score=b["health"]["consistency_score"],
            normalized_total=b["bid_total"],
            rank=0,
        )
        for b in bids_out
        if b["bid_total"] > 0
    ]
    recommended_id = None
    recommended_name = ""
    recommendation_reason = ""
    if rank_rows:
        rank_bids(rank_rows)
        winner = rank_rows[0]
        recommended_id = winner.id
        recommended_name = winner.company_name
        recommendation_reason = _reason_for(winner, bids_out)

    summary = {
        "bid_count": len(comparable),
        "line_count": len(rows),
        "priced_line_count": sum(1 for ln in lines_out if ln["bid_count"] > 0),
        "high_dispersion_line_count": len(high_disp_codes),
        "high_dispersion_line_codes": high_disp_codes,
        "outlier_cell_count": outlier_cell_count,
        "total_mean": outliers["mean"].quantize(q_money) if have_field else None,
        "total_std_dev": outliers["std_dev"].quantize(q_money) if have_field else None,
        "low_total_threshold": outliers["low_threshold"].quantize(q_money) if have_field else None,
        "high_total_threshold": outliers["high_threshold"].quantize(q_money) if have_field else None,
        "recommended_bidder_id": recommended_id,
        "recommended_company_name": recommended_name,
        "recommendation_reason": recommendation_reason,
    }

    return {
        "package_id": matrix.get("package_id"),
        "currency": (currency or "").strip().upper(),
        "unit_price_threshold_pct": unit_thr,
        "high_dispersion_cv_pct": disp_thr,
        "sigma_threshold": sigma_thr,
        "lines": lines_out,
        "bids": bids_out,
        "summary": summary,
    }
