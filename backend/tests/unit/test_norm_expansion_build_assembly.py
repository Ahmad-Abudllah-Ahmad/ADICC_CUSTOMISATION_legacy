# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Service tests for building a priced assembly from a production norm.

These drive :func:`app.modules.norm_expansion.service.build_assembly_from_norm`
end to end against a real (transaction-isolated) PostgreSQL session, seeding a
production norm, a labour-rate template and matching cost items, then asserting
the persisted assembly carries the built-up unit rate, the correct priced /
unpriced components, and the project / template wiring.

They use the shared ``oe_test_unit`` database via ``tests._pg`` (rolled back on
teardown), the same fixture style the assemblies module tests use - no new test
harness is introduced.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

from app.modules.labor_rates.models import LaborRateTemplate, OnCostComponent
from app.modules.norm_expansion.models import NormMaterial, ProductionNorm
from app.modules.norm_expansion.service import NormNotFoundError, build_assembly_from_norm
from tests._pg import transactional_session

D = Decimal


@pytest_asyncio.fixture
async def session():
    async with transactional_session() as s:
        yield s


async def _seed_plastering_norm(s) -> ProductionNorm:
    """A norm: 0.45 labour-h, 0.02 machine-h, 12 kg gypsum + 6 l water per m2."""
    norm = ProductionNorm(
        work_key=f"plastering_{uuid.uuid4().hex[:6]}",
        name="Internal plastering",
        unit="m2",
        category="finishing",
        labor_hours_per_unit=D("0.45"),
        machine_hours_per_unit=D("0.02"),
        is_active=True,
    )
    norm.materials.append(NormMaterial(name="Gypsum plaster", unit="kg", qty_per_unit=D("12.0"), sort_order=0))
    norm.materials.append(NormMaterial(name="Water", unit="l", qty_per_unit=D("6.0"), sort_order=1))
    s.add(norm)
    await s.flush()
    return norm


async def _seed_labor_template(s) -> LaborRateTemplate:
    """A template that builds up to a 36.00/h all-in rate (30 base + 20%)."""
    template = LaborRateTemplate(name="Plasterer", base_wage=D("30"), currency="EUR")
    template.components.append(
        OnCostComponent(label="Statutory charges", kind="percentage", value=D("20"), sort_order=0)
    )
    s.add(template)
    await s.flush()
    return template


async def _seed_cost_item(s, *, code: str, description: str, unit: str, rate: str, currency: str = "EUR"):
    from app.modules.costs.models import CostItem

    item = CostItem(
        code=code,
        description=description,
        unit=unit,
        rate=rate,
        currency=currency,
        source="custom",
        is_active=True,
    )
    s.add(item)
    await s.flush()
    return item


async def _seed_waste_factor(s, *, category: str, factor: str) -> None:
    """Insert one waste-factor library row (gross = net * factor)."""
    from app.modules.waste_factors.models import WasteFactor

    s.add(WasteFactor(category=category, label=category, factor=D(factor)))
    await s.flush()


@pytest.mark.asyncio
async def test_build_prices_labour_and_materials_and_persists(session):
    norm = await _seed_plastering_norm(session)
    template = await _seed_labor_template(session)
    gypsum = await _seed_cost_item(
        session, code=f"G-{uuid.uuid4().hex[:6]}", description="Gypsum plaster 25 kg bag", unit="kg", rate="0.50"
    )
    await _seed_cost_item(session, code=f"W-{uuid.uuid4().hex[:6]}", description="Water potable", unit="l", rate="0.01")

    assembly = await build_assembly_from_norm(
        session,
        norm.id,
        labor_rate_template_id=template.id,
    )

    assert assembly.is_template is False
    assert assembly.unit == "m2"
    assert assembly.currency == "EUR"
    assert assembly.code.startswith("NORM-")
    assert assembly.metadata_["source"] == "production_norm"
    assert assembly.metadata_["work_key"] == norm.work_key

    # labour 0.45*36 = 16.20; machine unpriced = 0; gypsum 12*0.50 = 6.00;
    # water 6*0.01 = 0.06 -> built-up unit rate 22.26.
    assert D(str(assembly.total_rate)) == D("22.26")

    by_type = {c.resource_type: c for c in assembly.components}
    assert len(assembly.components) == 4
    assert by_type["labor"].metadata_["priced"] is True
    assert D(str(by_type["labor"].unit_cost)) == D("36.0000")
    assert D(str(by_type["labor"].total)) == D("16.20")

    # No machine-rate template was given: the machine line is present but
    # unpriced and flagged, and contributes zero to the total.
    assert by_type["equipment"].metadata_["priced"] is False
    assert D(str(by_type["equipment"].unit_cost)) == D("0")
    assert "Machine / equipment" in assembly.metadata_["unpriced"]

    # Materials are linked back to the matched cost items.
    gypsum_comp = next(c for c in assembly.components if c.description == "Gypsum plaster")
    assert gypsum_comp.cost_item_id == gypsum.id
    assert gypsum_comp.metadata_["priced"] is True
    assert D(str(gypsum_comp.total)) == D("6.00")


@pytest.mark.asyncio
async def test_unmatched_material_is_unpriced_and_flagged(session):
    norm = await _seed_plastering_norm(session)
    template = await _seed_labor_template(session)
    # Only gypsum is in the catalogue; water has no matching cost item.
    await _seed_cost_item(
        session, code=f"G-{uuid.uuid4().hex[:6]}", description="Gypsum plaster 25 kg bag", unit="kg", rate="0.50"
    )

    assembly = await build_assembly_from_norm(session, norm.id, labor_rate_template_id=template.id)

    water = next(c for c in assembly.components if c.description == "Water")
    assert water.metadata_["priced"] is False
    assert D(str(water.unit_cost)) == D("0")
    assert water.cost_item_id is None
    assert "Water" in assembly.metadata_["unpriced"]
    # labour 16.20 + machine 0 + gypsum 6.00 + water 0 = 22.20.
    assert D(str(assembly.total_rate)) == D("22.20")


@pytest.mark.asyncio
async def test_missing_labour_template_leaves_labour_unpriced(session):
    norm = await _seed_plastering_norm(session)
    await _seed_cost_item(
        session, code=f"G-{uuid.uuid4().hex[:6]}", description="Gypsum plaster 25 kg bag", unit="kg", rate="0.50"
    )
    await _seed_cost_item(session, code=f"W-{uuid.uuid4().hex[:6]}", description="Water potable", unit="l", rate="0.01")

    assembly = await build_assembly_from_norm(session, norm.id, labor_rate_template_id=None)

    labour = next(c for c in assembly.components if c.resource_type == "labor")
    assert labour.metadata_["priced"] is False
    assert D(str(labour.unit_cost)) == D("0")
    assert "Labour" in assembly.metadata_["unpriced"]
    # Only the materials are priced: gypsum 6.00 + water 0.06 = 6.06.
    assert D(str(assembly.total_rate)) == D("6.06")


@pytest.mark.asyncio
async def test_project_scoping_sets_project_and_owner(session):
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    owner_id = uuid.uuid4()
    project_id = uuid.uuid4()
    session.add(User(id=owner_id, email=f"o-{uuid.uuid4().hex[:6]}@test.io", hashed_password="x", full_name="O"))
    await session.flush()
    session.add(Project(id=project_id, name="Norm Build", owner_id=owner_id, currency="EUR"))
    await session.flush()

    norm = await _seed_plastering_norm(session)
    template = await _seed_labor_template(session)

    assembly = await build_assembly_from_norm(
        session,
        norm.id,
        labor_rate_template_id=template.id,
        project_id=project_id,
        owner_id=str(owner_id),
    )

    assert assembly.project_id == project_id
    assert assembly.owner_id == owner_id
    assert assembly.is_template is False


@pytest.mark.asyncio
async def test_material_waste_grosses_up_component_total(session):
    # A library factor keyed by the material NAME grosses that material up;
    # a material with no library entry stays net == gross and is flagged.
    norm = await _seed_plastering_norm(session)
    template = await _seed_labor_template(session)
    await _seed_cost_item(
        session, code=f"G-{uuid.uuid4().hex[:6]}", description="Gypsum plaster 25 kg bag", unit="kg", rate="0.50"
    )
    await _seed_cost_item(session, code=f"W-{uuid.uuid4().hex[:6]}", description="Water potable", unit="l", rate="0.01")
    # Only "Gypsum plaster" has a factor; "Water" does not.
    await _seed_waste_factor(session, category="Gypsum plaster", factor="1.10")

    assembly = await build_assembly_from_norm(session, norm.id, labor_rate_template_id=template.id)

    gypsum = next(c for c in assembly.components if c.description == "Gypsum plaster")
    assert gypsum.metadata_["waste_matched"] is True
    assert gypsum.metadata_["waste_pct"] == "10.0000"
    assert gypsum.metadata_["net_qty"] == "12.0000"
    assert gypsum.metadata_["gross_qty"] == "13.2000"  # 12 * 1.10
    # The gross-up reaches component.total (net 12 * 0.50 * 1.10 = 6.60), not
    # just the metadata.
    assert D(str(gypsum.total)) == D("6.60")
    # The displayed quantity stays the net (installed) coefficient.
    assert D(str(gypsum.quantity)) == D("12")

    water = next(c for c in assembly.components if c.description == "Water")
    assert water.metadata_["waste_matched"] is False
    assert water.metadata_["waste_pct"] == "0.0000"
    assert water.metadata_["net_qty"] == water.metadata_["gross_qty"] == "6.0000"
    assert D(str(water.total)) == D("0.06")  # 6 * 0.01, no gross-up

    # labour 16.20 + machine 0 + gypsum 6.60 + water 0.06 = 22.86.
    assert D(str(assembly.total_rate)) == D("22.86")
    assert assembly.metadata_["waste_applied"] is True
    assert assembly.metadata_["waste_unmatched"] == ["Water"]


@pytest.mark.asyncio
async def test_apply_waste_false_prices_net_quantities(session):
    # Opting out leaves every material at net == gross and flags nothing.
    norm = await _seed_plastering_norm(session)
    template = await _seed_labor_template(session)
    await _seed_cost_item(
        session, code=f"G-{uuid.uuid4().hex[:6]}", description="Gypsum plaster 25 kg bag", unit="kg", rate="0.50"
    )
    await _seed_cost_item(session, code=f"W-{uuid.uuid4().hex[:6]}", description="Water potable", unit="l", rate="0.01")
    await _seed_waste_factor(session, category="Gypsum plaster", factor="1.10")

    assembly = await build_assembly_from_norm(session, norm.id, labor_rate_template_id=template.id, apply_waste=False)

    gypsum = next(c for c in assembly.components if c.description == "Gypsum plaster")
    assert gypsum.metadata_["waste_matched"] is False
    assert gypsum.metadata_["waste_pct"] == "0.0000"
    assert gypsum.metadata_["net_qty"] == gypsum.metadata_["gross_qty"] == "12.0000"
    assert D(str(gypsum.total)) == D("6.00")  # net, no gross-up despite the library factor

    # labour 16.20 + gypsum 6.00 + water 0.06 = 22.26.
    assert D(str(assembly.total_rate)) == D("22.26")
    assert assembly.metadata_["waste_applied"] is False
    assert assembly.metadata_["waste_unmatched"] == []


@pytest.mark.asyncio
async def test_missing_norm_raises_not_found(session):
    with pytest.raises(NormNotFoundError):
        await build_assembly_from_norm(session, uuid.uuid4())
