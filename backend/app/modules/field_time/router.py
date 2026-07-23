# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time API routes.

Endpoints (mounted at ``/api/v1/field-time``):

    POST   /timesheets/                          - Create a draft timesheet
    GET    /timesheets/?project_id=X             - List with filters
    GET    /timesheets/summary/?project_id=X     - Project rollup
    POST   /timesheets/suggest-cost-codes/       - Ranked cost-code suggestions
    GET    /timesheets/{id}/                      - Get one
    PATCH  /timesheets/{id}/                      - Update draft header
    DELETE /timesheets/{id}/                      - Delete draft
    POST   /timesheets/{id}/lines/               - Add a line to a draft
    PATCH  /timesheets/{id}/lines/{line_id}/     - Update a draft line
    DELETE /timesheets/{id}/lines/{line_id}/     - Delete a draft line
    POST   /timesheets/{id}/submit/              - Submit for approval
    POST   /timesheets/{id}/approve/             - Approve (posts hours, mints daywork)
    POST   /timesheets/{id}/reverse/             - Reverse an approved timesheet
    GET    /timesheets/{id}/validation/          - Validation report (read-only)

Every endpoint enforces project access (IDOR-safe: 404 on both missing and
forbidden) and the field_time RBAC permissions.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.field_time import field_time_math as ft
from app.modules.field_time.models import FieldTimesheet, FieldTimesheetLine
from app.modules.field_time.schemas import (
    FieldTimesheetCreate,
    FieldTimesheetLineCreate,
    FieldTimesheetLineResponse,
    FieldTimesheetLineUpdate,
    FieldTimesheetResponse,
    FieldTimesheetUpdate,
    FieldTimeSummary,
    ReverseTimesheetRequest,
    SuggestCostCodeRequest,
    SuggestCostCodeResponse,
    ValidationReportOut,
)
from app.modules.field_time.service import FieldTimeService

router = APIRouter(tags=["field_time"])


def _get_service(session: SessionDep) -> FieldTimeService:
    return FieldTimeService(session)


def _line_to_response(line: FieldTimesheetLine) -> FieldTimesheetLineResponse:
    """Build a line response, deriving the labour / plant kind."""
    kind = ft.KIND_PLANT if line.equipment_id else ft.KIND_LABOUR
    return FieldTimesheetLineResponse(
        id=line.id,
        timesheet_id=line.timesheet_id,
        resource_id=line.resource_id,
        equipment_id=line.equipment_id,
        hours=line.hours if line.hours is not None else ft.to_decimal(0),
        cost_code=line.cost_code or "",
        wbs=line.wbs,
        is_daywork=bool(line.is_daywork),
        variation_id=line.variation_id,
        daywork_sheet_id=line.daywork_sheet_id,
        note=line.note,
        kind=kind,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def _timesheet_to_response(timesheet: FieldTimesheet) -> FieldTimesheetResponse:
    """Build a timesheet response with its lines and the hours rollup."""
    line_dicts = [
        {
            "resource_id": str(line.resource_id) if line.resource_id else None,
            "equipment_id": str(line.equipment_id) if line.equipment_id else None,
            "hours": line.hours,
        }
        for line in timesheet.lines
    ]
    # Honour the project's rounding step (from metadata) so the header totals
    # match the summary and the payroll figures.
    config = ft.read_hours_config(getattr(timesheet, "metadata_", None))
    roll = ft.rollup(line_dicts, rounding_increment=config.rounding_increment)
    return FieldTimesheetResponse(
        id=timesheet.id,
        project_id=timesheet.project_id,
        reference=timesheet.reference or "",
        date=timesheet.date,
        status=timesheet.status,
        submitted_by=timesheet.submitted_by,
        submitted_at=timesheet.submitted_at,
        approved_by=timesheet.approved_by,
        approved_at=timesheet.approved_at,
        reverses_id=timesheet.reverses_id,
        note=timesheet.note,
        metadata=getattr(timesheet, "metadata_", {}) or {},
        lines=[_line_to_response(line) for line in timesheet.lines],
        labour_hours=str(roll.labour_hours),
        plant_hours=str(roll.plant_hours),
        created_at=timesheet.created_at,
        updated_at=timesheet.updated_at,
    )


async def _authorized_timesheet(
    service: FieldTimeService,
    session: SessionDep,
    timesheet_id: uuid.UUID,
    user_id: str,
) -> FieldTimesheet:
    """Load a timesheet and assert the caller may access its project (404 else)."""
    timesheet = await service.get_timesheet(timesheet_id)
    await verify_project_access(timesheet.project_id, user_id, session)
    return timesheet


# ── Collection: static routes first (before /{id}/) ──────────────────────────


@router.get("/timesheets/summary/", response_model=FieldTimeSummary)
async def get_summary(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.read")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimeSummary:
    """Project-level rollup of field timesheets."""
    await verify_project_access(project_id, user_id, session)
    data = await service.get_summary(project_id)
    return FieldTimeSummary(
        total=data["total"],
        by_status=data["by_status"],
        labour_hours=str(data["labour_hours"]),
        plant_hours=str(data["plant_hours"]),
        overtime_hours=str(data.get("overtime_hours", "0")),
    )


@router.post("/timesheets/suggest-cost-codes/", response_model=SuggestCostCodeResponse)
async def suggest_cost_codes(
    payload: SuggestCostCodeRequest,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.read")),
    service: FieldTimeService = Depends(_get_service),
) -> SuggestCostCodeResponse:
    """Return ranked, confidence-scored cost-code suggestions (never applied)."""
    await verify_project_access(project_id, user_id, session)
    suggestions = await service.suggest_cost_codes(project_id, payload.text, limit=payload.limit)
    return SuggestCostCodeResponse(suggestions=suggestions, applied=False)


@router.get("/timesheets/", response_model=list[FieldTimesheetResponse])
async def list_timesheets(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.read")),
    service: FieldTimeService = Depends(_get_service),
) -> list[FieldTimesheetResponse]:
    """List field timesheets for a project."""
    await verify_project_access(project_id, user_id, session)
    timesheets, _total = await service.list_timesheets(
        project_id,
        offset=offset,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        status_filter=status_filter,
    )
    return [_timesheet_to_response(t) for t in timesheets]


@router.post("/timesheets/", response_model=FieldTimesheetResponse, status_code=status.HTTP_201_CREATED)
async def create_timesheet(
    payload: FieldTimesheetCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.create")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Create a new draft field timesheet."""
    await verify_project_access(payload.project_id, user_id, session)
    timesheet = await service.create_timesheet(payload, user_id)
    return _timesheet_to_response(timesheet)


# ── Item routes ──────────────────────────────────────────────────────────────


@router.get("/timesheets/{timesheet_id}/", response_model=FieldTimesheetResponse)
async def get_timesheet(
    timesheet_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.read")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Get a single field timesheet."""
    timesheet = await _authorized_timesheet(service, session, timesheet_id, user_id)
    return _timesheet_to_response(timesheet)


@router.patch("/timesheets/{timesheet_id}/", response_model=FieldTimesheetResponse)
async def update_timesheet(
    timesheet_id: uuid.UUID,
    payload: FieldTimesheetUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.update")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Update a draft timesheet's header fields."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.update_timesheet(timesheet_id, payload)
    return _timesheet_to_response(timesheet)


@router.delete("/timesheets/{timesheet_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timesheet(
    timesheet_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.delete")),
    service: FieldTimeService = Depends(_get_service),
) -> None:
    """Delete a draft timesheet."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    await service.delete_timesheet(timesheet_id)


# ── Lines ────────────────────────────────────────────────────────────────────


@router.post("/timesheets/{timesheet_id}/lines/", response_model=FieldTimesheetResponse)
async def add_line(
    timesheet_id: uuid.UUID,
    payload: FieldTimesheetLineCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.update")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Add a line to a draft timesheet."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.add_line(timesheet_id, payload)
    return _timesheet_to_response(timesheet)


@router.patch("/timesheets/{timesheet_id}/lines/{line_id}/", response_model=FieldTimesheetResponse)
async def update_line(
    timesheet_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: FieldTimesheetLineUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.update")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Update a single line on a draft timesheet."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.update_line(timesheet_id, line_id, payload)
    return _timesheet_to_response(timesheet)


@router.delete("/timesheets/{timesheet_id}/lines/{line_id}/", response_model=FieldTimesheetResponse)
async def delete_line(
    timesheet_id: uuid.UUID,
    line_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.update")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Delete a line from a draft timesheet."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.delete_line(timesheet_id, line_id)
    return _timesheet_to_response(timesheet)


# ── Lifecycle ────────────────────────────────────────────────────────────────


@router.post("/timesheets/{timesheet_id}/submit/", response_model=FieldTimesheetResponse)
async def submit_timesheet(
    timesheet_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.update")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Submit a draft timesheet for approval."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.submit_timesheet(timesheet_id, user_id)
    return _timesheet_to_response(timesheet)


@router.post("/timesheets/{timesheet_id}/approve/", response_model=FieldTimesheetResponse)
async def approve_timesheet(
    timesheet_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.approve")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Approve a submitted timesheet (posts hours, mints daywork sheets)."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    timesheet = await service.approve_timesheet(timesheet_id, user_id)
    return _timesheet_to_response(timesheet)


@router.post("/timesheets/{timesheet_id}/reverse/", response_model=FieldTimesheetResponse)
async def reverse_timesheet(
    timesheet_id: uuid.UUID,
    payload: ReverseTimesheetRequest,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.approve")),
    service: FieldTimeService = Depends(_get_service),
) -> FieldTimesheetResponse:
    """Reverse an approved timesheet with a mirrored, netting timesheet."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    reversal = await service.reverse_timesheet(timesheet_id, payload, user_id)
    return _timesheet_to_response(reversal)


@router.get("/timesheets/{timesheet_id}/validation/", response_model=ValidationReportOut)
async def get_validation(
    timesheet_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("field_time.read")),
    service: FieldTimeService = Depends(_get_service),
) -> ValidationReportOut:
    """Return the field-time validation report for a timesheet (read-only)."""
    await _authorized_timesheet(service, session, timesheet_id, user_id)
    data = await service.validate_timesheet(timesheet_id)
    return ValidationReportOut(**data)
