# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Procurement API routes.

Endpoints:
    GET    /                           - List purchase orders
    POST   /                           - Create PO (auth required)
    GET    /goods-receipts             - List goods receipts
    POST   /goods-receipts             - Create GR (auth required)
    POST   /goods-receipts/{id}/confirm - Confirm GR (auth required)
    GET    /{id}                       - Get single PO
    PATCH  /{id}                       - Update PO (auth required)
    POST   /{id}/issue                 - Issue PO (auth required)

NOTE: Fixed-path routes (/goods-receipts) are registered BEFORE the parametric
/{po_id} route so that FastAPI does not try to parse "goods-receipts" as a UUID.
"""

import uuid
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    accessible_project_ids,
    verify_project_access,
)
from app.modules.contacts.models import Contact
from app.modules.procurement.models import PurchaseOrder
from app.modules.procurement.schemas import (
    GRCreate,
    GRListResponse,
    GRResponse,
    POCreate,
    POInvoiceCreatedResponse,
    POListResponse,
    POMatchStatusResponse,
    POResponse,
    PORetainageReleaseListResponse,
    PORetainageReleaseRequest,
    PORetainageReleaseResponse,
    POUpdate,
    ProcurementStatsResponse,
    ProjectDeliveryPerformanceResponse,
    SupplierScorecardResponse,
)
from app.modules.procurement.service import ProcurementService, _validate_3way_match

router = APIRouter(tags=["procurement"])


def _get_service(session: SessionDep) -> ProcurementService:
    return ProcurementService(session)


def _contact_display_name(c: Contact) -> str:
    """Return the human-readable contact label (company > "first last" > email)."""
    if c.company_name:
        return c.company_name
    full = f"{c.first_name or ''} {c.last_name or ''}".strip()
    return full or c.email or ""


async def _fetch_vendor_names(session: AsyncSession, vendor_ids: Iterable[str | None]) -> dict[str, str]:
    """Resolve ``vendor_contact_id`` → display name in one round trip.

    Returns a dict keyed by the string form of the contact UUID. Unknown IDs
    (contact deleted, typo in the string, etc.) just don't appear in the map,
    so the caller falls back to showing the raw UUID.
    """
    ids = {vid for vid in vendor_ids if vid}
    if not ids:
        return {}
    rows = (await session.execute(select(Contact).where(Contact.id.in_(ids)))).scalars().all()
    return {str(c.id): _contact_display_name(c) for c in rows}


def _po_to_response(po: PurchaseOrder, vendor_names: dict[str, str]) -> POResponse:
    resp = POResponse.model_validate(po)
    if po.vendor_contact_id:
        resp.vendor_name = vendor_names.get(po.vendor_contact_id)
    # Computed retainage values cannot come through ``model_validate`` (they
    # are ORM methods, not attributes), so stamp them here. Strings, in the
    # PO's own currency - never blended.
    resp.retainage_amount = str(po.retainage_amount())
    resp.retainage_held = str(po.retainage_held())
    # Non-blocking vendor-prequalification warnings (TOP-30 #20) - stamped by
    # the service gate on create/update as a transient attribute. Absent on a
    # plain list read, so default to empty.
    resp.vendor_warnings = list(getattr(po, "vendor_warnings", []) or [])
    return resp


# ── Purchase Orders (list / create) ─────────────────────────────────────────


@router.get(
    "/",
    response_model=POListResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def list_purchase_orders(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    vendor_contact_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    service: ProcurementService = Depends(_get_service),
) -> POListResponse:
    """List purchase orders with optional filters."""
    await verify_project_access(project_id, str(user_id), session)
    items, total = await service.list_pos(
        project_id=project_id,
        po_status=status,
        vendor_contact_id=vendor_contact_id,
        offset=offset,
        limit=limit,
    )
    vendor_names = await _fetch_vendor_names(service.session, (po.vendor_contact_id for po in items))
    return POListResponse(
        items=[_po_to_response(po, vendor_names) for po in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/",
    response_model=POResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("procurement.create"))],
)
async def create_purchase_order(
    data: POCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POResponse:
    """Create a new purchase order."""
    # IDOR: a PO is a financial commitment against a project, so the caller
    # must have access to ``data.project_id`` - not merely hold the global
    # ``procurement.create`` permission. Without this gate an EDITOR could
    # create POs against any project in any tenant. Mirrors the same check
    # on ``create_goods_receipt`` / ``create_invoice_from_po``.
    await verify_project_access(data.project_id, str(user_id), session)
    po = await service.create_po(data, user_id=user_id)
    vendor_names = await _fetch_vendor_names(service.session, [po.vendor_contact_id])
    return _po_to_response(po, vendor_names)


# ── Stats ────────────────────────────────────────────────────────────────────


@router.get(
    "/stats/",
    response_model=ProcurementStatsResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def procurement_stats(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: ProcurementService = Depends(_get_service),
) -> ProcurementStatsResponse:
    """Aggregate procurement statistics for a project.

    Returns total POs, breakdown by status, total committed amount,
    confirmed goods receipt count, and count of POs pending delivery.
    """
    await verify_project_access(project_id, str(user_id), session)
    return await service.get_stats(project_id)


# -- Supplier delivery performance / OTIF (fixed path - before /{po_id}) -----


@router.get(
    "/delivery-performance/",
    response_model=ProjectDeliveryPerformanceResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def get_delivery_performance(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: ProcurementService = Depends(_get_service),
) -> ProjectDeliveryPerformanceResponse:
    """Supplier on-time-in-full (OTIF) delivery performance for a project.

    Per supplier, and rolled up across the project: on-time rate, in-full rate,
    combined OTIF rate, average days late and the underlying receipt counts -
    all computed from stored PO promised dates and confirmed goods receipts.
    Read-only; scoped to the caller's project.
    """
    await verify_project_access(project_id, str(user_id), session)
    result = await service.get_delivery_performance(project_id)
    # Best-effort vendor display names - the same lookup the PO list uses so the
    # per-supplier rows can be labelled without a second round trip.
    vendor_names = await _fetch_vendor_names(session, [s.supplier_contact_id for s in result.suppliers])
    for supplier in result.suppliers:
        if supplier.supplier_contact_id:
            supplier.supplier_name = vendor_names.get(supplier.supplier_contact_id)
    return result


# ── Goods Receipts (MUST be before /{po_id}) ────────────────────────────────


@router.get(
    "/goods-receipts/",
    response_model=GRListResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def list_goods_receipts(
    user_id: CurrentUserId,
    session: SessionDep,
    # api-HIGH (GR tab): ``po_id`` used to be required, but the frontend GR
    # tab lists receipts by the active project via ``?project_id=<id>`` and
    # was getting a hard 422 (dead tab). Both are now OPTIONAL; the caller
    # supplies exactly one. The legacy ``po_id`` path is unchanged.
    po_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    service: ProcurementService = Depends(_get_service),
) -> GRListResponse:
    """List goods receipts, scoped by ``po_id`` OR ``project_id``."""
    # Exactly one scope is required - preserve the old behaviour of failing
    # fast when no scope is given, but as a clear 400 instead of a 422.
    if po_id is None and project_id is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either po_id or project_id.",
        )

    # ── project_id path: list GRs across the whole project ──────────────
    if project_id is not None:
        # IDOR gate - same project-scope check the PO list uses.
        await verify_project_access(project_id, str(user_id), session)
        rows, total = await service.list_goods_receipts_by_project(
            project_id=project_id,
            gr_status=status,
            limit=limit,
            offset=offset,
        )
        items_out: list[GRResponse] = []
        for gr, po_number in rows:
            resp = GRResponse.model_validate(gr)
            # Stamp the parent PO number (not on the GR ORM row itself).
            resp.po_number = po_number
            items_out.append(resp)
        return GRListResponse(items=items_out, total=total, offset=offset, limit=limit)

    # ── po_id path (unchanged legacy behaviour) ─────────────────────────
    po = await service.get_po(po_id)
    await verify_project_access(po.project_id, str(user_id), session)
    items, total = await service.list_goods_receipts(po_id=po_id, gr_status=status, limit=limit, offset=offset)
    out: list[GRResponse] = []
    for gr in items:
        resp = GRResponse.model_validate(gr)
        # All GRs here belong to the same PO - stamp its number for the FE.
        resp.po_number = po.po_number
        out.append(resp)
    return GRListResponse(items=out, total=total, offset=offset, limit=limit)


@router.post(
    "/goods-receipts/",
    response_model=GRResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("procurement.create"))],
)
async def create_goods_receipt(
    data: GRCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> GRResponse:
    """Create a goods receipt against a PO."""
    po = await service.get_po(data.po_id)
    await verify_project_access(po.project_id, str(user_id), session)
    gr = await service.create_goods_receipt(data, user_id=user_id)
    return GRResponse.model_validate(gr)


@router.post(
    "/goods-receipts/{gr_id}/confirm/",
    response_model=GRResponse,
    dependencies=[Depends(RequirePermission("procurement.confirm_receipt"))],
)
async def confirm_goods_receipt(
    gr_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> GRResponse:
    """Confirm a goods receipt."""
    existing_gr = await service.get_goods_receipt(gr_id)
    parent_po = await service.get_po(existing_gr.po_id)
    await verify_project_access(parent_po.project_id, str(user_id), session)
    gr = await service.confirm_goods_receipt(gr_id)
    return GRResponse.model_validate(gr)


# ── Supplier scorecard (fixed path - MUST be before /{po_id}) ───────────────


@router.get(
    "/suppliers/{contact_id}/scorecard/",
    response_model=SupplierScorecardResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def get_supplier_scorecard(
    contact_id: str,
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID | None = Query(default=None),
    period_days: int = Query(default=365, ge=1, le=3650),
    service: ProcurementService = Depends(_get_service),
) -> SupplierScorecardResponse:
    """Trailing-window KPIs for one supplier.

    When ``project_id`` is provided the access check enforces project-scope
    IDOR (the same gate the PO list uses). Without ``project_id`` the
    cross-project supplier-overview aggregate is scoped to ONLY the
    projects the caller may access (``accessible_project_ids``): an admin
    sees every project (``None`` = no filter), a normal user sees only
    their own. This stops a VIEWER in one tenant from reading another
    supplier's PO totals / KPIs across projects they cannot reach (IDOR on
    the aggregate).
    """
    scope_ids: set[uuid.UUID] | None = None
    if project_id is not None:
        await verify_project_access(project_id, str(user_id), session)
    else:
        # Cross-project overview: restrict the aggregate to the caller's
        # accessible projects. ``None`` (admin) means "do not filter".
        scope_ids = await accessible_project_ids(session, str(user_id))

    data = await service.get_supplier_scorecard(
        supplier_contact_id=contact_id,
        project_id=project_id,
        period_days=period_days,
        accessible_project_ids=scope_ids,
    )

    # Best-effort vendor display name - same lookup the PO list uses so
    # the scorecard modal can label the chart without a second round-trip.
    # On the cross-project overview, only resolve the name when the caller
    # actually has accessible POs for this supplier; otherwise an arbitrary
    # (inaccessible) contact UUID would still leak its display name even
    # though every KPI came back empty. The project-scoped path is already
    # access-gated, so it always resolves.
    if project_id is not None or data.get("total_po_count", 0) > 0:
        name_map = await _fetch_vendor_names(session, [contact_id])
        data["supplier_name"] = name_map.get(contact_id)
    return SupplierScorecardResponse.model_validate(data)


# ── PO by ID (parametric routes LAST) ───────────────────────────────────────


@router.get(
    "/{po_id}",
    response_model=POResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def get_purchase_order(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POResponse:
    """Get a single purchase order by ID."""
    po = await service.get_po(po_id)
    await verify_project_access(po.project_id, str(user_id), session)
    vendor_names = await _fetch_vendor_names(service.session, [po.vendor_contact_id])
    return _po_to_response(po, vendor_names)


@router.patch(
    "/{po_id}",
    response_model=POResponse,
    dependencies=[Depends(RequirePermission("procurement.update"))],
)
async def update_purchase_order(
    po_id: uuid.UUID,
    data: POUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POResponse:
    """Update a purchase order."""
    existing = await service.get_po(po_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    po = await service.update_po(po_id, data)
    vendor_names = await _fetch_vendor_names(service.session, [po.vendor_contact_id])
    return _po_to_response(po, vendor_names)


@router.post(
    "/{po_id}/create-invoice/",
    response_model=POInvoiceCreatedResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("procurement.create_invoice"))],
)
async def create_invoice_from_po(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    force: bool = Query(False, alias="force"),
    service: ProcurementService = Depends(_get_service),
) -> POInvoiceCreatedResponse:
    """Create a payable invoice pre-filled from PO line items.

    Copies the PO's vendor, amounts, and line items into a new draft invoice
    in the finance module.

    Runs a 3-way match (PO ↔ GR ↔ Invoice): each invoice line's quantity must
    not exceed the sum of confirmed goods-receipt quantities for the matching
    PO line, otherwise a 422 is raised.

    Pass ``force=true`` to bypass the 3-way match (e.g. service-only POs with
    no goods to physically receive). The override is audit-logged.

    Cross-module atomicity (R7):
        The Invoice header AND every InvoiceLineItem are inserted under a
        SAVEPOINT (``begin_nested``). Any failure inside the conversion
        body rolls back the partial finance writes WITHOUT discarding the
        outer request session - so a half-created invoice (header without
        line items) can never be left behind. The reference pattern is
        :func:`app.modules.variations.service.convert_vr_to_vo`.

        Authorisation is MANAGER (``procurement.create_invoice``): the
        PO → payable invoice path commits a financial obligation against
        the project that bypasses the normal invoice draft → approve →
        pay chain, so EDITORs may draft POs and receive goods but only
        MANAGER+ may convert one into a payable.
    """
    import logging as _logging

    from fastapi import HTTPException

    _log = _logging.getLogger(__name__)

    po = await service.get_po(po_id)
    await verify_project_access(po.project_id, str(user_id), session)

    # A PO becomes a payable obligation only once it is issued (or further
    # along). Draft/cancelled POs must not be invoiceable. The UI disables the
    # button, but the endpoint enforces it too so the guard can't be bypassed
    # via the API.
    if po.status not in {"issued", "partially_received", "completed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Purchase order must be issued before invoicing (current status: {po.status}).",
        )

    # Lazy import finance module
    try:
        from app.modules.finance.models import Invoice, InvoiceLineItem
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Finance module is not available.",
        )

    # Generate invoice number from PO number
    invoice_number = f"INV-{po.po_number}"

    po_items = po.items or []
    proposed_lines = [
        {
            "ordinal": idx,
            "po_item_id": item.id,
            "quantity": item.quantity,
            "description": item.description,
        }
        for idx, item in enumerate(po_items)
    ]

    violations = _validate_3way_match(po, proposed_lines)
    # Determine HTTP code by violation reason: ``no_confirmed_grs`` is a
    # workflow problem (caller skipped GR confirmation) → 400; everything
    # else is an arithmetic mismatch (over-invoicing) → 422.
    no_conf_violation = next(
        (v for v in violations if v.get("reason") == "no_confirmed_grs"),
        None,
    )
    if violations and not force:
        if no_conf_violation is not None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "no_confirmed_grs",
                    "message": no_conf_violation.get("message")
                    or ("No confirmed goods receipts exist for this PO; pass force=true to invoice without GR match."),
                    "errors": violations,
                },
            )
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "3-way match failed: invoice quantity exceeds confirmed "
                    "goods-receipt quantity for one or more lines. "
                    "Pass force=true to override."
                ),
                "errors": violations,
            },
        )
    if violations and force:
        _log.warning(
            "3-way match override on PO %s",
            po.po_number,
            extra={
                "po_id": str(po_id),
                "user_id": str(user_id),
                "force_3way_match": True,
                "bypassed_3way_match": True,
                "violations": violations,
            },
        )

    # ── Cross-module atomicity: SAVEPOINT around finance writes ─────────
    #
    # If the line-item flush blows up (FK violation, DB outage between
    # the two flushes), the header insert must be undone too - otherwise
    # the finance module ends up with a header-only invoice that has
    # ``amount_total`` set but no detail rows, silently double-counting
    # in dashboards. ``begin_nested`` issues a SAVEPOINT scoped to the
    # outer request transaction; we either commit both writes or roll
    # back both. Mirrors ``variations.convert_vr_to_vo`` (R6 atomicity).
    try:
        async with session.begin_nested():
            invoice = Invoice(
                project_id=po.project_id,
                contact_id=po.vendor_contact_id,
                invoice_direction="payable",
                invoice_number=invoice_number,
                invoice_date=po.issue_date or "",
                due_date=None,
                currency_code=po.currency_code,
                amount_subtotal=po.amount_subtotal,
                tax_amount=po.tax_amount,
                amount_total=po.amount_total,
                status="draft",
                notes=f"Auto-created from PO {po.po_number}",
                created_by=user_id,
                metadata_={
                    "source": "procurement",
                    "po_id": str(po_id),
                    "po_number": po.po_number,
                    "force_3way_match": bool(force and violations),
                    "bypassed_3way_match": bool(force and violations),
                },
            )
            session.add(invoice)
            await session.flush()

            for idx, item in enumerate(po_items):
                line = InvoiceLineItem(
                    invoice_id=invoice.id,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_rate=item.unit_rate,
                    amount=item.amount,
                    wbs_id=item.wbs_id,
                    cost_category=item.cost_category,
                    sort_order=idx,
                )
                session.add(line)

            await session.flush()

            # Audit row inside the same SAVEPOINT - so an audit-log
            # failure rolls the invoice back too. Best-effort log_activity
            # exists elsewhere; here we want the audit to be load-bearing
            # because the PO → payable conversion is the load-bearing
            # financial step (R7).
            try:
                from app.core.audit_log import log_activity

                await log_activity(
                    session,
                    actor_id=str(user_id) if user_id else None,
                    entity_type="purchase_order",
                    entity_id=str(po_id),
                    action="invoice_created",
                    reason=("PO → payable invoice conversion via create_invoice_from_po()"),
                    metadata={
                        "po_number": po.po_number,
                        "invoice_id": str(invoice.id),
                        "invoice_number": invoice_number,
                        "amount_total": str(po.amount_total),
                        "currency_code": po.currency_code or "",
                        "force_3way_match": bool(force and violations),
                    },
                )
            except Exception as exc:
                # Audit row failure inside the SAVEPOINT cancels the
                # whole conversion. This is intentional: silent audit
                # gaps on financial-commitment endpoints are a P0
                # compliance hazard.
                _log.exception(
                    "Audit log FAILED inside PO→Invoice SAVEPOINT, rolling back invoice (PO %s): %s",
                    po.po_number,
                    exc,
                )
                raise

        _log.info(
            "Created invoice %s from PO %s (project %s)",
            invoice_number,
            po.po_number,
            po.project_id,
        )
        # Typed response - amount_total is coerced to a Decimal-as-string by
        # the schema's before-validator so it never leaks onto the wire as a
        # JSON number (the previous untyped dict did exactly that).
        return POInvoiceCreatedResponse(
            invoice_id=invoice.id,
            invoice_number=invoice_number,
            po_id=po_id,
            po_number=po.po_number,
            amount_total=po.amount_total,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Failed to create invoice from PO %s: %s", po_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to create invoice from purchase order.",
        )


@router.get(
    "/{po_id}/match-status/",
    response_model=POMatchStatusResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def get_po_match_status(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POMatchStatusResponse:
    """3-way match summary (PO ↔ GR ↔ Invoice) per PO line."""
    po = await service.get_po(po_id)
    await verify_project_access(po.project_id, str(user_id), session)
    payload = await service.get_match_status(po_id)
    return POMatchStatusResponse.model_validate(payload)


@router.post(
    "/{po_id}/approve/",
    response_model=POResponse,
    dependencies=[Depends(RequirePermission("procurement.approve"))],
)
async def approve_purchase_order(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POResponse:
    """Approve a draft purchase order so it can be issued (TOP-30 #10).

    Approval commits the amount against the project budget; the PO must be
    approved before it is issued to the vendor.
    """
    existing = await service.get_po(po_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    po = await service.approve_po(po_id, approver_id=str(user_id))
    vendor_names = await _fetch_vendor_names(service.session, [po.vendor_contact_id])
    return _po_to_response(po, vendor_names)


@router.post(
    "/{po_id}/issue/",
    response_model=POResponse,
    dependencies=[Depends(RequirePermission("procurement.issue"))],
)
async def issue_purchase_order(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> POResponse:
    """Issue a purchase order."""
    existing = await service.get_po(po_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    po = await service.issue_po(po_id)
    vendor_names = await _fetch_vendor_names(service.session, [po.vendor_contact_id])
    return _po_to_response(po, vendor_names)


# ── Retainage (Gap F) ────────────────────────────────────────────────────────


@router.post(
    "/{po_id}/release-retainage/",
    response_model=PORetainageReleaseResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("procurement.approve"))],
)
async def release_po_retainage(
    po_id: uuid.UUID,
    body: PORetainageReleaseRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ProcurementService = Depends(_get_service),
) -> PORetainageReleaseResponse:
    """Release withheld retainage on a PO (MANAGER only).

    The release amount must be a positive decimal that does not exceed the
    currently-held balance, and the PO must be issued, partially received or
    completed. Each release is audit-logged and publishes the
    ``procurement.po.retainage_released`` event.
    """
    existing = await service.get_po(po_id)  # 404 + carries project for IDOR
    await verify_project_access(existing.project_id, str(user_id), session)

    try:
        release_amount = Decimal(body.amount)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid release amount: {body.amount!r}",
        ) from exc

    record = await service.release_po_retainage(
        po_id=po_id,
        release_amount=release_amount,
        reason=body.reason,
        user_id=uuid.UUID(str(user_id)) if user_id else None,
    )
    return PORetainageReleaseResponse.model_validate(record)


@router.get(
    "/{po_id}/retainage-releases/",
    response_model=PORetainageReleaseListResponse,
    dependencies=[Depends(RequirePermission("procurement.read"))],
)
async def list_po_retainage_releases(
    po_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: ProcurementService = Depends(_get_service),
) -> PORetainageReleaseListResponse:
    """List the retainage-release audit log for a PO."""
    existing = await service.get_po(po_id)  # 404 + carries project for IDOR
    await verify_project_access(existing.project_id, str(user_id), session)
    releases, total = await service.get_po_retainage_releases(
        po_id=po_id,
        offset=offset,
        limit=limit,
    )
    return PORetainageReleaseListResponse(
        items=[PORetainageReleaseResponse.model_validate(r) for r in releases],
        total=total,
        offset=offset,
        limit=limit,
    )
