# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design Options API routes.

Auto-mounted at ``/api/v1/design-options``.

Endpoints (P1 - set/option CRUD, attach-model, generate/pricing):
    POST   /sets/                              - create a design-option set
    GET    /sets/?project_id=X                 - list a project's option sets
    GET    /sets/{set_id}                       - get one set with its options
    POST   /sets/{set_id}/options/             - add an option to a set
    POST   /sets/{set_id}/baseline/            - mark an option as the baseline
    DELETE /sets/{set_id}                       - delete a set (and its options)
    POST   /options/{option_id}/attach-model/  - link a BIM model or a document
    POST   /options/{option_id}/generate/      - preview (dry run) or price an option
    DELETE /options/{option_id}                 - delete a single option

Every handler is gated by ``verify_project_access`` on the resource's project, so
a set or option from another tenant reads as 404 (never 403), the same IDOR-safe
convention used across the platform. Money, quantity and ratio values are plain
decimal strings on the wire (the Decimal-as-string contract); no float is ever
returned.

The side-by-side comparison and the spreadsheet export are appended below by the
comparison phase; they read the baseline and the per-option breakdown snapshots
this module persists.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.design_options.schemas import (
    AttachModelRequest,
    DesignOptionBaselineRequest,
    DesignOptionCreate,
    DesignOptionGenerateRequest,
    DesignOptionGenerateResponse,
    DesignOptionResponse,
    DesignOptionSetCreate,
    DesignOptionSetResponse,
)
from app.modules.design_options.service import DesignOptionsService

router = APIRouter(tags=["design_options"])


def _get_service(session: SessionDep) -> DesignOptionsService:
    return DesignOptionsService(session)


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """Best-effort parse of the authenticated user id into a UUID."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# ── Sets ─────────────────────────────────────────────────────────────────────


@router.post("/sets/", response_model=DesignOptionSetResponse, status_code=status.HTTP_201_CREATED)
async def create_set(
    data: DesignOptionSetCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionSetResponse:
    """Create a new design-option set for a project."""
    await verify_project_access(data.project_id, user_id, session)
    option_set = await service.create_set(data, created_by=_as_uuid(user_id))
    return DesignOptionSetResponse.model_validate(option_set)


@router.get("/sets/", response_model=list[DesignOptionSetResponse])
async def list_sets(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: DesignOptionsService = Depends(_get_service),
) -> list[DesignOptionSetResponse]:
    """List a project's design-option sets (newest first)."""
    await verify_project_access(project_id, user_id, session)
    sets = await service.list_sets(project_id)
    return [DesignOptionSetResponse.model_validate(s) for s in sets]


@router.get("/sets/{set_id}", response_model=DesignOptionSetResponse)
async def get_set(
    set_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionSetResponse:
    """Get one design-option set with its options."""
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    return DesignOptionSetResponse.model_validate(option_set)


@router.post(
    "/sets/{set_id}/options/",
    response_model=DesignOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_option(
    set_id: uuid.UUID,
    data: DesignOptionCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionResponse:
    """Add a new (empty, draft) option to a set."""
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    option = await service.create_option(option_set, data)
    return DesignOptionResponse.model_validate(option)


@router.post("/sets/{set_id}/baseline/", response_model=DesignOptionSetResponse)
async def set_baseline(
    set_id: uuid.UUID,
    data: DesignOptionBaselineRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionSetResponse:
    """Mark one option in the set as the baseline for delta comparison."""
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    updated = await service.set_baseline(option_set, data.option_id)
    return DesignOptionSetResponse.model_validate(updated)


@router.delete("/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_set(
    set_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> None:
    """Delete a set and, by cascade, all of its options."""
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    await service.delete_set(option_set)


# ── Options ──────────────────────────────────────────────────────────────────


@router.post("/options/{option_id}/attach-model/", response_model=DesignOptionResponse)
async def attach_model(
    option_id: uuid.UUID,
    data: AttachModelRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionResponse:
    """Pair an option with an existing BIM model or project document.

    The BIM hub owns CAD upload and conversion; this links an already-converted
    model (or records a document to convert) and moves the option's lifecycle
    forward. Exactly one of ``bim_model_id`` / ``source_document_id`` is required.
    """
    option = await service.get_option(option_id)
    await verify_project_access(option.project_id, user_id, session)
    updated = await service.attach_model(option, data)
    return DesignOptionResponse.model_validate(updated)


@router.post("/options/{option_id}/generate/", response_model=DesignOptionGenerateResponse)
async def generate_option(
    option_id: uuid.UUID,
    data: DesignOptionGenerateRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionGenerateResponse:
    """Preview (dry run) or apply the AI match into the option's own BOQ.

    With ``dry_run`` true the match runs and the would-be positions and totals
    are returned without writing anything (AI-augmented, human-confirmed). With
    ``dry_run`` false the confirmed matches are applied into the option's own BOQ
    and the option is priced (direct cost, markups, grand total, cost per m2 and
    a by-trade breakdown, all FX-correct in the project base currency).
    """
    option = await service.get_option(option_id)
    await verify_project_access(option.project_id, user_id, session)
    return await service.generate(option, data, actor_id=_as_uuid(user_id))


@router.delete("/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_option(
    option_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> None:
    """Delete a single option."""
    option = await service.get_option(option_id)
    await verify_project_access(option.project_id, user_id, session)
    await service.delete_option(option)


# ── comparison + export endpoints appended by the comparison phase ────────────
# The comparison phase appends GET /sets/{set_id}/comparison/ and
# GET /sets/{set_id}/comparison.xlsx below, reusing the same ``router`` object,
# the persisted baseline and the per-option breakdown snapshots. Append only; do
# not rewrite the handlers above and keep this marker.

# Imports for the appended comparison handler are kept here (module-level, in the
# comparison phase's own section) so the base import block above stays untouched;
# E402 is ignored project-wide for exactly this pattern.
from app.modules.design_options.comparison import DesignOptionComparator
from app.modules.design_options.schemas import DesignOptionComparisonResponse


@router.get("/sets/{set_id}/comparison/", response_model=DesignOptionComparisonResponse)
async def get_comparison(
    set_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> DesignOptionComparisonResponse:
    """Compare every option in a set side by side in one comparison currency.

    Reads each option's own bill of quantities, rebases every option to the set's
    single comparison currency (never blending currencies), and returns the
    per-option columns, the by-trade delta table, a transparent recommendation and
    a set-level fairness banner. Read-only; nothing is persisted. Access is gated
    on the set's project, so a set from another tenant reads as 404.
    """
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    return await DesignOptionComparator(session).build(option_set)


# ── option-appraisal export (export phase) ────────────────────────────────────
# Imports for the appended export handler are kept in this export-phase section
# (module-level, E402 ignored project-wide) so the base and comparison import
# blocks above stay untouched.
import io

from fastapi.responses import StreamingResponse

from app.core.http_headers import content_disposition_attachment
from app.modules.design_options.exporters import (
    XLSX_MEDIA_TYPE,
    build_option_appraisal_workbook,
    option_appraisal_filename,
)


@router.get("/sets/{set_id}/comparison.xlsx")
async def export_comparison_xlsx(
    set_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: DesignOptionsService = Depends(_get_service),
) -> StreamingResponse:
    """Download the option appraisal for a set as a formatted spreadsheet.

    Builds the same side-by-side comparison the JSON endpoint returns (one
    comparison currency, never blending), then writes it to an .xlsx workbook: the
    per-option appraisal matrix, the by-trade cost breakdown, the transparent
    recommendation and the fairness banner. Read-only; nothing is persisted.
    Access is gated on the set's project, so a set from another tenant reads as
    404.
    """
    option_set = await service.get_set(set_id)
    await verify_project_access(option_set.project_id, user_id, session)
    comparison = await DesignOptionComparator(session).build(option_set)
    blob = build_option_appraisal_workbook(comparison)
    filename = option_appraisal_filename(comparison.set_name)
    return StreamingResponse(
        io.BytesIO(blob),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": content_disposition_attachment(filename),
            "Content-Length": str(len(blob)),
        },
    )
