# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resource-depth ORM models (T3.1).

Two additive tables backing the resource-depth slice; the demand/cost lanes and
the curve algebra live in the pure :mod:`app.modules.resources.resource_engine`:

* ``oe_resources_rate`` - effective-dated, multi-type rate rows for a resource
  (cost / billing / overtime / custom). A *zero* rate is legitimate and is
  honoured by the resolver, never coalesced to the default.
* ``oe_resources_assignment_curve`` - an optional spreading curve per assignment
  (``flat`` / ``front_load`` / ``back_load`` / ``bell`` or explicit weights),
  unique on ``assignment_id`` so an assignment has at most one curve.

Registered by importing this module from ``resources/models.py`` (mirrors the
``progress_models`` / ``codes_models`` precedent), so the auto-discovery loader
picks the tables up before ``create_all``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

#: Rate types the resolver knows by name; custom strings are also accepted.
RATE_TYPES: tuple[str, ...] = ("cost", "billing", "overtime")
#: Curve shapes recognised by the engine; the first entry is the default.
CURVE_TYPES: tuple[str, ...] = ("flat", "front_load", "back_load", "bell")


class ResourceRate(Base):
    """One effective-dated rate row for a resource (cost / billing / overtime)."""

    __tablename__ = "oe_resources_rate"
    __table_args__ = (Index("ix_oe_resources_rate_lookup", "resource_id", "rate_type", "effective_from"),)

    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_resources_resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    rate_type: Mapped[str] = mapped_column(String(16), nullable=False, default="cost", server_default="cost")
    # Inclusive lower bound; exclusive upper bound (``None`` = open-ended).
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="", server_default="")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug repr
        return f"<ResourceRate r={self.resource_id} {self.rate_type}={self.rate} from={self.effective_from}>"


class AssignmentCurve(Base):
    """An optional resource-spreading curve for a single assignment."""

    __tablename__ = "oe_resources_assignment_curve"
    __table_args__ = (UniqueConstraint("assignment_id", name="uq_resources_assignment_curve_assignment"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_resources_assignment.id", ondelete="CASCADE"),
        nullable=False,
    )
    curve_type: Mapped[str] = mapped_column(String(16), nullable=False, default="flat", server_default="flat")
    # Optional explicit per-segment weights; when non-empty they override the
    # named curve (normalised to sum 1.0 by the engine).
    manual_weights: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug repr
        return f"<AssignmentCurve a={self.assignment_id} {self.curve_type}>"
