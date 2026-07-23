# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Assembly API routes.

Endpoints:
    POST   /                          - Create a new assembly
    GET    /                          - Search assemblies (q, category, unit, project_id, is_template)
    POST   /ai-generate               - AI-generate an assembly from natural language
    GET    /{assembly_id}             - Get assembly with all components
    PATCH  /{assembly_id}             - Update assembly
    DELETE /{assembly_id}             - Delete assembly and all components
    POST   /{assembly_id}/components            - Add a component
    PATCH  /{assembly_id}/components/{cid}      - Update a component
    DELETE /{assembly_id}/components/{cid}      - Delete a component
    POST   /{assembly_id}/apply-to-boq          - Apply assembly to a BOQ
    POST   /{assembly_id}/clone                 - Clone assembly
"""

import logging
import uuid
from datetime import UTC
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.i18n import get_locale
from app.core.validation.messages import translate
from app.dependencies import CurrentUserId, CurrentUserPayload, RequirePermission, SessionDep
from app.modules.assemblies.schemas import (
    AppliedComponent,
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    ApplyToBOQRequest,
    AssemblyCreate,
    AssemblyImportRequest,
    AssemblyResponse,
    AssemblySearchResponse,
    AssemblyTemplateResponse,
    AssemblyTemplateSearchResponse,
    AssemblyUpdate,
    AssemblyWithComponents,
    CloneAssemblyRequest,
    ComponentCreate,
    ComponentResponse,
    ComponentUpdate,
    ExpandPreviewRequest,
    ExpandPreviewResponse,
    ParameterValidationResponse,
    ReorderComponentsRequest,
)
from app.modules.assemblies.service import AssemblyService, _str_to_float

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assemblies"])


def _get_service(session: SessionDep) -> AssemblyService:
    return AssemblyService(session)


def _scope_owner_id(user_id: str, payload: dict | None) -> uuid.UUID | None:
    """Resolve the owner scope for collection/stats endpoints.

    Admins (role claim == ``admin``) get ``None`` - an unscoped,
    platform-wide view. Everyone else is pinned to their own ``owner_id``
    so list + stats never leak another tenant's assemblies (the per-item
    endpoints already 404 for non-owners; this closes the matching gap in
    the collection / aggregate endpoints).
    """
    if payload and payload.get("role") == "admin":
        return None
    try:
        return uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None


async def _verify_assembly_owner(
    session: SessionDep,
    assembly_id: uuid.UUID,
    user_id: str,
    payload: dict | None = None,
) -> None:
    """Load an assembly and verify ownership.

    Admins bypass the check via the role claim on the JWT payload.

    Returns 404 (not 403) on ownership mismatch so attackers cannot
    enumerate valid assembly UUIDs by probing for 403 responses.
    """
    if payload and payload.get("role") == "admin":
        return

    from app.modules.assemblies.repository import AssemblyRepository

    repo = AssemblyRepository(session)
    assembly = await repo.get_by_id(assembly_id)
    if assembly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assembly not found",
        )
    # Legacy/global templates with no owner are readable only by admins (handled
    # above). Treat as not-found for regular users to avoid leaking their ids.
    if assembly.owner_id is None or str(assembly.owner_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assembly not found",
        )


async def _verify_target_boq_owner(
    session: SessionDep,
    boq_id: uuid.UUID,
    user_id: str,
    payload: dict | None = None,
) -> None:
    """Verify the user owns the project that contains the given BOQ.

    Used by `apply_to_boq` to prevent cross-tenant injection of assembly
    positions into someone else's BOQ. Mirrors ``boq.router._verify_boq_owner``
    but lives here to avoid a circular import at module load time.
    """
    if payload and payload.get("role") == "admin":
        return

    from app.modules.boq.repository import BOQRepository
    from app.modules.projects.repository import ProjectRepository

    boq_repo = BOQRepository(session)
    boq = await boq_repo.get_by_id(boq_id)
    if boq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOQ not found")
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(boq.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=translate("errors.project_not_found", locale=get_locale())
        )
    if str(project.owner_id) != str(user_id):
        # 404 here too - don't let callers probe for valid BOQ ids.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOQ not found")


def _assembly_to_response(
    assembly: object,
    usage_count: int = 0,
) -> AssemblyResponse:
    """Convert an Assembly ORM model to an AssemblyResponse schema."""
    components = getattr(assembly, "components", None) or []
    metadata = getattr(assembly, "metadata_", {}) or {}
    tags: list[str] = metadata.get("tags", []) if isinstance(metadata, dict) else []
    return AssemblyResponse(
        id=assembly.id,  # type: ignore[attr-defined]
        code=assembly.code,  # type: ignore[attr-defined]
        name=assembly.name,  # type: ignore[attr-defined]
        description=assembly.description,  # type: ignore[attr-defined]
        unit=assembly.unit,  # type: ignore[attr-defined]
        category=assembly.category,  # type: ignore[attr-defined]
        classification=assembly.classification,  # type: ignore[attr-defined]
        total_rate=_str_to_float(assembly.total_rate),  # type: ignore[attr-defined]
        currency=assembly.currency,  # type: ignore[attr-defined]
        bid_factor=_str_to_float(assembly.bid_factor),  # type: ignore[attr-defined]
        regional_factors=assembly.regional_factors,  # type: ignore[attr-defined]
        parameters=getattr(assembly, "parameters", None) or [],
        is_template=assembly.is_template,  # type: ignore[attr-defined]
        project_id=assembly.project_id,  # type: ignore[attr-defined]
        owner_id=assembly.owner_id,  # type: ignore[attr-defined]
        is_active=assembly.is_active,  # type: ignore[attr-defined]
        component_count=len(components),
        usage_count=usage_count,
        tags=tags,
        metadata=metadata,
        created_at=assembly.created_at,  # type: ignore[attr-defined]
        updated_at=assembly.updated_at,  # type: ignore[attr-defined]
    )


def _component_to_response(comp: object) -> ComponentResponse:
    """Convert a Component ORM model to a ComponentResponse schema."""
    return ComponentResponse(
        id=comp.id,  # type: ignore[attr-defined]
        assembly_id=comp.assembly_id,  # type: ignore[attr-defined]
        cost_item_id=comp.cost_item_id,  # type: ignore[attr-defined]
        catalog_resource_id=getattr(comp, "catalog_resource_id", None),  # type: ignore[attr-defined]
        description=comp.description,  # type: ignore[attr-defined]
        resource_type=getattr(comp, "resource_type", None),  # type: ignore[attr-defined]
        factor=_str_to_float(comp.factor),  # type: ignore[attr-defined]
        quantity=_str_to_float(comp.quantity),  # type: ignore[attr-defined]
        quantity_formula=getattr(comp, "quantity_formula", None),  # type: ignore[attr-defined]
        unit=comp.unit,  # type: ignore[attr-defined]
        unit_cost=_str_to_float(comp.unit_cost),  # type: ignore[attr-defined]
        # v3 §10 - money as Decimal so the field_serializer emits an exact
        # decimal string, not a lossy float (mirrors the service builder).
        total=Decimal(str(comp.total or "0")),  # type: ignore[attr-defined]
        sort_order=comp.sort_order,  # type: ignore[attr-defined]
        metadata=comp.metadata_ or {},  # type: ignore[attr-defined]
        created_at=comp.created_at,  # type: ignore[attr-defined]
        updated_at=comp.updated_at,  # type: ignore[attr-defined]
    )


# ── Assembly CRUD ────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=AssemblyResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("assemblies.create"))],
)
async def create_assembly(
    data: AssemblyCreate,
    user_id: CurrentUserId,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyResponse:
    """Create a new assembly (composite cost item)."""
    assembly = await service.create_assembly(data, owner_id=user_id)
    return _assembly_to_response(assembly)


@router.get(
    "/",
    response_model=AssemblySearchResponse,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def search_assemblies(
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    q: str | None = Query(default=None, description="Text search on code, name, description"),
    category: str | None = Query(default=None, description="Filter by category"),
    unit: str | None = Query(default=None, description="Filter by unit"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    project_id: uuid.UUID | None = Query(default=None, description="Filter by project"),
    is_template: bool | None = Query(default=None, description="Filter by template flag"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    service: AssemblyService = Depends(_get_service),
) -> AssemblySearchResponse:
    """Search assemblies with optional filters and pagination.

    Scoped to the caller's own assemblies (per-tenant isolation) so the
    collection cannot leak other tenants' recipes - admins see all.
    """
    scope_owner = _scope_owner_id(user_id, payload)
    assemblies, total = await service.search_assemblies(
        q=q,
        category=category,
        unit=unit,
        tag=tag,
        project_id=project_id,
        is_template=is_template,
        offset=offset,
        limit=limit,
        owner_id=scope_owner,
    )

    # Compute usage counts for each assembly from BOQ metadata
    usage_map: dict[str, int] = {}
    try:
        usage_map = await service.get_usage_counts(
            [a.id for a in assemblies],
            owner_id=scope_owner,
        )
    except Exception:
        logger.debug("Could not compute assembly usage counts")

    return AssemblySearchResponse(
        items=[_assembly_to_response(a, usage_count=usage_map.get(str(a.id), 0)) for a in assemblies],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── AI Assembly Generation ──────────────────────────────────────────────────


class AIGenerateRequest(BaseModel):
    """Request body for AI assembly generation."""

    description: str = Field(..., min_length=3, max_length=500)
    region: str = Field(default="", max_length=50)
    unit: str = Field(default="m2", max_length=20)


@router.post(
    "/ai-generate/",
    dependencies=[Depends(RequirePermission("assemblies.create"))],
)
async def ai_generate_assembly(
    data: AIGenerateRequest,
    service: AssemblyService = Depends(_get_service),
) -> dict:
    """Generate an assembly from a natural language description.

    Searches the cost catalogue for matching components and synthesizes a
    grounded per-unit factor for each line (never a naive quantity of 1.0),
    keeping the rates catalogue-grounded. The result is NOT saved: the
    estimator reviews and confirms before creating, matching the platform's
    human-confirms-AI rule.

    Args:
        data: Description, optional region and unit.
        service: Assembly service (injected).

    Returns:
        dict with the generated assembly preview: components carrying real
        per-unit quantities, the rolled-up total rate and a confidence score.
    """
    return await service.ai_generate_preview(
        description=data.description,
        unit=data.unit,
        region=data.region,
    )


@router.get(
    "/stats/",
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def get_stats(
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    service: AssemblyService = Depends(_get_service),
) -> dict:
    """Return aggregated assembly statistics: totals, category breakdown, most-used.

    Scoped to the caller's own assemblies so the stats banner does not
    expose the platform-wide count to a non-admin tenant.
    """
    return await service.get_stats(owner_id=_scope_owner_id(user_id, payload))


@router.get(
    "/{assembly_id}",
    response_model=AssemblyWithComponents,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def get_assembly(
    assembly_id: uuid.UUID,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyWithComponents:
    """Get an assembly with all its components and computed total."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    return await service.get_assembly_with_components(assembly_id)


@router.patch(
    "/{assembly_id}",
    response_model=AssemblyResponse,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def update_assembly(
    assembly_id: uuid.UUID,
    data: AssemblyUpdate,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyResponse:
    """Update assembly metadata fields."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    is_admin = bool(payload and payload.get("role") == "admin")
    assembly = await service.update_assembly(
        assembly_id,
        data,
        caller_user_id=user_id,
        caller_is_admin=is_admin,
    )
    return _assembly_to_response(assembly)


@router.delete(
    "/{assembly_id}",
    status_code=204,
    dependencies=[Depends(RequirePermission("assemblies.delete"))],
)
async def delete_assembly(
    assembly_id: uuid.UUID,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> None:
    """Delete an assembly and all its components."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    await service.delete_assembly(assembly_id)


# ── Component CRUD ───────────────────────────────────────────────────────────


@router.post(
    "/{assembly_id}/components/",
    response_model=ComponentResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def add_component(
    assembly_id: uuid.UUID,
    data: ComponentCreate,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> ComponentResponse:
    """Add a new component to an assembly."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    component = await service.add_component(assembly_id, data)
    # Build response directly to avoid MissingGreenlet on expired ORM attrs
    try:
        return _component_to_response(component)
    except Exception:
        # Fallback: construct from known data
        from datetime import datetime

        total = data.factor * data.quantity * data.unit_cost
        now = datetime.now(UTC)
        return ComponentResponse(
            id=component.id,
            assembly_id=assembly_id,
            cost_item_id=data.cost_item_id,
            catalog_resource_id=data.catalog_resource_id,
            description=data.description,
            factor=data.factor,
            quantity=data.quantity,
            quantity_formula=data.quantity_formula,
            unit=data.unit,
            unit_cost=data.unit_cost,
            total=round(total, 2),
            sort_order=0,
            metadata={},
            created_at=now,
            updated_at=now,
        )


@router.patch(
    "/{assembly_id}/components/{component_id}",
    response_model=ComponentResponse,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def update_component(
    assembly_id: uuid.UUID,
    component_id: uuid.UUID,
    data: ComponentUpdate,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> ComponentResponse:
    """Update an assembly component. Recalculates totals."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    component = await service.update_component(assembly_id, component_id, data)
    return _component_to_response(component)


@router.delete(
    "/{assembly_id}/components/{component_id}",
    status_code=204,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def delete_component(
    assembly_id: uuid.UUID,
    component_id: uuid.UUID,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> None:
    """Delete a component from an assembly."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    await service.delete_component(assembly_id, component_id)


# ── Actions ──────────────────────────────────────────────────────────────────


@router.post(
    "/{assembly_id}/apply-to-boq/",
    status_code=201,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def apply_to_boq(
    assembly_id: uuid.UUID,
    data: ApplyToBOQRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> dict:
    """Apply an assembly to a BOQ as a new position.

    Creates a BOQ position with unit_rate = assembly total_rate (optionally
    adjusted by a regional factor) and source = "assembly".

    Verifies ownership of both the source assembly AND the target BOQ to
    prevent cross-tenant data injection.
    """
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    await _verify_target_boq_owner(session, data.boq_id, user_id, payload)
    position = await service.apply_to_boq(assembly_id, data)
    return {
        "position_id": str(position.id),  # type: ignore[attr-defined]
        "boq_id": str(data.boq_id),
        "assembly_id": str(assembly_id),
        "message": "Assembly applied to BOQ successfully",
    }


# ── Parametric assemblies (Issue #365) ───────────────────────────────────────


@router.post(
    "/{assembly_id}/validate-parameters/",
    response_model=ParameterValidationResponse,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def validate_parameters(
    assembly_id: uuid.UUID,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> ParameterValidationResponse:
    """Validate an assembly's parameter graph and resolve it at defaults.

    Returns the structured problems (unique names, resolvable references, no
    cycles) plus the resolved values so the editor can flag issues inline.
    """
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    return await service.validate_parameters(assembly_id)


@router.post(
    "/{assembly_id}/expand-preview/",
    response_model=ExpandPreviewResponse,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def expand_preview(
    assembly_id: uuid.UUID,
    data: ExpandPreviewRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> ExpandPreviewResponse:
    """Preview an assembly expansion at the supplied parameter values.

    Server-authoritative (Decimal-exact): returns each line's before (static)
    and after (computed) quantity plus the rolled-up rate, without persisting.
    """
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    return await service.expand_preview(assembly_id, data.parameter_values)


@router.post(
    "/{assembly_id}/clone/",
    response_model=AssemblyResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("assemblies.create"))],
)
async def clone_assembly(
    assembly_id: uuid.UUID,
    data: CloneAssemblyRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyResponse:
    """Clone an assembly, optionally into a different project."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    cloned = await service.clone_assembly(assembly_id, data, owner_id=user_id)
    return _assembly_to_response(cloned)


# ── Reorder ──────────────────────────────────────────────────────────────────


@router.post(
    "/{assembly_id}/reorder-components/",
    status_code=200,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def reorder_components(
    assembly_id: uuid.UUID,
    data: ReorderComponentsRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> dict:
    """Reorder components within an assembly.

    Accepts an ordered list of component IDs and updates sort_order
    accordingly.
    """
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    await service.reorder_components(assembly_id, data.component_ids)
    return {"status": "ok", "assembly_id": str(assembly_id)}


# ── Export / Import ──────────────────────────────────────────────────────────


@router.get(
    "/{assembly_id}/export/",
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def export_assembly(
    assembly_id: uuid.UUID,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> dict:
    """Export an assembly with all components as a shareable JSON payload."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    return await service.export_assembly(assembly_id)


@router.post(
    "/import/",
    response_model=AssemblyResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("assemblies.create"))],
)
async def import_assembly(
    data: AssemblyImportRequest,
    user_id: CurrentUserId,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyResponse:
    """Import an assembly from a JSON payload.

    Creates a new assembly with all components from the exported format.
    If the code already exists, a suffix is appended to make it unique.
    """
    assembly = await service.import_assembly(data.assembly, owner_id=user_id)
    return _assembly_to_response(assembly)


# ── Tags ─────────────────────────────────────────────────────────────────────


class UpdateTagsRequest(BaseModel):
    """Request body for updating assembly tags."""

    tags: list[str] = Field(default_factory=list, max_length=20)


@router.patch(
    "/{assembly_id}/tags/",
    response_model=AssemblyResponse,
    dependencies=[Depends(RequirePermission("assemblies.update"))],
)
async def update_tags(
    assembly_id: uuid.UUID,
    data: UpdateTagsRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
    service: AssemblyService = Depends(_get_service),
) -> AssemblyResponse:
    """Update tags on an assembly. Tags are stored in metadata."""
    await _verify_assembly_owner(session, assembly_id, user_id, payload)
    assembly = await service.update_tags(assembly_id, data.tags)
    return _assembly_to_response(assembly)


# ── Assembly Library templates (v3.13.0 - Slice 1) ───────────────────────────


def _template_to_response(template: object) -> AssemblyTemplateResponse:
    """Convert an AssemblyTemplate ORM row to its response schema."""
    components = getattr(template, "components", []) or []
    return AssemblyTemplateResponse(
        id=template.id,  # type: ignore[attr-defined]
        name=template.name,  # type: ignore[attr-defined]
        name_translations=getattr(template, "name_translations", {}) or {},
        category=getattr(template, "category", ""),
        unit=getattr(template, "unit", ""),
        components=list(components),
        classification=getattr(template, "classification", {}) or {},
        tags=list(getattr(template, "tags", []) or []),
        is_builtin=bool(getattr(template, "is_builtin", True)),
        component_count=len(components),
        created_at=template.created_at,  # type: ignore[attr-defined]
        updated_at=template.updated_at,  # type: ignore[attr-defined]
    )


@router.get(
    "/templates/",
    response_model=AssemblyTemplateSearchResponse,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def list_templates(
    session: SessionDep,
    q: str | None = Query(default=None, description="Free-text search"),
    category: str | None = Query(default=None, description="Filter by category"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    din276: str | None = Query(default=None, description="Filter by DIN 276 KG code"),
    masterformat: str | None = Query(default=None, description="Filter by MasterFormat division"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> AssemblyTemplateSearchResponse:
    """List Assembly Library templates with filters + pagination.

    Any authenticated user with ``assemblies.read`` can browse. Templates
    are read-only at this slice; future slices add user-contributed rows.
    """
    from app.modules.assemblies.repository import AssemblyTemplateRepository

    repo = AssemblyTemplateRepository(session)
    items, total = await repo.list_all(
        offset=offset,
        limit=limit,
        q=q,
        category=category,
        tag=tag,
        classification_din276=din276,
        classification_masterformat=masterformat,
    )
    return AssemblyTemplateSearchResponse(
        items=[_template_to_response(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/templates/{template_id}",
    response_model=AssemblyTemplateResponse,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def get_template(
    template_id: uuid.UUID,
    session: SessionDep,
) -> AssemblyTemplateResponse:
    """Fetch a single Assembly Library template by id."""
    from app.modules.assemblies.repository import AssemblyTemplateRepository

    repo = AssemblyTemplateRepository(session)
    template = await repo.get_by_id(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("errors.template_not_found", locale=get_locale()),
        )
    return _template_to_response(template)


def _component_total(factor: float, quantity: float, unit_rate: float) -> float:
    """Compute one applied component's total - pure float, finite-only.

    Returns 0.0 on overflow / non-finite inputs so the rolled-up
    ``grand_total`` is always a serialisable number.
    """
    try:
        total = float(factor) * float(quantity) * float(unit_rate)
    except (TypeError, ValueError):
        return 0.0
    if total != total or total in (float("inf"), float("-inf")):  # NaN / inf
        return 0.0
    return round(total, 4)


@router.post(
    "/templates/{template_id}/apply",
    response_model=ApplyTemplateResponse,
    status_code=200,
    dependencies=[Depends(RequirePermission("assemblies.read"))],
)
async def apply_template(
    template_id: uuid.UUID,
    data: ApplyTemplateRequest,
    user_id: CurrentUserId,
    payload: CurrentUserPayload,
    session: SessionDep,
) -> ApplyTemplateResponse:
    """Resolve a template against a project's cost catalogue.

    For each component:

    1. Run the existing ``costs.matcher.match_cwicr_items`` lexical
       search against the project's bound catalogue (filtered by region
       / source when those are set on the project). The lexical channel
       is the documented fallback that works without Qdrant - tests use
       this path.
    2. Pick the top match and capture its rate, code, currency.
    3. Scale ``factor`` by the user-supplied ``quantity``.

    Returns a non-persisted preview that the FE shows for confirmation.
    Verifies the caller owns the target project (mirrors the per-tenant
    isolation already in /apply-to-boq).
    """
    from app.modules.assemblies.repository import AssemblyTemplateRepository
    from app.modules.costs.matcher import match_cwicr_items
    from app.modules.projects.repository import ProjectRepository

    repo = AssemblyTemplateRepository(session)
    template = await repo.get_by_id(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("errors.template_not_found", locale=get_locale()),
        )

    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(data.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("errors.project_not_found", locale=get_locale()),
        )

    is_admin = bool(payload and payload.get("role") == "admin")
    if not is_admin and str(project.owner_id) != str(user_id):
        # 404 instead of 403 - don't leak project existence to attackers.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("errors.project_not_found", locale=get_locale()),
        )

    region = data.region or getattr(project, "region", None) or None
    language = data.language

    components_out: list[AppliedComponent] = []
    unresolved: list[str] = []
    grand_total = 0.0
    # Target currency for the rolled-up ``grand_total``. The project currency is
    # authoritative; when the project has none we lock the target to the first
    # matched component's currency (below). Money rule: NEVER blend currencies -
    # each component is converted into the target via the project's ``fx_rates``
    # before it is summed; a foreign component with no configured FX rate is
    # kept in its own currency and flagged (non-blocking), mirroring
    # ``apply_to_boq``'s ``currency_mismatch`` behaviour rather than silently
    # adding mismatched numbers (the previous behaviour).
    from app.modules.boq.service import _project_fx_map

    currency = (getattr(project, "currency", "") or "").strip().upper()
    fx_map = _project_fx_map(project)
    fx_warnings: set[str] = set()

    def _convert_component(amount: float, src_currency: str) -> float:
        """Convert ``amount`` from ``src_currency`` into the locked target.

        Foreign→target is multiplication by ``fx_rates[src]`` (units of target
        per 1 unit of source - the same convention the BOQ rollup uses). When no
        rate is configured the amount is returned unchanged and a warning is
        recorded so the un-converted value is visible, never silently blended.
        """
        nonlocal currency
        src = (src_currency or "").strip().upper()
        if not src:
            # Match carried no currency - treat as already in the target.
            return amount
        if not currency:
            # Project had no currency: lock the target to this first currency.
            currency = src
            return amount
        if src == currency:
            return amount
        raw_rate = fx_map.get(src)
        if raw_rate:
            try:
                rate = float(raw_rate)
            except (TypeError, ValueError):
                rate = 0.0
            if rate > 0.0 and rate == rate and rate not in (float("inf"), float("-inf")):
                return amount * rate
        # No usable FX rate - keep the native value and flag the mismatch.
        fx_warnings.add(
            f"Component priced in {src} could not be converted to {currency} "
            f"(no FX rate configured); its value was kept in {src}. "
            f"Add an FX rate in Project Settings to convert it."
        )
        return amount

    for raw in template.components or []:
        query = str(raw.get("cost_match_query", "")).strip()
        factor = float(raw.get("factor", 0.0) or 0.0)
        comp_unit = str(raw.get("unit", "")).strip() or template.unit
        role = str(raw.get("role", "material"))
        description = str(raw.get("description", query))

        matches = []
        if query:
            try:
                matches = await match_cwicr_items(
                    session,
                    query,
                    unit=comp_unit or None,
                    lang=language,
                    top_k=1,
                    region=region,
                    source="cwicr",
                )
            except Exception:  # noqa: BLE001 - keep the apply preview alive
                matches = []

            # Fallback: relax to source=None when the bound catalogue is
            # not CWICR-tagged. Cheap (one extra query at most) and keeps
            # the preview useful on tenants importing third-party rates.
            if not matches:
                try:
                    matches = await match_cwicr_items(
                        session,
                        query,
                        unit=comp_unit or None,
                        lang=language,
                        top_k=1,
                        region=region,
                        source=None,
                    )
                except Exception:  # noqa: BLE001
                    matches = []

        scaled_q = factor * float(data.quantity)
        matched_id: uuid.UUID | None = None
        matched_desc = ""
        matched_code = ""
        unit_rate = 0.0
        match_score = 0.0
        match_channel = "lexical"
        if matches:
            top = matches[0]
            # ``MatchResult`` is a flat pydantic model - fields are read
            # directly, not through a wrapped ``.item``.
            try:
                unit_rate = float(getattr(top, "unit_rate", 0.0) or 0.0)
            except (TypeError, ValueError):
                unit_rate = 0.0
            match_score = float(getattr(top, "score", 0.0) or 0.0)
            match_channel = str(getattr(top, "source", "lexical"))
            matched_desc = str(getattr(top, "description", "") or "")[:200]
            matched_code = str(getattr(top, "code", "") or "")
            raw_id = getattr(top, "cost_item_id", None)
            if raw_id:
                try:
                    matched_id = uuid.UUID(str(raw_id))
                except (TypeError, ValueError):
                    matched_id = None
            m_currency = getattr(top, "currency", "") or ""
        else:
            m_currency = ""
            unresolved.append(query or description)

        # Native total (in the matched item's currency) - what the component row
        # displays. The rolled-up ``grand_total`` instead accumulates each
        # component CONVERTED into the target currency so currencies are never
        # blended (``_convert_component`` also locks the target on first match).
        total = _component_total(factor, float(data.quantity), unit_rate)
        grand_total += _convert_component(total, m_currency)

        components_out.append(
            AppliedComponent(
                description=description,
                cost_match_query=query,
                matched_cost_item_id=matched_id,
                matched_description=matched_desc,
                matched_code=matched_code,
                factor=factor,
                scaled_quantity=scaled_q,
                unit=comp_unit,
                unit_rate=unit_rate,
                total=total,
                role=role,
                match_confidence=round(match_score, 4),
                match_channel=match_channel,
            )
        )

    warnings: list[str] = []
    if unresolved:
        warnings.append(f"{len(unresolved)} component(s) could not be matched against the project's cost catalogue.")
    # Surface any currency mismatches the conversion could not resolve, so the
    # un-converted (kept-native) components are visible rather than silently
    # blended into the target-currency grand total.
    warnings.extend(sorted(fx_warnings))

    # ``total_rate`` is the per-unit rate (assembly subtotal at quantity=1);
    # ``grand_total`` is the rolled-up total for the requested quantity.
    qty_safe = float(data.quantity) if data.quantity else 1.0
    total_rate = round(grand_total / qty_safe, 4) if qty_safe else 0.0

    return ApplyTemplateResponse(
        template_id=template.id,
        template_name=template.name,
        project_id=data.project_id,
        boq_position_id=data.boq_position_id,
        quantity=float(data.quantity),
        unit=template.unit,
        currency=currency,
        components=components_out,
        total_rate=total_rate,
        grand_total=round(grand_total, 4),
        unresolved_components=unresolved,
        warnings=warnings,
    )
