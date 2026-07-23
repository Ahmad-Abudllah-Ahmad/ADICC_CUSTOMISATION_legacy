# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design Options comparison aggregator.

Turns a set of design options into the side-by-side comparison the UI renders:
one column per option, a by-trade delta table, a transparent recommendation and a
set-level fairness banner.

Every option in a set is an alternative design for the SAME project, so the
options share one project base currency and one gross floor area. The aggregator
reads each option's OWN bill of quantities through the BOQ module's
currency-aware rollup (``compute_boq_totals``), so a bill whose lines are priced
in a foreign currency is converted to the project base BEFORE it is summed,
never blended. It then applies ONE uniform factor to present every option in a
single comparison currency. Because that factor is applied equally to every
option, the deltas, the cost-per-m2 ranking and the recommendation are unchanged
by the choice of display currency; the currency only relabels the numbers.

Money, quantity and ratio values are Decimal in Python and leave this module as
plain decimal strings (the platform Decimal-as-string contract); no float ever
reaches the wire. The classification maps, the bucket resolver and the money
helpers are reused from the module service so the live comparison and the
snapshot the generate step persisted bucket identically; the FX conversion and
the leaf-total rollup are reused from the BOQ service so the comparison, the BOQ
list, the export and the tender leveling all report one FX-correct figure.

A single, clearly marked validation hook
(:meth:`DesignOptionComparator._apply_validation_hook`) is where the validation
phase will run the ``design_options`` and ``boq_quality`` rule sets per option
and attach the per-option traffic-light status and rule-level fairness results.
Until then each column reports the option's persisted validation status and the
banner carries the data-driven notices computed here, so the response shape is
already final.
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import Position
from app.modules.boq.service import (
    BOQService,
    _is_section,
    _leaf_total_base_with_resources,
    _project_fx_map,
)
from app.modules.design_options.models import DesignOption, DesignOptionSet
from app.modules.design_options.schemas import (
    DesignOptionColumn,
    DesignOptionComparisonResponse,
    DesignOptionFairness,
    DesignOptionFairnessWarning,
    DesignOptionRecommendation,
    TradeDeltaOptionCell,
    TradeDeltaRow,
)
from app.modules.design_options.service import (
    _cents,
    _classify_bucket,
    _money_str,
    _parse_decimal,
)
from app.modules.projects.models import Project

logger = logging.getLogger(__name__)


def _warn(
    key: str,
    severity: str = "warning",
    context: dict[str, Any] | None = None,
) -> DesignOptionFairnessWarning:
    """Build a fairness notice under the ``designOptions.fairness`` i18n namespace."""
    return DesignOptionFairnessWarning(
        key=f"designOptions.fairness.{key}",
        severity=severity,
        context=context or {},
    )


@dataclass
class _TradeBucket:
    """One trade bucket for one option, cost already in the comparison currency."""

    key: str
    label: str
    system: str
    cost: Decimal
    unit: str
    quantity: Decimal


@dataclass
class _OptionAcc:
    """Working totals for one option column before serialisation to strings.

    All money is in the comparison currency; ``grand`` is held exactly equal to
    ``direct + markups`` so the decomposition always reconciles.
    """

    option: DesignOption
    direct: Decimal
    markups: Decimal
    grand: Decimal
    cost_per_m2: Decimal
    option_gfa: Decimal
    is_mixed: bool
    priced: bool
    position_count: int
    validation_status: str
    delta: Decimal = Decimal("0")
    delta_pct: Decimal | None = None


class DesignOptionComparator:
    """Aggregate a set's options into the side-by-side comparison response."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build(self, option_set: DesignOptionSet) -> DesignOptionComparisonResponse:
        """Build the full comparison for a set.

        Reads each option's own BOQ, rebases every option to one comparison
        currency, computes the per-option columns and by-trade delta rows, picks a
        recommendation and assembles the fairness banner.

        Args:
            option_set: The set to compare. Its ``options`` are eagerly loaded and
                already ordered by ``sort_order`` (selectin relationship).

        Returns:
            The comparison response with money, quantity and ratio values as
            plain decimal strings.
        """
        options = list(option_set.options)

        base_currency, fx_map, preferred, project_gfa = await self._project_context(option_set.project_id)
        requested = (getattr(option_set, "comparison_currency", "") or "").strip().upper()
        comparison_currency, fx_factor, currency_unavailable = self._resolve_comparison_currency(
            requested, base_currency, fx_map
        )

        boq_ids = [o.boq_id for o in options if o.boq_id is not None]
        totals = await self._option_totals(boq_ids)
        positions_by_boq = await self._load_positions(boq_ids)

        # Per-option working totals + per-option trade buckets, both already in
        # the comparison currency.
        columns: list[_OptionAcc] = []
        buckets_by_option: dict[uuid.UUID, dict[str, _TradeBucket]] = {}
        for opt in options:
            row = totals.get(opt.boq_id, {}) if opt.boq_id is not None else {}
            # compute_boq_totals already converts foreign-currency lines to the
            # project base before summing; the uniform factor then presents them
            # in the comparison currency. grand is kept as direct + markups so the
            # column always reconciles regardless of independent cent rounding.
            direct = _cents(_parse_decimal(row.get("direct_cost", 0)) * fx_factor)
            markups = _cents(_parse_decimal(row.get("markups_total", 0)) * fx_factor)
            grand = direct + markups
            is_mixed = bool(row.get("is_mixed_currency", False))

            option_gfa = _parse_decimal(opt.gfa)
            if option_gfa <= 0:
                option_gfa = project_gfa
            cost_per_m2 = _cents(direct / option_gfa) if option_gfa > 0 else Decimal("0")

            positions = positions_by_boq.get(opt.boq_id, []) if opt.boq_id is not None else []
            leaf_count = sum(1 for p in positions if not _is_section(p))
            priced = opt.boq_id is not None and grand > 0

            columns.append(
                _OptionAcc(
                    option=opt,
                    direct=direct,
                    markups=markups,
                    grand=grand,
                    cost_per_m2=cost_per_m2,
                    option_gfa=option_gfa,
                    is_mixed=is_mixed,
                    priced=priced,
                    position_count=leaf_count,
                    validation_status=opt.validation_status or "pending",
                )
            )
            buckets_by_option[opt.id] = self._bucket_positions(positions, base_currency, fx_map, preferred, fx_factor)

        # Baseline and per-option deltas (against the baseline grand total).
        baseline_id = option_set.baseline_option_id
        baseline_col = next((c for c in columns if c.option.id == baseline_id), None)
        baseline_grand = baseline_col.grand if baseline_col is not None else None
        for c in columns:
            if baseline_grand is None:
                continue
            c.delta = _cents(c.grand - baseline_grand)
            c.delta_pct = _cents(c.delta / baseline_grand * Decimal("100")) if baseline_grand > 0 else None

        recommendation = self._recommend(columns)
        fairness_warnings = self._fairness_warnings(
            options, columns, baseline_id, comparison_currency, requested, currency_unavailable
        )

        # ── Validation hook: run design_options + boq_quality per option, and
        #    the cross-option design_options rules over the whole set ──────────
        await self._apply_validation_hook(
            columns,
            fairness_warnings,
            buckets_by_option,
            positions_by_boq,
            comparison_currency,
            currency_unavailable,
            option_set.id,
            option_set.project_id,
        )

        fairness = self._fairness_banner(fairness_warnings)
        by_trade = self._build_by_trade(options, buckets_by_option, baseline_id)

        return DesignOptionComparisonResponse(
            set_id=option_set.id,
            set_name=option_set.name or "",
            comparison_currency=comparison_currency,
            baseline_option_id=baseline_id,
            options=[self._to_column(c, comparison_currency) for c in columns],
            by_trade=by_trade,
            recommendation=recommendation,
            fairness=fairness,
        )

    # ── Project context + comparison currency ────────────────────────────────

    async def _project_context(
        self,
        project_id: uuid.UUID,
    ) -> tuple[str, dict[str, str], str, Decimal]:
        """Resolve the shared project context: base currency, FX map, standard, GFA."""
        project = await self.session.get(Project, project_id)
        base_currency = (getattr(project, "currency", "") or "").strip().upper()
        fx_map = _project_fx_map(project)
        preferred = (getattr(project, "classification_standard", "") or "din276").strip().lower() or "din276"
        project_gfa = _parse_decimal(getattr(project, "gross_floor_area", None))
        return base_currency, fx_map, preferred, project_gfa

    def _resolve_comparison_currency(
        self,
        requested: str,
        base_currency: str,
        fx_map: dict[str, str],
    ) -> tuple[str, Decimal, bool]:
        """Pick the one currency every option is shown in and the factor to reach it.

        The options are first fully rebased to the project base currency by the BOQ
        rollup (never blending). This resolves the single display currency and the
        uniform scalar that converts a project-base amount into it:

        * blank request, or a request equal to the base -> stay in base, factor 1;
        * an unknown base currency -> stay in base (raw sums), flagged unavailable;
        * a request differing from the base with a usable rate -> convert with
          ``1 / rate`` (the project FX rate is base-per-foreign, so its reciprocal
          is foreign-per-base);
        * a request with no usable rate -> stay in base, flagged unavailable.

        Returns ``(comparison_currency, factor, unavailable)`` where
        ``comparison_currency`` always matches the currency the returned numbers are
        actually in, so the label never lies.
        """
        base = (base_currency or "").strip().upper()
        req = (requested or "").strip().upper()
        if not req or req == base:
            return base, Decimal("1"), False
        if not base:
            return base, Decimal("1"), True
        rate = _parse_decimal(fx_map.get(req))
        if rate > 0:
            return req, Decimal("1") / rate, False
        return base, Decimal("1"), True

    # ── Data loads ───────────────────────────────────────────────────────────

    async def _option_totals(self, boq_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
        """Currency-aware direct / markups / grand per option BOQ (project base)."""
        if not boq_ids:
            return {}
        return await BOQService(self.session).compute_boq_totals(boq_ids)

    async def _load_positions(self, boq_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Position]]:
        """Load every position for the option BOQs in one query, grouped by BOQ."""
        grouped: dict[uuid.UUID, list[Position]] = {}
        if not boq_ids:
            return grouped
        rows = (await self.session.execute(select(Position).where(Position.boq_id.in_(boq_ids)))).scalars().all()
        for pos in rows:
            grouped.setdefault(pos.boq_id, []).append(pos)
        return grouped

    # ── By-trade breakdown ───────────────────────────────────────────────────

    def _bucket_positions(
        self,
        positions: list[Position],
        base_currency: str,
        fx_map: dict[str, str],
        preferred: str,
        factor: Decimal,
    ) -> dict[str, _TradeBucket]:
        """Bucket one option's leaf positions by trade, cost in comparison currency.

        Each leaf is converted to the project base with the same FX-aware helper
        the BOQ rollup uses, then scaled by the uniform comparison factor, and
        bucketed by classification (DIN 276 group / MasterFormat division /
        free-form trade) using the shared service resolver so the bucketing matches
        the persisted snapshot. Each bucket reports its dominant unit (the unit that
        contributes the most cost) and that unit's summed quantity, so a per-trade
        quantity can be shown without blending m2 and m3.
        """
        raw: dict[str, dict[str, Any]] = {}
        for pos in positions:
            if _is_section(pos):
                continue
            cost = _leaf_total_base_with_resources(pos, fx_map, base_currency) * factor
            key, label, system = _classify_bucket(getattr(pos, "classification", None), preferred)
            entry = raw.setdefault(
                key,
                {"label": label, "system": system, "cost": Decimal("0"), "units": {}},
            )
            entry["cost"] += cost
            unit = (getattr(pos, "unit", "") or "").strip()
            if unit:
                per_unit = entry["units"].setdefault(unit, {"qty": Decimal("0"), "cost": Decimal("0")})
                per_unit["qty"] += _parse_decimal(getattr(pos, "quantity", 0))
                per_unit["cost"] += cost

        out: dict[str, _TradeBucket] = {}
        for key, entry in raw.items():
            units = entry["units"]
            dominant_unit = ""
            dominant_qty = Decimal("0")
            if units:
                dominant_unit = max(units.items(), key=lambda kv: kv[1]["cost"])[0]
                dominant_qty = units[dominant_unit]["qty"]
            out[key] = _TradeBucket(
                key=key,
                label=entry["label"],
                system=entry["system"],
                cost=_cents(entry["cost"]),
                unit=dominant_unit,
                quantity=dominant_qty,
            )
        return out

    def _build_by_trade(
        self,
        options: list[DesignOption],
        buckets_by_option: dict[uuid.UUID, dict[str, _TradeBucket]],
        baseline_id: uuid.UUID | None,
    ) -> list[TradeDeltaRow]:
        """Pivot the per-option buckets into trade rows, ordered by cost.

        The union of trade keys across all options becomes the rows; each row
        carries the baseline option's quantity and cost plus every option's cell
        (zero where an option has no line in that trade). Rows are ordered by the
        baseline cost then the total cost across options, both descending, so the
        biggest cost drivers surface first.
        """
        order: dict[str, dict[str, Any]] = {}
        for opt in options:
            for key, bucket in buckets_by_option.get(opt.id, {}).items():
                meta = order.setdefault(
                    key,
                    {"label": bucket.label, "system": bucket.system, "total": Decimal("0")},
                )
                meta["total"] += bucket.cost

        baseline_buckets = buckets_by_option.get(baseline_id, {}) if baseline_id is not None else {}

        ranked: list[tuple[Decimal, Decimal, TradeDeltaRow]] = []
        for key, meta in order.items():
            baseline_bucket = baseline_buckets.get(key)
            per_option = [self._trade_cell(opt.id, buckets_by_option.get(opt.id, {}).get(key)) for opt in options]
            row = TradeDeltaRow(
                key=key,
                label=meta["label"],
                classification_system=meta["system"],
                baseline_quantity=_money_str(baseline_bucket.quantity) if baseline_bucket else "0",
                baseline_cost=_money_str(baseline_bucket.cost) if baseline_bucket else "0",
                per_option=per_option,
            )
            baseline_cost = baseline_bucket.cost if baseline_bucket else Decimal("0")
            ranked.append((baseline_cost, meta["total"], row))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked]

    def _trade_cell(self, option_id: uuid.UUID, bucket: _TradeBucket | None) -> TradeDeltaOptionCell:
        """One option's cell in a trade row (zeros when the option lacks that trade)."""
        if bucket is None:
            return TradeDeltaOptionCell(option_id=option_id, quantity="0", unit="", cost="0")
        return TradeDeltaOptionCell(
            option_id=option_id,
            quantity=_money_str(bucket.quantity),
            unit=bucket.unit,
            cost=_money_str(bucket.cost),
        )

    # ── Recommendation ───────────────────────────────────────────────────────

    def _recommend(self, columns: list[_OptionAcc]) -> DesignOptionRecommendation:
        """Pick the recommended option by a transparent, explainable rule.

        Among options that are priced and pass the currency fairness check (their
        own bill does not mix currencies), the lowest cost per m2 wins. When no
        such option carries a cost per m2 (no gross floor area), it falls back to
        the lowest grand total. Confidence is the winner's relative margin over the
        runner-up, so a clear winner reads high and a near-tie reads low.
        """
        priced = [c for c in columns if c.priced and not c.is_mixed]
        by_cost_per_m2 = [c for c in priced if c.cost_per_m2 > 0]

        if by_cost_per_m2:
            candidates, use_area, reason = by_cost_per_m2, True, "designOptions.recommendation.lowestCostPerM2"
        elif priced:
            candidates, use_area, reason = priced, False, "designOptions.recommendation.lowestTotal"
        else:
            return DesignOptionRecommendation(
                option_id=None,
                confidence="0",
                reason_key="designOptions.recommendation.none",
            )

        candidates = sorted(candidates, key=lambda c: c.cost_per_m2 if use_area else c.grand)
        best = candidates[0]
        best_metric = best.cost_per_m2 if use_area else best.grand
        if len(candidates) == 1:
            confidence = Decimal("0.5")
            reason = "designOptions.recommendation.onlyOption"
        else:
            second_metric = candidates[1].cost_per_m2 if use_area else candidates[1].grand
            gap = (second_metric - best_metric) / second_metric if second_metric > 0 else Decimal("0")
            confidence = min(max(gap, Decimal("0")), Decimal("1"))

        return DesignOptionRecommendation(
            option_id=best.option.id,
            confidence=_money_str(_cents(confidence)),
            reason_key=reason,
        )

    # ── Fairness ─────────────────────────────────────────────────────────────

    def _fairness_warnings(
        self,
        options: list[DesignOption],
        columns: list[_OptionAcc],
        baseline_id: uuid.UUID | None,
        comparison_currency: str,
        requested: str,
        currency_unavailable: bool,
    ) -> list[DesignOptionFairnessWarning]:
        """Compute the honest, data-driven notices about the comparison as a whole."""
        warnings: list[DesignOptionFairnessWarning] = []
        priced = [c for c in columns if c.priced]
        unpriced = [c for c in columns if not c.priced]

        if len(options) < 2:
            warnings.append(_warn("singleOption", "info"))
        if baseline_id is None and len(priced) >= 2:
            warnings.append(_warn("noBaseline", "info"))
        if unpriced:
            warnings.append(_warn("unpricedOptions", "warning", {"count": len(unpriced)}))

        mixed = [c for c in columns if c.is_mixed]
        if mixed:
            warnings.append(_warn("mixedCurrencyOption", "warning", {"count": len(mixed)}))
        if currency_unavailable:
            warnings.append(
                _warn(
                    "comparisonCurrencyUnavailable",
                    "warning",
                    {"requested": requested, "used": comparison_currency},
                )
            )

        if any(c.priced and c.option_gfa <= 0 for c in columns):
            warnings.append(_warn("missingGfa", "warning"))
        distinct_gfa = {_money_str(c.option_gfa) for c in priced if c.option_gfa > 0}
        if len(distinct_gfa) > 1:
            warnings.append(_warn("mixedGfa", "info"))

        return warnings

    def _fairness_banner(self, warnings: list[DesignOptionFairnessWarning]) -> DesignOptionFairness:
        """Roll the notices into a traffic-light status (highest severity wins)."""
        if any(w.severity == "error" for w in warnings):
            status = "error"
        elif any(w.severity == "warning" for w in warnings):
            status = "warnings"
        else:
            status = "ok"
        return DesignOptionFairness(status=status, warnings=warnings)

    async def _apply_validation_hook(
        self,
        columns: list[_OptionAcc],
        warnings: list[DesignOptionFairnessWarning],
        buckets_by_option: dict[uuid.UUID, dict[str, _TradeBucket]],
        positions_by_boq: dict[uuid.UUID, list[Position]],
        comparison_currency: str,
        currency_unavailable: bool,
        set_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        """First-class validation: run the rule sets and attach their results.

        Every option's OWN bill is validated through the core engine with the
        ``design_options`` and ``boq_quality`` rule sets, which sets that option's
        traffic-light ``validation_status``; the cross-option ``design_options``
        rules then run once over the whole set and their findings are appended to
        the fairness banner. Validation only augments the read-only comparison, so
        any failure degrades to the option's persisted status and the honest "not
        validated yet" notice rather than breaking the response.
        """
        # Persisted status is the floor; a successful run overwrites it per option.
        for c in columns:
            c.validation_status = c.option.validation_status or "pending"

        try:
            from app.core.i18n import get_locale
            from app.modules.design_options.validators import (
                evaluate_design_option_set,
                to_validation_position,
            )

            try:
                locale = get_locale()
            except Exception:  # noqa: BLE001 - locale is best-effort context only
                locale = ""

            payloads: list[dict[str, Any]] = []
            for c in columns:
                positions = positions_by_boq.get(c.option.boq_id, []) if c.option.boq_id is not None else []
                trades = [
                    {
                        "key": b.key,
                        "label": b.label,
                        "unit": b.unit,
                        "cost": _money_str(b.cost),
                        "quantity": _money_str(b.quantity),
                    }
                    for b in buckets_by_option.get(c.option.id, {}).values()
                ]
                payloads.append(
                    {
                        "id": str(c.option.id),
                        "name": c.option.name or "",
                        # Effective GFA (option's own, or the project fallback P2
                        # already resolved into ``option_gfa``).
                        "gfa": _money_str(c.option_gfa),
                        "priced": c.priced,
                        "is_mixed": c.is_mixed,
                        "grand_total": _money_str(c.grand),
                        "positions": [to_validation_position(p) for p in positions],
                        "trades": trades,
                    }
                )

            outcome = await evaluate_design_option_set(
                payloads,
                {
                    "set_id": str(set_id),
                    "project_id": str(project_id),
                    "comparison_currency": comparison_currency,
                    "currency_unavailable": currency_unavailable,
                    "locale": locale,
                },
            )

            for c in columns:
                status = outcome.per_option_status.get(str(c.option.id))
                if status:
                    c.validation_status = status
            warnings.extend(outcome.fairness)
        except Exception:  # noqa: BLE001 - validation augments; never break the comparison
            logger.warning("design_options comparison validation failed", exc_info=True)

        # If nothing actually validated (rules unregistered or the run failed),
        # keep the honest "not validated yet" notice so the banner never implies a
        # clean pass that never happened.
        priced = [c for c in columns if c.priced]
        if priced and all(c.validation_status in ("pending", "") for c in priced):
            warnings.append(_warn("validationPending", "info"))

    # ── Serialisation ────────────────────────────────────────────────────────

    def _to_column(self, c: _OptionAcc, comparison_currency: str) -> DesignOptionColumn:
        """Serialise one working column to the response shape (money as strings)."""
        return DesignOptionColumn(
            option_id=c.option.id,
            name=c.option.name or "",
            direct_cost=_money_str(c.direct),
            markups_total=_money_str(c.markups),
            grand_total=_money_str(c.grand),
            delta_vs_baseline=_money_str(c.delta),
            delta_pct=_money_str(c.delta_pct) if c.delta_pct is not None else None,
            cost_per_m2=_money_str(c.cost_per_m2),
            gfa=_money_str(c.option_gfa),
            currency=comparison_currency,
            element_count=int(c.option.element_count or 0),
            position_count=c.position_count,
            validation_status=c.validation_status,
        )
