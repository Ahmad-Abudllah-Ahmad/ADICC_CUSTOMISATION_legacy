# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Closeout API routes (auto-mounted at /api/v1/closeout).

Endpoints (all RequirePermission + per-project access check):
    GET    /projects/{project_id}/package         get-or-404
    POST   /projects/{project_id}/package         create from project_type
    GET    /packages/{id}                          full response (slots + completeness + gaps)
    POST   /packages/{id}/slots                    add custom slot
    PATCH  /slots/{id}                             update slot
    DELETE /slots/{id}                             remove slot
    POST   /slots/{id}/bind                        bind document / external URL
    POST   /slots/{id}/unbind                      clear binding
    POST   /slots/{id}/verify                      human sign-off
    POST   /packages/{id}/suggest-bindings         AI suggest (never auto-binds)
    POST   /packages/{id}/build                    submit build job (poll /jobs)
    GET    /packages/{id}/download                 stream the built ZIP (409 if never built)
"""

from __future__ import annotations

import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.http_headers import content_disposition_attachment
from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.closeout.models import CloseoutBinding, CloseoutPackage, CloseoutSlot
from app.modules.closeout.schemas import (
    BindingSuggestion,
    BindSlotRequest,
    BuildPackageResponse,
    CloseoutBindingResponse,
    CloseoutPackageResponse,
    CloseoutSlotResponse,
    CreatePackageRequest,
    CreateSlotRequest,
    OutstandingWork,
    SlotStatus,
    SuggestBindingsResponse,
    UpdateSlotRequest,
    VerifySlotRequest,
)
from app.modules.closeout.service import CloseoutService

router = APIRouter(tags=["closeout"])
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> CloseoutService:
    return CloseoutService(session)


# ── Response builders ────────────────────────────────────────────────────────


async def _binding_response(
    service: CloseoutService,
    binding: CloseoutBinding | None,
) -> CloseoutBindingResponse | None:
    if binding is None:
        return None
    document_name: str | None = None
    if binding.document_id is not None:
        try:
            from app.modules.documents.models import Document

            doc = await service.session.get(Document, binding.document_id)
            document_name = doc.name if doc is not None else None
        except Exception:  # noqa: BLE001 - name is cosmetic
            document_name = None
    return CloseoutBindingResponse(
        id=binding.id,
        slot_id=binding.slot_id,
        document_id=binding.document_id,
        document_name=document_name,
        external_url=binding.external_url,
        is_verified=binding.is_verified,
        verified_by=binding.verified_by,
        verified_at=binding.verified_at,
        suggested_by_ai=binding.suggested_by_ai,
        ai_confidence=binding.ai_confidence,
        metadata=binding.metadata_ or {},
        created_at=binding.created_at,
    )


async def _package_response(service: CloseoutService, package: CloseoutPackage) -> CloseoutPackageResponse:
    slots = await service.repo.list_slots(package.id)
    bindings = await service.repo.list_bindings_for_package(package.id)
    has_built = bool(package.package_key)
    # One live open-work read, shared by the slot statuses and the gap list, so
    # the certifying gate and the advisory rollup agree and query once.
    outstanding = await service._outstanding_work(package.project_id)

    slot_views: list[CloseoutSlotResponse] = []
    for slot in slots:
        binding = bindings.get(slot.id)
        st = service._slot_status(slot, binding, has_built=has_built, outstanding=outstanding)
        slot_views.append(
            CloseoutSlotResponse(
                id=slot.id,
                package_id=slot.package_id,
                slot_key=slot.slot_key,
                title=slot.title,
                category=slot.category,
                discipline=slot.discipline,
                is_required=slot.is_required,
                source_kind=slot.source_kind,
                generated_artifact=slot.generated_artifact,
                ordinal=slot.ordinal,
                metadata=slot.metadata_ or {},
                status=SlotStatus(st),
                binding=await _binding_response(service, binding),
            )
        )

    gaps = await service.gaps(package, outstanding=outstanding)
    ready = len(gaps) == 0 and package.required_slot_count > 0
    meta = package.metadata_ or {}
    return CloseoutPackageResponse(
        id=package.id,
        project_id=package.project_id,
        title=package.title,
        project_type=package.project_type,
        status=package.status,
        checklist_template=package.checklist_template,
        required_slot_count=package.required_slot_count,
        delivered_slot_count=package.delivered_slot_count,
        completeness_pct=package.completeness_pct,
        last_built_job_id=package.last_built_job_id,
        last_built_at=package.last_built_at,
        has_built_package=has_built,
        metadata=meta,
        created_at=package.created_at,
        updated_at=package.updated_at,
        issued_at=meta.get("issued_at"),
        issued_by=meta.get("issued_by"),
        slots=slot_views,
        gaps=gaps,
        ready=ready,
        outstanding_work=OutstandingWork(**outstanding),
    )


async def _slot_response(service: CloseoutService, slot: CloseoutSlot) -> CloseoutSlotResponse:
    binding = await service.repo.get_binding_for_slot(slot.id)
    package = await service.repo.get_package(slot.package_id)
    has_built = bool(package.package_key) if package is not None else False
    # Apply the same live certifying gate the package view uses, so a single
    # slot echoed after a mutation agrees with the full readiness picture.
    outstanding = await service._outstanding_work(package.project_id) if package is not None else None
    st = service._slot_status(slot, binding, has_built=has_built, outstanding=outstanding)
    return CloseoutSlotResponse(
        id=slot.id,
        package_id=slot.package_id,
        slot_key=slot.slot_key,
        title=slot.title,
        category=slot.category,
        discipline=slot.discipline,
        is_required=slot.is_required,
        source_kind=slot.source_kind,
        generated_artifact=slot.generated_artifact,
        ordinal=slot.ordinal,
        metadata=slot.metadata_ or {},
        status=SlotStatus(st),
        binding=await _binding_response(service, binding),
    )


async def _load_slot_and_verify(
    service: CloseoutService,
    slot_id: uuid.UUID,
    user_id: str | None,
) -> CloseoutSlot:
    """Load a slot, then verify the caller has access to its project."""
    slot = await service.get_slot_or_404(slot_id)
    package = await service.get_package_or_404(slot.package_id)
    await verify_project_access(package.project_id, user_id or "", service.session)
    return slot


async def _load_package_and_verify(
    service: CloseoutService,
    package_id: uuid.UUID,
    user_id: str | None,
) -> CloseoutPackage:
    package = await service.get_package_or_404(package_id)
    await verify_project_access(package.project_id, user_id or "", service.session)
    return package


# ── Package endpoints ─────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/package", response_model=CloseoutPackageResponse)
async def get_project_package(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.read")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutPackageResponse:
    """Get the closeout package for a project (404 if not created yet)."""
    await verify_project_access(project_id, user_id or "", session)
    package = await service.get_package_for_project(project_id)
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No closeout package for this project")
    return await _package_response(service, package)


@router.post("/projects/{project_id}/package", response_model=CloseoutPackageResponse, status_code=201)
async def create_project_package(
    project_id: uuid.UUID,
    body: CreatePackageRequest,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.create")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutPackageResponse:
    """Create the project's closeout package, seeded from the project type."""
    await verify_project_access(project_id, user_id or "", session)
    package = await service.create_package(project_id, body.project_type, title=body.title)
    return await _package_response(service, package)


@router.get("/packages/{package_id}", response_model=CloseoutPackageResponse)
async def get_package(
    package_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.read")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutPackageResponse:
    """Full package view with slots, completeness and gaps."""
    package = await _load_package_and_verify(service, package_id, user_id)
    return await _package_response(service, package)


@router.post("/packages/{package_id}/slots", response_model=CloseoutSlotResponse, status_code=201)
async def add_slot(
    package_id: uuid.UUID,
    body: CreateSlotRequest,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.update")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutSlotResponse:
    """Add a custom checklist slot to a package."""
    package = await _load_package_and_verify(service, package_id, user_id)
    slot = await service.add_slot(package, body.model_dump())
    return await _slot_response(service, slot)


@router.patch("/slots/{slot_id}", response_model=CloseoutSlotResponse)
async def update_slot(
    slot_id: uuid.UUID,
    body: UpdateSlotRequest,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.update")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutSlotResponse:
    """Update a checklist slot."""
    slot = await _load_slot_and_verify(service, slot_id, user_id)
    slot = await service.update_slot(slot, body.model_dump(exclude_unset=True))
    return await _slot_response(service, slot)


@router.delete("/slots/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.delete")),
    service: CloseoutService = Depends(_get_service),
) -> None:
    """Remove a checklist slot."""
    slot = await _load_slot_and_verify(service, slot_id, user_id)
    await service.delete_slot(slot)


@router.post("/slots/{slot_id}/bind", response_model=CloseoutSlotResponse)
async def bind_slot(
    slot_id: uuid.UUID,
    body: BindSlotRequest,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.update")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutSlotResponse:
    """Bind a slot to a CDE document or external URL."""
    slot = await _load_slot_and_verify(service, slot_id, user_id)
    await service.bind_slot(
        slot,
        document_id=body.document_id,
        external_url=body.external_url,
        mark_verified=body.mark_verified,
        verified_by=str(user_id) if user_id else None,
        metadata=body.metadata,
    )
    return await _slot_response(service, slot)


@router.post("/slots/{slot_id}/unbind", response_model=CloseoutSlotResponse)
async def unbind_slot(
    slot_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.update")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutSlotResponse:
    """Clear a slot's binding."""
    slot = await _load_slot_and_verify(service, slot_id, user_id)
    await service.unbind_slot(slot)
    return await _slot_response(service, slot)


@router.post("/slots/{slot_id}/verify", response_model=CloseoutSlotResponse)
async def verify_slot(
    slot_id: uuid.UUID,
    body: VerifySlotRequest,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.verify")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutSlotResponse:
    """Human sign-off on a slot's evidence (manager act)."""
    slot = await _load_slot_and_verify(service, slot_id, user_id)
    await service.verify_slot(slot, is_verified=body.is_verified, verified_by=str(user_id) if user_id else None)
    return await _slot_response(service, slot)


@router.post("/packages/{package_id}/suggest-bindings", response_model=SuggestBindingsResponse)
async def suggest_bindings(
    package_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.read")),
    service: CloseoutService = Depends(_get_service),
) -> SuggestBindingsResponse:
    """AI-suggest which CDE documents fill empty slots. Binds nothing."""
    package = await _load_package_and_verify(service, package_id, user_id)
    raw = await service.suggest_bindings(package)
    return SuggestBindingsResponse(suggestions=[BindingSuggestion(**s) for s in raw])


@router.post("/packages/{package_id}/build", response_model=BuildPackageResponse)
async def build_package(
    package_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.build")),
    service: CloseoutService = Depends(_get_service),
) -> BuildPackageResponse:
    """Submit an idempotent build job and return the JobRun id to poll."""
    package = await _load_package_and_verify(service, package_id, user_id)
    job = await service.build_package(package)
    return BuildPackageResponse(
        job_id=job.id,
        status=job.status,
        progress_percent=job.progress_percent,
        package_id=package.id,
    )


@router.post("/packages/{package_id}/issue", response_model=CloseoutPackageResponse)
async def issue_package(
    package_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.verify")),
    service: CloseoutService = Depends(_get_service),
) -> CloseoutPackageResponse:
    """Issue the package to the client (terminal state).

    Rejects with 409 unless every required item is delivered and every
    certifying artifact's live work is complete. Issuing to the client is a
    manager sign-off act, so it reuses the closeout.verify permission.
    """
    package = await _load_package_and_verify(service, package_id, user_id)
    package = await service.issue_package(package, issued_by=str(user_id) if user_id else None)
    return await _package_response(service, package)


@router.get("/packages/{package_id}/download")
async def download_package(
    package_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("closeout.read")),
    service: CloseoutService = Depends(_get_service),
) -> StreamingResponse:
    """Stream the built closeout ZIP from storage (409 if never built)."""
    from app.core.storage import get_storage_backend

    package = await _load_package_and_verify(service, package_id, user_id)
    if not package.package_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closeout package has not been built yet - run Build first",
        )
    try:
        data = await get_storage_backend().get(package.package_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Built package is no longer available - rebuild it",
        ) from exc
    filename = f"closeout_{package.project_id}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition_attachment(filename),
            "Content-Length": str(len(data)),
        },
    )
