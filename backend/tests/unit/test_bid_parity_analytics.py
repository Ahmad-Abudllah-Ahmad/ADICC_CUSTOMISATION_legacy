# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free unit tests for line-level bid parity and fairness analytics.

Exercises the pure ``compute_bid_parity_analytics`` helper over hand-built
leveling matrices (the exact shape ``leveling_matrix`` emits): line
median / mean / spread, per-cell outlier flagging at the threshold boundary,
cost-driver ranking, per-bid health verdicts, the most-consistent
recommendation, empty / single-bid edges, Decimal exactness and the
zero-price / divide-by-zero guards.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.modules.bid_management.analytics import compute_bid_parity_analytics
from app.modules.bid_management.schemas import BidParityAnalyticsResponse

# ── Matrix builders (mirror the leveling_matrix cell / row shape) ──────────


def _cell(
    bidder_id: uuid.UUID,
    name: str,
    unit: Any,
    qty: Any = "1",
    *,
    status: str = "included",
    total: Any = None,
) -> dict[str, Any]:
    unit_d = Decimal(str(unit))
    qty_d = Decimal(str(qty))
    total_d = Decimal(str(total)) if total is not None else unit_d * qty_d
    return {
        "bidder_id": bidder_id,
        "company_name": name,
        "unit_price": unit_d,
        "quantity_priced": qty_d,
        "total_price": total_d,
        "inclusion_status": status,
        "alternative_offered": False,
        "comment": "",
        "prevailing_wage_applicable": False,
        "is_low": False,
    }


def _row(
    code: str,
    cells: list[dict[str, Any]],
    *,
    mandatory: bool = True,
    desc: str = "",
    unit: str = "m2",
) -> dict[str, Any]:
    return {
        "line_item_id": uuid.uuid4(),
        "line_item_code": code,
        "description": desc,
        "unit": unit,
        "quantity": Decimal("1"),
        "is_mandatory": mandatory,
        "cells": cells,
        "excluded_count": 0,
        "clarification_count": 0,
    }


def _matrix(rows: list[dict[str, Any]], bidders: list[tuple[uuid.UUID, str]]) -> dict[str, Any]:
    return {
        "package_id": uuid.uuid4(),
        "bidder_ids": [b for b, _ in bidders],
        "bidder_names": [n for _, n in bidders],
        "rows": rows,
    }


def _one_line(unit_prices: list[Any], *, mandatory: bool = True) -> dict[str, Any]:
    """Single-line matrix, one bidder per supplied unit price (qty 1)."""
    bidders: list[tuple[uuid.UUID, str]] = []
    cells: list[dict[str, Any]] = []
    for i, price in enumerate(unit_prices):
        bid_id = uuid.uuid4()
        name = f"Bidder {i + 1}"
        bidders.append((bid_id, name))
        cells.append(_cell(bid_id, name, price))
    return _matrix([_row("L1", cells, mandatory=mandatory)], bidders)


# ── Per-line statistics ────────────────────────────────────────────────────


def test_line_stats_median_mean_min_max_spread() -> None:
    m = _one_line([Decimal("80"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("120")])
    line = compute_bid_parity_analytics(m)["lines"][0]

    assert line["bid_count"] == 5
    assert line["median_unit_price"] == Decimal("100.00")
    assert line["mean_unit_price"] == Decimal("100.00")  # 500 / 5
    assert line["min_unit_price"] == Decimal("80.00")
    assert line["max_unit_price"] == Decimal("120.00")
    assert line["spread"] == Decimal("40.00")
    assert line["spread_pct"] == Decimal("40.00")  # 40 / 100 * 100
    assert line["max_over_median"] == Decimal("1.2000")  # 120 / 100


def test_mean_is_decimal_exact_and_repeating_is_rounded() -> None:
    # (100 + 100 + 101) / 3 = 100.3333... rounds to 100.33
    m = _one_line([Decimal("100"), Decimal("100"), Decimal("101")])
    line = compute_bid_parity_analytics(m)["lines"][0]
    assert line["mean_unit_price"] == Decimal("100.33")
    assert isinstance(line["mean_unit_price"], Decimal)


# ── Per-cell outlier flag at the threshold boundary ────────────────────────


def test_outlier_not_flagged_at_exact_threshold() -> None:
    # 80 and 120 sit exactly 20% from the median of 100. Strict ">" means
    # neither is flagged at a 20% threshold.
    m = _one_line([Decimal("80"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("120")])
    line = compute_bid_parity_analytics(m, unit_price_threshold_pct=Decimal("20"))["lines"][0]

    assert line["outlier_count"] == 0
    assert all(not c["is_outlier"] for c in line["cells"])
    assert max(c["deviation_pct"] for c in line["cells"]) == Decimal("20.00")


def test_outlier_flagged_just_past_threshold_both_directions() -> None:
    # 79 and 121 sit 21% from the median of 100 -> both flagged.
    m = _one_line([Decimal("79"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("121")])
    line = compute_bid_parity_analytics(m, unit_price_threshold_pct=Decimal("20"))["lines"][0]

    assert line["outlier_count"] == 2
    flagged = [c for c in line["cells"] if c["is_outlier"]]
    assert {c["direction"] for c in flagged} == {"above", "below"}
    assert all(c["deviation_pct"] == Decimal("21.00") for c in flagged)


def test_threshold_is_configurable() -> None:
    m = _one_line([Decimal("100"), Decimal("100"), Decimal("100"), Decimal("130")])
    # 130 is 30% above the median of 100.
    tight = compute_bid_parity_analytics(m, unit_price_threshold_pct=Decimal("20"))["lines"][0]
    loose = compute_bid_parity_analytics(m, unit_price_threshold_pct=Decimal("40"))["lines"][0]
    assert tight["outlier_count"] == 1
    assert loose["outlier_count"] == 0


# ── Cost-driver ranking ────────────────────────────────────────────────────


def test_cost_driver_ranking_top_n_and_contribution() -> None:
    a = uuid.uuid4()
    rows = [
        _row("L1", [_cell(a, "A", "500")]),
        _row("L2", [_cell(a, "A", "300")]),
        _row("L3", [_cell(a, "A", "100")]),
        _row("L4", [_cell(a, "A", "50")]),
    ]
    bid = compute_bid_parity_analytics(_matrix(rows, [(a, "A")]), top_drivers=3)["bids"][0]

    assert bid["bid_total"] == Decimal("950.00")
    drivers = bid["cost_drivers"]
    assert len(drivers) == 3  # top 3 only
    assert [d["line_item_code"] for d in drivers] == ["L1", "L2", "L3"]
    assert drivers[0]["total_price"] == Decimal("500.00")
    assert drivers[0]["contribution_pct"] == Decimal("52.63")  # 500 / 950 * 100


# ── Per-bid structural health check ────────────────────────────────────────


def test_health_check_counts_outliers_missing_and_abnormal_total() -> None:
    a, b, c, d, e = (uuid.uuid4() for _ in range(5))
    named = [(a, "A"), (b, "B"), (c, "C"), (d, "D"), (e, "E")]
    # L1: four bidders at 1000, E far below at 100 (per-line low outlier).
    l1 = _row(
        "L1",
        [
            _cell(a, "A", "1000"),
            _cell(b, "B", "1000"),
            _cell(c, "C", "1000"),
            _cell(d, "D", "1000"),
            _cell(e, "E", "100"),
        ],
    )
    # L2 mandatory: A-D price 500, E does not bid it (excluded / zero cell).
    l2 = _row(
        "L2",
        [
            _cell(a, "A", "500"),
            _cell(b, "B", "500"),
            _cell(c, "C", "500"),
            _cell(d, "D", "500"),
            _cell(e, "E", "0", status="excluded", total="0"),
        ],
    )
    res = compute_bid_parity_analytics(_matrix([l1, l2], named), sigma_threshold=Decimal("1"))

    e_bid = next(x for x in res["bids"] if x["bidder_id"] == e)
    health = e_bid["health"]
    assert health["outlier_line_count"] == 1
    assert health["outlier_low_count"] == 1
    assert health["outlier_high_count"] == 0
    assert health["missing_mandatory_count"] == 1
    assert health["missing_mandatory_codes"] == ["L2"]
    assert health["abnormal_total"] == "low"
    assert health["verdict"] == "attention"
    assert set(health["flags"]) == {"abnormally_low_total", "missing_mandatory", "outlier_lines"}

    # A prices at the median everywhere and covers every mandatory line.
    a_bid = next(x for x in res["bids"] if x["bidder_id"] == a)
    assert a_bid["health"]["verdict"] == "clean"
    assert a_bid["health"]["flags"] == []


def test_verdict_review_when_only_line_outliers() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        _row("L1", [_cell(a, "A", "100"), _cell(b, "B", "100"), _cell(c, "C", "100")]),
        _row("L2", [_cell(a, "A", "100"), _cell(b, "B", "200"), _cell(c, "C", "100")]),
    ]
    res = compute_bid_parity_analytics(_matrix(rows, [(a, "A"), (b, "B"), (c, "C")]))
    b_bid = next(x for x in res["bids"] if x["bidder_id"] == b)
    assert b_bid["health"]["outlier_line_count"] == 1
    assert b_bid["health"]["missing_mandatory_count"] == 0
    assert b_bid["health"]["abnormal_total"] == "normal"
    assert b_bid["health"]["verdict"] == "review"


# ── Overall parity summary + recommendation ───────────────────────────────


def test_recommended_is_most_consistent_never_the_outlier() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        _row("L1", [_cell(a, "A", "100"), _cell(b, "B", "100"), _cell(c, "C", "100")]),
        _row("L2", [_cell(a, "A", "100"), _cell(b, "B", "200"), _cell(c, "C", "100")]),
    ]
    summary = compute_bid_parity_analytics(_matrix(rows, [(a, "A"), (b, "B"), (c, "C")]))["summary"]
    assert summary["recommended_bidder_id"] in {a, c}
    assert summary["recommended_bidder_id"] != b
    assert summary["recommendation_reason"] != ""


def test_high_dispersion_line_detection() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # Prices 50 / 100 / 300 -> coefficient of variation well above 30%.
    wide = _row("WIDE", [_cell(a, "A", "50"), _cell(b, "B", "100"), _cell(c, "C", "300")])
    # Prices 100 / 101 / 99 -> tight, low dispersion.
    tight = _row("TIGHT", [_cell(a, "A", "100"), _cell(b, "B", "101"), _cell(c, "C", "99")])
    res = compute_bid_parity_analytics(
        _matrix([wide, tight], [(a, "A"), (b, "B"), (c, "C")]),
        high_dispersion_cv_pct=Decimal("30"),
    )
    lines = {ln["line_item_code"]: ln for ln in res["lines"]}
    assert lines["WIDE"]["high_dispersion"] is True
    assert lines["TIGHT"]["high_dispersion"] is False
    assert res["summary"]["high_dispersion_line_count"] == 1
    assert res["summary"]["high_dispersion_line_codes"] == ["WIDE"]


def test_currency_and_thresholds_echoed() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _matrix([_row("L1", [_cell(a, "A", "100"), _cell(b, "B", "100")])], [(a, "A"), (b, "B")])
    res = compute_bid_parity_analytics(m, currency="eur", unit_price_threshold_pct=Decimal("25"))
    assert res["currency"] == "EUR"
    assert res["unit_price_threshold_pct"] == Decimal("25")
    assert res["package_id"] == m["package_id"]


# ── Edge cases ─────────────────────────────────────────────────────────────


def test_empty_matrix_is_well_defined() -> None:
    res = compute_bid_parity_analytics(_matrix([], []))
    assert res["lines"] == []
    assert res["bids"] == []
    summary = res["summary"]
    assert summary["bid_count"] == 0
    assert summary["recommended_bidder_id"] is None
    assert summary["total_mean"] is None
    assert summary["outlier_cell_count"] == 0


def test_single_bid_has_no_field_stats_and_no_outliers() -> None:
    a = uuid.uuid4()
    rows = [_row("L1", [_cell(a, "A", "100")]), _row("L2", [_cell(a, "A", "200")])]
    res = compute_bid_parity_analytics(_matrix(rows, [(a, "A")]))

    assert res["summary"]["bid_count"] == 1
    assert res["summary"]["total_mean"] is None  # need >= 2 comparable totals
    assert res["summary"]["outlier_cell_count"] == 0
    for line in res["lines"]:
        assert line["bid_count"] == 1
        assert line["outlier_count"] == 0
        assert line["cv_pct"] == Decimal("0.00")
        assert line["high_dispersion"] is False
    # A single priced bid is trivially the recommendation.
    assert res["summary"]["recommended_bidder_id"] == a


def test_identical_prices_no_divide_by_zero() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    m = _matrix(
        [_row("L1", [_cell(a, "A", "100"), _cell(b, "B", "100"), _cell(c, "C", "100")])],
        [(a, "A"), (b, "B"), (c, "C")],
    )
    line = compute_bid_parity_analytics(m)["lines"][0]
    assert line["bid_count"] == 3
    assert line["cv_pct"] == Decimal("0.00")
    assert line["spread"] == Decimal("0.00")
    assert line["max_over_median"] == Decimal("1.0000")
    assert line["outlier_count"] == 0


def test_zero_and_excluded_cells_excluded_from_median() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cells = [
        _cell(a, "A", "100"),
        _cell(b, "B", "100"),
        _cell(c, "C", "0", status="excluded", total="0"),  # no real bid
    ]
    res = compute_bid_parity_analytics(_matrix([_row("L1", cells)], [(a, "A"), (b, "B"), (c, "C")]))
    line = res["lines"][0]
    assert line["bid_count"] == 2  # only the two positive competitive bids
    assert line["median_unit_price"] == Decimal("100.00")
    assert line["outlier_count"] == 0
    # C left a mandatory line unpriced -> counted as a missing mandatory line.
    c_bid = next(x for x in res["bids"] if x["bidder_id"] == c)
    assert c_bid["health"]["missing_mandatory_count"] == 1
    assert c_bid["bid_total"] == Decimal("0.00")
    assert c_bid["cost_drivers"] == []


def test_line_with_no_competitive_bids_yields_null_stats() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    cells = [
        _cell(a, "A", "0", status="excluded", total="0"),
        _cell(b, "B", "0", status="excluded", total="0"),
    ]
    res = compute_bid_parity_analytics(_matrix([_row("L1", cells, mandatory=False)], [(a, "A"), (b, "B")]))
    line = res["lines"][0]
    assert line["bid_count"] == 0
    assert line["median_unit_price"] is None
    assert line["spread_pct"] is None
    assert line["cells"] == []
    assert res["summary"]["bid_count"] == 0


def test_clarification_and_excluded_status_never_competitive() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cells = [
        _cell(a, "A", "100"),
        _cell(b, "B", "100"),
        _cell(c, "C", "5", status="clarification_needed"),  # priced but not competing
    ]
    line = compute_bid_parity_analytics(_matrix([_row("L1", cells)], [(a, "A"), (b, "B"), (c, "C")]))["lines"][0]
    # The clarification bid must not drag the median down to trigger false outliers.
    assert line["bid_count"] == 2
    assert line["median_unit_price"] == Decimal("100.00")
    assert line["outlier_count"] == 0


# ── Decimal exactness + type integrity ─────────────────────────────────────


def test_all_money_fields_are_decimal() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _matrix([_row("L1", [_cell(a, "A", "100.10"), _cell(b, "B", "200.20")])], [(a, "A"), (b, "B")])
    res = compute_bid_parity_analytics(m)
    line = res["lines"][0]
    for key in (
        "median_unit_price",
        "mean_unit_price",
        "min_unit_price",
        "max_unit_price",
        "spread",
        "spread_pct",
        "cv_pct",
        "max_over_median",
    ):
        assert isinstance(line[key], Decimal), key
    assert line["median_unit_price"] == Decimal("150.15")  # (100.10 + 200.20) / 2
    for cell in line["cells"]:
        assert isinstance(cell["unit_price"], Decimal)
        assert isinstance(cell["deviation_pct"], Decimal)
    for bid in res["bids"]:
        assert isinstance(bid["bid_total"], Decimal)
        assert isinstance(bid["health"]["consistency_score"], Decimal)
        for driver in bid["cost_drivers"]:
            assert isinstance(driver["total_price"], Decimal)
            assert isinstance(driver["contribution_pct"], Decimal)


# ── Guards ─────────────────────────────────────────────────────────────────


def test_negative_thresholds_raise() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _matrix([_row("L1", [_cell(a, "A", "100"), _cell(b, "B", "100")])], [(a, "A"), (b, "B")])
    with pytest.raises(ValueError):
        compute_bid_parity_analytics(m, unit_price_threshold_pct=Decimal("-1"))
    with pytest.raises(ValueError):
        compute_bid_parity_analytics(m, high_dispersion_cv_pct=Decimal("-5"))


# ── Response-schema integration (no DB) ────────────────────────────────────


def test_result_validates_against_response_schema() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        _row("L1", [_cell(a, "A", "100"), _cell(b, "B", "121"), _cell(c, "C", "100")]),
        _row("L2", [_cell(a, "A", "50"), _cell(b, "B", "50"), _cell(c, "C", "0", status="excluded", total="0")]),
    ]
    m = _matrix(rows, [(a, "A"), (b, "B"), (c, "C")])
    res = compute_bid_parity_analytics(m)
    model = BidParityAnalyticsResponse.model_validate(res)
    assert model.package_id == m["package_id"]
    assert len(model.lines) == 2
    assert len(model.bids) == 3
    assert model.summary.recommended_bidder_id in {a, c}
