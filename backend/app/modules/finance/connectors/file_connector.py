# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File-based ERP / accounting connector.

Push: writes the project's invoices and payments to the configured storage
backend as CSV (or JSON) files - the simplest, vendor-neutral way to hand
finance data to any accounting package, which all import flat files.

Pull: reads a general-ledger file (CSV or JSON) and posts balanced
double-entry transactions into the platform ledger via the finance
service. Every user-controlled cell on export is run through
``neutralise_formula`` so a malicious description can't become a
spreadsheet formula in the downstream system.

The connector is project-scoped: ``config.project_id`` selects which
project's documents are pushed and which project the pulled ledger rows
belong to.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.csv_safety import neutralise_formula
from app.modules.finance.connectors.base import (
    Connector,
    ConnectorField,
    PushPayload,
    SyncResult,
    to_decimal,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


# Columns emitted on push, in order. Keys map into the normalised dicts the
# service builds in PushPayload.
_INVOICE_COLUMNS: tuple[str, ...] = (
    "invoice_number",
    "invoice_direction",
    "invoice_date",
    "due_date",
    "counterparty",
    "currency_code",
    "amount_subtotal",
    "tax_amount",
    "retention_amount",
    "amount_total",
    "status",
    "notes",
)
_PAYMENT_COLUMNS: tuple[str, ...] = (
    "invoice_number",
    "payment_date",
    "amount",
    "currency_code",
    "exchange_rate_snapshot",
    "reference",
    "is_refund",
)
_LEDGER_COLUMNS: tuple[str, ...] = (
    "transaction_ref",
    "account_code",
    "debit_amount",
    "credit_amount",
    "currency_code",
    "posted_at",
    "description",
)

# Header aliases accepted on inbound GL files (case-insensitive). Maps a
# normalised header to the canonical field name the parser expects.
_INBOUND_ALIASES: dict[str, str] = {
    "transaction_ref": "transaction_ref",
    "transaction": "transaction_ref",
    "ref": "transaction_ref",
    "reference": "transaction_ref",
    "journal": "transaction_ref",
    "journal_ref": "transaction_ref",
    "account_code": "account_code",
    "account": "account_code",
    "gl_account": "account_code",
    "debit_amount": "debit_amount",
    "debit": "debit_amount",
    "dr": "debit_amount",
    "credit_amount": "credit_amount",
    "credit": "credit_amount",
    "cr": "credit_amount",
    "currency_code": "currency_code",
    "currency": "currency_code",
    "ccy": "currency_code",
    "posted_at": "posted_at",
    "date": "posted_at",
    "posting_date": "posted_at",
    "description": "description",
    "memo": "description",
    "narrative": "description",
}

_SOURCE_TYPE = "erp_connector"


class FileConnector(Connector):
    """CSV / JSON file connector."""

    connector_type = "file_csv"
    display_name = "File export / import (CSV or JSON)"
    supported_directions = ("push", "pull", "both")
    setting_fields = (
        ConnectorField(
            "format",
            "File format",
            kind="select",
            options=("csv", "json"),
            help="Format for pushed files and the expected format of the inbound ledger file.",
        ),
        ConnectorField(
            "out_prefix",
            "Output folder",
            help="Storage prefix for exported files. Defaults to connectors/<id>/out.",
        ),
        ConnectorField(
            "inbound_key",
            "Inbound ledger file",
            help="Storage key of the general-ledger file to import on pull.",
        ),
        ConnectorField(
            "delimiter",
            "CSV delimiter",
            help="Single character. Defaults to a comma.",
        ),
    )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _format(self) -> str:
        return str(self.settings().get("format") or "csv").strip().lower()

    def _delimiter(self) -> str:
        raw = str(self.settings().get("delimiter") or ",")
        return raw[0] if raw else ","

    def _out_prefix(self) -> str:
        prefix = str(self.settings().get("out_prefix") or f"connectors/{self.config.id}/out")
        return prefix.strip("/")

    # ── Validation ────────────────────────────────────────────────────────

    async def validate_config(self) -> list[str]:
        problems: list[str] = []
        fmt = self._format()
        if fmt not in ("csv", "json"):
            problems.append(f"Unsupported format {fmt!r}; choose 'csv' or 'json'.")
        if self.config.project_id is None:
            problems.append("This connector must be scoped to a project.")
        direction = (self.config.direction or "both").lower()
        if direction in ("pull", "both") and not str(self.settings().get("inbound_key") or "").strip():
            problems.append("Pull is enabled but no inbound ledger file key is configured.")
        return problems

    # ── Push ──────────────────────────────────────────────────────────────

    async def push(self, payload: PushPayload, *, dry_run: bool) -> SyncResult:
        result = SyncResult(direction="push")
        fmt = self._format()
        run_prefix = f"{self._out_prefix()}/{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        preview: dict[str, int] = {}

        datasets: list[tuple[str, list[dict[str, Any]], tuple[str, ...]]] = [
            ("invoices", payload.invoices, _INVOICE_COLUMNS),
            ("payments", payload.payments, _PAYMENT_COLUMNS),
        ]
        if payload.ledger:
            datasets.append(("ledger", payload.ledger, _LEDGER_COLUMNS))

        for name, rows, columns in datasets:
            if not rows:
                continue
            preview[name] = len(rows)
            result.records_out += len(rows)
            if dry_run:
                continue
            if fmt == "json":
                body = _rows_to_json(rows, columns)
                key = f"{run_prefix}/{name}.json"
            else:
                body = _rows_to_csv(rows, columns, self._delimiter())
                key = f"{run_prefix}/{name}.csv"
            await self.storage.put(key, body)
            result.file_keys.append(key)

        result.details["format"] = fmt
        result.details["dry_run"] = dry_run
        result.details["preview"] = preview
        if dry_run:
            result.details["note"] = "Dry run - no files were written."
        return result

    # ── Pull ──────────────────────────────────────────────────────────────

    async def pull(self, *, dry_run: bool) -> SyncResult:
        result = SyncResult(direction="pull")
        inbound_key = str(self.settings().get("inbound_key") or "").strip()
        if not inbound_key:
            result.errors.append("No inbound ledger file configured.")
            return result
        if self.config.project_id is None:
            result.errors.append("Connector is not scoped to a project; cannot post ledger rows.")
            return result

        try:
            raw = await self.storage.get(inbound_key)
        except FileNotFoundError:
            result.errors.append(f"Inbound file not found: {inbound_key}")
            return result
        except Exception as exc:  # noqa: BLE001 - surface as a sync error, don't crash the run.
            result.errors.append(f"Could not read inbound file: {exc}")
            return result

        try:
            rows = _parse_inbound(raw, self._format(), self._delimiter())
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Could not parse inbound file: {exc}")
            return result

        result.records_in = len(rows)
        if not rows:
            result.warnings.append("Inbound file contained no ledger rows.")
            return result

        # Idempotency: never re-import a transaction_ref this connector
        # already posted for the project. Re-running pull on the same file
        # is then a safe no-op rather than a duplicate ledger.
        already = await self._existing_refs()

        # Group legs by transaction_ref.
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ref = str(row.get("transaction_ref") or "").strip()
            if not ref:
                result.warnings.append("Skipped a row with no transaction_ref.")
                continue
            groups.setdefault(ref, []).append(row)

        account_map = self.settings().get("account_map")
        account_map = account_map if isinstance(account_map, dict) else {}
        written = 0
        skipped_existing = 0

        for ref, legs in groups.items():
            if ref in already:
                skipped_existing += 1
                continue
            debit_total = sum((to_decimal(leg.get("debit_amount")) for leg in legs), to_decimal(0))
            credit_total = sum((to_decimal(leg.get("credit_amount")) for leg in legs), to_decimal(0))
            if debit_total <= 0 or debit_total != credit_total:
                result.errors.append(
                    f"Transaction {ref}: unbalanced (debit {debit_total} vs credit {credit_total}); skipped."
                )
                continue
            debit_legs = [leg for leg in legs if to_decimal(leg.get("debit_amount")) > 0]
            credit_legs = [leg for leg in legs if to_decimal(leg.get("credit_amount")) > 0]
            if len(debit_legs) != 1 or len(credit_legs) != 1:
                result.warnings.append(f"Transaction {ref}: multi-leg journals are not imported yet; skipped.")
                continue
            debit_acct = _map_account(debit_legs[0].get("account_code"), account_map, result)
            credit_acct = _map_account(credit_legs[0].get("account_code"), account_map, result)
            if not debit_acct or not credit_acct:
                result.errors.append(f"Transaction {ref}: missing debit or credit account; skipped.")
                continue
            if not dry_run:
                ok = await self._write_pair(ref, legs[0], debit_acct, credit_acct, debit_total, result)
                if not ok:
                    continue
            written += 1

        result.records_out = written
        result.details["transactions_written"] = written
        result.details["skipped_already_imported"] = skipped_existing
        result.details["dry_run"] = dry_run
        if dry_run:
            result.details["note"] = "Dry run - no ledger rows were written."
        return result

    async def _existing_refs(self) -> set[str]:
        from sqlalchemy import select

        from app.modules.finance.models import LedgerEntry

        stmt = (
            select(LedgerEntry.transaction_ref)
            .where(LedgerEntry.project_id == self.config.project_id)
            .where(LedgerEntry.source_type == _SOURCE_TYPE)
            .distinct()
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return {str(r) for r in rows}

    async def _write_pair(
        self,
        ref: str,
        sample: dict[str, Any],
        debit_acct: str,
        credit_acct: str,
        amount: Any,
        result: SyncResult,
    ) -> bool:
        from app.modules.finance.schemas import LedgerEntryCreate
        from app.modules.finance.service import FinanceService

        posted_at = str(sample.get("posted_at") or "").strip()[:30]
        data = LedgerEntryCreate(
            project_id=self.config.project_id,
            transaction_ref=ref[:100],
            debit_account=debit_acct[:100],
            credit_account=credit_acct[:100],
            debit_amount=str(amount),
            credit_amount=str(amount),
            description=(str(sample.get("description") or "") or None),
            currency_code=str(sample.get("currency_code") or "")[:10],
            posted_at=posted_at,
            source_type=_SOURCE_TYPE,
            source_id=str(self.config.id),
            created_by=str(self.config.created_by) if self.config.created_by else None,
        )
        try:
            await FinanceService(self.session).create_ledger_transaction(data)
        except Exception as exc:  # noqa: BLE001 - record per-transaction, keep going.
            result.errors.append(f"Transaction {ref}: ledger write failed ({exc}).")
            return False
        return True


# ── Module-level serialisation / parsing helpers ─────────────────────────


def _rows_to_csv(rows: Sequence[dict[str, Any]], columns: tuple[str, ...], delimiter: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([neutralise_formula(_cell(row.get(col))) for col in columns])
    return buffer.getvalue().encode("utf-8")


def _rows_to_json(rows: Sequence[dict[str, Any]], columns: tuple[str, ...]) -> bytes:
    payload = [{col: neutralise_formula(_cell(row.get(col))) for col in columns} for row in rows]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _cell(value: Any) -> Any:
    """Render a value for a flat-file cell - bools as lowercase text, None as ''."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _parse_inbound(raw: bytes, fmt: str, delimiter: str) -> list[dict[str, Any]]:
    """Parse an inbound GL file into a list of canonical-keyed dicts."""
    text = raw.decode("utf-8-sig", errors="replace")
    records: list[dict[str, Any]]
    if fmt == "json":
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            # tolerate {"rows": [...]} or {"entries": [...]} wrappers
            for key in ("rows", "entries", "ledger", "data"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
        if not isinstance(parsed, list):
            raise ValueError("JSON ledger file must be a list of rows.")
        records = [r for r in parsed if isinstance(r, dict)]
    else:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        records = [dict(r) for r in reader]
    return [_normalise_row(r) for r in records]


def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map arbitrary header names onto the canonical field set."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        canonical = _INBOUND_ALIASES.get(str(key).strip().lower().replace(" ", "_"))
        if canonical:
            out[canonical] = value
    return out


def _map_account(raw: Any, account_map: dict[str, Any], result: SyncResult) -> str:
    """Apply the config's account_map to an inbound account code.

    Unmapped codes pass through unchanged but are recorded as a warning so
    nothing is silently written with a garbage account string.
    """
    code = str(raw or "").strip()
    if not code:
        return ""
    mapped = account_map.get(code)
    if mapped:
        return str(mapped)
    if account_map and code not in account_map:
        result.warnings.append(f"Account code {code!r} has no mapping; imported as-is.")
    return code
