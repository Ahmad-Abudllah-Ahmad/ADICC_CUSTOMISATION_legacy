# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""EVM-snapshot ORM model.

One new table - ``oe_schedule_evm_snapshot`` - that freezes the time-phased
earned-value rollup (planned value, earned value, budget at completion and the
EV/PV schedule performance index) of a schedule at a given data date. Snapshots
accrue automatically as the schedule's data date advances, so the cost /
schedule performance trend can be charted over time.

Kept in its own module (like ``progress_models`` and ``codes_models``) so
``models.py`` stays readable; it is imported from ``models.py`` so the table
registers on ``Base.metadata`` for ``create_all`` and the module loader.

Scoping mirrors the rest of the schedule module: a ``schedule_id`` foreign key
(cascade-delete with the parent schedule) plus a denormalised ``project_id`` so a
trend query can be tenant-scoped without joining back through the schedule, the
same shape :class:`~app.modules.schedule.models.ScheduleBaseline` already uses.

Idempotency: a unique constraint on ``(schedule_id, data_date)`` means recording
again at the same data date upserts the single row for that date rather than
duplicating it, so re-running a data-date advance never inflates the trend.

Money discipline: ``pv`` / ``ev`` / ``bac`` are ``Numeric(20, 4)`` (Decimal),
matching ``Activity.cost_planned``; ``spi`` is a dimensionless ratio. Actual cost
(AC) and the cost performance index (CPI = EV/AC) are intentionally absent - the
schedule domain never computes an AC, so persisting either would be fabricated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class ScheduleEvmSnapshot(Base):
    """A frozen EVM rollup of a schedule at one data date (for trend charting).

    See :mod:`app.modules.schedule.evm_snapshot_service` for the producer (hooked
    where the data date advances) and :mod:`evm_snapshot_math` for the SPI
    derivation. ``recorded_at`` is the wall-clock capture time (audit), distinct
    from ``data_date`` which is the schedule status date the figures describe.
    """

    __tablename__ = "oe_schedule_evm_snapshot"
    __table_args__ = (
        # One snapshot per (schedule, data date): a re-record at the same data
        # date upserts this row instead of duplicating the trend point.
        UniqueConstraint("schedule_id", "data_date", name="uq_sched_evm_snapshot_sched_date"),
        Index("ix_sched_evm_snapshot_schedule_date", "schedule_id", "data_date"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_schedule.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        nullable=False,
        index=True,
    )
    # Schedule status / data date the figures below describe (ISO YYYY-MM-DD).
    data_date: Mapped[str] = mapped_column(String(40), nullable=False)

    # ── EVM rollup (money is Decimal) ─────────────────────────────────────
    pv: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc="Planned value (BCWS) - time-phased budget earned by the data date.",
    )
    ev: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc="Earned value (BCWP) - budget of the work actually performed.",
    )
    bac: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        doc="Budget at completion - total planned cost of the schedule.",
    )
    # EV/PV schedule performance index. NULL when PV is zero at the data date
    # (no baseline accrued yet), so the divide-by-zero reads as "not applicable"
    # rather than a misleading number. Three decimals - it is a charted ratio.
    spi: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        doc="Schedule performance index EV/PV; NULL when PV is zero.",
    )
    # NOTE: there is intentionally no AC / CPI column. The schedule EVM rollup
    # never computes an actual cost, so a cost performance index would be
    # fabricated; the cost side is owned by the finance EVM module.

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="Wall-clock capture time (audit), distinct from data_date.",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<ScheduleEvmSnapshot schedule={self.schedule_id} data_date={self.data_date} ev={self.ev}>"
