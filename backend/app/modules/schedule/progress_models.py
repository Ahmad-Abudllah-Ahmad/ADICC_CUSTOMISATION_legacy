# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Progress-rigor ORM models (T3.2).

One new table - ``oe_schedule_activity_step`` - holding the weighted checklist
steps whose completion rolls up into a ``physical``-type activity's percent
(see :mod:`app.modules.schedule.progress_math`). Kept in its own module (like
``codes_models``) so ``models.py`` stays readable; it is imported from
``models.py`` so the table registers on ``Base.metadata`` for the loader.

The new *columns* on :class:`Activity` (percent-complete type, remaining
duration, units, calendar link, suspend/resume audit) live inline on the
``Activity`` class in ``models.py`` because they extend an existing table.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class ProgressStep(Base):
    """One weighted step of a ``physical``-type activity's progress.

    The weighted average of the steps' ``percent_complete`` rolls up into the
    parent activity's ``progress_pct`` (``app.modules.schedule.progress_math.
    step_rollup``). A ``is_milestone`` step that is below 100% caps the parent
    strictly below complete, so an activity with an open milestone never reads
    100% even when the weighted mean would.
    """

    __tablename__ = "oe_schedule_activity_step"
    __table_args__ = (
        CheckConstraint("weight >= 0", name="ck_sched_step_weight_nonneg"),
        CheckConstraint(
            "percent_complete >= 0 AND percent_complete <= 100",
            name="ck_sched_step_pct_range",
        ),
        Index("ix_sched_step_activity_order", "activity_id", "sort_order"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("1"), server_default="1")
    percent_complete: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0"), server_default="0"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<ProgressStep {self.name!r} w={self.weight} {self.percent_complete}%>"
