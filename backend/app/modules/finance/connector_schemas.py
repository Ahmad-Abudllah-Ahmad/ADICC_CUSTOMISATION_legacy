# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the finance connectors API.

Security note: the encrypted ``credentials`` blob is NEVER echoed back to
the client. Responses carry a ``has_credentials`` boolean instead, and the
create / update payloads accept a write-only ``credentials`` object.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_DIRECTIONS = ("push", "pull", "both")


class ConnectorFieldInfo(BaseModel):
    key: str
    label: str
    kind: str = "text"
    options: list[str] = Field(default_factory=list)
    help: str = ""
    secret: bool = False


class ConnectorTypeInfo(BaseModel):
    connector_type: str
    display_name: str
    supported_directions: list[str] = Field(default_factory=list)
    fields: list[ConnectorFieldInfo] = Field(default_factory=list)


class ConnectorConfigCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=120)
    connector_type: str = Field(..., min_length=1, max_length=50)
    direction: str = Field(default="both", pattern=r"^(push|pull|both)$")
    is_active: bool = False
    auto_push: bool = False
    auto_push_events: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    # Write-only secret bag (S3 keys, SFTP creds, API tokens). Encrypted at
    # rest, never returned.
    credentials: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorConfigUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    direction: str | None = Field(default=None, pattern=r"^(push|pull|both)$")
    is_active: bool | None = None
    auto_push: bool | None = None
    auto_push_events: list[str] | None = None
    settings: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ConnectorConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    name: str
    connector_type: str
    direction: str
    is_active: bool
    auto_push: bool
    auto_push_events: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    has_credentials: bool = False
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, config: Any) -> ConnectorConfigResponse:
        return cls(
            id=config.id,
            project_id=config.project_id,
            name=config.name,
            connector_type=config.connector_type,
            direction=config.direction,
            is_active=config.is_active,
            auto_push=config.auto_push,
            auto_push_events=list(config.auto_push_events or []),
            settings=dict(config.settings_ or {}),
            has_credentials=bool(config.credentials),
            last_sync_at=config.last_sync_at,
            last_sync_status=config.last_sync_status,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


class ConnectorConfigListResponse(BaseModel):
    items: list[ConnectorConfigResponse]
    total: int


class SyncTriggerRequest(BaseModel):
    direction: str = Field(default="both", pattern=r"^(push|pull|both)$")
    dry_run: bool = True


class ValidateResponse(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)


class SyncLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connector_config_id: UUID
    project_id: UUID | None = None
    direction: str
    trigger: str
    triggered_by_event: str | None = None
    status: str
    is_dry_run: bool
    records_in: int
    records_out: int
    file_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    job_run_id: UUID | None = None
    started_at: str
    finished_at: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, log: Any) -> SyncLogResponse:
        return cls(
            id=log.id,
            connector_config_id=log.connector_config_id,
            project_id=log.project_id,
            direction=log.direction,
            trigger=log.trigger,
            triggered_by_event=log.triggered_by_event,
            status=log.status,
            is_dry_run=log.is_dry_run,
            records_in=log.records_in,
            records_out=log.records_out,
            file_keys=list(log.file_keys or []),
            warnings=list(log.warnings or []),
            errors=list(log.errors or []),
            details=dict(log.details_ or {}),
            job_run_id=log.job_run_id,
            started_at=log.started_at,
            finished_at=log.finished_at,
            created_at=log.created_at,
            updated_at=log.updated_at,
        )


class SyncLogListResponse(BaseModel):
    items: list[SyncLogResponse]
    total: int
