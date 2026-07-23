# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Full EVM ORM models.

Tables:
    oe_evm_forecast - advanced EVM forecast records with ETC, EAC, VAC, TCPI
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class EVMForecast(Base):
    """Advanced EVM forecast with ETC, EAC, VAC, and TCPI metrics."""

    __tablename__ = "oe_evm_forecast"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        nullable=False,
        index=True,
    )
    forecast_date: Mapped[str] = mapped_column(String(40), nullable=False)
    etc_: Mapped[str] = mapped_column(
        "etc",
        String(50),
        nullable=False,
        default="0",
    )
    eac: Mapped[str] = mapped_column(String(50), nullable=False, default="0")
    vac: Mapped[str] = mapped_column(String(50), nullable=False, default="0")
    tcpi: Mapped[str] = mapped_column(String(50), nullable=False, default="0")
    forecast_method: Mapped[str] = mapped_column(String(50), nullable=False, default="cpi")
    confidence_range_low: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_range_high: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── Predictive alert tracking (TOP-30 #19) ──────────────────────────────
    # When a forecast breaches a project AlertRule the batch job stamps
    # ``alert_status='triggered'`` + ``triggered_at`` and emits
    # ``forecast.alert_triggered``. Users then move it to ``acknowledged`` or
    # ``snoozed`` from the Forecasts tab. NULL means "no alert on this row".
    alert_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<EVMForecast project={self.project_id} date={self.forecast_date}>"
