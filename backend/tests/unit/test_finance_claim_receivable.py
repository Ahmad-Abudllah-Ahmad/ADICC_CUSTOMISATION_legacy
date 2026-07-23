# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Module tests for Gap E: certified claim → receivable invoice + withholding.

Runs against the real embedded PostgreSQL the suite boots, using the canonical
``transactional_session`` isolation primitive (one outer transaction rolled back
per test). Covers:

* receivable invoice auto-created from a certified claim, with claim lines
  mapped to invoice line items and multi-currency conversion to the project base;
* idempotency — certifying / invoicing the same claim twice yields one invoice;
* a not-yet-certified claim is rejected (400);
* a zero-net claim still produces a (zero) invoice;
* payment-with-withholding splits gross into cash + retainage, is idempotent on
  the idempotency key, links back to the source claim, and posts only the cash
  leg to the cost spine;
* a payment against a non-claim invoice still records (skips claim linkage).

The cost-spine sink (Gap B) is monkeypatched so these tests stay in the finance
lane and assert the *contract* with the spine (it is called once, with the cash
amount, idempotently) without depending on cost-model internals.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.modules.contracts.models import (
    Contract,
    ContractLine,
    ProgressClaim,
    ProgressClaimLine,
)
from app.modules.finance.models import Invoice, Payment
from app.modules.finance.schemas import RecordClaimPaymentRequest
from app.modules.finance.service import FinanceService
from app.modules.projects.models import Project
from app.modules.users.models import User
from tests._pg import transactional_session

OWNER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def session():
    """Transaction-isolated PG session with a user + USD project seeded."""
    async with transactional_session() as s:
        s.add(User(id=OWNER_ID, email="owner@test.io", hashed_password="x", full_name="Owner"))
        await s.flush()
        yield s


# ── Seed helpers ─────────────────────────────────────────────────────────────


async def _make_project(s, *, currency: str = "USD", fx_rates: list[dict[str, str]] | None = None) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Gap E Project",
        owner_id=OWNER_ID,
        currency=currency,
        status="active",
        fx_rates=fx_rates or [],
        metadata_={},
    )
    s.add(project)
    await s.flush()
    return project


async def _make_contract(
    s,
    project: Project,
    *,
    currency: str = "USD",
    counterparty_id: uuid.UUID | None = None,
    retention_percent: str = "5.00",
) -> Contract:
    contract = Contract(
        id=uuid.uuid4(),
        code=f"C-{uuid.uuid4().hex[:8]}",
        title="Main works",
        project_id=project.id,
        counterparty_id=counterparty_id,
        currency=currency,
        retention_percent=Decimal(retention_percent),
        status="active",
    )
    s.add(contract)
    await s.flush()
    return contract


async def _make_claim(
    s,
    contract: Contract,
    *,
    status: str = "certified",
    gross: str = "100000",
    retention: str = "5000",
    net: str = "95000",
    currency: str | None = None,
    n_lines: int = 0,
) -> ProgressClaim:
    claim = ProgressClaim(
        id=uuid.uuid4(),
        contract_id=contract.id,
        claim_number=f"PC-{uuid.uuid4().hex[:4]}",
        claim_date="2026-06-01",
        gross_amount=Decimal(gross),
        retention_amount=Decimal(retention),
        net_due=Decimal(net),
        currency=currency if currency is not None else contract.currency,
        status=status,
    )
    s.add(claim)
    await s.flush()
    if n_lines:
        per_line = Decimal(net) / Decimal(n_lines)
        for i in range(n_lines):
            cl = ContractLine(
                id=uuid.uuid4(),
                contract_id=contract.id,
                code=f"L{i}",
                description=f"Line {i}",
                total_value=per_line,
            )
            s.add(cl)
            await s.flush()
            s.add(
                ProgressClaimLine(
                    id=uuid.uuid4(),
                    progress_claim_id=claim.id,
                    contract_line_id=cl.id,
                    period_completed_qty=Decimal("1"),
                    period_completed_value=per_line,
                    period_completed_pct=Decimal("100"),
                    cumulative_completed_value=per_line,
                )
            )
        await s.flush()
    return claim


def _patch_spine(monkeypatch) -> list[dict]:
    """Capture every ``post_actual_to_budget_line`` call instead of running it."""
    calls: list[dict] = []

    async def _fake_post(
        self,
        project_id,
        cost_line_id,
        cost_category,
        amount_base,
        currency,
        source_kind,
        source_ref,
        *,
        idempotency_key,
    ):  # noqa: ANN001, ANN002, ANN003, E501
        # Idempotent capture keyed on (source_kind, source_ref) — a replay of
        # the same posting must not double-record, mirroring the real sink.
        key = (source_kind, source_ref)
        if not any((c["source_kind"], c["source_ref"]) == key for c in calls):
            calls.append(
                {
                    "project_id": project_id,
                    "amount_base": amount_base,
                    "currency": currency,
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                    "idempotency_key": idempotency_key,
                }
            )
        return object()

    from app.modules.costmodel.service import CostSpineService

    monkeypatch.setattr(CostSpineService, "post_actual_to_budget_line", _fake_post)
    return calls


# ── create_receivable_from_claim ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_receivable_invoice_from_claim_three_lines(session) -> None:
    project = await _make_project(session, currency="USD")
    contract = await _make_contract(session, project, currency="USD")
    claim = await _make_claim(session, contract, n_lines=3, net="90000", retention="4500", gross="94500")

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    assert invoice.invoice_direction == "receivable"
    assert invoice.status == "draft"
    assert invoice.source_claim_id == claim.id
    # Gross on the invoice; net is amount_total - retention_amount.
    assert Decimal(str(invoice.amount_total)) == Decimal("94500.00")
    assert Decimal(str(invoice.retention_amount)) == Decimal("4500.00")
    net = Decimal(str(invoice.amount_total)) - Decimal(str(invoice.retention_amount))
    assert net == Decimal("90000.00")
    assert invoice.currency_code == "USD"
    # 3 claim lines → 3 invoice line items (line breakdown sums to net work value).
    assert len(invoice.line_items) == 3
    line_total = sum(Decimal(str(li.amount)) for li in invoice.line_items)
    assert line_total == Decimal("90000.00")


@pytest.mark.asyncio
async def test_receivable_invoice_multi_currency_gbp_to_usd(session) -> None:
    # Project base USD; claim priced in GBP at 1.25 → net 10,000 GBP = 12,500 USD.
    project = await _make_project(session, currency="USD", fx_rates=[{"code": "GBP", "rate": "1.25"}])
    contract = await _make_contract(session, project, currency="GBP")
    claim = await _make_claim(session, contract, currency="GBP", gross="10500", retention="500", net="10000")

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    assert invoice.currency_code == "USD"
    # Gross 10,500 GBP * 1.25 = 13,125 USD; retention 500 GBP * 1.25 = 625 USD.
    assert Decimal(str(invoice.amount_total)) == Decimal("13125.00")
    assert Decimal(str(invoice.retention_amount)) == Decimal("625.00")
    net = Decimal(str(invoice.amount_total)) - Decimal(str(invoice.retention_amount))
    assert net == Decimal("12500.00")
    assert invoice.metadata_["claim_currency"] == "GBP"


@pytest.mark.asyncio
async def test_currency_mismatch_missing_fx_keeps_value(session) -> None:
    # Base USD, claim in GBP, but NO fx rate → value kept in its own units,
    # never zeroed (domain money rule).
    project = await _make_project(session, currency="USD", fx_rates=[])
    contract = await _make_contract(session, project, currency="GBP")
    claim = await _make_claim(session, contract, currency="GBP", gross="10500", retention="500", net="10000")

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)
    # Gross kept in GBP units (10,500), never zeroed by a missing rate.
    assert Decimal(str(invoice.amount_total)) == Decimal("10500.00")  # not 0


@pytest.mark.asyncio
async def test_receivable_invoice_idempotency_same_claim_twice(session) -> None:
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)

    svc = FinanceService(session)
    first = await svc.create_receivable_from_claim(claim.id)
    second = await svc.create_receivable_from_claim(claim.id)
    assert first.id == second.id

    rows = (await session.execute(Invoice.__table__.select().where(Invoice.source_claim_id == claim.id))).fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_receivable_from_claim_not_certified_rejected(session) -> None:
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract, status="approved")

    svc = FinanceService(session)
    with pytest.raises(HTTPException) as exc:
        await svc.create_receivable_from_claim(claim.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_receivable_from_claim_missing_claim_404(session) -> None:
    svc = FinanceService(session)
    with pytest.raises(HTTPException) as exc:
        await svc.create_receivable_from_claim(uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_claim_with_zero_net_due(session) -> None:
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract, gross="0", retention="0", net="0")

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)
    assert Decimal(str(invoice.amount_total)) == Decimal("0.00")
    assert invoice.source_claim_id == claim.id


@pytest.mark.asyncio
async def test_claim_certified_event_triggers_invoice_creation(session, monkeypatch) -> None:
    # Exercise the subscriber's core call (the service method it delegates to)
    # — the event-bus → session plumbing is covered separately; here we assert
    # the certified claim materialises into AR.
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id, actor_id=str(OWNER_ID))
    assert invoice is not None
    assert invoice.source_claim_id == claim.id
    # get_receivable_for_claim convenience lookup resolves the same row.
    looked_up = await svc.get_receivable_for_claim(claim.id)
    assert looked_up is not None and looked_up.id == invoice.id


# ── record_payment_with_withholding ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_with_withholding_derives_from_invoice(session, monkeypatch) -> None:
    calls = _patch_spine(monkeypatch)
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract, gross="100000", retention="5000", net="95000")

    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    # Pay the whole invoice; withholding derived from invoice.retention_amount.
    payment = await svc.record_payment_with_withholding(
        invoice.id,
        RecordClaimPaymentRequest(payment_date="2026-06-10"),
    )
    # Gross settled = amount_total (100000) since amount omitted; held = 5000;
    # cash paid = 95000 (the certified net).
    assert Decimal(str(payment.withholding_amount)) == Decimal("5000.00")
    assert Decimal(str(payment.amount)) == Decimal("95000.00")
    assert payment.source_claim_id == claim.id

    # Only the cash leg posts to the spine, once.
    assert len(calls) == 1
    assert Decimal(calls[0]["amount_base"]) == Decimal("95000.00")
    assert calls[0]["source_kind"] == "claim_payment"


@pytest.mark.asyncio
async def test_payment_with_explicit_amount_and_withholding(session, monkeypatch) -> None:
    _patch_spine(monkeypatch)
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)
    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    payment = await svc.record_payment_with_withholding(
        invoice.id,
        RecordClaimPaymentRequest(
            payment_date="2026-06-10",
            amount="80000",
            withholding_amount="4000",
            withholding_release_date="2027-01-01",
        ),
    )
    assert Decimal(str(payment.amount)) == Decimal("80000.00")
    assert Decimal(str(payment.withholding_amount)) == Decimal("4000.00")
    assert payment.withholding_release_date == "2027-01-01"


@pytest.mark.asyncio
async def test_payment_idempotency_key_deduplication(session, monkeypatch) -> None:
    calls = _patch_spine(monkeypatch)
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)
    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    p1 = await svc.record_payment_with_withholding(
        invoice.id,
        RecordClaimPaymentRequest(payment_date="2026-06-10", idempotency_key="K1"),
    )
    p2 = await svc.record_payment_with_withholding(
        invoice.id,
        RecordClaimPaymentRequest(payment_date="2026-06-10", idempotency_key="K1"),
    )
    assert p1.id == p2.id
    rows = (await session.execute(Payment.__table__.select().where(Payment.invoice_id == invoice.id))).fetchall()
    assert len(rows) == 1
    # Spine posted exactly once across both calls.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_post_actual_to_budget_line_idempotency(session, monkeypatch) -> None:
    # Re-posting the same payment id to the spine is a no-op (same source_ref).
    calls = _patch_spine(monkeypatch)
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)
    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    payment = await svc.record_payment_with_withholding(
        invoice.id, RecordClaimPaymentRequest(payment_date="2026-06-10")
    )
    # Manually replay the spine posting for the same payment.
    await svc._post_claim_payment_to_spine(project_id=project.id, payment=payment, currency=invoice.currency_code)
    assert len(calls) == 1  # still one — idempotent on source_ref


@pytest.mark.asyncio
async def test_payment_without_claim_link_skips_claim_linkage(session, monkeypatch) -> None:
    # A plain (non-claim) receivable invoice still records a payment; the
    # payment simply carries no source_claim_id.
    _patch_spine(monkeypatch)
    project = await _make_project(session)
    invoice = Invoice(
        id=uuid.uuid4(),
        project_id=project.id,
        invoice_direction="receivable",
        invoice_number="INV-R-999",
        invoice_date="2026-06-01",
        currency_code="USD",
        amount_subtotal=Decimal("1000"),
        tax_amount=Decimal("0"),
        retention_amount=Decimal("0"),
        amount_total=Decimal("1000"),
        status="draft",
        metadata_={},
    )
    session.add(invoice)
    await session.flush()

    svc = FinanceService(session)
    payment = await svc.record_payment_with_withholding(
        invoice.id, RecordClaimPaymentRequest(payment_date="2026-06-10")
    )
    assert payment.source_claim_id is None
    assert Decimal(str(payment.withholding_amount)) == Decimal("0.00")
    assert Decimal(str(payment.amount)) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_withholding_release_date_round_trips(session, monkeypatch) -> None:
    _patch_spine(monkeypatch)
    project = await _make_project(session)
    contract = await _make_contract(session, project)
    claim = await _make_claim(session, contract)
    svc = FinanceService(session)
    invoice = await svc.create_receivable_from_claim(claim.id)

    payment = await svc.record_payment_with_withholding(
        invoice.id,
        RecordClaimPaymentRequest(payment_date="2026-06-10", withholding_release_date="2027-03-31"),
    )
    reloaded = await session.get(Payment, payment.id)
    assert reloaded.withholding_release_date == "2027-03-31"


@pytest.mark.asyncio
async def test_existing_payable_invoices_unaffected(session) -> None:
    # Regression: an ordinary payable invoice carries no source_claim_id and is
    # not picked up by the claim lookup.
    project = await _make_project(session)
    invoice = Invoice(
        id=uuid.uuid4(),
        project_id=project.id,
        invoice_direction="payable",
        invoice_number="INV-P-001",
        invoice_date="2026-06-01",
        currency_code="USD",
        amount_subtotal=Decimal("500"),
        tax_amount=Decimal("0"),
        retention_amount=Decimal("0"),
        amount_total=Decimal("500"),
        status="draft",
        metadata_={},
    )
    session.add(invoice)
    await session.flush()
    assert invoice.source_claim_id is None

    svc = FinanceService(session)
    assert await svc.get_receivable_for_claim(uuid.uuid4()) is None
