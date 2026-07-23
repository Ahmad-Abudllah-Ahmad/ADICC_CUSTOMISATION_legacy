# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ORM models for finance ERP / accounting connectors.

Tables:
    oe_finance_connector_config - a configured connection to an external
                                  accounting / ERP system.
    oe_finance_sync_log         - one row per sync run (push or pull),
                                  including dry runs, for the history view.

Kept in a separate module from ``finance/models.py`` so the connector
surface stays self-contained; ``finance/models.py`` re-exports the two
classes so the startup model-discovery (which scans each module's
``models.py``) registers the tables for ``Base.metadata.create_all``.
"""

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class AccountingConnectorConfig(Base):
    """A configured link to an external accounting / ERP system.

    ``project_id`` null means a tenant/global connector; non-null scopes it
    to a single project (the common case for the file connector). Secrets
    live encrypted in :attr:`credentials`; non-secret options live in
    :attr:`settings_`.
    """

    __tablename__ = "oe_finance_connector_config"
    __table_args__ = (
        Index("ix_connector_project_active", "project_id", "is_active"),
        UniqueConstraint("project_id", "name", name="uq_connector_proj_name"),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # What this config is allowed to do: "push" | "pull" | "both".
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="both", server_default="both")
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False, server_default="false")
    auto_push: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False, server_default="false")
    # Event names that trigger an automatic push, e.g.
    # ["invoice.paid", "invoice.approved"].
    auto_push_events: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    # Non-secret config: {format, out_prefix, inbound_key, account_map,
    # delimiter, encoding}. Stored under the column name "settings".
    settings_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "settings",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    # Fernet-encrypted JSON blob of secrets (S3 keys, SFTP creds, API
    # tokens for future connectors). NEVER echoed back to the client.
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<AccountingConnectorConfig {self.name} ({self.connector_type})>"


class SyncLog(Base):
    """One sync run against a connector config - push or pull, live or dry."""

    __tablename__ = "oe_finance_sync_log"
    __table_args__ = (Index("ix_synclog_config_started", "connector_config_id", "started_at"),)

    connector_config_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_finance_connector_config.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised for fast project-scoped log queries.
    project_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # push | pull | both
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # manual | event | scheduled
    triggered_by_event: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", server_default="running")
    is_dry_run: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False, server_default="false")
    records_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    file_keys: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    warnings: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    errors: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    details_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "details",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    job_run_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    def __repr__(self) -> str:
        return f"<SyncLog {self.direction} {self.status} config={self.connector_config_id}>"
