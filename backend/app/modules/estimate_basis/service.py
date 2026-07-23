# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-basis business logic.

Reads the finished estimate contents (the BOQ positions of a project), runs the
pure :mod:`.derivation` engine over them, and persists the drafted
basis-of-estimate. Also serves the read / edit / export of a stored document.

The heavy reasoning lives in :mod:`.derivation` (stdlib-only, unit tested); this
layer only moves rows in and out and shapes the response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.modules.allowances.models import Allowance
from app.modules.boq.models import BOQ, Position
from app.modules.costs.models import CostItem, CostItemUsage
from app.modules.estimate_basis.derivation import (
    TradeCoverage,
    derive_trades,
    draft_basis,
    fmt_decimal,
)
from app.modules.estimate_basis.models import EstimateBasis
from app.modules.estimate_basis.schemas import (
    CoverageSummary,
    EstimateBasisResponse,
    EstimateBasisSummary,
    QualificationItem,
    TradePresenceOut,
    TradeRefOut,
    UpdateRequest,
)
from app.modules.preliminaries.models import PrelimItem
from app.modules.preliminaries.prelim_math import rollup_by_category

# Bound the position scan so a runaway project can never OOM the worker; the same
# ceiling the BOQ Project Intelligence widgets use. A basis of estimate is a
# qualitative summary, so the first 20k lines already cover the trade picture.
_POSITION_CAP = 20_000

# A section header carries no unit; the derivation only wants priced line items.
_LINE_ITEM_FILTER = Position.unit != ""


class EstimateBasisService:
    """Draft, store and serve the basis-of-estimate for a project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Reads over the estimate ──────────────────────────────────────────────

    async def _load_positions(
        self,
        project_id: uuid.UUID,
        boq_id: uuid.UUID | None,
    ) -> list[Position]:
        """Return the priced line items of a project (or one of its BOQs).

        Section headers (no unit) are dropped and the children/parent eager
        loads suppressed - the derivation reads only scalar columns.
        """
        stmt = (
            select(Position)
            .join(BOQ, Position.boq_id == BOQ.id)
            .where(BOQ.project_id == project_id)
            .where(_LINE_ITEM_FILTER)
            .order_by(Position.sort_order, Position.ordinal)
            .limit(_POSITION_CAP)
            .options(noload(Position.children), noload(Position.parent))
        )
        if boq_id is not None:
            stmt = stmt.where(Position.boq_id == boq_id)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    @staticmethod
    def _position_to_dict(pos: Position) -> dict:
        """Project a Position ORM row into the plain dict the engine consumes."""
        return {
            "classification": pos.classification or {},
            "description": pos.description or "",
            "quantity": pos.quantity,
            "unit_rate": pos.unit_rate,
            "total": pos.total,
        }

    # ── Reads over the sibling estimating modules ────────────────────────────

    async def _load_allowances(self, project_id: uuid.UUID) -> list[dict]:
        """Return the project's allowances as plain dicts for the deriver.

        Only the held amount is read (not the drawdowns): the basis records the
        allowance that was set, not what has since been spent against it. Ordered
        by type then age so a regenerate is stable.
        """
        stmt = (
            select(Allowance)
            .where(Allowance.project_id == project_id)
            .order_by(Allowance.allowance_type, Allowance.created_at)
            .limit(500)
        )
        rows = await self.session.execute(stmt)
        return [
            {
                "id": str(a.id),
                "label": a.label or "",
                "allowance_type": a.allowance_type or "",
                "held_amount": a.held_amount,
                "currency": a.currency or "",
            }
            for a in rows.scalars().all()
        ]

    async def _load_preliminaries_summary(self, project_id: uuid.UUID, currency: str) -> dict:
        """Roll the project's preliminaries up via ``prelim_math`` into a summary.

        Returns the grand / time-related / fixed totals, the item count and the
        estimate currency, ready for the deriver. An empty project yields a
        zero-count summary that drafts no line.
        """
        stmt = select(PrelimItem).where(PrelimItem.project_id == project_id).limit(2000)
        rows = await self.session.execute(stmt)
        items = [
            {
                "item_type": p.item_type,
                "category": p.category,
                "rate_per_period": p.rate_per_period,
                "periods": p.periods,
                "fixed_amount": p.fixed_amount,
            }
            for p in rows.scalars().all()
        ]
        rollup = rollup_by_category(items)
        return {
            "grand_total": rollup.grand_total,
            "time_related_total": rollup.time_related_total,
            "fixed_total": rollup.fixed_total,
            "item_count": rollup.item_count,
            "currency": (currency or "").strip(),
        }

    async def _derive_pricing_base_date(
        self,
        project_id: uuid.UUID,
        boq_id: uuid.UUID | None,
    ) -> str | None:
        """Return the date the priced rates are current to, or ``None``.

        Prefers the freshest ``price_as_of`` across the cost items actually
        applied in the project (through the usage ledger); falls back to the
        estimate's stated base date (the BOQ ``base_date``, the escalation base).
        """
        price_stmt = (
            select(func.max(CostItem.price_as_of))
            .select_from(CostItemUsage)
            .join(CostItem, CostItem.id == CostItemUsage.cost_item_id)
            .where(CostItemUsage.project_id == project_id)
        )
        price_as_of = (await self.session.execute(price_stmt)).scalar()
        if price_as_of is not None:
            return price_as_of.isoformat()

        base_stmt = select(func.max(BOQ.base_date)).where(BOQ.project_id == project_id)
        if boq_id is not None:
            base_stmt = base_stmt.where(BOQ.id == boq_id)
        base_date = (await self.session.execute(base_stmt)).scalar()
        if base_date:
            return str(base_date).strip() or None
        return None

    # ── Generate ─────────────────────────────────────────────────────────────

    async def generate(
        self,
        *,
        project_id: uuid.UUID,
        boq_id: uuid.UUID | None,
        title: str | None,
        currency: str,
        base_date: str | None,
        created_by: uuid.UUID | None,
    ) -> EstimateBasis:
        """Derive and persist a fresh basis-of-estimate for the project.

        Always inserts a new document (drafts are versioned, not overwritten), so
        a regenerate never silently discards a client's prior edits.
        """
        positions = await self._load_positions(project_id, boq_id)
        coverage = derive_trades([self._position_to_dict(p) for p in positions])
        allowances = await self._load_allowances(project_id)
        preliminaries = await self._load_preliminaries_summary(project_id, currency)
        pricing_base_date = await self._derive_pricing_base_date(project_id, boq_id)
        draft = draft_basis(
            coverage,
            currency=currency,
            base_date=base_date,
            allowances=allowances,
            preliminaries=preliminaries,
            pricing_base_date=pricing_base_date,
        )

        doc = EstimateBasis(
            project_id=project_id,
            boq_id=boq_id,
            title=(title or "").strip() or "Basis of estimate",
            status="draft",
            inclusions=[q.to_dict() for q in draft.inclusions],
            exclusions=[q.to_dict() for q in draft.exclusions],
            assumptions=[q.to_dict() for q in draft.assumptions],
            coverage=self._coverage_summary(coverage).model_dump(),
            generated_at=datetime.now(UTC).isoformat(),
            created_by=created_by,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    @staticmethod
    def _coverage_summary(coverage: TradeCoverage) -> CoverageSummary:
        """Shape a :class:`TradeCoverage` into the serialisable summary."""
        return CoverageSummary(
            present_trades=[
                TradePresenceOut(
                    code=p.code,
                    label=p.label,
                    core=p.core,
                    position_count=p.position_count,
                    total=fmt_decimal(p.total),
                )
                for p in coverage.present
            ],
            absent_trades=[TradeRefOut(code=t.code, label=t.label) for t in coverage.absent_core],
            total_positions=coverage.total_positions,
            classified_positions=coverage.classified_positions,
            unclassified_positions=coverage.unclassified_positions,
            zero_rate_positions=coverage.zero_rate_positions,
            missing_quantity_positions=coverage.missing_quantity_positions,
            provisional_positions=coverage.provisional_positions,
            by_others_positions=coverage.by_others_positions,
        )

    # ── Read / list ──────────────────────────────────────────────────────────

    async def get_document(self, document_id: uuid.UUID) -> EstimateBasis | None:
        """Fetch one document by id, or ``None`` when it does not exist."""
        return await self.session.get(EstimateBasis, document_id)

    async def list_for_project(self, project_id: uuid.UUID) -> list[EstimateBasis]:
        """Every basis document for a project, newest first."""
        stmt = (
            select(EstimateBasis)
            .where(EstimateBasis.project_id == project_id)
            .order_by(EstimateBasis.created_at.desc())
            .limit(200)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    # ── Update ───────────────────────────────────────────────────────────────

    async def update_document(
        self,
        doc: EstimateBasis,
        payload: UpdateRequest,
    ) -> EstimateBasis:
        """Persist user edits. Only the provided fields are touched."""
        if payload.title is not None:
            doc.title = payload.title.strip() or doc.title
        if payload.status is not None:
            doc.status = payload.status
        if payload.notes is not None:
            doc.notes = payload.notes
        if payload.inclusions is not None:
            doc.inclusions = [self._normalize_item(i, "inclusion") for i in payload.inclusions]
        if payload.exclusions is not None:
            doc.exclusions = [self._normalize_item(i, "exclusion") for i in payload.exclusions]
        if payload.assumptions is not None:
            doc.assumptions = [self._normalize_item(i, "assumption") for i in payload.assumptions]
        await self.session.flush()
        return doc

    @staticmethod
    def _normalize_item(item: QualificationItem, category: str) -> dict:
        """Force an incoming item onto its list's category and serialise it."""
        data = item.model_dump()
        data["category"] = category
        return data

    # ── Response shaping ─────────────────────────────────────────────────────

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        """ISO-8601 for a timestamp column, or ``None``."""
        return value.isoformat() if value is not None else None

    @classmethod
    def to_response(cls, doc: EstimateBasis) -> EstimateBasisResponse:
        """Build the full-document response from a stored row."""
        return EstimateBasisResponse(
            id=str(doc.id),
            project_id=str(doc.project_id),
            boq_id=str(doc.boq_id) if doc.boq_id else None,
            title=doc.title,
            status=doc.status,
            notes=doc.notes or "",
            inclusions=[QualificationItem.model_validate(i) for i in (doc.inclusions or [])],
            exclusions=[QualificationItem.model_validate(i) for i in (doc.exclusions or [])],
            assumptions=[QualificationItem.model_validate(i) for i in (doc.assumptions or [])],
            coverage=CoverageSummary.model_validate(doc.coverage or {}),
            generated_at=doc.generated_at,
            created_at=cls._iso(doc.created_at),
            updated_at=cls._iso(doc.updated_at),
        )

    @classmethod
    def to_summary(cls, doc: EstimateBasis) -> EstimateBasisSummary:
        """Build the lightweight list row from a stored document."""
        return EstimateBasisSummary(
            id=str(doc.id),
            project_id=str(doc.project_id),
            boq_id=str(doc.boq_id) if doc.boq_id else None,
            title=doc.title,
            status=doc.status,
            inclusion_count=len(doc.inclusions or []),
            exclusion_count=len(doc.exclusions or []),
            assumption_count=len(doc.assumptions or []),
            generated_at=doc.generated_at,
            created_at=cls._iso(doc.created_at),
            updated_at=cls._iso(doc.updated_at),
        )

    # ── Export ───────────────────────────────────────────────────────────────

    @classmethod
    def render_markdown(cls, doc: EstimateBasis) -> str:
        """Render the document as Markdown for inclusion with a proposal.

        Only enabled lines are written - a line the estimator toggled off stays
        out of the client-facing export.
        """
        lines: list[str] = [f"# {doc.title}", ""]
        meta = f"Status: {doc.status}"
        if doc.generated_at:
            meta += f"  ·  Generated: {doc.generated_at}"
        lines.append(f"_{meta}_")
        lines.append("")

        sections = (
            ("Inclusions", doc.inclusions),
            ("Exclusions", doc.exclusions),
            ("Assumptions", doc.assumptions),
        )
        for heading, items in sections:
            enabled = [it for it in (items or []) if it.get("enabled", True)]
            lines.append(f"## {heading}")
            if enabled:
                for it in enabled:
                    lines.append(f"- {str(it.get('text', '')).strip()}")
            else:
                lines.append("- None.")
            lines.append("")

        if (doc.notes or "").strip():
            lines.append("## Notes")
            lines.append(doc.notes.strip())
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
