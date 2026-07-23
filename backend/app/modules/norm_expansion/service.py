# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Production-norm business logic.

Owns the norm library CRUD and the expansion orchestration: it resolves a
``work_key`` to a stored norm, turns the ORM row into the pure
:class:`app.modules.norm_expansion.expand_math.NormCoefficients` value object,
and runs the deterministic Decimal expansion. Keeping the math in a separate
pure module means the DB layer here stays thin and the arithmetic stays
unit-testable without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.norm_expansion.expand_math import (
    ExpansionResult,
    MaterialCoefficient,
    NormCoefficients,
    expand,
)
from app.modules.norm_expansion.models import NormMaterial, ProductionNorm
from app.modules.norm_expansion.schemas import (
    NormCreate,
    NormMaterialCreate,
    NormUpdate,
)


class WorkKeyExistsError(ValueError):
    """Raised when creating / renaming a norm to a ``work_key`` already in use."""

    def __init__(self, work_key: str) -> None:
        self.work_key = work_key
        super().__init__(f"work_key already exists: {work_key}")


class NormNotFoundError(LookupError):
    """Raised when a build target references a norm id that does not exist.

    The router maps this to a 404 so building an assembly from a missing norm
    never leaks an existence oracle or raises an unhandled 500.
    """

    def __init__(self, norm_id: uuid.UUID) -> None:
        self.norm_id = norm_id
        super().__init__(f"production norm not found: {norm_id}")


def norm_to_coefficients(norm: ProductionNorm) -> NormCoefficients:
    """Build the pure coefficient value object from an ORM norm row.

    The ORM ``materials`` collection is eager-loaded (``selectin``), so reading
    it here never triggers a lazy load outside the async greenlet.

    Args:
        norm: A loaded :class:`ProductionNorm` with its materials.

    Returns:
        The equivalent :class:`NormCoefficients`.
    """
    return NormCoefficients(
        labor_hours_per_unit=norm.labor_hours_per_unit,
        machine_hours_per_unit=norm.machine_hours_per_unit,
        materials=tuple(
            MaterialCoefficient(name=m.name, unit=m.unit, qty_per_unit=m.qty_per_unit) for m in norm.materials
        ),
    )


class NormExpansionService:
    """Thin orchestration layer over the production-norm tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Reads ──────────────────────────────────────────────────────────────

    async def list_norms(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        active_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ProductionNorm]:
        """List norms, newest first, with optional text / category filters."""
        stmt = select(ProductionNorm)
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                func.lower(ProductionNorm.work_key).like(like) | func.lower(ProductionNorm.name).like(like)
            )
        if category:
            stmt = stmt.where(ProductionNorm.category == category)
        if active_only:
            stmt = stmt.where(ProductionNorm.is_active.is_(True))
        stmt = stmt.order_by(ProductionNorm.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_norm(self, norm_id: uuid.UUID) -> ProductionNorm | None:
        """Load a single norm (with materials) by primary key."""
        result = await self.session.execute(select(ProductionNorm).where(ProductionNorm.id == norm_id))
        return result.scalar_one_or_none()

    async def get_by_work_key(self, work_key: str) -> ProductionNorm | None:
        """Load a single norm (with materials) by its unique ``work_key``."""
        result = await self.session.execute(select(ProductionNorm).where(ProductionNorm.work_key == work_key.strip()))
        return result.scalar_one_or_none()

    # ── Writes ─────────────────────────────────────────────────────────────

    async def create_norm(self, data: NormCreate) -> ProductionNorm:
        """Create a norm with its inline material coefficients.

        Raises:
            WorkKeyExistsError: If a norm with the same ``work_key`` exists.
        """
        if await self.get_by_work_key(data.work_key) is not None:
            raise WorkKeyExistsError(data.work_key)
        norm = ProductionNorm(
            work_key=data.work_key,
            name=data.name,
            unit=data.unit,
            category=data.category,
            labor_hours_per_unit=data.labor_hours_per_unit,
            machine_hours_per_unit=data.machine_hours_per_unit,
            notes=data.notes,
            is_active=data.is_active,
        )
        for index, mat in enumerate(data.materials):
            norm.materials.append(_build_material(mat, fallback_order=index))
        self.session.add(norm)
        await self.session.flush()
        return norm

    async def update_norm(self, norm_id: uuid.UUID, data: NormUpdate) -> ProductionNorm | None:
        """Patch a norm's scalar fields in place.

        Raises:
            WorkKeyExistsError: If ``work_key`` is changed to one already taken
                by a different norm.
        """
        norm = await self.get_norm(norm_id)
        if norm is None:
            return None
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        new_key = fields.get("work_key")
        if new_key is not None and new_key != norm.work_key:
            clash = await self.get_by_work_key(new_key)
            if clash is not None and clash.id != norm.id:
                raise WorkKeyExistsError(new_key)
        for key, value in fields.items():
            setattr(norm, key, value)
        await self.session.flush()
        return norm

    async def delete_norm(self, norm_id: uuid.UUID) -> bool:
        """Delete a norm and its materials. Returns True if a row was removed."""
        norm = await self.get_norm(norm_id)
        if norm is None:
            return False
        await self.session.delete(norm)
        await self.session.flush()
        return True

    async def add_material(
        self,
        norm: ProductionNorm,
        data: NormMaterialCreate,
    ) -> NormMaterial:
        """Attach one material coefficient to an existing norm."""
        next_order = data.sort_order or (max((m.sort_order for m in norm.materials), default=-1) + 1)
        material = NormMaterial(
            norm_id=norm.id,
            name=data.name,
            unit=data.unit,
            qty_per_unit=data.qty_per_unit,
            sort_order=next_order,
        )
        self.session.add(material)
        await self.session.flush()
        return material

    async def get_material(self, material_id: uuid.UUID) -> NormMaterial | None:
        """Load a single material coefficient by primary key."""
        result = await self.session.execute(select(NormMaterial).where(NormMaterial.id == material_id))
        return result.scalar_one_or_none()

    async def delete_material(self, material_id: uuid.UUID) -> bool:
        """Delete one material coefficient. Returns True if a row was removed."""
        material = await self.get_material(material_id)
        if material is None:
            return False
        await self.session.delete(material)
        await self.session.flush()
        return True

    # ── Expansion ──────────────────────────────────────────────────────────

    async def expand_work_key(
        self,
        work_key: str,
        quantity: Decimal,
    ) -> tuple[ProductionNorm, ExpansionResult] | None:
        """Resolve ``work_key`` and expand ``quantity`` into resource demand.

        Returns ``None`` when no norm matches the key so the caller can map it
        to a 404 (single) or an ``unmatched`` entry (batch).
        """
        norm = await self.get_by_work_key(work_key)
        if norm is None:
            return None
        result = expand(norm_to_coefficients(norm), quantity)
        return norm, result


def _build_material(data: NormMaterialCreate, *, fallback_order: int) -> NormMaterial:
    """Construct a NormMaterial from a create payload, defaulting sort order."""
    return NormMaterial(
        name=data.name,
        unit=data.unit,
        qty_per_unit=data.qty_per_unit,
        sort_order=data.sort_order or fallback_order,
    )


# ── Priced assembly build (slice 1a) ─────────────────────────────────────────
# Turn a production norm's per-unit coefficients into a saved, priced Assembly:
# labour-hours costed by an all-in labour rate, machine-hours by an equipment
# rate, and each material by a matched cost item. The resulting assembly's
# total_rate is the built-up unit rate.

# Reject a material match whose lexical score is below this. The matcher only
# returns candidates that pass a token prefilter, but a weak best match is more
# likely a false positive than a real price, so we leave the line unpriced (and
# flagged) rather than attach a misleading rate.
_MATERIAL_MATCH_MIN_SCORE = 0.30

# Fallbacks so an Assembly (which requires a non-empty code / name / unit) can
# always be created even from a sparsely filled norm row.
_DEFAULT_ASSEMBLY_UNIT = "unit"
_DEFAULT_ASSEMBLY_CURRENCY = "EUR"


def _assembly_code(work_key: str) -> str:
    """Build a unique, <=100 char assembly code for a norm-derived build.

    A fresh random suffix is appended so re-building the same norm (for another
    project, or with a different labour rate) never collides on the assembly's
    unique ``code``.
    """
    suffix = uuid.uuid4().hex[:8]
    prefix = f"NORM-{work_key}"[: 100 - len(suffix) - 1]
    return f"{prefix}-{suffix}"


async def _resolve_labor_rate(
    session: AsyncSession,
    template_id: uuid.UUID | None,
) -> tuple[Decimal | None, str]:
    """Resolve an all-in labour rate per hour from a labour-rate template.

    Returns ``(rate, currency)``. When no template id is given, or the template
    does not exist, the rate is ``None`` so the caller prices labour to zero and
    flags the line unpriced.
    """
    if template_id is None:
        return None, ""
    from app.modules.labor_rates import rate_math
    from app.modules.labor_rates.service import LaborRateService

    template = await LaborRateService(session).get_template(template_id)
    if template is None:
        return None, ""
    rate = rate_math.all_in_rate(
        template.base_wage,
        [rate_math.OnCost(label=c.label, kind=c.kind, value=c.value) for c in template.components],
    )
    return rate, (template.currency or "")


async def _resolve_material_price(
    session: AsyncSession,
    name: str,
    unit: str,
    *,
    region: str | None,
) -> tuple[object, str]:
    """Find a cost item for a material and return its price plus currency.

    Runs the shared lexical cost matcher, takes the best match above the score
    floor, then reads that cost item's exact Decimal ``rate`` (not the matcher's
    lossy float). Returns a :class:`price_math.MaterialPrice` and the matched
    item's currency (empty string when unpriced).
    """
    from app.modules.costs.matcher import match_cwicr_items
    from app.modules.costs.models import CostItem
    from app.modules.norm_expansion.price_math import MaterialPrice

    matches = await match_cwicr_items(
        session,
        name,
        unit=unit or None,
        top_k=1,
        source=None,
    )
    if not matches or matches[0].score < _MATERIAL_MATCH_MIN_SCORE:
        return MaterialPrice(unit_cost=None), ""

    best = matches[0]
    item = await session.get(CostItem, uuid.UUID(best.cost_item_id))
    if item is None:
        return MaterialPrice(unit_cost=None), ""

    currency = item.currency or best.currency or ""
    try:
        rate = Decimal(str(item.rate))
    except (InvalidOperation, ValueError):
        rate = Decimal("NaN")
    if not rate.is_finite() or rate < 0:
        # Matched a row but its stored rate is unusable: link it for audit but
        # leave the line unpriced so a bad rate never silently prices the build.
        return (
            MaterialPrice(
                unit_cost=None,
                cost_item_id=best.cost_item_id,
                matched_description=best.description,
            ),
            currency,
        )
    return (
        MaterialPrice(
            unit_cost=rate,
            cost_item_id=best.cost_item_id,
            matched_description=best.description,
        ),
        currency,
    )


async def build_assembly_from_norm(
    session: AsyncSession,
    norm_id: uuid.UUID,
    *,
    labor_rate_template_id: uuid.UUID | None = None,
    machine_rate_template_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    owner_id: str | None = None,
    region: str | None = None,
    currency: str | None = None,
    apply_waste: bool = True,
) -> object:
    """Build and persist a priced Assembly from a production norm.

    Loads the norm, resolves an all-in labour rate (from ``labor_rate_template_id``
    when given), an optional equipment rate (from ``machine_rate_template_id``),
    and a matched cost item per material, then prices the norm's per-unit
    coefficients with the pure :func:`price_math.price_build_up`. The priced
    lines are persisted as a new project-scoped Assembly (``is_template`` False)
    through the existing assemblies service, so the assembly's ``total_rate`` is
    the built-up unit rate and each component links back to its cost item.

    Waste factors feed the material quantities: a material coefficient is the NET
    (installed) quantity, so when ``apply_waste`` is set each material is grossed
    up to its purchased (gross) quantity by a factor resolved from the
    :class:`~app.modules.waste_factors.models.WasteFactor` library, keyed by the
    material's ``name`` (there is no separate material category column, so the
    name is the lookup key; it is matched case-insensitively via
    :func:`~app.modules.waste_factors.waste_math.resolve_factor`). The gross-up is
    persisted through the assemblies material-waste path (``metadata['waste_pct']``
    -> ``component.total``), and the net / waste_pct / gross figures are recorded
    on each material component's metadata for the resource grid. A material with
    no library entry stays at net == gross and is collected under the assembly's
    ``metadata['waste_unmatched']``.

    Lines with no resolved rate / cost are still created, at a zero unit cost and
    flagged ``priced=False`` in their metadata (and collected under the
    assembly's ``metadata['unpriced']``), so the UI can surface them for the
    estimator to resolve rather than hiding a gap.

    Args:
        session: Active async DB session.
        norm_id: The production norm to build from.
        labor_rate_template_id: Labour-rate template to price labour-hours; when
            absent, labour is left unpriced and flagged.
        machine_rate_template_id: Labour-rate template used as the equipment
            rate to price machine-hours; when absent, machine time is left
            unpriced and flagged.
        project_id: When given, the assembly is scoped to that project.
        owner_id: The creating user id (for per-tenant ownership).
        region: Optional region hint biasing the material cost match.
        currency: Optional currency override; otherwise resolved from the labour
            rate, then the first matched material, then ``EUR``.
        apply_waste: When ``True`` (default) each material is grossed up net ->
            gross using the waste-factor library. Set ``False`` to price the net
            quantities with no waste allowance (nothing is flagged unmatched).

    Returns:
        The persisted :class:`Assembly` with its priced components loaded.

    Raises:
        NormNotFoundError: If ``norm_id`` does not resolve to a norm.
    """
    from app.modules.assemblies.schemas import AssemblyCreate, ComponentCreate
    from app.modules.assemblies.service import AssemblyService
    from app.modules.norm_expansion.price_math import MATERIAL, price_build_up
    from app.modules.waste_factors.service import WasteFactorService
    from app.modules.waste_factors.waste_math import resolve_factor

    service = NormExpansionService(session)
    norm = await service.get_norm(norm_id)
    if norm is None:
        raise NormNotFoundError(norm_id)

    coefficients = norm_to_coefficients(norm)

    labor_rate, labor_currency = await _resolve_labor_rate(session, labor_rate_template_id)
    machine_rate, machine_currency = await _resolve_labor_rate(session, machine_rate_template_id)

    # Resolve the waste-factor library once. The factor for a material is keyed
    # by the material's ``name`` (there is no per-material category column) and
    # matched case-insensitively; an absent name -> pass-through factor 1.0.
    waste_factor_map: dict[str, Decimal] = {}
    if apply_waste:
        waste_factor_map = await WasteFactorService(session).factor_map()

    material_prices = []
    material_currencies: list[str] = []
    material_waste: list[bool] = []
    for material in norm.materials:
        price, mat_currency = await _resolve_material_price(session, material.name, material.unit, region=region)
        if apply_waste:
            factor, matched = resolve_factor(material.name, waste_factor_map)
        else:
            factor, matched = Decimal("1"), False
        material_prices.append(replace(price, waste_factor=factor, waste_matched=matched))
        material_waste.append(matched)
        if mat_currency:
            material_currencies.append(mat_currency)

    # Materials the caller asked to gross up but the library had no factor for.
    waste_unmatched = [
        material.name
        for material, matched in zip(norm.materials, material_waste, strict=True)
        if apply_waste and not matched
    ]

    resolved_currency = (
        (currency or "").strip()
        or labor_currency
        or machine_currency
        or (material_currencies[0] if material_currencies else "")
        or _DEFAULT_ASSEMBLY_CURRENCY
    )

    build = price_build_up(
        coefficients,
        labor_rate=labor_rate,
        machine_rate=machine_rate,
        material_prices=material_prices,
        currency=resolved_currency,
    )

    assembly_unit = (norm.unit or "").strip() or _DEFAULT_ASSEMBLY_UNIT
    assembly_name = (norm.name or "").strip() or norm.work_key

    assembly_service = AssemblyService(session)
    assembly = await assembly_service.create_assembly(
        AssemblyCreate(
            code=_assembly_code(norm.work_key),
            name=assembly_name,
            description=f"Priced build-up from production norm '{norm.work_key}'.",
            unit=assembly_unit,
            category=norm.category or "",
            currency=resolved_currency,
            is_template=False,
            project_id=project_id,
            metadata={
                "source": "production_norm",
                "norm_id": str(norm.id),
                "work_key": norm.work_key,
                "labor_rate_template_id": (str(labor_rate_template_id) if labor_rate_template_id else None),
                "machine_rate_template_id": (str(machine_rate_template_id) if machine_rate_template_id else None),
                "built_up_unit_rate": format(build.unit_rate, "f"),
                "unpriced": list(build.unpriced),
                "waste_applied": apply_waste,
                "waste_unmatched": waste_unmatched,
            },
        ),
        owner_id=owner_id,
    )

    for line in build.lines:
        component_unit = (line.unit or "").strip() or _DEFAULT_ASSEMBLY_UNIT
        cost_item_uuid = uuid.UUID(line.cost_item_id) if line.cost_item_id else None
        component_metadata: dict[str, Any] = {
            "source": "production_norm",
            "priced": line.priced,
            "resource_kind": line.kind,
            "kind_i18n_key": line.kind_i18n_key,
            "unpriced_reason": line.note,
        }
        if line.resource_type == MATERIAL:
            # The component ``quantity`` stays the NET (installed) coefficient;
            # ``waste_pct`` is the key the assemblies typed-total formula reads to
            # gross ``component.total`` up (``base * (1 + waste_pct/100)``), so the
            # gross-up flows into the money total, not just the metadata.
            # net_qty / gross_qty are recorded so the /boq resource grid and
            # Resource Summary can show "net X + Y% waste = gross Z".
            component_metadata["waste_pct"] = format(line.waste_pct, "f")
            component_metadata["net_qty"] = format(line.net_qty, "f")
            component_metadata["gross_qty"] = format(line.gross_qty, "f")
            component_metadata["waste_matched"] = line.waste_matched
        await assembly_service.add_component(
            assembly.id,
            ComponentCreate(
                cost_item_id=cost_item_uuid,
                description=line.description,
                resource_type=line.resource_type,
                factor=1.0,
                quantity=line.quantity,
                unit=component_unit,
                unit_cost=line.unit_cost,
                metadata=component_metadata,
            ),
        )

    # ``AssemblyRepository.create`` calls ``session.refresh`` which eagerly
    # selectin-loads an (empty) components collection onto the identity-mapped
    # assembly, so a plain re-query would hand back that stale empty collection.
    # Refresh the relationship (and the recomputed total_rate) explicitly to get
    # the four persisted components and the built-up rate.
    await session.refresh(assembly, attribute_names=["total_rate", "components"])
    return assembly
