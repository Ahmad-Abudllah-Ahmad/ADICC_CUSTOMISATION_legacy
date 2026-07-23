"""Data-integrity unit tests for :class:`ProcurementService` (Wave 4).

Covers the concurrency / failure-mode guards added in the data-integrity wave:

* a goods receipt cannot be CREATED already ``confirmed`` (it must enter at
  ``draft`` so confirmation runs the PO rollup + finance event + confirm-time
  over-receipt cap);
* PO line items cannot be REPLACED once goods receipts exist (the destructive
  delete would orphan the ``GoodsReceiptItem.po_item_id`` linkage via the
  ``ON DELETE SET NULL`` FK and corrupt the received-quantity accounting);
* the goods-receipt confirm path uses the atomic ``confirm_if_draft`` guard so
  a concurrent double-confirm cannot double-publish ``procurement.gr.confirmed``.

Repositories are stubbed, mirroring ``test_procurement.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from app.modules.procurement.models import GoodsReceipt
from app.modules.procurement.schemas import (
    GRCreate,
    GRItemCreate,
    POCreate,
    POItemCreate,
    POUpdate,
)
from app.modules.procurement.service import ProcurementService

PROJECT_ID = uuid.uuid4()


# ── Stubs (same shape as test_procurement.py) ─────────────────────────────


class _StubPORepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Any] = {}
        self._counter = 0
        self._item_repo: _StubPOItemRepo | None = None

    async def create(self, po: Any) -> Any:
        if getattr(po, "id", None) is None:
            po.id = uuid.uuid4()
        now = datetime.now(UTC)
        po.created_at = now
        po.updated_at = now
        if not hasattr(po, "items"):
            po.items = []
        if not hasattr(po, "goods_receipts"):
            po.goods_receipts = []
        self.rows[po.id] = po
        return po

    async def get(self, po_id: uuid.UUID) -> Any:
        po = self.rows.get(po_id)
        if po is not None and self._item_repo is not None:
            po.items = [it for it in self._item_repo.rows.values() if it.po_id == po_id]
        return po

    async def update(self, po_id: uuid.UUID, **kwargs: Any) -> None:
        po = self.rows.get(po_id)
        if po:
            for k, v in kwargs.items():
                setattr(po, k, v)
            po.updated_at = datetime.now(UTC)

    async def next_po_number(self, project_id: uuid.UUID) -> str:
        self._counter += 1
        return f"PO-{self._counter:04d}"


class _StubPOItemRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Any] = {}

    async def create(self, item: Any) -> Any:
        if getattr(item, "id", None) is None:
            item.id = uuid.uuid4()
        now = datetime.now(UTC)
        item.created_at = now
        item.updated_at = now
        self.rows[item.id] = item
        return item

    async def delete_by_po(self, po_id: uuid.UUID) -> None:
        self.rows = {k: v for k, v in self.rows.items() if v.po_id != po_id}


class _StubGRRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Any] = {}
        self.confirm_calls = 0

    async def create(self, gr: Any) -> Any:
        if getattr(gr, "id", None) is None:
            gr.id = uuid.uuid4()
        now = datetime.now(UTC)
        gr.created_at = now
        gr.updated_at = now
        if not hasattr(gr, "items"):
            gr.items = []
        self.rows[gr.id] = gr
        return gr

    async def get(self, gr_id: uuid.UUID) -> Any:
        return self.rows.get(gr_id)

    async def update(self, gr_id: uuid.UUID, **kwargs: Any) -> None:
        gr = self.rows.get(gr_id)
        if gr:
            for k, v in kwargs.items():
                setattr(gr, k, v)

    async def confirm_if_draft(self, gr_id: uuid.UUID) -> bool:
        """Mirror the real conditional UPDATE: only the draft -> confirmed
        transition counts; a second call on an already-confirmed row is a
        no-op that returns False (the loser of a double-confirm race)."""
        self.confirm_calls += 1
        gr = self.rows.get(gr_id)
        if gr is None or gr.status != "draft":
            return False
        gr.status = "confirmed"
        return True


class _StubGRItemRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Any] = {}

    async def create(self, item: Any) -> Any:
        if getattr(item, "id", None) is None:
            item.id = uuid.uuid4()
        self.rows[item.id] = item
        return item


class _EmptyResult:
    """Stub SQLAlchemy result: every aggregate query returns no rows."""

    def all(self) -> list[Any]:
        return []

    def scalar_one_or_none(self) -> Any:
        return None


class _StubSession:
    """Minimal async session for service paths that issue aggregate SELECTs.

    The confirm path calls ``_confirmed_received_by_item`` (a SUM grouped by
    po_item_id); returning an empty result models "no prior confirmed receipts",
    which is the correct precondition for these single-GR tests.
    """

    def expunge(self, _obj: Any) -> None:  # noqa: D401 - stub
        return None

    async def execute(self, _stmt: Any) -> _EmptyResult:
        return _EmptyResult()


def _make_service() -> ProcurementService:
    svc = ProcurementService.__new__(ProcurementService)
    svc.session = _StubSession()
    svc.po_repo = _StubPORepo()
    svc.po_item_repo = _StubPOItemRepo()
    svc.po_repo._item_repo = svc.po_item_repo
    svc.gr_repo = _StubGRRepo()
    svc.gr_item_repo = _StubGRItemRepo()
    return svc


def _po_data(**overrides: Any) -> POCreate:
    defaults = {
        "project_id": PROJECT_ID,
        "po_type": "standard",
        "amount_subtotal": "1000.00",
        "tax_amount": "0",
    }
    defaults.update(overrides)
    return POCreate(**defaults)


# ── 1. GR cannot be created already confirmed ──────────────────────────────


@pytest.mark.asyncio
async def test_create_goods_receipt_rejects_non_draft_status() -> None:
    """A GR posted with status='confirmed' is rejected (must enter at draft).

    Otherwise the receipt counts as confirmed for over-receipt math but the PO
    never rolls up to partially_received/completed and the
    ``procurement.gr.confirmed`` finance event never fires - an inconsistent
    state. Mirrors the draft-only entry guard on create_po().
    """
    svc = _make_service()
    po = await svc.create_po(_po_data())
    svc.po_repo.rows[po.id].status = "issued"

    gr_data = GRCreate(po_id=po.id, receipt_date="2026-04-10", status="confirmed")
    with pytest.raises(HTTPException) as exc:
        await svc.create_goods_receipt(gr_data)
    assert exc.value.status_code == 400
    assert "draft" in exc.value.detail


@pytest.mark.asyncio
async def test_create_goods_receipt_draft_still_allowed() -> None:
    """The default (draft) create path is unaffected by the new guard."""
    svc = _make_service()
    po = await svc.create_po(_po_data())
    svc.po_repo.rows[po.id].status = "issued"

    gr = await svc.create_goods_receipt(GRCreate(po_id=po.id, receipt_date="2026-04-10"))
    assert gr.status == "draft"


# ── 2. PO items cannot be replaced once goods receipts exist ───────────────


@pytest.mark.asyncio
async def test_update_po_replace_items_blocked_when_gr_exists() -> None:
    """Replacing line items on a PO that already has GRs is a 409.

    The destructive delete_by_po would NULL the GoodsReceiptItem.po_item_id
    link (ON DELETE SET NULL) and corrupt the received-quantity accounting.
    """
    svc = _make_service()
    po = await svc.create_po(
        _po_data(items=[POItemCreate(description="Rebar", quantity="100", unit_rate="2")]),
    )
    # Simulate a confirmed goods receipt already recorded against the PO. Use a
    # real GoodsReceipt ORM instance so assigning to the instrumented
    # ``goods_receipts`` relationship does not trip SQLAlchemy's backref event.
    svc.po_repo.rows[po.id].status = "partially_received"
    svc.po_repo.rows[po.id].goods_receipts = [GoodsReceipt(po_id=po.id, receipt_date="2026-04-10", status="confirmed")]

    with pytest.raises(HTTPException) as exc:
        await svc.update_po(
            po.id,
            POUpdate(items=[POItemCreate(description="Rebar (edited)", quantity="5", unit_rate="2")]),
        )
    assert exc.value.status_code == 409
    assert "goods receipts" in exc.value.detail
    # The original line item must be untouched (no destructive delete happened).
    remaining = [it for it in svc.po_item_repo.rows.values() if it.po_id == po.id]
    assert len(remaining) == 1
    assert remaining[0].description == "Rebar"


@pytest.mark.asyncio
async def test_update_po_replace_items_allowed_without_gr() -> None:
    """With no goods receipts, item replacement still works (no regression)."""
    svc = _make_service()
    po = await svc.create_po(
        _po_data(items=[POItemCreate(description="Rebar", quantity="100", unit_rate="2")]),
    )
    assert svc.po_repo.rows[po.id].goods_receipts == []

    updated = await svc.update_po(
        po.id,
        POUpdate(items=[POItemCreate(description="Cement", quantity="10", unit_rate="50")]),
    )
    items = [it for it in svc.po_item_repo.rows.values() if it.po_id == po.id]
    assert len(items) == 1
    assert items[0].description == "Cement"
    # Header re-aggregated from the new line: 10 * 50 = 500.
    assert updated.amount_subtotal == "500"


@pytest.mark.asyncio
async def test_update_po_header_only_change_allowed_with_gr() -> None:
    """A header-only PATCH (no items[]) is still allowed when GRs exist - the
    guard only blocks the destructive item replace, not other edits."""
    svc = _make_service()
    po = await svc.create_po(_po_data())
    svc.po_repo.rows[po.id].status = "partially_received"
    svc.po_repo.rows[po.id].goods_receipts = [GoodsReceipt(po_id=po.id, receipt_date="2026-04-10", status="confirmed")]

    updated = await svc.update_po(po.id, POUpdate(notes="updated note"))
    assert updated.notes == "updated note"


# ── 3. Confirm uses the atomic guard / double-confirm is a no-op ───────────


@pytest.mark.asyncio
async def test_confirm_goods_receipt_uses_atomic_guard() -> None:
    """confirm_goods_receipt flips draft -> confirmed via confirm_if_draft."""
    svc = _make_service()
    po = await svc.create_po(
        _po_data(items=[POItemCreate(description="Rebar", quantity="100", unit_rate="2")]),
    )
    svc.po_repo.rows[po.id].status = "issued"
    po_item_id = next(iter(svc.po_item_repo.rows.values())).id

    gr = await svc.create_goods_receipt(
        GRCreate(
            po_id=po.id,
            receipt_date="2026-04-10",
            items=[GRItemCreate(po_item_id=po_item_id, quantity_received="100")],
        ),
    )
    confirmed = await svc.confirm_goods_receipt(gr.id)
    assert confirmed.status == "confirmed"
    assert svc.gr_repo.confirm_calls == 1


@pytest.mark.asyncio
async def test_confirm_goods_receipt_double_confirm_conflicts() -> None:
    """A second confirm on an already-confirmed GR raises 409 (lost the race),
    rather than re-running the rollup / re-publishing the finance event."""
    svc = _make_service()
    po = await svc.create_po(
        _po_data(items=[POItemCreate(description="Rebar", quantity="100", unit_rate="2")]),
    )
    svc.po_repo.rows[po.id].status = "issued"
    po_item_id = next(iter(svc.po_item_repo.rows.values())).id

    gr = await svc.create_goods_receipt(
        GRCreate(
            po_id=po.id,
            receipt_date="2026-04-10",
            items=[GRItemCreate(po_item_id=po_item_id, quantity_received="100")],
        ),
    )
    await svc.confirm_goods_receipt(gr.id)

    # Simulate a concurrent double-confirm: the read-time ``status != draft``
    # guard sees a still-draft row (both racing requests do), but at write time
    # the row was already flipped by the winner, so confirm_if_draft matches no
    # row and returns False -> the service must 409 rather than re-run.
    svc.gr_repo.rows[gr.id].status = "draft"  # read-time check passes
    orig_confirm = svc.gr_repo.confirm_if_draft

    async def _racing_confirm(gr_id: uuid.UUID) -> bool:
        svc.gr_repo.rows[gr_id].status = "confirmed"  # a concurrent winner committed first
        return await orig_confirm(gr_id)

    svc.gr_repo.confirm_if_draft = _racing_confirm  # type: ignore[assignment]

    with pytest.raises(HTTPException) as exc:
        await svc.confirm_goods_receipt(gr.id)
    assert exc.value.status_code == 409
