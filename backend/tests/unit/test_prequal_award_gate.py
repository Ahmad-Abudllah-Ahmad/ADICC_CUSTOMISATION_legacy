"""Prequalification award gate (TOP-30 #20).

A subcontractor that is administratively blocked, or whose prequalification is
``rejected`` / ``suspended``, must not be moved onto a live subcontract or paid.
``pending`` (the default for a fresh vendor) and ``approved`` may proceed.

Two layers:

* pure-logic tests of :func:`subcontractor_award_block`;
* real-PostgreSQL tests that activating an agreement and submitting a payment
  are refused with a 409 for a barred vendor and allowed for an approved one.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subcontractors.schemas import AgreementUpdate, PaymentApplicationCreate
from app.modules.subcontractors.service import (
    SubcontractorService,
    subcontractor_award_block,
)
from tests._pg import transactional_session


def _sub(*, blocked=False, prequal="approved"):
    return SimpleNamespace(is_blocked=blocked, prequalification_status=prequal)


def test_approved_is_awardable() -> None:
    result = subcontractor_award_block(_sub(prequal="approved"))
    assert result.blocked is False
    assert result.reasons == []


def test_pending_is_awardable() -> None:
    # pending is the default for a fresh vendor - allowed, the UI only nudges
    result = subcontractor_award_block(_sub(prequal="pending"))
    assert result.blocked is False


def test_rejected_is_barred() -> None:
    result = subcontractor_award_block(_sub(prequal="rejected"))
    assert result.blocked is True
    assert result.reasons == ["prequalification_rejected"]


def test_suspended_is_barred() -> None:
    result = subcontractor_award_block(_sub(prequal="suspended"))
    assert result.blocked is True
    assert result.reasons == ["prequalification_suspended"]


def test_blocked_is_barred() -> None:
    result = subcontractor_award_block(_sub(blocked=True, prequal="approved"))
    assert result.blocked is True
    assert result.reasons == ["subcontractor_blocked"]


def test_blocked_and_rejected_lists_both() -> None:
    result = subcontractor_award_block(_sub(blocked=True, prequal="rejected"))
    assert result.blocked is True
    assert result.reasons == ["subcontractor_blocked", "prequalification_rejected"]


# ── real-PostgreSQL gate ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with transactional_session(disable_fks=True) as s:
        yield s


async def _seed_agreement(
    session: AsyncSession,
    *,
    blocked=False,
    prequal="approved",
    agreement_status="draft",
):
    from app.modules.subcontractors.models import SubcontractAgreement, Subcontractor

    sub = Subcontractor(
        legal_name="Acme Trades",
        is_blocked=blocked,
        prequalification_status=prequal,
    )
    session.add(sub)
    await session.flush()
    agreement = SubcontractAgreement(
        subcontractor_id=sub.id,
        project_id=uuid.uuid4(),
        title="Drywall package",
        status=agreement_status,
        currency="CAD",
    )
    session.add(agreement)
    await session.flush()
    return sub, agreement


@pytest.mark.asyncio
async def test_activation_blocked_for_rejected_sub(session: AsyncSession) -> None:
    _sub_row, agreement = await _seed_agreement(session, prequal="rejected")
    svc = SubcontractorService(session)
    with pytest.raises(HTTPException) as exc:
        await svc.update_agreement(agreement.id, AgreementUpdate(status="active"))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "prequalification_rejected"


@pytest.mark.asyncio
async def test_activation_blocked_for_blocked_sub(session: AsyncSession) -> None:
    _sub_row, agreement = await _seed_agreement(session, blocked=True)
    svc = SubcontractorService(session)
    with pytest.raises(HTTPException) as exc:
        await svc.update_agreement(agreement.id, AgreementUpdate(status="active"))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "subcontractor_blocked"


@pytest.mark.asyncio
async def test_activation_allowed_for_approved_sub(session: AsyncSession) -> None:
    _sub_row, agreement = await _seed_agreement(session, prequal="approved")
    svc = SubcontractorService(session)
    updated = await svc.update_agreement(agreement.id, AgreementUpdate(status="active"))
    assert updated.status == "active"


@pytest.mark.asyncio
async def test_payment_submission_blocked_for_suspended_sub(session: AsyncSession) -> None:
    # An agreement that went live while the sub was approved, but the sub has
    # since been suspended: the next payment must still be refused.
    _sub_row, agreement = await _seed_agreement(session, prequal="suspended", agreement_status="active")
    svc = SubcontractorService(session)
    with pytest.raises(HTTPException) as exc:
        await svc.submit_payment_application(
            PaymentApplicationCreate(agreement_id=agreement.id, gross_amount=Decimal("5000")),
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "prequalification_suspended"
