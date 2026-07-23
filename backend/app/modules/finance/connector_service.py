# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Service layer for finance ERP / accounting connectors.

Owns the connector config CRUD (with credential encryption) and the
``run_sync`` orchestration: gather the data, hand it to the connector,
persist a :class:`SyncLog`, and stamp the config's last-sync fields. The
connector itself does the transport work; this service is the bridge to
the rest of the finance module.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.crypto import encrypt_secret
from app.core.storage import get_storage_backend
from app.modules.finance.connector_models import AccountingConnectorConfig, SyncLog
from app.modules.finance.connectors.base import ConnectorError, PushPayload, SyncResult
from app.modules.finance.connectors.registry import connector_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# How many invoices / payments a single push gathers. Beyond this the run
# still succeeds but records a warning so silent truncation never reads as
# "exported everything".
_PUSH_PAGE_LIMIT = 5000


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _coerce_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


class ConnectorService:
    """Business logic for connector configs and sync runs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Config CRUD ───────────────────────────────────────────────────────

    async def list_configs(
        self,
        *,
        project_id: uuid.UUID | None = None,
        include_global: bool = True,
    ) -> list[AccountingConnectorConfig]:
        stmt = select(AccountingConnectorConfig)
        if project_id is not None:
            if include_global:
                stmt = stmt.where(
                    (AccountingConnectorConfig.project_id == project_id)
                    | (AccountingConnectorConfig.project_id.is_(None))
                )
            else:
                stmt = stmt.where(AccountingConnectorConfig.project_id == project_id)
        stmt = stmt.order_by(AccountingConnectorConfig.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_config(self, config_id: uuid.UUID) -> AccountingConnectorConfig | None:
        return await self.session.get(AccountingConnectorConfig, config_id)

    async def get_config_or_404(self, config_id: uuid.UUID) -> AccountingConnectorConfig:
        config = await self.get_config(config_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return config

    async def create_config(self, data: Any, *, actor_id: str | None = None) -> AccountingConnectorConfig:
        if not connector_registry.has(data.connector_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown connector_type '{data.connector_type}'.",
            )
        config = AccountingConnectorConfig(
            project_id=data.project_id,
            name=data.name,
            connector_type=data.connector_type,
            direction=(data.direction or "both"),
            is_active=bool(data.is_active),
            auto_push=bool(data.auto_push),
            auto_push_events=list(data.auto_push_events or []),
            settings_=dict(data.settings or {}),
            credentials=_encode_credentials(data.credentials),
            created_by=_coerce_uuid(actor_id),
            metadata_=dict(getattr(data, "metadata", None) or {}),
        )
        self.session.add(config)
        try:
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001 - surface the duplicate-name conflict cleanly.
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A connector with this name already exists for the project.",
            ) from exc
        await self.session.refresh(config)
        return config

    async def update_config(self, config_id: uuid.UUID, data: Any) -> AccountingConnectorConfig:
        config = await self.get_config_or_404(config_id)
        fields = data.model_dump(exclude_unset=True)
        if "name" in fields:
            config.name = fields["name"]
        if "direction" in fields and fields["direction"]:
            config.direction = fields["direction"]
        if "is_active" in fields:
            config.is_active = bool(fields["is_active"])
        if "auto_push" in fields:
            config.auto_push = bool(fields["auto_push"])
        if "auto_push_events" in fields:
            config.auto_push_events = list(fields["auto_push_events"] or [])
        if "settings" in fields and fields["settings"] is not None:
            config.settings_ = dict(fields["settings"])
        if "metadata" in fields and fields["metadata"] is not None:
            config.metadata_ = dict(fields["metadata"])
        # Credentials: only touch when the field is present AND not None. An
        # absent / null field means "leave the stored secret unchanged" so the
        # client never has to round-trip the secret it can't read back.
        if fields.get("credentials") is not None:
            config.credentials = _encode_credentials(fields["credentials"])
        try:
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A connector with this name already exists for the project.",
            ) from exc
        await self.session.refresh(config)
        return config

    async def delete_config(self, config_id: uuid.UUID) -> None:
        config = await self.get_config_or_404(config_id)
        await self.session.delete(config)
        await self.session.commit()

    # ── Validation ────────────────────────────────────────────────────────

    async def validate_config(self, config_id: uuid.UUID) -> list[str]:
        config = await self.get_config_or_404(config_id)
        try:
            connector = connector_registry.create(config, storage=get_storage_backend(), session=self.session)
        except ConnectorError as exc:
            return [str(exc)]
        return await connector.validate_config()

    # ── Sync ──────────────────────────────────────────────────────────────

    async def run_sync(
        self,
        config_id: uuid.UUID,
        *,
        direction: str,
        dry_run: bool,
        actor_id: str | None = None,
        trigger: str = "manual",
        triggered_by_event: str | None = None,
        job_run_id: uuid.UUID | None = None,
    ) -> SyncLog:
        config = await self.get_config_or_404(config_id)
        allowed = (config.direction or "both").lower()
        requested = (direction or allowed).lower()
        do_push = requested in ("push", "both") and allowed in ("push", "both")
        do_pull = requested in ("pull", "both") and allowed in ("pull", "both")
        log_direction = "both" if (do_push and do_pull) else ("push" if do_push else "pull")

        started = _utcnow_iso()
        combined = SyncResult(direction=log_direction)

        if not do_push and not do_pull:
            combined.errors.append(
                f"Direction '{requested}' is not permitted by this connector (it allows '{allowed}')."
            )
        else:
            try:
                connector = connector_registry.create(config, storage=get_storage_backend(), session=self.session)
            except ConnectorError as exc:
                connector = None
                combined.errors.append(str(exc))

            if connector is not None:
                problems = await connector.validate_config()
                if problems:
                    combined.errors.extend(problems)
                else:
                    if do_push:
                        payload = await self._gather_push_payload(config.project_id, combined)
                        push_res = await connector.push(payload, dry_run=dry_run)
                        _fold(combined, push_res)
                    if do_pull:
                        pull_res = await connector.pull(dry_run=dry_run)
                        _fold(combined, pull_res)

        finished = _utcnow_iso()
        log = SyncLog(
            connector_config_id=config.id,
            project_id=config.project_id,
            direction=log_direction,
            trigger=trigger,
            triggered_by_event=triggered_by_event,
            status=combined.status,
            is_dry_run=dry_run,
            records_in=combined.records_in,
            records_out=combined.records_out,
            file_keys=list(combined.file_keys),
            warnings=list(combined.warnings),
            errors=list(combined.errors),
            details_=dict(combined.details),
            job_run_id=job_run_id,
            started_at=started,
            finished_at=finished,
            created_by=_coerce_uuid(actor_id),
        )
        self.session.add(log)
        # Don't let a dry run rewrite the connector's real last-sync stamp.
        if not dry_run:
            config.last_sync_at = finished
            config.last_sync_status = combined.status
        await self.session.commit()
        await self.session.refresh(log)

        # Best-effort audit row. A failure here must NOT roll back the sync.
        try:
            from app.core.audit_log import log_activity

            await log_activity(
                self.session,
                actor_id=actor_id,
                entity_type="connector",
                entity_id=str(config.id),
                action="sync",
                metadata={
                    "direction": log_direction,
                    "dry_run": dry_run,
                    "status": combined.status,
                    "records_in": combined.records_in,
                    "records_out": combined.records_out,
                    "trigger": trigger,
                },
            )
        except Exception:
            logger.debug("connector: audit log_activity failed", exc_info=True)

        return log

    # ── Logs ──────────────────────────────────────────────────────────────

    async def list_logs(
        self,
        *,
        config_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SyncLog], int]:
        base = select(SyncLog)
        if config_id is not None:
            base = base.where(SyncLog.connector_config_id == config_id)
        if project_id is not None:
            base = base.where(SyncLog.project_id == project_id)
        total = (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        stmt = base.order_by(SyncLog.started_at.desc()).offset(offset).limit(limit)
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total

    async def get_log(self, log_id: uuid.UUID) -> SyncLog | None:
        return await self.session.get(SyncLog, log_id)

    # ── Push payload assembly ─────────────────────────────────────────────

    async def _gather_push_payload(
        self,
        project_id: uuid.UUID | None,
        result: SyncResult,
    ) -> PushPayload:
        from app.modules.finance.repository import InvoiceRepository, PaymentRepository

        payload = PushPayload()
        if project_id is None:
            return payload

        invoices, inv_total = await InvoiceRepository(self.session).list(
            project_id=project_id, limit=_PUSH_PAGE_LIMIT, offset=0
        )
        payments, pay_total = await PaymentRepository(self.session).list(
            project_id=project_id, limit=_PUSH_PAGE_LIMIT, offset=0
        )
        if inv_total > len(invoices):
            result.warnings.append(
                f"Only the first {len(invoices)} of {inv_total} invoices were exported (page limit)."
            )
        if pay_total > len(payments):
            result.warnings.append(
                f"Only the first {len(payments)} of {pay_total} payments were exported (page limit)."
            )

        names = await self._counterparty_names(invoices)
        inv_number_by_id = {str(inv.id): inv.invoice_number for inv in invoices}

        payload.invoices = [
            _invoice_dict(inv, names.get(str(inv.contact_id) if inv.contact_id else "", "")) for inv in invoices
        ]
        payload.payments = [_payment_dict(pay, inv_number_by_id.get(str(pay.invoice_id), "")) for pay in payments]
        return payload

    async def _counterparty_names(self, invoices: list) -> dict[str, str]:
        """Best-effort Contact.id -> display name. Never raises."""
        ids = {str(inv.contact_id) for inv in invoices if inv.contact_id}
        if not ids:
            return {}
        try:
            from app.modules.contacts.models import Contact

            rows = (await self.session.execute(select(Contact).where(Contact.id.in_(ids)))).scalars().all()
            out: dict[str, str] = {}
            for c in rows:
                label = c.company_name or f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email or ""
                out[str(c.id)] = label
            return out
        except Exception:
            logger.debug("connector: counterparty resolution failed", exc_info=True)
            return {}


# ── Module-level helpers ─────────────────────────────────────────────────


def _fold(combined: SyncResult, part: SyncResult) -> None:
    """Fold a per-direction result into the combined run result."""
    combined.records_in += part.records_in
    combined.records_out += part.records_out
    combined.file_keys.extend(part.file_keys)
    combined.warnings.extend(part.warnings)
    combined.errors.extend(part.errors)
    combined.details[part.direction] = part.details


def _encode_credentials(value: object) -> str | None:
    """Serialise + encrypt a credentials dict, or pass through None."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value)
        except (TypeError, ValueError):
            return None
    if not text or text in ("{}", "null"):
        return None
    return encrypt_secret(text)


def _invoice_dict(inv: Any, counterparty: str) -> dict[str, Any]:
    return {
        "invoice_number": inv.invoice_number,
        "invoice_direction": inv.invoice_direction,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date or "",
        "counterparty": counterparty,
        "currency_code": inv.currency_code or "",
        "amount_subtotal": str(inv.amount_subtotal),
        "tax_amount": str(inv.tax_amount),
        "retention_amount": str(inv.retention_amount),
        "amount_total": str(inv.amount_total),
        "status": inv.status,
        "notes": inv.notes or "",
    }


def _payment_dict(pay: Any, invoice_number: str) -> dict[str, Any]:
    return {
        "invoice_number": invoice_number,
        "payment_date": pay.payment_date,
        "amount": str(pay.amount),
        "currency_code": pay.currency_code or "",
        "exchange_rate_snapshot": str(pay.exchange_rate_snapshot),
        "reference": pay.reference or "",
        "is_refund": pay.is_refund,
    }
