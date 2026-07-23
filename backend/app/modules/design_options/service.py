# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design Options service - attach-model and per-option BOQ/cost orchestration.

Business logic for building and pricing alternative design options. Each option
is paired with its OWN bill of quantities so a full set of options can be
compared side by side without one option's numbers bleeding into another's.

The generate flow is the heart of this module and is deliberately assembled from
existing platform services rather than re-implemented:

* the BIM hub owns CAD upload and conversion (this module only links the
  resulting model to an option);
* element matching owns turning a model into confirmed, priced groups
  (this module runs a match session scoped to the option's model, previews it,
  and on confirm applies it into the option's own BOQ via
  ``target_boq_id``);
* the BOQ editor owns the FX-correct money rollup and markups
  (this module totals the option's BOQ through it).

Money, quantity and ratio values are Decimal in Python and are stored on the
option as plain decimal strings (the platform Decimal-as-string contract); no
float ever reaches the option row or the wire. Currencies are never blended: the
rollup runs through the BOQ module's currency-aware totalling, and a mixed
currency BOQ is surfaced as a warning rather than summed blindly.

AI-augmented, human-confirmed: ``generate`` exposes a ``dry_run`` preview that
runs the match and returns the would-be positions and totals WITHOUT writing
anything. Only a non-dry-run call applies the matches and prices the option.
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.design_options.models import DesignOption, DesignOptionSet
from app.modules.design_options.repository import DesignOptionsRepository
from app.modules.design_options.schemas import (
    AttachModelRequest,
    DesignOptionCreate,
    DesignOptionGeneratePreviewLine,
    DesignOptionGenerateRequest,
    DesignOptionGenerateResponse,
    DesignOptionSetCreate,
)

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_VALID_METHODS = ("vector", "lexical", "resources", "llm")

# DIN 276 top-level cost groups (stable key -> default English label). The
# frontend localises the label via t('designOptions.trade.<key>'); the backend
# only stores a stable key and an honest English default, mirroring how the
# conceptual-estimate module keeps ELEMENT_LABELS.
_DIN276_GROUPS: dict[str, str] = {
    "100": "Land",
    "200": "Preparatory measures",
    "300": "Building construction",
    "400": "Building services",
    "500": "External works",
    "600": "Furnishings",
    "700": "Ancillary costs",
    "800": "Financing",
}

# MasterFormat divisions (common subset; unknown divisions fall back to a
# "Division NN" label so nothing is dropped).
_MASTERFORMAT_DIVISIONS: dict[str, str] = {
    "00": "Procurement and contracting",
    "01": "General requirements",
    "02": "Existing conditions",
    "03": "Concrete",
    "04": "Masonry",
    "05": "Metals",
    "06": "Wood, plastics and composites",
    "07": "Thermal and moisture protection",
    "08": "Openings",
    "09": "Finishes",
    "10": "Specialties",
    "11": "Equipment",
    "12": "Furnishings",
    "13": "Special construction",
    "14": "Conveying equipment",
    "21": "Fire suppression",
    "22": "Plumbing",
    "23": "Heating, ventilating and air conditioning",
    "25": "Integrated automation",
    "26": "Electrical",
    "27": "Communications",
    "28": "Electronic safety and security",
    "31": "Earthwork",
    "32": "Exterior improvements",
    "33": "Utilities",
    "34": "Transportation",
    "35": "Waterway and marine construction",
}


# ── Decimal helpers (Decimal-as-string contract) ─────────────────────────────


def _parse_decimal(value: object) -> Decimal:
    """Parse an arbitrary value into a finite Decimal, never raising."""
    try:
        if value is None or value == "":
            return Decimal("0")
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _money_str(value: object) -> str:
    """Render a value as a plain decimal string, guarding non-finite values."""
    dec = value if isinstance(value, Decimal) else _parse_decimal(value)
    if not dec.is_finite():
        return "0"
    return format(dec, "f")


def _cents(value: Decimal) -> Decimal:
    """Quantise a Decimal to two places, half-up (money precision)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _slug(text: str) -> str:
    """Filesystem/JSON-safe stable key from a free-form label."""
    lowered = "".join(ch.lower() if ch.isalnum() else "-" for ch in (text or "").strip())
    parts = [p for p in lowered.split("-") if p]
    return "-".join(parts) or "unclassified"


def _classify_bucket(classification: object, preferred: str) -> tuple[str, str, str]:
    """Map a position classification to a (key, label, system) trade bucket.

    Tries the project's preferred classification standard first, then the other
    supported standards, then a free-form ``trade`` tag, so a project set up for
    DIN 276 still buckets a MasterFormat-coded line sensibly. An unclassified
    line lands in a single ``unclassified`` bucket rather than being dropped.
    """
    codes = classification if isinstance(classification, dict) else {}
    order = [preferred, *[s for s in ("din276", "masterformat", "trade") if s != preferred]]
    for system in order:
        raw = codes.get(system)
        code = str(raw).strip() if raw not in (None, "") else ""
        if not code:
            continue
        if system == "din276":
            first = next((ch for ch in code if ch.isdigit()), "")
            if first and first != "0":
                key = f"{first}00"
                return key, _DIN276_GROUPS.get(key, f"DIN 276 {key}"), "din276"
        elif system == "masterformat":
            digits = "".join(ch for ch in code if ch.isdigit())
            if len(digits) >= 2:
                div = digits[:2]
                return div, _MASTERFORMAT_DIVISIONS.get(div, f"Division {div}"), "masterformat"
        else:  # free-form trade tag
            return _slug(code), code, "trade"
    return "unclassified", "Unclassified", "none"


class DesignOptionsService:
    """Business logic for design-option sets, options and their pricing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DesignOptionsRepository(session)

    # ── Sets ─────────────────────────────────────────────────────────────

    async def create_set(
        self,
        data: DesignOptionSetCreate,
        *,
        created_by: uuid.UUID | None,
    ) -> DesignOptionSet:
        """Create a new design-option set for a project."""
        option_set = DesignOptionSet(
            project_id=data.project_id,
            name=data.name,
            comparison_currency=(data.comparison_currency or "").strip().upper(),
            created_by=created_by,
        )
        option_set = await self.repo.create_set(option_set)
        logger.info("Design-option set created: %s (project=%s)", option_set.name, data.project_id)
        # Re-fetch through a query so the selectin ``options`` relationship is
        # eagerly populated for the response (accessing it on the freshly added
        # instance would otherwise trip an async lazy-load).
        return await self.repo.get_set(option_set.id)  # type: ignore[return-value]

    async def get_set(self, set_id: uuid.UUID) -> DesignOptionSet:
        """Get a set by id or raise 404. Access is gated by the router."""
        option_set = await self.repo.get_set(set_id)
        if option_set is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design-option set not found")
        return option_set

    async def list_sets(self, project_id: uuid.UUID) -> list[DesignOptionSet]:
        """List all sets for a project (newest first)."""
        return await self.repo.list_sets(project_id)

    async def set_baseline(self, option_set: DesignOptionSet, option_id: uuid.UUID) -> DesignOptionSet:
        """Mark one option in the set as the baseline for delta comparison."""
        option = await self.repo.get_option(option_id)
        if option is None or option.set_id != option_set.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option not found in this set")
        await self.repo.update_set_fields(option_set.id, baseline_option_id=option.id)
        await self.session.flush()
        logger.info("Design-option baseline set: set=%s option=%s", option_set.id, option_id)
        return await self.get_set(option_set.id)

    async def delete_set(self, option_set: DesignOptionSet) -> None:
        """Hard-delete a set and, by cascade, all of its options."""
        await self.repo.delete_set(option_set.id)
        logger.info("Design-option set deleted: %s", option_set.id)

    # ── Options ──────────────────────────────────────────────────────────

    async def create_option(self, option_set: DesignOptionSet, data: DesignOptionCreate) -> DesignOption:
        """Create a new empty option inside a set (draft status)."""
        option = DesignOption(
            set_id=option_set.id,
            project_id=option_set.project_id,
            name=data.name,
            sort_order=await self.repo.next_sort_order(option_set.id),
        )
        option = await self.repo.create_option(option)
        logger.info("Design option created: %s (set=%s)", option.name, option_set.id)
        return option

    async def get_option(self, option_id: uuid.UUID) -> DesignOption:
        """Get an option by id or raise 404. Access is gated by the router."""
        option = await self.repo.get_option(option_id)
        if option is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design option not found")
        return option

    async def delete_option(self, option: DesignOption) -> None:
        """Hard-delete a single option."""
        await self.repo.delete_option(option.id)
        logger.info("Design option deleted: %s", option.id)

    async def attach_model(self, option: DesignOption, data: AttachModelRequest) -> DesignOption:
        """Pair an option with a converted BIM model or an existing document.

        Exactly one of ``bim_model_id`` / ``source_document_id`` must be given.
        The BIM hub owns the CAD upload + conversion pipeline (its upload-cad /
        upload / from-document endpoints); this method never re-implements that.
        It links an already-converted model, or records a document to convert,
        applying a cross-project IDOR guard on whatever it links.
        """
        has_model = data.bim_model_id is not None
        has_doc = data.source_document_id is not None
        if has_model == has_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide exactly one of bim_model_id or source_document_id.",
            )

        if has_model:
            from app.modules.bim_hub.models import BIMModel

            model = await self.session.get(BIMModel, data.bim_model_id)
            # Cross-project guard: a model from another project must read as 404
            # (not 403) so option ids cannot be used to probe foreign models.
            if model is None or model.project_id != option.project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BIM model not found")
            meta = dict(option.metadata_ or {})
            meta["attached_model_format"] = getattr(model, "model_format", "") or ""
            meta["attached_element_count"] = int(getattr(model, "element_count", 0) or 0)
            await self.repo.update_option_fields(
                option.id,
                bim_model_id=model.id,
                source_document_id=None,
                status="model_attached",
                error="",
                metadata_=meta,
            )
            logger.info("Design option %s linked to BIM model %s", option.id, model.id)
        else:
            from app.modules.documents.repository import DocumentRepository

            doc = await DocumentRepository(self.session).get_by_id(data.source_document_id)
            if doc is None or doc.project_id != option.project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

            # Adopt an already-converted model when the BIM hub cross-linked one
            # to this document (its from-document idempotency stamp); otherwise
            # record the document and mark the option as awaiting conversion, so
            # the caller runs the BIM hub from-document endpoint and re-attaches
            # the resulting model. No conversion is triggered from here.
            doc_meta = doc.metadata_ if isinstance(doc.metadata_, dict) else {}
            linked_model_id = doc_meta.get("source_id") if doc_meta.get("source_module") == "bim_hub" else None
            fields: dict[str, object] = {"source_document_id": doc.id, "error": ""}
            adopted = False
            if linked_model_id:
                from app.modules.bim_hub.models import BIMModel

                try:
                    model = await self.session.get(BIMModel, uuid.UUID(str(linked_model_id)))
                except (ValueError, TypeError):
                    model = None
                if model is not None and model.project_id == option.project_id:
                    fields["bim_model_id"] = model.id
                    fields["status"] = "model_attached"
                    adopted = True
            if not adopted:
                # Document recorded, no model yet: it must be converted by the
                # BIM hub before the option can be priced.
                fields["status"] = "converting"
            await self.repo.update_option_fields(option.id, **fields)
            logger.info(
                "Design option %s linked to document %s (model adopted=%s)",
                option.id,
                doc.id,
                adopted,
            )

        await self.session.flush()
        return await self.get_option(option.id)

    # ── Generate (match -> preview/apply -> price) ───────────────────────

    async def generate(
        self,
        option: DesignOption,
        req: DesignOptionGenerateRequest,
        *,
        actor_id: uuid.UUID | None,
    ) -> DesignOptionGenerateResponse:
        """Match the option's model, preview it, and on confirm price its BOQ.

        Steps:
            1. Require an attached BIM model.
            2. Ensure the option has its OWN BOQ (create one when ``boq_id`` is
               null). This is what keeps two options from collapsing into one
               shared BOQ: every option carries a distinct ``boq_id`` and the
               apply is always targeted at it.
            3. Ensure a match session scoped to the option's model.
            4. Run the match and auto-confirm the confident groups (skipped on a
               non-dry-run apply when a prior preview already confirmed them).
            5. Preview (``dry_run``) or apply the confirmed groups into the
               option's own BOQ via ``target_boq_id``.
            6. On apply, roll up the option BOQ's direct cost, markups and grand
               total through the BOQ module (FX-correct, currency-aware), compute
               cost per m2 against the project GFA, snapshot the by-trade
               breakdown, and persist the headline strings.
        """
        warnings: list[str] = []

        if option.bim_model_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attach a BIM model to this option before generating its estimate.",
            )

        from app.modules.projects.models import Project

        project = await self.session.get(Project, option.project_id)

        # ── 2. Ensure the option owns its BOQ (anti-collapse invariant) ──
        boq_id = option.boq_id
        if boq_id is None:
            from app.modules.boq.schemas import BOQCreate
            from app.modules.boq.service import BOQService

            option_set = await self.session.get(DesignOptionSet, option.set_id)
            set_name = option_set.name if option_set is not None else "Design options"
            boq_name = f"{set_name} / {option.name or 'Option'}"[:255]
            boq = await BOQService(self.session).create_boq(
                BOQCreate(
                    project_id=option.project_id,
                    name=boq_name,
                    description=f"Priced bill of quantities for design option '{option.name}'.",
                    estimate_type="design_option",
                )
            )
            boq_id = boq.id
            await self.repo.update_option_fields(option.id, boq_id=boq_id)
            option.boq_id = boq_id

        # ── 3. Ensure a match session scoped to the option's model ───────
        from app.modules.match_elements import schemas as match_schemas
        from app.modules.match_elements.service import get_service as get_match_service

        match_service = get_match_service()
        session_id = option.match_session_id
        if session_id is None:
            created = await match_service.create_session(
                self.session,
                match_schemas.SessionCreate(
                    project_id=option.project_id,
                    bim_model_id=option.bim_model_id,
                    source="bim",
                    name=f"Design option: {option.name}"[:255],
                    catalogue_id=req.catalogue_id,
                    catalogue_ids=req.catalogue_ids,
                    auto_confirm_threshold=req.auto_confirm_threshold,
                ),
                created_by=actor_id,
            )
            session_id = created.id
            await self.repo.update_option_fields(option.id, match_session_id=session_id)
            option.match_session_id = session_id

        # ── 4. Match + auto-confirm ──────────────────────────────────────
        # On a dry run always (re)match so the preview reflects the current
        # catalogue. On an apply, reuse the groups a prior preview already
        # confirmed; only match from scratch when the session has neither
        # confirmed nor applied groups (a direct apply with no preview).
        confirmed_count = await self._count_groups(session_id, ("confirmed",))
        applied_count = await self._count_groups(session_id, ("applied",))
        if req.dry_run or (confirmed_count == 0 and applied_count == 0):
            method = (req.method or "vector").strip().lower()
            if method not in _VALID_METHODS:
                method = "vector"
            try:
                await match_service.run_match(
                    self.session,
                    session_id,
                    match_schemas.RunMatchRequest(
                        method=method,
                        # RunMatchRequest caps max_groups at 200 and top_k at 50;
                        # clamp so a larger option-level request never 422s the
                        # inner match call.
                        max_groups=min(req.max_groups, 200),
                        top_k=min(req.top_k, 50),
                    ),
                    actor_id,
                )
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001 - a matcher failure degrades to an empty preview
                logger.warning("Design option %s match run failed", option.id, exc_info=True)
                warnings.append("match_failed")
            await match_service.bulk_confirm(
                self.session,
                session_id,
                match_schemas.BulkConfirmRequest(threshold=req.auto_confirm_threshold),
                actor_id,
            )

        # ── 5. Preview or apply into the option's OWN BOQ ────────────────
        apply_res = await match_service.apply_to_boq(
            self.session,
            session_id,
            match_schemas.ApplyToBoqRequest(dry_run=req.dry_run, target_boq_id=boq_id),
            actor_id,
        )

        groups_total = await self._count_groups(session_id, None)
        groups_confirmed = await self._count_groups(session_id, ("confirmed", "applied"))
        element_count = await self._sum_group_elements(session_id, ("confirmed", "applied"))

        gfa_dec = _parse_decimal(getattr(project, "gross_floor_area", None))
        gfa_str = _money_str(gfa_dec) if gfa_dec > 0 else "0"
        gfa_unit = option.gfa_unit or "m2"

        preview_lines = [
            DesignOptionGeneratePreviewLine(
                group_key=p.group_key,
                description=p.description,
                unit=p.unit,
                quantity=_money_str(_parse_decimal(p.quantity)),
                unit_rate=_money_str(p.unit_rate),
                currency=p.currency or "",
                line_total=_money_str(p.line_total),
                section_path=list(p.section_path or []),
            )
            for p in apply_res.positions
        ]

        # ── 6a. Dry run: report the preview, persist nothing ─────────────
        if req.dry_run:
            direct = _cents(_parse_decimal(apply_res.grand_total))
            currency = (apply_res.currency or getattr(project, "currency", "") or "").upper()
            if gfa_dec > 0:
                cost_per_m2 = _cents(direct / gfa_dec)
            else:
                cost_per_m2 = Decimal("0")
                warnings.append("no_gfa")
            return DesignOptionGenerateResponse(
                option_id=option.id,
                dry_run=True,
                boq_id=boq_id,
                method=req.method,
                status=option.status,
                positions_created=apply_res.positions_created,
                element_count=element_count,
                position_count=len(apply_res.positions),
                groups_total=groups_total,
                groups_confirmed=groups_confirmed,
                direct_cost=_money_str(direct),
                markups_total="0",
                grand_total=_money_str(direct),
                cost_per_m2=_money_str(cost_per_m2),
                gfa=gfa_str,
                gfa_unit=gfa_unit,
                currency=currency,
                breakdown=self._preview_breakdown(apply_res.positions),
                preview=preview_lines,
                warnings=warnings,
            )

        # ── 6b. Apply: authoritative FX-correct rollup + persist ─────────
        from app.modules.boq.service import BOQService, _project_fx_map

        totals = await BOQService(self.session).compute_boq_totals([boq_id])
        totals_row = totals.get(boq_id, {})
        base_currency = (totals_row.get("base_currency") or getattr(project, "currency", "") or "").upper()
        direct = _cents(_parse_decimal(totals_row.get("direct_cost", 0)))
        markups = _cents(_parse_decimal(totals_row.get("markups_total", 0)))
        grand = _cents(_parse_decimal(totals_row.get("grand_total", 0)))
        is_mixed = bool(totals_row.get("is_mixed_currency", False))
        if is_mixed:
            warnings.append("mixed_currency")

        fx_map = _project_fx_map(project)
        breakdown = await self._build_trade_breakdown(boq_id, project, base_currency, fx_map)
        position_count = await self._count_positions(boq_id)

        if gfa_dec > 0:
            cost_per_m2 = _cents(direct / gfa_dec)
        else:
            cost_per_m2 = Decimal("0")
            warnings.append("no_gfa")

        await self.repo.update_option_fields(
            option.id,
            direct_cost=_money_str(direct),
            markups_total=_money_str(markups),
            grand_total=_money_str(grand),
            cost_per_m2=_money_str(cost_per_m2),
            gfa=gfa_str,
            gfa_unit=gfa_unit,
            currency=base_currency,
            element_count=element_count,
            position_count=position_count,
            breakdown=breakdown,
            status="priced",
            error="",
        )
        await self.session.flush()
        logger.info(
            "Design option priced: option=%s boq=%s direct=%s grand=%s %s (mixed=%s)",
            option.id,
            boq_id,
            direct,
            grand,
            base_currency,
            is_mixed,
        )

        return DesignOptionGenerateResponse(
            option_id=option.id,
            dry_run=False,
            boq_id=boq_id,
            method=req.method,
            status="priced",
            positions_created=apply_res.positions_created,
            element_count=element_count,
            position_count=position_count,
            groups_total=groups_total,
            groups_confirmed=groups_confirmed,
            direct_cost=_money_str(direct),
            markups_total=_money_str(markups),
            grand_total=_money_str(grand),
            cost_per_m2=_money_str(cost_per_m2),
            gfa=gfa_str,
            gfa_unit=gfa_unit,
            currency=base_currency,
            is_mixed_currency=is_mixed,
            breakdown=breakdown,
            preview=preview_lines,
            warnings=warnings,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _count_groups(
        self,
        session_id: uuid.UUID,
        statuses: tuple[str, ...] | None,
    ) -> int:
        """Count match groups for a session, optionally filtered by status."""
        from app.modules.match_elements.models import MatchGroup

        stmt = select(func.count(MatchGroup.id)).where(MatchGroup.session_id == session_id)
        if statuses:
            stmt = stmt.where(MatchGroup.status.in_(statuses))
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def _sum_group_elements(
        self,
        session_id: uuid.UUID,
        statuses: tuple[str, ...],
    ) -> int:
        """Sum the BIM element count across a session's groups in the given states."""
        from app.modules.match_elements.models import MatchGroup

        stmt = (
            select(func.coalesce(func.sum(MatchGroup.element_count), 0))
            .where(MatchGroup.session_id == session_id)
            .where(MatchGroup.status.in_(statuses))
        )
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def _count_positions(self, boq_id: uuid.UUID) -> int:
        """Count the positions written into an option's BOQ (flat, no sections)."""
        from app.modules.boq.models import Position

        stmt = select(func.count(Position.id)).where(Position.boq_id == boq_id)
        return int((await self.session.execute(stmt)).scalar() or 0)

    def _preview_breakdown(self, positions: list) -> list[dict]:
        """Group dry-run preview lines into a by-trade snapshot (best effort).

        A preview line carries the resolved classification label as its
        ``section_path`` head rather than the raw code, so preview buckets group
        by that label. The authoritative code-based breakdown is built from real
        positions in :meth:`_build_trade_breakdown` on apply.
        """
        buckets: dict[str, dict] = {}
        for p in positions:
            section_path = list(getattr(p, "section_path", None) or [])
            label = section_path[0] if section_path else "Unclassified"
            key = _slug(label)
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "classification_system": "preview",
                    "cost": Decimal("0"),
                },
            )
            bucket["cost"] += _parse_decimal(getattr(p, "line_total", 0))
        out = [
            {
                "key": b["key"],
                "label": b["label"],
                "classification_system": b["classification_system"],
                "quantity": "0",
                "unit": "",
                "cost": _money_str(_cents(b["cost"])),
            }
            for b in buckets.values()
        ]
        out.sort(key=lambda entry: _parse_decimal(entry["cost"]), reverse=True)
        return out

    async def _build_trade_breakdown(
        self,
        boq_id: uuid.UUID,
        project: object,
        base_currency: str,
        fx_map: dict[str, str],
    ) -> list[dict]:
        """Snapshot the option BOQ's cost per trade in the project base currency.

        Every leaf position is converted into the base currency with the same
        FX-aware helper the BOQ export/rollup uses, then bucketed by
        classification (DIN 276 group, MasterFormat division or free-form trade).
        Each entry carries a dominant unit and its summed quantity (the unit that
        contributes the most cost in the bucket), so the comparison phase can show
        a per-trade quantity without blending m2 and m3. Money and quantity are
        Decimal-as-strings.
        """
        from app.modules.boq.models import Position
        from app.modules.boq.service import _is_section, _leaf_total_base_with_resources

        preferred = (getattr(project, "classification_standard", "") or "din276").strip().lower() or "din276"
        rows = (await self.session.execute(select(Position).where(Position.boq_id == boq_id))).scalars().all()

        buckets: dict[str, dict] = {}
        for pos in rows:
            if _is_section(pos):
                continue
            cost = _leaf_total_base_with_resources(pos, fx_map, base_currency)
            key, label, system = _classify_bucket(getattr(pos, "classification", None), preferred)
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "classification_system": system,
                    "cost": Decimal("0"),
                    "_units": {},
                },
            )
            bucket["cost"] += cost
            unit = (getattr(pos, "unit", "") or "").strip()
            if unit:
                per_unit = bucket["_units"].setdefault(unit, {"qty": Decimal("0"), "cost": Decimal("0")})
                per_unit["qty"] += _parse_decimal(getattr(pos, "quantity", 0))
                per_unit["cost"] += cost

        out: list[dict] = []
        for bucket in buckets.values():
            units = bucket.pop("_units")
            dominant_unit = ""
            dominant_qty = Decimal("0")
            if units:
                dominant_unit = max(units.items(), key=lambda kv: kv[1]["cost"])[0]
                dominant_qty = units[dominant_unit]["qty"]
            out.append(
                {
                    "key": bucket["key"],
                    "label": bucket["label"],
                    "classification_system": bucket["classification_system"],
                    "quantity": _money_str(dominant_qty),
                    "unit": dominant_unit,
                    "cost": _money_str(_cents(bucket["cost"])),
                }
            )
        out.sort(key=lambda entry: _parse_decimal(entry["cost"]), reverse=True)
        return out
