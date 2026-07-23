# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defects-liability service layer (post-handover warranty and DLP register).

Async data access on top of the module's own two tables plus the read-side
loaders that project persisted rows onto the pure
:class:`app.modules.defects_liability.register.WarrantyRow` list fed to the
computation core. A defect is only ever created, listed or mutated after its
parent warranty is confirmed to belong to the same project
(:meth:`_require_warranty_in_project`), so a defect can never be attached across
projects even when the caller is authorised on their own project - the
defense-in-depth companion to the router's :func:`verify_project_access` gate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from app.modules.defects_liability import register
from app.modules.defects_liability.models import DlpDefect, DlpWarranty

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.defects_liability.schemas import (
        DefectCreate,
        DefectUpdate,
        WarrantyCreate,
        WarrantyUpdate,
    )


def _as_optional_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """Coerce an actor id to ``uuid.UUID`` or ``None`` (never raise).

    The current user id arrives as the JWT subject string; a well-formed value
    is stored as a proper GUID, and anything unparseable is stored as ``None``
    rather than corrupting the ``created_by`` column.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _to_defect_row(row: DlpDefect) -> register.DefectRow:
    """Project a persisted defect row onto the pure :class:`register.DefectRow`."""
    return register.DefectRow(
        status=str(row.status),
        severity=row.severity,
        due_date=row.due_date,
    )


def _to_warranty_row(row: DlpWarranty) -> register.WarrantyRow:
    """Project a persisted warranty row (with its defects) onto :class:`register.WarrantyRow`."""
    return register.WarrantyRow(
        id=str(row.id) if row.id is not None else None,
        reference=str(row.reference or ""),
        title=str(row.title or ""),
        status=str(row.status),
        subcontractor_name=row.subcontractor_name,
        work_package=row.work_package,
        warranty_type=row.warranty_type,
        dlp_end_date=row.dlp_end_date,
        warranty_end_date=row.warranty_end_date,
        defects=[_to_defect_row(d) for d in row.defects],
    )


class DefectsLiabilityService:
    """Stateless business logic for the defects-liability / DLP register."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Warranties ---------------------------------------------------------

    async def create_warranty(
        self,
        project_id: uuid.UUID,
        payload: WarrantyCreate,
        created_by: str | None,
    ) -> DlpWarranty:
        """Create a warranty / DLP entry (409 if the reference is already used)."""
        await self._require_unique_reference(project_id, payload.reference)
        warranty = DlpWarranty(
            project_id=project_id,
            reference=payload.reference,
            title=payload.title,
            element_description=payload.element_description,
            subcontractor_id=payload.subcontractor_id,
            subcontractor_name=payload.subcontractor_name,
            work_package=payload.work_package,
            warranty_type=payload.warranty_type,
            handover_date=payload.handover_date,
            warranty_start_date=payload.warranty_start_date,
            warranty_months=payload.warranty_months,
            warranty_end_date=payload.warranty_end_date,
            dlp_end_date=payload.dlp_end_date,
            status=payload.status,
            retention_release_date=payload.retention_release_date,
            contract_id=payload.contract_id,
            document_id=payload.document_id,
            sort_order=payload.sort_order,
            notes=payload.notes,
            created_by=_as_optional_uuid(created_by),
        )
        self.session.add(warranty)
        await self.session.flush()
        return warranty

    async def list_warranties(
        self,
        project_id: uuid.UUID,
        *,
        warranty_status: str | None = None,
        subcontractor_id: uuid.UUID | None = None,
        work_package: str | None = None,
        warranty_type: str | None = None,
    ) -> list[DlpWarranty]:
        """List a project's warranty / DLP entries with optional filters."""
        stmt = select(DlpWarranty).where(DlpWarranty.project_id == project_id)
        if warranty_status is not None:
            stmt = stmt.where(DlpWarranty.status == warranty_status)
        if subcontractor_id is not None:
            stmt = stmt.where(DlpWarranty.subcontractor_id == subcontractor_id)
        if work_package is not None:
            stmt = stmt.where(DlpWarranty.work_package == work_package)
        if warranty_type is not None:
            stmt = stmt.where(DlpWarranty.warranty_type == warranty_type)
        stmt = stmt.order_by(DlpWarranty.sort_order.asc(), DlpWarranty.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_warranty(self, project_id: uuid.UUID, warranty_id: uuid.UUID) -> DlpWarranty | None:
        """Load one warranty, scoped to the project (``None`` if foreign/absent)."""
        stmt = select(DlpWarranty).where(
            DlpWarranty.id == warranty_id,
            DlpWarranty.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def require_warranty(self, project_id: uuid.UUID, warranty_id: uuid.UUID) -> DlpWarranty:
        """Load one in-project warranty or raise 404 (missing or foreign alike)."""
        warranty = await self.get_warranty(project_id, warranty_id)
        if warranty is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warranty not found in this project",
            )
        return warranty

    async def update_warranty(
        self,
        project_id: uuid.UUID,
        warranty_id: uuid.UUID,
        payload: WarrantyUpdate,
    ) -> DlpWarranty:
        """Patch a warranty / DLP entry; only provided fields are changed."""
        warranty = await self.require_warranty(project_id, warranty_id)
        data = payload.model_dump(exclude_unset=True)
        new_reference = data.get("reference")
        if new_reference is not None and new_reference != warranty.reference:
            await self._require_unique_reference(project_id, new_reference, exclude_warranty_id=warranty_id)
        for key, value in data.items():
            setattr(warranty, key, value)
        await self.session.flush()
        return warranty

    async def delete_warranty(self, project_id: uuid.UUID, warranty_id: uuid.UUID) -> None:
        """Delete an in-project warranty and its defects (404 if missing or foreign)."""
        warranty = await self.require_warranty(project_id, warranty_id)
        await self.session.delete(warranty)
        await self.session.flush()

    # -- Defects ------------------------------------------------------------

    async def create_defect(
        self,
        project_id: uuid.UUID,
        warranty_id: uuid.UUID,
        payload: DefectCreate,
        created_by: str | None,
    ) -> DlpDefect:
        """Raise a defect against a warranty, re-verifying the warranty is in the project.

        The warranty is confirmed to belong to ``project_id`` first, so the
        defect's ``project_id`` (copied from the verified path project) and
        ``warranty_id`` can never straddle two projects.
        """
        await self._require_warranty_in_project(project_id, warranty_id)
        defect = DlpDefect(
            project_id=project_id,
            warranty_id=warranty_id,
            reference=payload.reference,
            description=payload.description,
            severity=payload.severity,
            raised_date=payload.raised_date,
            due_date=payload.due_date,
            status=payload.status,
            rectified_date=payload.rectified_date,
            responsible_party=payload.responsible_party,
            punchlist_id=payload.punchlist_id,
            ncr_id=payload.ncr_id,
            created_by=_as_optional_uuid(created_by),
        )
        self.session.add(defect)
        await self.session.flush()
        return defect

    async def list_defects(
        self,
        project_id: uuid.UUID,
        *,
        warranty_id: uuid.UUID | None = None,
        defect_status: str | None = None,
        severity: str | None = None,
    ) -> list[DlpDefect]:
        """List a project's defects with optional warranty / status / severity filters.

        When a ``warranty_id`` is given it is first confirmed to belong to the
        project, so listing another project's warranty's defects by id is a 404.
        """
        if warranty_id is not None:
            await self._require_warranty_in_project(project_id, warranty_id)
        stmt = select(DlpDefect).where(DlpDefect.project_id == project_id)
        if warranty_id is not None:
            stmt = stmt.where(DlpDefect.warranty_id == warranty_id)
        if defect_status is not None:
            stmt = stmt.where(DlpDefect.status == defect_status)
        if severity is not None:
            stmt = stmt.where(DlpDefect.severity == severity)
        stmt = stmt.order_by(DlpDefect.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_defect(self, project_id: uuid.UUID, defect_id: uuid.UUID) -> DlpDefect | None:
        """Load one defect, scoped to the project (``None`` if foreign/absent)."""
        stmt = select(DlpDefect).where(
            DlpDefect.id == defect_id,
            DlpDefect.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def require_defect(self, project_id: uuid.UUID, defect_id: uuid.UUID) -> DlpDefect:
        """Load one in-project defect or raise 404 (missing or foreign alike)."""
        defect = await self.get_defect(project_id, defect_id)
        if defect is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Defect not found in this project",
            )
        return defect

    async def update_defect(
        self,
        project_id: uuid.UUID,
        defect_id: uuid.UUID,
        payload: DefectUpdate,
    ) -> DlpDefect:
        """Patch (or close) a defect; only provided fields are changed."""
        defect = await self.require_defect(project_id, defect_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(defect, key, value)
        await self.session.flush()
        return defect

    # -- Derived register (DB loaders + pure core) --------------------------

    async def build_register(
        self,
        project_id: uuid.UUID,
        as_of: date | None = None,
        horizon_days: int = 30,
    ) -> dict:
        """Full defects-liability register rollup for a project."""
        as_of = as_of or datetime.now(UTC).date()
        warranties = [_to_warranty_row(r) for r in await self.list_warranties(project_id)]
        report = register.build_report(warranties, as_of=as_of, horizon_days=horizon_days)
        payload = report.to_dict()
        payload["project_id"] = str(project_id)
        return payload

    async def get_retention_release_readiness(
        self,
        project_id: uuid.UUID,
        as_of: date | None = None,
    ) -> dict:
        """Entries clear for final retention release (DLP ended, nothing outstanding)."""
        as_of = as_of or datetime.now(UTC).date()
        warranties = [_to_warranty_row(r) for r in await self.list_warranties(project_id)]
        ready = register.retention_release_ready_warranties(warranties, as_of)
        return {
            "project_id": str(project_id),
            "as_of": as_of.isoformat(),
            "total": len(warranties),
            "ready_count": len(ready),
            "ready": [w.to_ref(as_of) for w in ready],
        }

    # -- Ownership / integrity guards ---------------------------------------

    async def _require_warranty_in_project(
        self,
        project_id: uuid.UUID,
        warranty_id: uuid.UUID,
    ) -> DlpWarranty:
        """Confirm a warranty id references a warranty in this project, else 404.

        The linchpin of the module's IDOR defence: a defect can only ever be
        attached to (or listed under) a warranty that belongs to the same
        project, so a foreign warranty id smuggled onto a create / list is
        rejected even though the caller passed the project access gate.
        """
        stmt = select(DlpWarranty).where(
            DlpWarranty.id == warranty_id,
            DlpWarranty.project_id == project_id,
        )
        warranty = (await self.session.execute(stmt)).scalar_one_or_none()
        if warranty is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warranty not found in this project",
            )
        return warranty

    async def _require_unique_reference(
        self,
        project_id: uuid.UUID,
        reference: str,
        *,
        exclude_warranty_id: uuid.UUID | None = None,
    ) -> None:
        """Raise 409 when ``reference`` is already used by another warranty in the project.

        Enforces the ``uq_dlp_warranty_project_reference`` constraint with a
        friendly conflict instead of letting a duplicate surface as a raw DB
        integrity error on flush.
        """
        stmt = select(DlpWarranty.id).where(
            DlpWarranty.project_id == project_id,
            DlpWarranty.reference == reference,
        )
        if exclude_warranty_id is not None:
            stmt = stmt.where(DlpWarranty.id != exclude_warranty_id)
        if (await self.session.execute(stmt)).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A warranty with reference {reference!r} already exists in this project",
            )
