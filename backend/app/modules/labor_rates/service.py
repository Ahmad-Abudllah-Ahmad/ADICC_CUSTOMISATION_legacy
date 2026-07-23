# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Labor rate service - stateless build-up orchestration and persistence.

The rate arithmetic lives in :mod:`app.modules.labor_rates.rate_math` (pure
Decimal). This layer maps the schema payloads onto that math for the stateless
``compute`` path and persists / retrieves templates and crews.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.labor_rates import rate_math
from app.modules.labor_rates.models import CrewMember, LaborRateTemplate, OnCostComponent
from app.modules.labor_rates.schemas import (
    ComputeRequest,
    CrewBreakdown,
    CrewMemberLineOut,
    CrewMemberOut,
    CrewResponse,
    CrewSaveRequest,
    OnCostLineOut,
    RateBreakdown,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.modules.price_breakdown.model import ResourceKind

if TYPE_CHECKING:
    from app.modules.costs.models import CostItem


class LaborRateTemplateNotFoundError(LookupError):
    """Raised when publishing references a template id that does not exist.

    The router maps this to a 404 so publishing a missing template never leaks
    an existence oracle or raises an unhandled 500. In practice the router
    pre-checks ownership (and therefore existence) before calling the service,
    so this guards the service for any other caller.
    """

    def __init__(self, template_id: uuid.UUID) -> None:
        self.template_id = template_id
        super().__init__(f"labor rate template not found: {template_id}")


def _crew_to_breakdown(build: rate_math.CrewBuildUp, currency: str) -> CrewBreakdown:
    """Map a pure crew build-up onto the response schema."""
    return CrewBreakdown(
        currency=currency,
        headcount=build.headcount,
        total_cost_per_hour=build.total_cost_per_hour,
        blended_hourly_rate=build.blended_hourly_rate,
        members=[
            CrewMemberLineOut(
                trade=member.trade,
                count=member.count,
                all_in_rate=member.all_in_rate,
                line_cost=member.line_cost,
            )
            for member in build.members
        ],
    )


def compute_breakdown(req: ComputeRequest) -> RateBreakdown:
    """Build the all-in rate breakdown (and optional crew blend) for a request.

    Pure function of its input - no I/O - so it is safe to call directly from
    the request handler without a session.

    Args:
        req: The compute request (base wage, on-costs and optional crew).

    Returns:
        The full :class:`RateBreakdown`.
    """
    components = [rate_math.OnCost(label=c.label, kind=c.kind, value=c.value) for c in req.components]
    build = rate_math.build_up(req.base_wage, components)

    crew_out: CrewBreakdown | None = None
    if req.crew:
        crew_build = rate_math.crew_rate(
            [rate_math.CrewMemberInput(trade=m.trade, count=m.count, all_in_rate=m.all_in_rate) for m in req.crew]
        )
        crew_out = _crew_to_breakdown(crew_build, req.currency)

    return RateBreakdown(
        base_wage=build.base_wage,
        currency=req.currency,
        percentage_total=build.percentage_total,
        fixed_total=build.fixed_total,
        all_in_rate=build.all_in_rate,
        lines=[
            OnCostLineOut(
                label=line.label,
                kind=line.kind,
                value=line.value,
                amount=line.amount,
                subtotal=line.subtotal,
            )
            for line in build.lines
        ],
        crew=crew_out,
    )


class LaborRateService:
    """Business logic for labor rate templates and crews."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Compute ─────────────────────────────────────────────────────────────

    @staticmethod
    def compute(req: ComputeRequest) -> RateBreakdown:
        """Return the built-up rate breakdown for a stateless request."""
        return compute_breakdown(req)

    # ── Templates ───────────────────────────────────────────────────────────

    def to_template_response(self, template: LaborRateTemplate) -> TemplateResponse:
        """Convert a template ORM row to its response, computing the all-in rate."""
        components = list(template.components)
        all_in = rate_math.all_in_rate(
            template.base_wage,
            [rate_math.OnCost(label=c.label, kind=c.kind, value=c.value) for c in components],
        )
        return TemplateResponse(
            id=template.id,
            owner_id=template.owner_id,
            name=template.name,
            base_wage=template.base_wage,
            currency=template.currency,
            description=template.description,
            components=components,
            all_in_rate=all_in,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    async def create_template(self, data: TemplateCreate, owner_id: uuid.UUID | None) -> LaborRateTemplate:
        """Create a template and its on-cost components.

        Args:
            data: The create payload.
            owner_id: The owning user (``None`` for a platform-wide row).

        Returns:
            The persisted template with its components loaded.
        """
        template = LaborRateTemplate(
            owner_id=owner_id,
            name=data.name,
            base_wage=data.base_wage,
            currency=data.currency,
            description=data.description,
        )
        for index, component in enumerate(data.components):
            template.components.append(
                OnCostComponent(
                    label=component.label,
                    kind=component.kind,
                    value=component.value,
                    sort_order=index,
                )
            )
        self.session.add(template)
        await self.session.flush()
        return template

    async def get_template(self, template_id: uuid.UUID) -> LaborRateTemplate | None:
        """Fetch a template with its components, or ``None`` when missing."""
        stmt = (
            select(LaborRateTemplate)
            .where(LaborRateTemplate.id == template_id)
            .options(selectinload(LaborRateTemplate.components))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_templates(self, owner_id: uuid.UUID | None) -> list[LaborRateTemplate]:
        """List a user's templates (or all, for an unscoped/admin caller).

        Args:
            owner_id: The owning user to scope to, or ``None`` for no scope.

        Returns:
            Templates ordered most-recent first.
        """
        stmt = select(LaborRateTemplate).options(selectinload(LaborRateTemplate.components))
        if owner_id is not None:
            stmt = stmt.where(LaborRateTemplate.owner_id == owner_id)
        stmt = stmt.order_by(LaborRateTemplate.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_template(self, template: LaborRateTemplate, data: TemplateUpdate) -> LaborRateTemplate:
        """Apply a partial update, optionally replacing the component list.

        Args:
            template: The already-loaded template to mutate.
            data: The partial update payload.

        Returns:
            The updated template.
        """
        fields = data.model_dump(exclude_unset=True)

        if "name" in fields:
            template.name = data.name  # type: ignore[assignment]
        if "base_wage" in fields and data.base_wage is not None:
            template.base_wage = data.base_wage
        if "currency" in fields and data.currency is not None:
            template.currency = data.currency
        if "description" in fields and data.description is not None:
            template.description = data.description

        if data.components is not None:
            template.components.clear()
            for index, component in enumerate(data.components):
                template.components.append(
                    OnCostComponent(
                        label=component.label,
                        kind=component.kind,
                        value=component.value,
                        sort_order=index,
                    )
                )

        await self.session.flush()
        return template

    async def delete_template(self, template: LaborRateTemplate) -> None:
        """Delete a template and its components (cascade)."""
        await self.session.delete(template)
        await self.session.flush()

    # ── Publish (rate -> cost database link) ─────────────────────────────────

    async def publish_template_as_cost_item(
        self,
        template_id: uuid.UUID,
        *,
        region: str | None = None,
        catalog: uuid.UUID | None = None,
        currency: str | None = None,
        owner_id: str | None = None,
    ) -> "CostItem":
        """Publish a template's all-in rate as a reusable labor cost item.

        Closes the missing rate -> cost-database link: a rate built here becomes
        a pickable cost line in the very same pickers assemblies and the BOQ
        already use. The template is resolved, its all-in Decimal rate is
        computed exactly as the priced-assembly build does
        (:func:`rate_math.all_in_rate` over the base wage and on-cost
        components, so the published rate equals the rate an assembly prices
        with), and a labour :class:`CostItem` is created through the existing
        costs service - no new columns, no migration. The cost item carries unit
        ``h``, the all-in rate (Decimal-as-string), resource kind ``labor`` and
        a clear name (template name plus region).

        Idempotent publish (upsert). The item's ``code`` encodes the template
        and the target catalog and the region lives in the ``region`` column, so
        the ``(code, region)`` uniqueness the costs table already enforces makes
        the dedup key exactly (template, region, catalog). When a matching
        published item already exists it is updated in place (rate, currency,
        name, resource tagging, ``is_active``) rather than duplicated; otherwise
        a fresh one is created.

        Args:
            template_id: The labour-rate template to publish.
            region: Region tag for the cost item; blank resolves to global/NULL.
            catalog: Owning cost catalog id. When set and no ``currency`` is
                given, the item inherits the catalog currency at creation.
            currency: ISO currency override; otherwise the template's currency
                (then the catalog's, then region-derived at read time).
            owner_id: The publishing user id, recorded in metadata for
                provenance. Cost items are global, so this never scopes the row.

        Returns:
            The created or updated labour :class:`CostItem`.

        Raises:
            LaborRateTemplateNotFoundError: When ``template_id`` does not resolve.
        """
        from app.modules.costs.schemas import CostItemCreate, CostItemUpdate
        from app.modules.costs.service import CostItemService

        template = await self.get_template(template_id)
        if template is None:
            raise LaborRateTemplateNotFoundError(template_id)

        all_in = _template_all_in_rate(template)
        region_norm = (region or "").strip() or None
        resolved_currency = (currency or "").strip() or (template.currency or "").strip()
        code = _published_labor_code(template_id, catalog)
        description = _published_labor_description(template.name, region_norm)

        metadata: dict[str, Any] = {
            "resource_kind": _PUBLISHED_LABOR_KIND,
            "published_from": "labor_rate_template",
            "labor_rate_template_id": str(template_id),
            "base_wage": format(template.base_wage, "f"),
            "all_in_rate": format(all_in, "f"),
        }
        if owner_id:
            metadata["published_by"] = str(owner_id)
        classification = {"collection": _PUBLISHED_LABOR_COLLECTION, "resource_kind": _PUBLISHED_LABOR_KIND}

        costs = CostItemService(self.session)
        existing = await costs.repo.get_by_code(code, region=region_norm)
        if existing is not None:
            # Same template + region + catalog: refresh the row in place so a
            # re-publish never leaves a duplicate pickable line behind.
            update_fields: dict[str, Any] = {
                "description": description,
                "unit": _PUBLISHED_LABOR_UNIT,
                "rate": all_in,
                "source": _PUBLISHED_LABOR_SOURCE,
                "classification": classification,
                "tags": [_PUBLISHED_LABOR_KIND],
                "metadata": metadata,
                "is_active": True,
            }
            if resolved_currency:
                update_fields["currency"] = resolved_currency
            return await costs.update_cost_item(existing.id, CostItemUpdate(**update_fields))

        return await costs.create_cost_item(
            CostItemCreate(
                code=code,
                description=description,
                unit=_PUBLISHED_LABOR_UNIT,
                rate=all_in,
                currency=resolved_currency,
                source=_PUBLISHED_LABOR_SOURCE,
                classification=classification,
                tags=[_PUBLISHED_LABOR_KIND],
                region=region_norm,
                catalog_id=catalog,
                metadata=metadata,
            )
        )

    # ── Crews ───────────────────────────────────────────────────────────────

    async def save_crew(self, data: CrewSaveRequest, owner_id: uuid.UUID | None) -> CrewResponse:
        """Create or replace a crew's members and return its blended rate.

        Args:
            data: The crew payload (optional crew id, currency and members).
            owner_id: The owning user.

        Returns:
            The saved crew with its blended breakdown.
        """
        crew_id = data.crew_id or uuid.uuid4()

        # Replace: drop the crew's existing members for this owner, then insert.
        await self.session.execute(
            delete(CrewMember).where(CrewMember.crew_id == crew_id, CrewMember.owner_id == owner_id)
        )
        for index, member in enumerate(data.members):
            self.session.add(
                CrewMember(
                    owner_id=owner_id,
                    crew_id=crew_id,
                    trade=member.trade,
                    count=member.count,
                    all_in_rate=member.all_in_rate,
                    currency=data.currency,
                    sort_order=index,
                )
            )
        await self.session.flush()
        return await self.get_crew(crew_id, owner_id)

    async def list_crew_members(self, crew_id: uuid.UUID, owner_id: uuid.UUID | None) -> list[CrewMember]:
        """Return a crew's members ordered by sort order."""
        stmt = select(CrewMember).where(CrewMember.crew_id == crew_id)
        if owner_id is not None:
            stmt = stmt.where(CrewMember.owner_id == owner_id)
        stmt = stmt.order_by(CrewMember.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_crew(self, crew_id: uuid.UUID, owner_id: uuid.UUID | None) -> CrewResponse:
        """Return a crew's members plus its blended rate breakdown."""
        members = await self.list_crew_members(crew_id, owner_id)
        currency = next((m.currency for m in members if m.currency), "")
        build = rate_math.crew_rate(
            [rate_math.CrewMemberInput(trade=m.trade, count=m.count, all_in_rate=m.all_in_rate) for m in members]
        )
        return CrewResponse(
            crew_id=crew_id,
            currency=currency,
            headcount=build.headcount,
            total_cost_per_hour=build.total_cost_per_hour,
            blended_hourly_rate=build.blended_hourly_rate,
            members=[CrewMemberOut.model_validate(m) for m in members],
        )

    async def delete_crew(self, crew_id: uuid.UUID, owner_id: uuid.UUID | None) -> int:
        """Delete every member of a crew, returning how many rows were removed."""
        result = await self.session.execute(
            delete(CrewMember).where(CrewMember.crew_id == crew_id, CrewMember.owner_id == owner_id)
        )
        await self.session.flush()
        return int(result.rowcount or 0)


# ── Publish helpers (a template's all-in rate -> a labor cost item) ───────────
# A published labour rate is an atomic priced resource, so it lands in the cost
# table as a cost item priced per hour (unit ``h``) and tagged as a ``labor``
# resource - the same canonical token assemblies, the BoQ and the price
# breakdown already read, so a published rate reads and prices identically.

# Cost item shape for a published labour rate.
_PUBLISHED_LABOR_UNIT = "h"
# Provenance marker in ``CostItem.source`` so published rates are identifiable
# and never mistaken for imported CWICR rows.
_PUBLISHED_LABOR_SOURCE = "labor_rate"
# Canonical resource-kind token shared across the cost spine ("labor").
_PUBLISHED_LABOR_KIND = ResourceKind.LABOUR.value
# Human-facing classification collection a published labour rate files under.
_PUBLISHED_LABOR_COLLECTION = "Labour"


def _template_all_in_rate(template: LaborRateTemplate) -> Decimal:
    """All-in Decimal rate for a template, computed exactly as the norm build.

    Mirrors ``norm_expansion._resolve_labor_rate`` so a published rate equals the
    rate a priced assembly built from the same template would carry.
    """
    return rate_math.all_in_rate(
        template.base_wage,
        [rate_math.OnCost(label=c.label, kind=c.kind, value=c.value) for c in template.components],
    )


def _published_labor_code(template_id: uuid.UUID, catalog_id: uuid.UUID | None) -> str:
    """Deterministic cost-item code encoding the template and target catalog.

    The region lives in the cost item's own ``region`` column, so the existing
    ``(code, region)`` uniqueness turns this code into the dedup key (template,
    region, catalog): re-publishing the same trio lands on the same row.
    """
    catalog_part = catalog_id.hex if catalog_id is not None else "GLOBAL"
    return f"LABOR-RATE-{template_id.hex}-{catalog_part}"


def _published_labor_description(template_name: str, region: str | None) -> str:
    """Clear cost-item name: the template name, suffixed with the region."""
    base = (template_name or "").strip() or "Labor rate"
    return f"{base} ({region})" if region else base
