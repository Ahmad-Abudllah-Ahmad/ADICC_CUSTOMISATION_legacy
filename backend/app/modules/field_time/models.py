# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time ORM models.

Tables:
    oe_field_time_timesheet       - a foreman's end-of-day, cost-coded, signed
                                    field timesheet for one project-day
    oe_field_time_line            - one labour or plant hours booking on a
                                    timesheet, coded to a BOQ position

A timesheet moves draft -> submitted -> approved; once approved it is immutable
and the only correction is a reversing timesheet (the original flips to
``reversed`` and a new timesheet with ``reverses_id`` set nets it out).

Each line is labour XOR plant: exactly one of ``resource_id`` (a person / crew
from the resources module) or ``equipment_id`` (a machine from the equipment
module) is set. That invariant is enforced both in the service and by a DB CHECK
constraint so a malformed row can never be persisted.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_types import AwareDateTime, SafeDate
from app.database import GUID, Base

# Line completeness is enforced in the DB too: exactly one of resource_id /
# equipment_id must be non-null (labour XOR plant). ``num_nonnulls`` is not
# portable to SQLite, so spell the XOR out explicitly.
_LABOUR_XOR_PLANT = (
    "(resource_id IS NOT NULL AND equipment_id IS NULL) OR (resource_id IS NULL AND equipment_id IS NOT NULL)"
)


class FieldTimesheet(Base):
    """A signed field timesheet for one project on one day."""

    __tablename__ = "oe_field_time_timesheet"
    __table_args__ = (
        Index("ix_oe_field_time_timesheet_project_date", "project_id", "date"),
        # One live timesheet number per project (human reference). Reversals get
        # their own row; the number is stored in metadata, not uniquely keyed.
        UniqueConstraint("project_id", "reference", name="uq_oe_field_time_timesheet_project_ref"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Human-facing sequential reference within the project (e.g. "FT-000123").
    reference: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    date: Mapped[date] = mapped_column(SafeDate(), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)

    submitted_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)

    # A reversal points at the timesheet it reverses (self-FK). NULL for an
    # ordinary timesheet. SET NULL so deleting a stray original never blocks.
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_field_time_timesheet.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    lines: Mapped[list["FieldTimesheetLine"]] = relationship(
        back_populates="timesheet",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<FieldTimesheet {self.reference or self.id} {self.date} ({self.status})>"


class FieldTimesheetLine(Base):
    """One labour or plant hours booking on a field timesheet.

    Labour XOR plant: exactly one of ``resource_id`` / ``equipment_id`` is set.
    Hours are a ``Decimal`` (never float); ``cost_code`` / ``wbs`` code the line
    to a BOQ position so the hours flow into the right cost line.
    """

    __tablename__ = "oe_field_time_line"
    __table_args__ = (
        CheckConstraint(_LABOUR_XOR_PLANT, name="ck_oe_field_time_line_labour_xor_plant"),
        Index("ix_oe_field_time_line_resource", "resource_id"),
        Index("ix_oe_field_time_line_equipment", "equipment_id"),
    )

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_field_time_timesheet.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Labour: a person / crew from the resources module.
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_resources_resource.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Plant: a machine from the equipment module.
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_equipment_equipment.id", ondelete="SET NULL"),
        nullable=True,
    )
    hours: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    cost_code: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    wbs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_daywork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # The variation this daywork was performed under (issued variation order).
    variation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_variations_order.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Soft link to the oe_variations_daywork_sheet row minted on approval for a
    # daywork line. Plain GUID (no DB FK) - the sheet is created dynamically by
    # the variations service and this only records the resulting id for trace.
    daywork_sheet_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    timesheet: Mapped[FieldTimesheet] = relationship(back_populates="lines")

    def __repr__(self) -> str:
        kind = "labour" if self.resource_id else "plant"
        return f"<FieldTimesheetLine {kind} {self.hours}h {self.cost_code}>"
