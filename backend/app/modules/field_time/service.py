# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time service - business logic for the foreman's field timesheet.

Stateless service layer over the pure engine
(:mod:`app.modules.field_time.field_time_math`). Responsibilities:

* Timesheet + line CRUD while the timesheet is still a draft.
* The lifecycle ``draft -> submitted -> approved``, with validation gating each
  forward step (a submit / approve is blocked when any ERROR-severity rule
  fails). Once approved a timesheet is immutable; the only correction is a
  reversing timesheet (the original flips to ``reversed`` and a new timesheet
  with ``reverses_id`` set nets it out - see :meth:`reverse_timesheet`).
* On approval, mirroring each daywork line onto a signed daywork sheet via the
  variations service, and publishing the hours / cost rollup so payroll and the
  cost / EVM model can reconcile against real booked time.

All money is ``Decimal`` and all cross-module reads are best-effort: a missing
optional collaborator degrades gracefully rather than failing the transition.
The service never commits - it flushes and lets the request-scoped session
commit, matching every peer module.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import get_locale
from app.core.json_merge import merge_metadata
from app.core.validation.engine import ValidationReport, validation_engine
from app.modules.field_time import field_time_math as ft
from app.modules.field_time.models import FieldTimesheet, FieldTimesheetLine
from app.modules.field_time.repository import FieldTimeRepository
from app.modules.field_time.schemas import (
    CostCodeSuggestionOut,
    FieldTimesheetCreate,
    FieldTimesheetLineCreate,
    FieldTimesheetLineUpdate,
    FieldTimesheetUpdate,
)

if TYPE_CHECKING:
    from app.modules.field_time.schemas import ReverseTimesheetRequest

logger = logging.getLogger(__name__)

# The rule set the validation engine runs for a field timesheet.
_RULE_SET = "field_time"
# Variation-order statuses that count as "open" (still accepting daywork cost).
_OPEN_VARIATION_STATUSES = ("issued", "in_progress")
# Lifecycle statuses.
_DRAFT = "draft"
_SUBMITTED = "submitted"
_APPROVED = "approved"
_REVERSED = "reversed"


def _utcnow() -> datetime:
    """Return a timezone-aware UTC now."""
    return datetime.now(UTC)


def _as_uuid(value: object) -> uuid.UUID | None:
    """Best-effort coerce to UUID, else None."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


class FieldTimeService:
    """Business logic for field timesheets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = FieldTimeRepository(session)

    # ── Create ───────────────────────────────────────────────────────────────

    async def create_timesheet(
        self,
        data: FieldTimesheetCreate,
        user_id: str | None = None,
    ) -> FieldTimesheet:
        """Create a new draft timesheet, optionally with its lines."""
        for line in data.lines:
            self._assert_line_xor(line.resource_id, line.equipment_id)

        reference = await self.repo.next_reference(data.project_id)
        # Record who drafted the timesheet in metadata (the model tracks the
        # submitter / approver as columns, but not the original drafter).
        metadata = dict(data.metadata or {})
        if user_id:
            metadata.setdefault("created_by", str(user_id))
        timesheet = FieldTimesheet(
            project_id=data.project_id,
            reference=reference,
            date=data.date,
            status=_DRAFT,
            note=data.note,
            metadata_=metadata,
        )
        timesheet = await self.repo.create(timesheet)
        for line in data.lines:
            await self.repo.add_line(self._line_from_create(timesheet.id, line))

        await self.session.refresh(timesheet)
        logger.info(
            "Field timesheet created: %s (%s) for project %s with %d line(s)",
            reference,
            timesheet.date,
            data.project_id,
            len(data.lines),
        )
        return timesheet

    # ── Read ─────────────────────────────────────────────────────────────────

    async def get_timesheet(self, timesheet_id: uuid.UUID) -> FieldTimesheet:
        """Get a timesheet by id (404 if missing)."""
        timesheet = await self.repo.get_by_id(timesheet_id)
        if timesheet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This field timesheet does not exist or has been removed. Refresh the list and try again.",
            )
        return timesheet

    async def list_timesheets(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        date_from: date | None = None,
        date_to: date | None = None,
        status_filter: str | None = None,
    ) -> tuple[list[FieldTimesheet], int]:
        """List timesheets for a project."""
        return await self.repo.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            status=status_filter,
        )

    async def get_summary(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Project rollup: counts by status plus labour / plant / overtime hours.

        The hour totals count only live approved timesheets (an approved sheet
        that has not been reversed). Each timesheet's own timekeeping rules from
        its metadata are honoured: hours are rounded to the project step if one
        is set, and overtime is the sum, per worker per day, of hours above the
        project's daily threshold (zero when no threshold is configured).
        """
        counts = await self.repo.status_counts(project_id)
        # Hours over live (approved, non-reversal) timesheets - the authoritative
        # actuals a manager cares about at a glance.
        timesheets, _total = await self.repo.list_for_project(project_id, limit=100000)
        labour = Decimal("0")
        plant = Decimal("0")
        overtime = Decimal("0")
        for ts in timesheets:
            if ts.status != _APPROVED or ts.reverses_id is not None:
                continue
            config = ft.read_hours_config(getattr(ts, "metadata_", None))
            lines = self._line_dicts(ts)
            roll = ft.rollup(lines, rounding_increment=config.rounding_increment)
            labour += roll.labour_hours
            plant += roll.plant_hours
            if config.overtime_daily_threshold is not None:
                overtime += ft.daily_overtime(lines, daily_threshold=config.overtime_daily_threshold)
        return {
            "total": sum(counts.values()),
            "by_status": counts,
            "labour_hours": ft.quantize_hours(labour),
            "plant_hours": ft.quantize_hours(plant),
            "overtime_hours": ft.quantize_hours(overtime),
        }

    # ── Update (draft only) ──────────────────────────────────────────────────

    async def update_timesheet(
        self,
        timesheet_id: uuid.UUID,
        data: FieldTimesheetUpdate,
    ) -> FieldTimesheet:
        """Update a draft timesheet's header fields."""
        timesheet = await self.get_timesheet(timesheet_id)
        self._assert_draft(timesheet, "edit")

        fields = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            incoming = fields.pop("metadata")
            fields["metadata_"] = (
                merge_metadata(getattr(timesheet, "metadata_", None), incoming)
                if isinstance(incoming, dict)
                else incoming
            )
        if not fields:
            return timesheet

        await self.repo.update_fields(timesheet_id, **fields)
        await self.session.refresh(timesheet)
        return timesheet

    async def add_line(
        self,
        timesheet_id: uuid.UUID,
        data: FieldTimesheetLineCreate,
    ) -> FieldTimesheet:
        """Add a line to a draft timesheet."""
        timesheet = await self.get_timesheet(timesheet_id)
        self._assert_draft(timesheet, "add a line to")
        self._assert_line_xor(data.resource_id, data.equipment_id)
        await self.repo.add_line(self._line_from_create(timesheet_id, data))
        await self.session.refresh(timesheet)
        return timesheet

    async def update_line(
        self,
        timesheet_id: uuid.UUID,
        line_id: uuid.UUID,
        data: FieldTimesheetLineUpdate,
    ) -> FieldTimesheet:
        """Update a single line on a draft timesheet."""
        timesheet = await self.get_timesheet(timesheet_id)
        self._assert_draft(timesheet, "edit a line of")
        line = await self.repo.get_line(line_id)
        if line is None or line.timesheet_id != timesheet_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That line is not part of this timesheet. Reload the timesheet and try again.",
            )

        fields = data.model_dump(exclude_unset=True)
        # Resolve the post-update identifiers to enforce labour XOR plant.
        new_resource = fields.get("resource_id", line.resource_id)
        new_equipment = fields.get("equipment_id", line.equipment_id)
        self._assert_line_xor(new_resource, new_equipment)
        if not fields:
            return timesheet

        await self.repo.update_line_fields(line_id, **fields)
        await self.session.refresh(timesheet)
        return timesheet

    async def delete_line(self, timesheet_id: uuid.UUID, line_id: uuid.UUID) -> FieldTimesheet:
        """Delete a line from a draft timesheet."""
        timesheet = await self.get_timesheet(timesheet_id)
        self._assert_draft(timesheet, "remove a line from")
        line = await self.repo.get_line(line_id)
        if line is None or line.timesheet_id != timesheet_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That line is not part of this timesheet. Reload the timesheet and try again.",
            )
        await self.repo.delete_line(line_id)
        await self.session.refresh(timesheet)
        return timesheet

    # ── Delete (draft only) ──────────────────────────────────────────────────

    async def delete_timesheet(self, timesheet_id: uuid.UUID) -> None:
        """Delete a draft timesheet. Submitted / approved sheets cannot be deleted."""
        timesheet = await self.get_timesheet(timesheet_id)
        self._assert_draft(timesheet, "delete")
        await self.repo.delete(timesheet_id)
        logger.info("Field timesheet deleted: %s", timesheet_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def submit_timesheet(self, timesheet_id: uuid.UUID, user_id: str | None) -> FieldTimesheet:
        """Submit a draft timesheet for approval (draft -> submitted).

        Blocked (HTTP 422) when any ERROR-severity validation rule fails.
        """
        timesheet = await self.get_timesheet(timesheet_id)
        if timesheet.status != _DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This timesheet is already '{timesheet.status}', so it cannot be submitted again. "
                    "Only a draft can be sent for approval."
                ),
            )
        if not timesheet.lines:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Add at least one hours line before submitting. An empty timesheet cannot be sent for approval.",
            )
        await self._validate_or_raise(timesheet, operation="submit")

        await self.repo.update_fields(
            timesheet_id,
            status=_SUBMITTED,
            submitted_by=_as_uuid(user_id),
            submitted_at=_utcnow(),
        )
        await self.session.refresh(timesheet)
        self._publish_submitted(timesheet, user_id)
        logger.info("Field timesheet submitted: %s", timesheet_id)
        return timesheet

    async def approve_timesheet(self, timesheet_id: uuid.UUID, user_id: str | None) -> FieldTimesheet:
        """Approve a submitted timesheet (submitted -> approved).

        On approval the hours become authoritative actuals: the cost rollup is
        computed, each daywork line is mirrored onto a signed daywork sheet, and
        ``field_time.timesheet_approved`` is published for payroll / cost.
        """
        timesheet = await self.get_timesheet(timesheet_id)
        if timesheet.status != _SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This timesheet is '{timesheet.status}'. Only a submitted timesheet can be approved. "
                    "Submit it for approval first."
                ),
            )
        await self._validate_or_raise(timesheet, operation="approve")

        line_dicts = self._line_dicts(timesheet)
        labour_rates = await self._labour_rates(line_dicts)
        plant_rates = await self._plant_rates(line_dicts, timesheet.project_id)
        currency = await self._project_base_currency(timesheet.project_id)

        # Mirror daywork lines onto signed daywork sheets (best-effort - the
        # hours actuals must post even if the daywork write-through hiccups).
        await self._write_through_daywork(timesheet, labour_rates, plant_rates, currency, user_id)

        await self.repo.update_fields(
            timesheet_id,
            status=_APPROVED,
            approved_by=_as_uuid(user_id),
            approved_at=_utcnow(),
        )
        await self.session.refresh(timesheet)
        await self._audit(timesheet, prior=_SUBMITTED, new=_APPROVED, user_id=user_id)

        roll = ft.rollup(line_dicts, labour_rates=labour_rates, plant_rates=plant_rates)
        self._publish_approved(timesheet, roll, currency, user_id)
        logger.info("Field timesheet approved: %s by %s", timesheet_id, user_id)
        return timesheet

    async def reverse_timesheet(
        self,
        timesheet_id: uuid.UUID,
        data: ReverseTimesheetRequest,
        user_id: str | None,
    ) -> FieldTimesheet:
        """Reverse an approved timesheet with a mirrored, netting timesheet.

        Approved timesheets are immutable. To correct them a reversing timesheet
        is created (its hours net the original to zero for cost / payroll) and the
        original flips to ``reversed``. Returns the new reversal timesheet.
        """
        original = await self.get_timesheet(timesheet_id)
        if original.status != _APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Only an approved timesheet can be reversed. This one is '{original.status}', "
                    "so there are no approved hours to undo."
                ),
            )

        mirrored = ft.reverse_lines(self._line_dicts(original))
        reference = await self.repo.next_reference(original.project_id)
        now = _utcnow()
        actor = _as_uuid(user_id)
        reversal = FieldTimesheet(
            project_id=original.project_id,
            reference=reference,
            date=original.date,
            status=_APPROVED,
            reverses_id=original.id,
            note=data.note,
            submitted_by=actor,
            submitted_at=now,
            approved_by=actor,
            approved_at=now,
            metadata_={"reverses": str(original.id), "reverses_reference": original.reference},
        )
        reversal = await self.repo.create(reversal)
        for line in mirrored:
            await self.repo.add_line(
                FieldTimesheetLine(
                    timesheet_id=reversal.id,
                    resource_id=_as_uuid(line.get("resource_id")),
                    equipment_id=_as_uuid(line.get("equipment_id")),
                    hours=ft.to_decimal(line.get("hours")),
                    cost_code=str(line.get("cost_code") or ""),
                    wbs=line.get("wbs"),
                    is_daywork=bool(line.get("is_daywork")),
                    variation_id=_as_uuid(line.get("variation_id")),
                    note=line.get("note"),
                ),
            )

        await self.repo.update_fields(timesheet_id, status=_REVERSED)
        await self.session.refresh(reversal)
        await self._audit(original, prior=_APPROVED, new=_REVERSED, user_id=user_id)

        roll = ft.rollup(self._line_dicts(reversal))
        self._publish_reversed(reversal, original, roll, user_id)
        logger.info("Field timesheet %s reversed by %s (reversal=%s)", timesheet_id, user_id, reversal.id)
        return reversal

    # ── Validation ───────────────────────────────────────────────────────────

    async def validate_timesheet(self, timesheet_id: uuid.UUID) -> dict[str, Any]:
        """Run the field-time rule set and return the report (read-only)."""
        timesheet = await self.get_timesheet(timesheet_id)
        report = await self._validate(timesheet, operation="read")
        return self._report_to_dict(report)

    async def _validate(self, timesheet: FieldTimesheet, *, operation: str) -> ValidationReport:
        """Build the validation payload and run the ``field_time`` rule set."""
        valid_cost_codes, valid_wbs = await self._resolve_cost_codes(timesheet.project_id)
        open_variation_ids = await self._open_variation_ids(timesheet.project_id)
        # The per-worker daily cap is a project setting (defaults to 24 hours):
        # forward it so the rule checks hours against the configured ceiling
        # rather than a single hard-coded value.
        config = ft.read_hours_config(getattr(timesheet, "metadata_", None))
        payload = {
            "id": str(timesheet.id),
            "project_id": str(timesheet.project_id),
            "date": str(timesheet.date),
            "status": timesheet.status,
            "lines": self._line_dicts(timesheet),
        }
        metadata: dict[str, Any] = {
            "locale": get_locale(),
            "operation": operation,
            "valid_cost_codes": (list(valid_cost_codes) if valid_cost_codes is not None else None),
            "valid_wbs": (list(valid_wbs) if valid_wbs is not None else None),
            "open_variation_ids": (list(open_variation_ids) if open_variation_ids is not None else None),
            "max_hours_per_day": str(config.max_hours_per_day),
        }
        return await validation_engine.validate(
            data=payload,
            rule_sets=[_RULE_SET],
            target_type="field_timesheet",
            target_id=str(timesheet.id),
            project_id=str(timesheet.project_id),
            metadata=metadata,
        )

    async def _validate_or_raise(self, timesheet: FieldTimesheet, *, operation: str) -> ValidationReport:
        """Run validation and raise HTTP 422 when any ERROR-severity rule fails."""
        report = await self._validate(timesheet, operation=operation)
        if report.has_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": (
                        f"This timesheet has problems that must be fixed before you can {operation} it. "
                        "See the errors listed below, correct each line, then try again."
                    ),
                    "report": report.summary(),
                    "errors": [
                        {
                            "rule_id": r.rule_id,
                            "message": r.message,
                            "element_ref": r.element_ref,
                        }
                        for r in report.errors
                    ],
                },
            )
        return report

    # ── Cost-code suggestions (AI-augmented, human-confirmed) ────────────────

    async def suggest_cost_codes(
        self,
        project_id: uuid.UUID,
        text: str,
        *,
        limit: int = 5,
    ) -> list[CostCodeSuggestionOut]:
        """Rank BOQ cost codes by similarity to ``text`` (never auto-applied)."""
        candidates = await self._cost_code_candidates(project_id)
        suggestions = ft.suggest_cost_codes(text, candidates, limit=limit)
        return [CostCodeSuggestionOut(code=s.code, label=s.label, confidence=s.confidence) for s in suggestions]

    # ── Helpers: line construction ───────────────────────────────────────────

    @staticmethod
    def _assert_line_xor(resource_id: object, equipment_id: object) -> None:
        """Enforce labour XOR plant on a line (exactly one identifier set)."""
        has_resource = resource_id is not None
        has_equipment = equipment_id is not None
        if has_resource == has_equipment:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Each line records either a worker (labour) or a machine (plant), not both and "
                    "not neither. Pick one for this line and save again."
                ),
            )

    @staticmethod
    def _line_from_create(timesheet_id: uuid.UUID, data: FieldTimesheetLineCreate) -> FieldTimesheetLine:
        """Build a line ORM object from a create schema."""
        return FieldTimesheetLine(
            timesheet_id=timesheet_id,
            resource_id=data.resource_id,
            equipment_id=data.equipment_id,
            hours=data.hours,
            cost_code=data.cost_code or "",
            wbs=data.wbs,
            is_daywork=data.is_daywork,
            variation_id=data.variation_id,
            note=data.note,
        )

    @staticmethod
    def _line_dicts(timesheet: FieldTimesheet) -> list[dict[str, Any]]:
        """Render a timesheet's lines as plain dicts for the pure engine."""
        out: list[dict[str, Any]] = []
        for line in timesheet.lines:
            out.append(
                {
                    "id": str(line.id),
                    "resource_id": str(line.resource_id) if line.resource_id else None,
                    "equipment_id": str(line.equipment_id) if line.equipment_id else None,
                    "hours": line.hours if line.hours is not None else Decimal("0"),
                    "cost_code": line.cost_code or "",
                    "wbs": line.wbs,
                    "is_daywork": bool(line.is_daywork),
                    "variation_id": str(line.variation_id) if line.variation_id else None,
                    "note": line.note or "",
                },
            )
        return out

    # ── Helpers: cross-module resolution (all best-effort) ───────────────────

    async def _resolve_cost_codes(
        self,
        project_id: uuid.UUID,
    ) -> tuple[set[str] | None, set[str] | None]:
        """Return ``(valid_cost_codes, valid_wbs)`` for a project's BOQ, or None.

        None means "could not resolve" (BOQ module absent, query failed, or the
        project has no positions yet) so the cost-code rule skips rather than
        flagging every line - a project without a BOQ is not a data error.
        """
        try:
            from sqlalchemy import select

            from app.modules.boq.models import BOQ, Position

            stmt = (
                select(Position.reference_code, Position.ordinal, Position.wbs_id, Position.cost_code_id)
                .join(BOQ, Position.boq_id == BOQ.id)
                .where(BOQ.project_id == project_id)
            )
            rows = (await self.session.execute(stmt)).all()
        except Exception:
            logger.debug("Cost-code resolution unavailable for project=%s", project_id)
            return None, None

        cost_codes: set[str] = set()
        wbs: set[str] = set()
        for reference_code, ordinal, wbs_id, cost_code_id in rows:
            for code in (reference_code, ordinal, cost_code_id):
                if code:
                    cost_codes.add(str(code).strip())
            if wbs_id:
                wbs.add(str(wbs_id).strip())
        return (cost_codes or None), (wbs or None)

    async def _cost_code_candidates(self, project_id: uuid.UUID) -> list[dict[str, str]]:
        """Return ``[{"code", "label"}]`` cost-code candidates from the BOQ."""
        try:
            from sqlalchemy import select

            from app.modules.boq.models import BOQ, Position

            stmt = (
                select(Position.reference_code, Position.ordinal, Position.description)
                .join(BOQ, Position.boq_id == BOQ.id)
                .where(BOQ.project_id == project_id)
            )
            rows = (await self.session.execute(stmt)).all()
        except Exception:
            logger.debug("Cost-code candidates unavailable for project=%s", project_id)
            return []

        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        for reference_code, ordinal, description in rows:
            code = str(reference_code or ordinal or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            candidates.append({"code": code, "label": str(description or "").strip()})
        return candidates

    async def _open_variation_ids(self, project_id: uuid.UUID) -> set[str] | None:
        """Return the set of open variation-order ids, or None if unavailable."""
        try:
            from sqlalchemy import select

            from app.modules.variations.models import VariationOrder

            stmt = select(VariationOrder.id).where(
                VariationOrder.project_id == project_id,
                VariationOrder.status.in_(_OPEN_VARIATION_STATUSES),
            )
            rows = (await self.session.execute(stmt)).scalars().all()
        except Exception:
            logger.debug("Open-variation lookup unavailable for project=%s", project_id)
            return None
        return {str(r) for r in rows}

    async def _labour_rates(self, line_dicts: list[dict[str, Any]]) -> dict[str, Decimal]:
        """Resolve ``{resource_id: hourly_rate}`` from the resources module."""
        ids = [_as_uuid(line.get("resource_id")) for line in line_dicts]
        ids = [i for i in ids if i is not None]
        if not ids:
            return {}
        try:
            from sqlalchemy import select

            from app.modules.resources.models import Resource

            stmt = select(Resource.id, Resource.default_cost_rate).where(Resource.id.in_(ids))
            rows = (await self.session.execute(stmt)).all()
        except Exception:
            logger.debug("Labour-rate lookup unavailable")
            return {}
        return {str(rid): ft.to_decimal(rate) for rid, rate in rows}

    async def _plant_rates(
        self,
        line_dicts: list[dict[str, Any]],
        project_id: uuid.UUID,
    ) -> dict[str, Decimal]:
        """Resolve ``{equipment_id: hourly_rate}`` from the project's rentals.

        Uses the highest ``internal_rate_per_hour`` recorded for the equipment on
        this project. Missing rate -> the equipment is absent from the map and the
        pure rollup treats it as zero cost (hours still counted).
        """
        ids = [_as_uuid(line.get("equipment_id")) for line in line_dicts]
        ids = [i for i in ids if i is not None]
        if not ids:
            return {}
        try:
            from sqlalchemy import select

            from app.modules.equipment.models import EquipmentRental

            stmt = select(EquipmentRental.equipment_id, EquipmentRental.internal_rate_per_hour).where(
                EquipmentRental.equipment_id.in_(ids),
                EquipmentRental.project_id == project_id,
            )
            rows = (await self.session.execute(stmt)).all()
        except Exception:
            logger.debug("Plant-rate lookup unavailable for project=%s", project_id)
            return {}
        rates: dict[str, Decimal] = {}
        for equipment_id, rate in rows:
            key = str(equipment_id)
            value = ft.to_decimal(rate)
            if value > rates.get(key, Decimal("0")):
                rates[key] = value
        return rates

    async def _project_base_currency(self, project_id: uuid.UUID) -> str:
        """Best-effort read of the project's base currency (empty when unknown)."""
        try:
            from app.modules.costmodel.repository import BudgetLineRepository

            base, _fx = await BudgetLineRepository(self.session)._project_fx_context(project_id)
            return str(base or "").strip().upper()
        except Exception:
            logger.debug("Base-currency lookup unavailable for project=%s", project_id)
            return ""

    # ── Helpers: daywork write-through ───────────────────────────────────────

    async def _write_through_daywork(
        self,
        timesheet: FieldTimesheet,
        labour_rates: dict[str, Decimal],
        plant_rates: dict[str, Decimal],
        currency: str,
        user_id: str | None,
    ) -> None:
        """Mirror daywork lines onto signed daywork sheets (one per variation).

        Best-effort: any failure is logged and swallowed so the approval (and the
        hours actuals it posts) is never held hostage by the daywork write-through.
        """
        daywork_lines = [line for line in self._line_dicts(timesheet) if line.get("is_daywork")]
        if not daywork_lines:
            return
        try:
            from app.modules.variations.schemas import DayworkSheetCreate, DayworkSheetLineCreate
            from app.modules.variations.service import VariationsService

            variations = VariationsService(self.session)
            # Group daywork lines by the variation they were performed under so
            # each signed sheet stays scoped to a single variation.
            by_variation: dict[str, list[dict[str, Any]]] = {}
            for line in daywork_lines:
                by_variation.setdefault(str(line.get("variation_id") or ""), []).append(line)

            for variation_id, group in by_variation.items():
                sheet = await variations.create_daywork_sheet(
                    DayworkSheetCreate(
                        project_id=timesheet.project_id,
                        work_date=str(timesheet.date),
                        description=(
                            f"Field timesheet {timesheet.reference} daywork"
                            + (f" (variation {variation_id})" if variation_id else "")
                        ),
                        currency=currency,
                        status="draft",
                    ),
                    user_id,
                )
                drafts = ft.daywork_line_drafts(group, labour_rates=labour_rates, plant_rates=plant_rates)
                for draft in drafts:
                    await variations.add_daywork_line(
                        DayworkSheetLineCreate(
                            sheet_id=sheet.id,
                            line_type=draft.line_type,
                            description=draft.description,
                            quantity=draft.quantity,
                            unit=draft.unit,
                            unit_rate=draft.unit_rate,
                            worker_name=draft.worker_name,
                            equipment_code=draft.equipment_code,
                        ),
                    )
                # Stamp the resulting sheet id back onto the source lines.
                for line in group:
                    line_uuid = _as_uuid(line.get("id"))
                    if line_uuid is not None:
                        await self.repo.update_line_fields(line_uuid, daywork_sheet_id=sheet.id)
            await self.session.refresh(timesheet)
        except Exception:
            logger.exception(
                "Daywork write-through failed for timesheet=%s - approval unaffected",
                timesheet.id,
            )

    # ── Helpers: events + audit ──────────────────────────────────────────────

    def _publish_submitted(self, timesheet: FieldTimesheet, user_id: str | None) -> None:
        roll = ft.rollup(self._line_dicts(timesheet))
        from app.modules.field_time.events import publish_timesheet_submitted

        publish_timesheet_submitted(
            timesheet_id=str(timesheet.id),
            project_id=str(timesheet.project_id),
            work_date=str(timesheet.date),
            labour_hours=str(roll.labour_hours),
            plant_hours=str(roll.plant_hours),
            actor_id=user_id,
        )

    def _publish_approved(
        self,
        timesheet: FieldTimesheet,
        roll: ft.CostRollup,
        currency: str,
        user_id: str | None,
    ) -> None:
        from app.modules.field_time.events import publish_timesheet_approved

        publish_timesheet_approved(
            timesheet_id=str(timesheet.id),
            project_id=str(timesheet.project_id),
            work_date=str(timesheet.date),
            labour_hours=str(roll.labour_hours),
            plant_hours=str(roll.plant_hours),
            labour_cost=str(roll.labour_cost),
            plant_cost=str(roll.plant_cost),
            currency=currency,
            actor_id=user_id,
        )

    def _publish_reversed(
        self,
        reversal: FieldTimesheet,
        original: FieldTimesheet,
        roll: ft.CostRollup,
        user_id: str | None,
    ) -> None:
        from app.modules.field_time.events import publish_timesheet_reversed

        publish_timesheet_reversed(
            timesheet_id=str(reversal.id),
            reverses_id=str(original.id),
            project_id=str(reversal.project_id),
            work_date=str(reversal.date),
            labour_hours=str(roll.labour_hours),
            plant_hours=str(roll.plant_hours),
            actor_id=user_id,
        )

    async def _audit(
        self,
        timesheet: FieldTimesheet,
        *,
        prior: str,
        new: str,
        user_id: str | None,
    ) -> None:
        """Write a universal audit-trail entry for a status change (best-effort)."""
        try:
            from app.core.audit_log import log_activity

            await log_activity(
                self.session,
                actor_id=user_id,
                entity_type="field_timesheet",
                entity_id=str(timesheet.id),
                action="status_changed",
                from_status=prior,
                to_status=new,
                reason=f"Field timesheet {new}",
                module="field_time",
                parent_entity_type="project",
                parent_entity_id=str(timesheet.project_id),
                before_state={"status": prior},
                after_state={"status": new},
            )
        except Exception:
            logger.debug("Audit-log write skipped for timesheet=%s", timesheet.id)

    # ── Helpers: assertions + report ─────────────────────────────────────────

    @staticmethod
    def _assert_draft(timesheet: FieldTimesheet, action: str) -> None:
        """Raise 400 unless the timesheet is still a draft."""
        if timesheet.status != _DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"You can only {action} a draft timesheet. This one is '{timesheet.status}' and is now locked. "
                    "To change an approved timesheet, reverse it and enter a new one."
                ),
            )

    @staticmethod
    def _report_to_dict(report: ValidationReport) -> dict[str, Any]:
        """Flatten a ValidationReport into the API response shape."""
        summary = report.summary()
        return {
            "status": summary["status"],
            "score": summary["score"],
            "counts": summary["counts"],
            "results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "severity": r.severity.value,
                    "category": r.category.value,
                    "passed": r.passed,
                    "message": r.message,
                    "element_ref": r.element_ref,
                    "suggestion": r.suggestion,
                }
                for r in report.results
            ],
        }
