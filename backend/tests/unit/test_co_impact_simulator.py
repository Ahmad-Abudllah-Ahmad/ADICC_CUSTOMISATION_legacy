"""Change-order what-if impact simulator + AI/heuristic draft (TOP-30 #11).

Two layers are covered:

* The pure projection / heuristic helpers (no DB) - these are the deterministic
  core that always works, with or without an AI provider key.
* The service ``simulate_impact`` against real PostgreSQL - proving the budget,
  FX, schedule and override wiring lines up with the finance aggregation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.changeorders.models import ChangeOrder
from app.modules.changeorders.service import (
    ChangeOrderService,
    _compute_impact_projection,
    _heuristic_days,
    _heuristic_draft,
    _heuristic_money,
)
from app.modules.finance.models import ProjectBudget
from app.modules.projects.models import Project
from tests._pg import transactional_session


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with transactional_session(disable_fks=True) as s:
        yield s


# ── Pure projection math ─────────────────────────────────────────────────────


def test_projection_cost_and_evm_math() -> None:
    proj = _compute_impact_projection(
        bac=Decimal("1000000"),
        ev=Decimal("400000"),
        ac=Decimal("420000"),
        pv=Decimal("1000000"),
        co_cost_base=Decimal("50000"),
        schedule_days=5,
        planned_end="2027-12-31",
        item_count=3,
        target_boq_name="Main BOQ",
    )
    # Cost: budget grows by exactly the CO amount.
    assert proj["cost"]["budget_before"] == "1000000.00"
    assert proj["cost"]["budget_after"] == "1050000.00"
    assert proj["cost"]["delta"] == "50000.00"
    assert proj["cost"]["pct_of_budget"] == 5.0
    # EVM: CPI = 400000/420000 = 0.9524; EAC = AC + (BAC-EV)/CPI.
    assert proj["evm"]["cpi"] == "0.9524"
    assert proj["evm"]["eac_before"] == "1050000.00"
    assert proj["evm"]["eac_after"] == "1102500.00"
    assert proj["evm"]["vac_before"] == "-50000.00"
    assert proj["evm"]["vac_after"] == "-52500.00"


def test_projection_schedule_shifts_end_date() -> None:
    proj = _compute_impact_projection(
        bac=Decimal("0"),
        ev=Decimal("0"),
        ac=Decimal("0"),
        pv=Decimal("0"),
        co_cost_base=Decimal("0"),
        schedule_days=5,
        planned_end="2027-12-31",
        item_count=0,
        target_boq_name=None,
    )
    assert proj["schedule"]["current_end_date"] == "2027-12-31"
    assert proj["schedule"]["projected_end_date"] == "2028-01-05"
    assert proj["schedule"]["finish_moves"] is True


def test_projection_handles_missing_end_date_and_zero_budget() -> None:
    proj = _compute_impact_projection(
        bac=Decimal("0"),
        ev=Decimal("0"),
        ac=Decimal("0"),
        pv=Decimal("0"),
        co_cost_base=Decimal("1000"),
        schedule_days=0,
        planned_end=None,
        item_count=0,
        target_boq_name=None,
    )
    assert proj["schedule"]["current_end_date"] is None
    assert proj["schedule"]["projected_end_date"] is None
    assert proj["schedule"]["finish_moves"] is False
    # No baseline budget -> percentage is 0, not a division error.
    assert proj["cost"]["pct_of_budget"] == 0.0


# ── Heuristic draft (offline, no AI key) ─────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Material cost ~USD 15k", Decimal("15000")),
        ("approx 15,000 CAD extra material", Decimal("15000")),
        ("cost impact EUR 8.500,50", Decimal("8500.50")),
        ("total $1,250,000.00 budget overrun", Decimal("1250000.00")),
        ("no figures, just words", Decimal("0")),
    ],
)
def test_heuristic_money(text: str, expected: Decimal) -> None:
    assert _heuristic_money(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("about 3 days delay expected", 3),
        ("a 10 working days extension", 10),
        ("no schedule mention here", 0),
    ],
)
def test_heuristic_days(text: str, expected: int) -> None:
    assert _heuristic_days(text) == expected


def test_heuristic_draft_shape() -> None:
    draft = _heuristic_draft(
        "Extra excavation due to rock. ~3 days delay. Material cost USD 15k.",
        "CAD",
        "daily_log",
        None,
    )
    assert draft["ai_used"] is False
    assert draft["provider"] == "heuristic"
    assert draft["cost_impact"] == "15000.00"
    assert draft["schedule_impact_days"] == 3
    # Daily-log sourced drafts default to the "unforeseen" reason category.
    assert draft["reason_category"] == "unforeseen"
    assert draft["lines"] and draft["lines"][0]["cost_delta"] == "15000.00"
    assert 0 < draft["confidence"] <= 100


# ── Service-level simulate_impact against real PostgreSQL ────────────────────


async def _seed(
    session: AsyncSession,
    *,
    project_currency: str,
    co_currency: str,
    co_cost: str,
    schedule_days: int,
    revised_budget: str = "1000000",
    fx_rates: list | None = None,
) -> ChangeOrder:
    project = Project(
        name="Impact Sim Project",
        owner_id=str(uuid.uuid4()),
        currency=project_currency,
        planned_end_date="2027-12-31",
        fx_rates=fx_rates or [],
    )
    session.add(project)
    await session.flush()

    session.add(
        ProjectBudget(
            project_id=project.id,
            category="Base",
            currency_code=project_currency,
            original_budget=Decimal("0"),
            revised_budget=Decimal(revised_budget),
            committed=Decimal("0"),
            actual=Decimal("0"),
            forecast_final=Decimal("0"),
        )
    )
    order = ChangeOrder(
        project_id=project.id,
        code="CO-001",
        title="Rock excavation",
        description="",
        currency=co_currency,
        cost_impact=Decimal(co_cost),
        schedule_impact_days=schedule_days,
    )
    session.add(order)
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_simulate_same_currency_adds_to_budget(session: AsyncSession) -> None:
    order = await _seed(
        session,
        project_currency="CAD",
        co_currency="CAD",
        co_cost="50000",
        schedule_days=5,
    )
    svc = ChangeOrderService(session)
    result = await svc.simulate_impact(order.id)
    assert result["base_currency"] == "CAD"
    assert result["fx_converted"] is True
    assert result["cost"]["budget_before"] == "1000000.00"
    assert result["cost"]["budget_after"] == "1050000.00"
    assert result["schedule"]["projected_end_date"] == "2028-01-05"
    assert result["evm"]["bac_after"] == "1050000.00"


@pytest.mark.asyncio
async def test_simulate_respects_cost_override(session: AsyncSession) -> None:
    order = await _seed(
        session,
        project_currency="CAD",
        co_currency="CAD",
        co_cost="50000",
        schedule_days=0,
    )
    svc = ChangeOrderService(session)
    result = await svc.simulate_impact(order.id, cost_override="120000", schedule_override=10)
    assert result["cost"]["budget_after"] == "1120000.00"
    assert result["schedule"]["days_added"] == 10


@pytest.mark.asyncio
async def test_simulate_fx_converts_foreign_co_cost(session: AsyncSession) -> None:
    # Project base CAD; CO priced in USD at 1.35 CAD per USD.
    order = await _seed(
        session,
        project_currency="CAD",
        co_currency="USD",
        co_cost="50000",
        schedule_days=0,
        fx_rates=[{"code": "USD", "rate": "1.35"}],
    )
    svc = ChangeOrderService(session)
    result = await svc.simulate_impact(order.id)
    assert result["fx_converted"] is True
    assert result["co_cost_base"] == "67500.00"  # 50000 * 1.35
    assert result["cost"]["budget_after"] == "1067500.00"


@pytest.mark.asyncio
async def test_simulate_flags_missing_fx_rate(session: AsyncSession) -> None:
    order = await _seed(
        session,
        project_currency="CAD",
        co_currency="USD",
        co_cost="50000",
        schedule_days=0,
        fx_rates=[],  # no USD rate configured
    )
    svc = ChangeOrderService(session)
    result = await svc.simulate_impact(order.id)
    assert result["fx_converted"] is False
    assert any("FX rate" in n for n in result["notes"])
