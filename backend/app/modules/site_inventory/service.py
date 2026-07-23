# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site-inventory service layer.

Async data access on top of the module's own tables, plus the read-side loaders
that build :class:`app.modules.site_inventory.ledger.Movement` lists and the
per-position BoQ budgets fed to the pure computation core. Every referenced id
(item, location, BoQ position, procurement goods receipt) is confirmed to belong
to the same project before a movement is written, so a movement can never be
attached to another project's resource even when the caller is authorised on
their own project.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from app.modules.site_inventory import ledger
from app.modules.site_inventory.models import StockItem, StockLocation, StockMovement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.site_inventory.schemas import (
        LocationCreate,
        MovementCreate,
        StockItemCreate,
    )

_ZERO = Decimal("0")


def _to_decimal(value: object) -> Decimal:
    """Coerce a stored value to ``Decimal``, treating junk / ``None`` as zero."""
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO


class SiteInventoryService:
    """Stateless business logic for on-site material metering and stock."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Locations ----------------------------------------------------------

    async def create_location(self, project_id: uuid.UUID, payload: LocationCreate) -> StockLocation:
        """Create a geo-tagged storage location on a project."""
        location = StockLocation(
            project_id=project_id,
            name=payload.name,
            code=payload.code,
            latitude=_to_decimal(payload.latitude) if payload.latitude is not None else None,
            longitude=_to_decimal(payload.longitude) if payload.longitude is not None else None,
            address=payload.address,
            is_active=payload.is_active,
            metadata_=dict(payload.metadata),
        )
        self.session.add(location)
        await self.session.flush()
        return location

    async def list_locations(self, project_id: uuid.UUID) -> list[StockLocation]:
        """List every storage location on a project, newest first."""
        stmt = (
            select(StockLocation)
            .where(StockLocation.project_id == project_id)
            .order_by(StockLocation.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_location(self, project_id: uuid.UUID, location_id: uuid.UUID) -> StockLocation | None:
        """Load one location, scoped to the project (``None`` if foreign/absent)."""
        stmt = select(StockLocation).where(
            StockLocation.id == location_id,
            StockLocation.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # -- Items --------------------------------------------------------------

    async def create_item(self, project_id: uuid.UUID, payload: StockItemCreate) -> StockItem:
        """Create a stock item / material record, validating cross-module links."""
        if payload.boq_position_id is not None:
            await self._require_boq_position_in_project(project_id, payload.boq_position_id)
        if payload.default_location_id is not None:
            await self._require_location_in_project(project_id, payload.default_location_id)

        item = StockItem(
            project_id=project_id,
            name=payload.name,
            sku=payload.sku,
            unit=payload.unit,
            boq_position_id=payload.boq_position_id,
            procurement_req_item_id=payload.procurement_req_item_id,
            default_location_id=payload.default_location_id,
            standard_unit_cost=(
                _to_decimal(payload.standard_unit_cost) if payload.standard_unit_cost is not None else None
            ),
            currency=payload.currency,
            reorder_point=(_to_decimal(payload.reorder_point) if payload.reorder_point is not None else None),
            is_active=payload.is_active,
            metadata_=dict(payload.metadata),
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_items(self, project_id: uuid.UUID) -> list[StockItem]:
        """List every stock item on a project, newest first."""
        stmt = select(StockItem).where(StockItem.project_id == project_id).order_by(StockItem.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_item(self, project_id: uuid.UUID, item_id: uuid.UUID) -> StockItem | None:
        """Load one item, scoped to the project (``None`` if foreign/absent)."""
        stmt = select(StockItem).where(StockItem.id == item_id, StockItem.project_id == project_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # -- Movements ----------------------------------------------------------

    async def record_movement(
        self,
        project_id: uuid.UUID,
        payload: MovementCreate,
        actor_id: str | None,
    ) -> StockMovement:
        """Record a stock movement after confirming every reference is in-project.

        Raises 404 if the item, a location, the BoQ position or the goods
        receipt referenced does not belong to ``project_id`` - this is the
        defense-in-depth companion to the router's project-access gate, closing
        the door on attaching a movement to another project's resource.
        """
        item = await self.get_item(project_id, payload.item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock item not found in this project")

        if payload.location_id is not None:
            await self._require_location_in_project(project_id, payload.location_id)
        if payload.to_location_id is not None:
            await self._require_location_in_project(project_id, payload.to_location_id)
        if payload.boq_position_id is not None:
            await self._require_boq_position_in_project(project_id, payload.boq_position_id)
        if payload.goods_receipt_id is not None:
            await self._require_goods_receipt_in_project(project_id, payload.goods_receipt_id)

        movement = StockMovement(
            project_id=project_id,
            item_id=payload.item_id,
            movement_type=payload.movement_type,
            quantity=_to_decimal(payload.quantity),
            unit_cost=_to_decimal(payload.unit_cost),
            currency=payload.currency,
            location_id=payload.location_id,
            to_location_id=payload.to_location_id,
            boq_position_id=payload.boq_position_id,
            goods_receipt_id=payload.goods_receipt_id,
            occurred_at=payload.occurred_at or datetime.now(UTC),
            actor_id=actor_id,
            note=payload.note,
            metadata_=dict(payload.metadata),
        )
        self.session.add(movement)
        await self.session.flush()
        return movement

    async def list_movements(
        self,
        project_id: uuid.UUID,
        *,
        item_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        movement_type: str | None = None,
        limit: int = 500,
    ) -> list[StockMovement]:
        """List movements for a project with optional item / location / type filters."""
        stmt = select(StockMovement).where(StockMovement.project_id == project_id)
        if item_id is not None:
            stmt = stmt.where(StockMovement.item_id == item_id)
        if location_id is not None:
            stmt = stmt.where(
                (StockMovement.location_id == location_id) | (StockMovement.to_location_id == location_id),
            )
        if movement_type is not None:
            stmt = stmt.where(StockMovement.movement_type == movement_type)
        stmt = stmt.order_by(StockMovement.occurred_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _all_movements(self, project_id: uuid.UUID) -> list[StockMovement]:
        """Load every movement for a project (ordered), for a full ledger rollup."""
        stmt = (
            select(StockMovement)
            .where(StockMovement.project_id == project_id)
            .order_by(StockMovement.occurred_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # -- Derived reports (DB loaders + pure ledger) -------------------------

    async def stock_on_hand(
        self,
        project_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
    ) -> dict:
        """Per-item stock on hand for a project, optionally within one location."""
        if location_id is not None:
            await self._require_location_in_project(project_id, location_id)

        rows = await self._all_movements(project_id)
        movements = [_to_ledger_movement(r) for r in rows]
        if location_id is not None:
            on_hand = ledger.stock_on_hand_by_item_at_location(movements, str(location_id))
        else:
            on_hand = ledger.stock_on_hand_by_item(movements)

        items = {str(item.id): item for item in await self.list_items(project_id)}
        out_rows = []
        for item_id in sorted(on_hand):
            item = items.get(item_id)
            out_rows.append(
                {
                    "item_id": item_id,
                    "name": item.name if item is not None else "",
                    "unit": item.unit if item is not None else "",
                    "on_hand": str(on_hand[item_id].quantize(Decimal("0.0001"))),
                },
            )
        return {
            "project_id": str(project_id),
            "location_id": str(location_id) if location_id is not None else None,
            "item_count": len(out_rows),
            "rows": out_rows,
        }

    async def material_variance_report(self, project_id: uuid.UUID) -> dict:
        """Per-position material-cost variance: actual consumed vs BoQ budget."""
        rows = await self._all_movements(project_id)
        movements = [_to_ledger_movement(r) for r in rows]

        consumed_position_ids = {
            m.boq_position_id
            for m in movements
            if m.boq_position_id is not None and m.movement_type == ledger.MovementType.CONSUMPTION.value
        }
        budgets = await self._position_budgets(project_id, consumed_position_ids)
        summary = ledger.summarize_variance(ledger.material_cost_variance(movements, budgets))
        payload = summary.to_dict()
        payload["project_id"] = str(project_id)
        return payload

    async def waste_report(
        self,
        project_id: uuid.UUID,
        *,
        opening_stock: Decimal | None = None,
        period_days: Decimal | None = None,
    ) -> dict:
        """Waste ratio plus turnover / days-on-hand for a project's materials.

        ``opening_stock`` and ``period_days`` are optional. When both are given,
        turnover and days-on-hand are computed over ``average_inventory`` (opening
        vs current on hand); otherwise those two figures are ``None`` and only the
        waste ratio and totals are reported, so the endpoint degrades gracefully.
        """
        rows = await self._all_movements(project_id)
        movements = [_to_ledger_movement(r) for r in rows]

        on_hand = ledger.stock_on_hand(movements)
        consumed = ledger.total_consumed(movements)
        wasted = ledger.total_wasted(movements)
        received = ledger.total_inbound(movements)

        span = period_days if period_days is not None else ledger.period_days(movements)
        opening = opening_stock if opening_stock is not None else _ZERO
        avg_inventory = ledger.average_inventory(opening, on_hand)
        turnover = ledger.inventory_turnover(consumed, avg_inventory)
        days = ledger.days_on_hand(avg_inventory, consumed, span) if span is not None else None

        def _s(value: Decimal | None, quant: str) -> str | None:
            if value is None:
                return None
            return str(value.quantize(Decimal(quant)))

        return {
            "project_id": str(project_id),
            "total_inbound": _s(received, "0.0001"),
            "total_consumed": _s(consumed, "0.0001"),
            "total_wasted": _s(wasted, "0.0001"),
            "stock_on_hand": _s(on_hand, "0.0001"),
            "waste_ratio": _s(ledger.waste_ratio(movements), "0.000001"),
            "average_inventory": _s(avg_inventory, "0.0001"),
            "inventory_turnover": _s(turnover, "0.000001"),
            "days_on_hand": _s(days, "0.01"),
            "period_days": _s(span, "0.01"),
        }

    # -- Cross-module ownership guards --------------------------------------

    async def _require_location_in_project(self, project_id: uuid.UUID, location_id: uuid.UUID) -> None:
        """Confirm a storage location belongs to the project, else 404."""
        location = await self.get_location(project_id, location_id)
        if location is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage location not found in this project",
            )

    async def _require_boq_position_in_project(self, project_id: uuid.UUID, position_id: uuid.UUID) -> None:
        """Confirm a BoQ position belongs to the project (via its BoQ), else 404."""
        if not await self._boq_position_in_project(project_id, position_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BoQ position not found in this project",
            )

    async def _require_goods_receipt_in_project(self, project_id: uuid.UUID, goods_receipt_id: uuid.UUID) -> None:
        """Confirm a procurement goods receipt belongs to the project, else 404."""
        from app.modules.procurement.models import GoodsReceipt, PurchaseOrder

        stmt = (
            select(GoodsReceipt.id)
            .join(PurchaseOrder, GoodsReceipt.po_id == PurchaseOrder.id)
            .where(GoodsReceipt.id == goods_receipt_id, PurchaseOrder.project_id == project_id)
        )
        if (await self.session.execute(stmt)).first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Goods receipt not found in this project",
            )

    async def _boq_position_in_project(self, project_id: uuid.UUID, position_id: uuid.UUID) -> bool:
        """True when a BoQ position's owning BoQ is in the project."""
        from app.modules.boq.models import BOQ, Position

        stmt = (
            select(Position.id)
            .join(BOQ, Position.boq_id == BOQ.id)
            .where(Position.id == position_id, BOQ.project_id == project_id)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def _position_budgets(
        self,
        project_id: uuid.UUID,
        position_ids: set[str | None],
    ) -> dict[str, Decimal]:
        """Budgeted material cost per BoQ position, scoped to the project.

        Only positions whose owning BoQ is in ``project_id`` are returned, so a
        foreign position id smuggled onto a movement can never pull another
        project's estimate figure into this report. The budget is the position's
        stored line total (``quantity * unit_rate``).
        """
        wanted = {pid for pid in position_ids if pid}
        if not wanted:
            return {}

        from app.modules.boq.models import BOQ, Position

        as_uuid: list[uuid.UUID] = []
        for pid in wanted:
            try:
                as_uuid.append(uuid.UUID(str(pid)))
            except (ValueError, TypeError):
                continue
        if not as_uuid:
            return {}

        stmt = (
            select(Position.id, Position.quantity, Position.unit_rate, Position.total)
            .join(BOQ, Position.boq_id == BOQ.id)
            .where(Position.id.in_(as_uuid), BOQ.project_id == project_id)
        )
        budgets: dict[str, Decimal] = {}
        for pid, quantity, unit_rate, total in (await self.session.execute(stmt)).all():
            budget = _to_decimal(total)
            if budget == _ZERO:
                budget = _to_decimal(quantity) * _to_decimal(unit_rate)
            budgets[str(pid)] = budget
        return budgets


def _to_ledger_movement(row: StockMovement) -> ledger.Movement:
    """Project a persisted movement row onto the pure :class:`ledger.Movement`."""
    return ledger.Movement(
        movement_type=str(row.movement_type),
        quantity=_to_decimal(row.quantity),
        unit_cost=_to_decimal(row.unit_cost),
        item_id=str(row.item_id) if row.item_id is not None else None,
        location_id=str(row.location_id) if row.location_id is not None else None,
        to_location_id=str(row.to_location_id) if row.to_location_id is not None else None,
        boq_position_id=str(row.boq_position_id) if row.boq_position_id is not None else None,
        occurred_at=row.occurred_at,
    )
