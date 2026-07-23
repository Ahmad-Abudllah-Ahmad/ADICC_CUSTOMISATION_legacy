# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts data access layer."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contracts.models import (
    Contract,
    ContractDocument,
    ContractLine,
    ContractMilestone,
    ContractParty,
    ContractSecurity,
    ContractTypeConfiguration,
    EOTClaim,
    FeeStructure,
    FinalAccount,
    GainshareConfiguration,
    LDClause,
    ProgressClaim,
    ProgressClaimLine,
    RetentionSchedule,
)


class _CRUDBase:
    """Common CRUD operations shared by all contracts repositories."""

    model: type
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, item_id: uuid.UUID) -> Any:
        return await self.session.get(self.model, item_id)

    async def create(self, item: Any) -> Any:
        self.session.add(item)
        await self.session.flush()
        return item

    async def update_fields(self, item_id: uuid.UUID, **fields: Any) -> None:
        stmt = update(self.model).where(self.model.id == item_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, item_id: uuid.UUID) -> None:
        obj = await self.get_by_id(item_id)
        if obj is not None:
            await self.session.delete(obj)
            await self.session.flush()


class ContractRepository(_CRUDBase):
    model = Contract

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        counterparty_type: str | None = None,
        contract_type: str | None = None,
    ) -> tuple[list[Contract], int]:
        stmt = select(Contract).where(Contract.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Contract.status == status)
        if counterparty_type is not None:
            stmt = stmt.where(Contract.counterparty_type == counterparty_type)
        if contract_type is not None:
            stmt = stmt.where(Contract.contract_type == contract_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        items = (
            (await self.session.execute(stmt.order_by(Contract.created_at.desc()).offset(offset).limit(limit)))
            .scalars()
            .all()
        )
        return list(items), total

    async def list_active_for_counterparty(
        self,
        counterparty_id: uuid.UUID,
    ) -> list[Contract]:
        stmt = select(Contract).where(
            Contract.counterparty_id == counterparty_id,
            Contract.status == "active",
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Contract | None:
        result = await self.session.execute(select(Contract).where(Contract.code == code).limit(1))
        return result.scalar_one_or_none()


class ContractLineRepository(_CRUDBase):
    model = ContractLine

    async def list_for_contract(self, contract_id: uuid.UUID) -> list[ContractLine]:
        stmt = (
            select(ContractLine)
            .where(ContractLine.contract_id == contract_id)
            .order_by(ContractLine.order_index, ContractLine.code)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, lines: list[ContractLine]) -> list[ContractLine]:
        for line in lines:
            self.session.add(line)
        await self.session.flush()
        return lines


class ContractTypeConfigurationRepository(_CRUDBase):
    model = ContractTypeConfiguration

    async def list_all(self) -> list[ContractTypeConfiguration]:
        result = await self.session.execute(
            select(ContractTypeConfiguration).order_by(
                ContractTypeConfiguration.contract_type,
            )
        )
        return list(result.scalars().all())

    async def get_by_type(
        self,
        contract_type: str,
    ) -> ContractTypeConfiguration | None:
        result = await self.session.execute(
            select(ContractTypeConfiguration)
            .where(
                ContractTypeConfiguration.contract_type == contract_type,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class RetentionScheduleRepository(_CRUDBase):
    model = RetentionSchedule

    async def list_for_contract(
        self,
        contract_id: uuid.UUID,
    ) -> list[RetentionSchedule]:
        result = await self.session.execute(
            select(RetentionSchedule).where(
                RetentionSchedule.contract_id == contract_id,
            )
        )
        return list(result.scalars().all())


class FeeStructureRepository(_CRUDBase):
    model = FeeStructure

    async def get_for_contract(self, contract_id: uuid.UUID) -> FeeStructure | None:
        result = await self.session.execute(
            select(FeeStructure)
            .where(
                FeeStructure.contract_id == contract_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class GainshareConfigurationRepository(_CRUDBase):
    model = GainshareConfiguration

    async def get_for_contract(
        self,
        contract_id: uuid.UUID,
    ) -> GainshareConfiguration | None:
        result = await self.session.execute(
            select(GainshareConfiguration)
            .where(
                GainshareConfiguration.contract_id == contract_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class LDClauseRepository(_CRUDBase):
    model = LDClause

    async def list_for_contract(self, contract_id: uuid.UUID) -> list[LDClause]:
        result = await self.session.execute(select(LDClause).where(LDClause.contract_id == contract_id))
        return list(result.scalars().all())


class ProgressClaimRepository(_CRUDBase):
    model = ProgressClaim

    async def claims_for_contract(
        self,
        contract_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> tuple[list[ProgressClaim], int]:
        stmt = select(ProgressClaim).where(ProgressClaim.contract_id == contract_id)
        if status is not None:
            stmt = stmt.where(ProgressClaim.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        items = (
            (await self.session.execute(stmt.order_by(ProgressClaim.created_at.desc()).offset(offset).limit(limit)))
            .scalars()
            .all()
        )
        return list(items), total

    async def next_claim_number(self, contract_id: uuid.UUID) -> str:
        result = await self.session.execute(
            select(func.count()).select_from(ProgressClaim).where(ProgressClaim.contract_id == contract_id)
        )
        count = result.scalar_one()
        return f"PC-{count + 1:04d}"

    async def unpaid_claims_total(self, contract_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(ProgressClaim.net_due), 0)).where(
                ProgressClaim.contract_id == contract_id,
                ProgressClaim.status.in_(("submitted", "approved", "certified")),
            )
        )
        value = result.scalar_one()
        return Decimal(str(value or 0))

    async def paid_total(self, contract_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(ProgressClaim.net_due), 0)).where(
                ProgressClaim.contract_id == contract_id,
                ProgressClaim.status == "paid",
            )
        )
        value = result.scalar_one()
        return Decimal(str(value or 0))

    async def outstanding_retention(self, contract_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(ProgressClaim.retention_amount), 0)).where(
                ProgressClaim.contract_id == contract_id,
                ProgressClaim.status.in_(("approved", "certified", "paid")),
            )
        )
        value = result.scalar_one()
        return Decimal(str(value or 0))


class ProgressClaimLineRepository(_CRUDBase):
    model = ProgressClaimLine

    async def list_for_claim(
        self,
        claim_id: uuid.UUID,
    ) -> list[ProgressClaimLine]:
        result = await self.session.execute(
            select(ProgressClaimLine).where(
                ProgressClaimLine.progress_claim_id == claim_id,
            )
        )
        return list(result.scalars().all())

    async def bulk_create(
        self,
        lines: list[ProgressClaimLine],
    ) -> list[ProgressClaimLine]:
        for line in lines:
            self.session.add(line)
        await self.session.flush()
        return lines

    async def delete_for_claim(self, claim_id: uuid.UUID) -> int:
        """Delete every claim line belonging to ``claim_id``.

        Returns the number of rows removed. Used by the Gap I progress bridge
        when committing a freshly-populated set of lines: the existing draft
        lines are wiped in one statement (instead of an N+1 per-row delete)
        before the new breakdown is inserted, so re-running the populate +
        commit is idempotent and never accumulates stale duplicate lines.
        """
        stmt = sa_delete(ProgressClaimLine).where(
            ProgressClaimLine.progress_claim_id == claim_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def prior_period_value_by_line(
        self,
        contract_id: uuid.UUID,
        *,
        exclude_claim_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, Decimal]:
        """Sum of ``period_completed_value`` per contract line across prior claims.

        Used to maintain the running ``cumulative_completed_value`` on each new
        claim line: the cumulative for a line is every recognised period value
        billed against it so far (this contract's non-rejected claims) plus the
        current period. Rejected claims are excluded because they were never
        recognised as work-in-place; the claim currently being (re)generated is
        excluded via ``exclude_claim_id`` so a re-run does not double-count its
        own previous lines. Returns ``{contract_line_id: Decimal}``.
        """
        stmt = (
            select(
                ProgressClaimLine.contract_line_id,
                func.coalesce(func.sum(ProgressClaimLine.period_completed_value), 0),
            )
            .join(
                ProgressClaim,
                ProgressClaim.id == ProgressClaimLine.progress_claim_id,
            )
            .where(
                ProgressClaim.contract_id == contract_id,
                ProgressClaim.status != "rejected",
            )
            .group_by(ProgressClaimLine.contract_line_id)
        )
        if exclude_claim_id is not None:
            stmt = stmt.where(ProgressClaimLine.progress_claim_id != exclude_claim_id)
        result = await self.session.execute(stmt)
        return {row[0]: Decimal(str(row[1] or 0)) for row in result.all()}

    async def lines_with_status_for_contract(
        self,
        contract_id: uuid.UUID,
    ) -> list[tuple[ProgressClaimLine, str]]:
        """All claim lines for a contract + their parent claim status.

        Single JOIN query - replaces an N+1 (one claim-line query per
        progress claim) in the SoV-status rollup.
        """
        stmt = (
            select(ProgressClaimLine, ProgressClaim.status)
            .join(
                ProgressClaim,
                ProgressClaim.id == ProgressClaimLine.progress_claim_id,
            )
            .where(ProgressClaim.contract_id == contract_id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class FinalAccountRepository(_CRUDBase):
    model = FinalAccount

    async def get_for_contract(self, contract_id: uuid.UUID) -> FinalAccount | None:
        result = await self.session.execute(
            select(FinalAccount)
            .where(
                FinalAccount.contract_id == contract_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class ContractPartyRepository(_CRUDBase):
    model = ContractParty

    async def list_for_contract(self, contract_id: uuid.UUID) -> list[ContractParty]:
        stmt = (
            select(ContractParty)
            .where(ContractParty.contract_id == contract_id)
            .order_by(ContractParty.is_primary.desc(), ContractParty.party_role)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ContractSecurityRepository(_CRUDBase):
    model = ContractSecurity

    async def list_for_contract(
        self,
        contract_id: uuid.UUID,
        *,
        status: str | None = None,
        security_type: str | None = None,
    ) -> list[ContractSecurity]:
        stmt = select(ContractSecurity).where(ContractSecurity.contract_id == contract_id)
        if status is not None:
            stmt = stmt.where(ContractSecurity.status == status)
        if security_type is not None:
            stmt = stmt.where(ContractSecurity.security_type == security_type)
        result = await self.session.execute(stmt.order_by(ContractSecurity.created_at.desc()))
        return list(result.scalars().all())

    async def has_active_of_type(self, contract_id: uuid.UUID, security_type: str) -> bool:
        """True when an active security of the given type exists on the contract."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ContractSecurity)
            .where(
                ContractSecurity.contract_id == contract_id,
                ContractSecurity.security_type == security_type,
                ContractSecurity.status == "active",
            )
        )
        return int(result.scalar_one() or 0) > 0


class EOTClaimRepository(_CRUDBase):
    model = EOTClaim

    async def list_for_contract(
        self,
        contract_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[EOTClaim]:
        stmt = select(EOTClaim).where(EOTClaim.contract_id == contract_id)
        if status is not None:
            stmt = stmt.where(EOTClaim.status == status)
        result = await self.session.execute(stmt.order_by(EOTClaim.created_at.desc()))
        return list(result.scalars().all())

    async def next_eot_number(self, contract_id: uuid.UUID) -> str:
        result = await self.session.execute(
            select(func.count()).select_from(EOTClaim).where(EOTClaim.contract_id == contract_id)
        )
        count = result.scalar_one()
        return f"EOT-{count + 1:04d}"

    async def total_days_granted(self, contract_id: uuid.UUID) -> int:
        """Sum of granted days across decided EOT claims on the contract."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(EOTClaim.days_granted), 0)).where(
                EOTClaim.contract_id == contract_id,
                EOTClaim.status.in_(("granted", "partially_granted")),
            )
        )
        return int(result.scalar_one() or 0)


class ContractDocumentRepository(_CRUDBase):
    model = ContractDocument

    async def list_for_contract(
        self,
        contract_id: uuid.UUID,
        *,
        doc_role: str | None = None,
    ) -> list[ContractDocument]:
        stmt = select(ContractDocument).where(ContractDocument.contract_id == contract_id)
        if doc_role is not None:
            stmt = stmt.where(ContractDocument.doc_role == doc_role)
        result = await self.session.execute(stmt.order_by(ContractDocument.created_at.desc()))
        return list(result.scalars().all())


class ContractMilestoneRepository(_CRUDBase):
    model = ContractMilestone

    async def list_for_contract(self, contract_id: uuid.UUID) -> list[ContractMilestone]:
        stmt = (
            select(ContractMilestone)
            .where(ContractMilestone.contract_id == contract_id)
            .order_by(ContractMilestone.planned_date, ContractMilestone.code)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
