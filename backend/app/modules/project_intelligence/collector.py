# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project state collector - gathers project data from all modules.

Uses raw SQL via session.execute(text(...)) for speed and to avoid
circular imports with other module services. All queries are project-scoped
and run in parallel via asyncio.gather().
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

logger = logging.getLogger(__name__)


# ── State dataclasses ──────────────────────────────────────────────────────


@dataclass
class BOQState:
    """Bill of Quantities domain state."""

    exists: bool = False
    total_items: int = 0
    items_with_zero_price: int = 0
    items_with_zero_quantity: int = 0
    sections_count: int = 0
    resources_linked: int = 0
    resources_total: int = 0
    last_modified: str | None = None
    validation_errors: int = 0
    export_ready: bool = False
    completion_pct: float = 0.0
    # Scope-drift: leaf-position count now vs the captured scope baseline.
    position_count: int = 0
    baseline_position_count: int = 0
    baseline_source: str = "none"


@dataclass
class ScheduleState:
    """Schedule domain state."""

    exists: bool = False
    activities_count: int = 0
    linked_to_boq: bool = False
    has_critical_path: bool = False
    baseline_set: bool = False
    duration_days: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    completion_pct: float = 0.0
    # Real progress signals for the Schedule-health KPI (both 0..100).
    progress_pct: float = 0.0
    baseline_adherence_pct: float = 0.0


@dataclass
class TakeoffState:
    """Takeoff / CAD domain state."""

    files_uploaded: int = 0
    files_processed: int = 0
    formats: list[str] = field(default_factory=list)
    quantities_extracted: int = 0
    linked_to_boq: bool = False
    completion_pct: float = 0.0


@dataclass
class ValidationState:
    """Validation domain state."""

    last_run: str | None = None
    total_errors: int = 0
    critical_errors: int = 0
    warnings: int = 0
    passed_rules: int = 0
    total_rules: int = 0
    completion_pct: float = 0.0
    # Stable aliases for the dashboard Real-time validation widget.
    rules_passed: int = 0
    rules_total: int = 0
    errors: int = 0


@dataclass
class RiskState:
    """Risk register domain state."""

    register_exists: bool = False
    total_risks: int = 0
    high_severity_unmitigated: int = 0
    contingency_set: bool = False
    completion_pct: float = 0.0


@dataclass
class TenderingState:
    """Tendering domain state."""

    bid_packages: int = 0
    bids_received: int = 0
    bids_compared: bool = False
    completion_pct: float = 0.0


@dataclass
class DocumentsState:
    """Documents domain state."""

    total_files: int = 0
    categories_covered: list[str] = field(default_factory=list)
    completion_pct: float = 0.0


@dataclass
class ReportsState:
    """Reports domain state."""

    reports_generated: int = 0
    last_report: str | None = None
    completion_pct: float = 0.0


@dataclass
class CostModelState:
    """5D cost model domain state.

    The ``forecast_*`` fields (TOP-30 #19) carry the latest predictive EVM
    forecast so the dashboard's Cost detail tab and the forecast-gap rule
    can surface a forecast overrun without a second round-trip. They stay
    ``None`` when no forecast has been computed yet.
    """

    budget_set: bool = False
    baseline_exists: bool = False
    actuals_linked: bool = False
    earned_value_active: bool = False
    completion_pct: float = 0.0
    forecast_eac: str | None = None
    forecast_vac: str | None = None
    forecast_alert_active: bool = False


# ── v1.4.6: 4 newly-wired domains ─────────────────────────────────────────
#
# These 4 modules existed but the collector was blind to them - score
# was a partial picture.  Each new dataclass mirrors the shape of the
# pre-existing ones (one ``completion_pct`` for the dashboard, plus the
# few counts the scorer needs to detect "missing" gaps).


@dataclass
class RequirementsState:
    """Requirements & Quality Gates domain state (v1.4.6)."""

    total_sets: int = 0
    total_items: int = 0
    items_linked_to_boq: int = 0
    items_linked_to_bim: int = 0
    gate_pass_rate: float = 0.0
    last_modified: str | None = None
    completion_pct: float = 0.0


@dataclass
class BIMState:
    """BIM Hub domain state (v1.4.6)."""

    models_count: int = 0
    models_ready: int = 0
    elements_total: int = 0
    elements_linked_to_boq: int = 0
    elements_with_validation: int = 0
    last_modified: str | None = None
    completion_pct: float = 0.0


@dataclass
class TasksState:
    """Tasks / defects / inspections domain state (v1.4.6)."""

    total_tasks: int = 0
    open_tasks: int = 0
    overdue_tasks: int = 0
    tasks_linked_to_bim: int = 0
    completion_pct: float = 0.0


@dataclass
class AssembliesState:
    """Assemblies / calculations domain state (v1.4.6)."""

    total_assemblies: int = 0
    project_assemblies: int = 0
    template_assemblies: int = 0
    components_total: int = 0
    completion_pct: float = 0.0


@dataclass
class ProjectState:
    """Complete snapshot of a project's state across all modules."""

    project_id: str = ""
    project_type: str = ""
    project_name: str = ""
    region: str = ""
    standard: str = ""
    currency: str = ""
    created_at: str = ""
    collected_at: str = ""

    boq: BOQState = field(default_factory=BOQState)
    schedule: ScheduleState = field(default_factory=ScheduleState)
    takeoff: TakeoffState = field(default_factory=TakeoffState)
    validation: ValidationState = field(default_factory=ValidationState)
    risk: RiskState = field(default_factory=RiskState)
    tendering: TenderingState = field(default_factory=TenderingState)
    documents: DocumentsState = field(default_factory=DocumentsState)
    reports: ReportsState = field(default_factory=ReportsState)
    cost_model: CostModelState = field(default_factory=CostModelState)
    requirements: RequirementsState = field(default_factory=RequirementsState)
    bim: BIMState = field(default_factory=BIMState)
    tasks: TasksState = field(default_factory=TasksState)
    assemblies: AssembliesState = field(default_factory=AssembliesState)


# ── Collector ──────────────────────────────────────────────────────────────


async def _collect_project_info(
    session: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    """Fetch basic project info."""
    try:
        row = (
            await session.execute(
                text(
                    "SELECT name, region, classification_standard, currency, "
                    "project_type, created_at "
                    "FROM oe_projects_project WHERE id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()
        if row:
            return {
                "name": row[0] or "",
                "region": row[1] or "",
                "standard": row[2] or "",
                "currency": row[3] or "",
                "project_type": row[4] or "",
                "created_at": str(row[5]) if row[5] else "",
            }
    except Exception:
        logger.debug("Could not fetch project info for %s", project_id)
    return {
        "name": "",
        "region": "",
        "standard": "",
        "currency": "",
        "project_type": "",
        "created_at": "",
    }


async def _collect_boq(
    session: AsyncSession,
    project_id: str,
) -> BOQState:
    """Collect BOQ domain state."""
    state = BOQState()
    try:
        # Count BOQs and positions
        boq_rows = (
            await session.execute(
                text("SELECT b.id, b.updated_at FROM oe_boq_boq b WHERE b.project_id = :pid"),
                {"pid": project_id},
            )
        ).fetchall()

        if not boq_rows:
            return state

        state.exists = True
        boq_ids = [str(r[0]) for r in boq_rows]

        # Find latest modification time
        timestamps = [str(r[1]) for r in boq_rows if r[1]]
        if timestamps:
            state.last_modified = max(timestamps)

        # Count positions across all BOQs
        if boq_ids:
            # Build a safe IN clause with bind parameters
            placeholders = ", ".join(f":bid{i}" for i in range(len(boq_ids)))
            params: dict[str, Any] = {f"bid{i}": bid for i, bid in enumerate(boq_ids)}

            pos_stats = (
                await session.execute(
                    text(
                        f"SELECT "
                        f"  COUNT(*) AS total, "
                        f"  SUM(CASE WHEN (unit_rate = '0' OR unit_rate = '0.00' OR unit_rate = '' OR unit_rate IS NULL) AND parent_id IS NOT NULL THEN 1 ELSE 0 END) AS zero_price, "
                        f"  SUM(CASE WHEN (quantity = '0' OR quantity = '0.00' OR quantity = '' OR quantity IS NULL) AND parent_id IS NOT NULL THEN 1 ELSE 0 END) AS zero_qty, "
                        f"  SUM(CASE WHEN parent_id IS NULL THEN 1 ELSE 0 END) AS sections, "
                        f"  SUM(CASE WHEN validation_status = 'errors' THEN 1 ELSE 0 END) AS val_errors "
                        f"FROM oe_boq_position WHERE boq_id IN ({placeholders})"
                    ),
                    params,
                )
            ).first()

            if pos_stats:
                state.total_items = pos_stats[0] or 0
                state.items_with_zero_price = pos_stats[1] or 0
                state.items_with_zero_quantity = pos_stats[2] or 0
                state.sections_count = pos_stats[3] or 0
                state.validation_errors = pos_stats[4] or 0

        # Completion percentage: items with valid prices / total items (excluding sections)
        leaf_items = state.total_items - state.sections_count
        # Leaf-position count is the scope-coverage numerator (real, non-zero
        # for any project with priced rows). Sections are structural, not scope.
        state.position_count = max(0, leaf_items)
        if leaf_items > 0:
            items_ok = leaf_items - max(state.items_with_zero_price, state.items_with_zero_quantity)
            state.completion_pct = max(0.0, min(1.0, items_ok / leaf_items))
        elif state.sections_count > 0:
            state.completion_pct = 0.3  # Has structure but no items

        state.export_ready = (
            state.total_items > 0 and state.items_with_zero_price == 0 and state.items_with_zero_quantity == 0
        )

        # Scope baseline: the leaf-position count this project's scope was
        # frozen at. Resolution order (most authoritative first):
        #   1. Explicit baseline captured into the project's metadata JSONB
        #      (set via POST /scope-baseline/ - persisted, deliberate).
        #   2. The earliest BOQ version snapshot's position count (the natural
        #      "first frozen estimate").
        #   3. The current leaf count (no drift yet - coverage reads 100%).
        baseline, source = await _resolve_scope_baseline(session, project_id, boq_ids, state.position_count)
        state.baseline_position_count = baseline
        state.baseline_source = source

    except Exception:
        logger.debug("Could not collect BOQ state for %s", project_id, exc_info=True)
    return state


def _count_snapshot_positions(snapshot_data: Any) -> int:
    """Count leaf positions inside a BOQ version snapshot's payload.

    Snapshots store ``snapshot_data`` as a JSON blob. We tolerate the two
    shapes seen in the wild: a flat ``{"positions": [...]}`` list, or a
    nested tree under ``positions``/``children``. Section rows (a node that
    carries children) are not counted as scope leaves. Returns 0 for an
    unrecognised shape so a malformed snapshot never poisons the baseline.
    """
    if not isinstance(snapshot_data, dict):
        return 0
    positions = snapshot_data.get("positions")
    if not isinstance(positions, list):
        return 0

    def _walk(nodes: list) -> int:
        leaves = 0
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                leaves += _walk(children)
            else:
                # A node with no children is a leaf. When the snapshot is flat
                # (no nesting at all) every row is a leaf, which is correct.
                leaves += 1
        return leaves

    return _walk(positions)


async def _resolve_scope_baseline(
    session: AsyncSession,
    project_id: str,
    boq_ids: list[str],
    current_leaf_count: int,
) -> tuple[int, str]:
    """Resolve the scope baseline for the scope-coverage metric.

    Returns ``(baseline_count, source)`` where source is one of
    ``metadata`` / ``snapshot`` / ``current``. Read-only and fail-soft:
    any error falls back to the current count so coverage degrades to 100%
    rather than 0% (a missing baseline must never look like total scope loss).
    """
    # 1. Explicit, persisted baseline in the project metadata JSONB.
    try:
        row = (
            await session.execute(
                text("SELECT metadata FROM oe_projects_project WHERE id = :pid"),
                {"pid": project_id},
            )
        ).first()
        meta = row[0] if row else None
        if isinstance(meta, dict):
            pi_meta = meta.get("project_intelligence")
            if isinstance(pi_meta, dict):
                raw = pi_meta.get("scope_baseline_positions")
                if isinstance(raw, (int, float)) and int(raw) > 0:
                    return int(raw), "metadata"
    except Exception:
        logger.debug("scope baseline metadata read failed for %s", project_id, exc_info=True)

    # 2. Earliest BOQ version snapshot across this project's BOQs.
    if boq_ids:
        try:
            placeholders = ", ".join(f":sid{i}" for i in range(len(boq_ids)))
            params: dict[str, Any] = {f"sid{i}": bid for i, bid in enumerate(boq_ids)}
            snap_row = (
                await session.execute(
                    text(
                        f"SELECT snapshot_data FROM oe_boq_snapshot "  # noqa: S608 - placeholders are bound params
                        f"WHERE boq_id IN ({placeholders}) "
                        f"ORDER BY created_at ASC LIMIT 1"
                    ),
                    params,
                )
            ).first()
            if snap_row and snap_row[0] is not None:
                count = _count_snapshot_positions(snap_row[0])
                if count > 0:
                    return count, "snapshot"
        except Exception:
            logger.debug("scope baseline snapshot read failed for %s", project_id, exc_info=True)

    # 3. No baseline captured yet - the current scope is the baseline.
    return current_leaf_count, "current"


async def _collect_schedule(
    session: AsyncSession,
    project_id: str,
) -> ScheduleState:
    """Collect schedule domain state."""
    state = ScheduleState()
    try:
        sched_row = (
            await session.execute(
                text("SELECT id, start_date, end_date FROM oe_schedule_schedule WHERE project_id = :pid LIMIT 1"),
                {"pid": project_id},
            )
        ).first()

        if not sched_row:
            return state

        state.exists = True
        schedule_id = str(sched_row[0])
        state.start_date = sched_row[1]
        state.end_date = sched_row[2]

        # Count activities
        act_row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "  SUM(CASE WHEN dependencies != '[]' AND dependencies IS NOT NULL THEN 1 ELSE 0 END) "
                    "FROM oe_schedule_activity WHERE schedule_id = :sid"
                ),
                {"sid": schedule_id},
            )
        ).first()

        if act_row:
            state.activities_count = act_row[0] or 0
            has_deps = (act_row[1] or 0) > 0
            state.has_critical_path = has_deps

        # Check baseline
        baseline_row = (
            await session.execute(
                text("SELECT COUNT(*) FROM oe_schedule_baseline WHERE schedule_id = :sid"),
                {"sid": schedule_id},
            )
        ).first()
        state.baseline_set = bool(baseline_row and baseline_row[0] > 0)

        # Calculate duration
        if state.start_date and state.end_date:
            try:
                from datetime import date as dt_date

                sd = dt_date.fromisoformat(state.start_date[:10])
                ed = dt_date.fromisoformat(state.end_date[:10])
                state.duration_days = (ed - sd).days
            except (ValueError, TypeError):
                pass

        # Schedule-health signals (drives the dashboard KPI card). We read
        # each activity's planned span + actual progress and compare actual
        # against the time-elapsed planned progress at the data date.
        if state.activities_count > 0:
            await _compute_schedule_health(session, schedule_id, state)

        # Completion estimate
        if state.activities_count > 0:
            pct = 0.3  # base for existing schedule
            if state.has_critical_path:
                pct += 0.2
            if state.baseline_set:
                pct += 0.2
            if state.start_date and state.end_date:
                pct += 0.3
            state.completion_pct = min(1.0, pct)

    except Exception:
        logger.debug("Could not collect schedule state for %s", project_id, exc_info=True)
    return state


async def _compute_schedule_health(
    session: AsyncSession,
    schedule_id: str,
    state: ScheduleState,
) -> None:
    """Compute mean progress and baseline adherence from activity progress.

    * ``progress_pct`` - the mean actual percent-complete across activities.
    * ``baseline_adherence_pct`` - the share of activities whose actual
      progress is at or above the time-elapsed planned progress (i.e. not
      behind schedule). A project where every activity is keeping pace reads
      100; one where every activity lags reads 0.

    Planned progress is the deterministic linear time-elapsed model
    (0% before start, 100% after planned finish). Read-only and fail-soft.
    """
    from app.modules.project_intelligence.forecast import _parse_iso_date

    try:
        rows = (
            await session.execute(
                text(
                    "SELECT s.data_date, a.start_date, a.end_date, a.progress_pct "
                    "FROM oe_schedule_activity a "
                    "JOIN oe_schedule_schedule s ON a.schedule_id = s.id "
                    "WHERE a.schedule_id = :sid"
                ),
                {"sid": schedule_id},
            )
        ).fetchall()
    except Exception:
        logger.debug("schedule health read failed for %s", schedule_id, exc_info=True)
        return

    if not rows:
        return

    from datetime import date as _date

    actuals: list[float] = []
    on_pace = 0
    counted = 0
    for data_date_raw, start_raw, end_raw, prog_raw in rows:
        try:
            actual = float(prog_raw) if prog_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            actual = 0.0
        actual = max(0.0, min(100.0, actual))
        actuals.append(actual)

        sd = _parse_iso_date(start_raw)
        ed = _parse_iso_date(end_raw)
        dd = _parse_iso_date(data_date_raw) or _date.today()
        if sd is None or ed is None or ed <= sd:
            # No dated span to judge adherence against; skip this activity in
            # the adherence ratio (but it still counts toward mean progress).
            continue
        if dd <= sd:
            planned = 0.0
        elif dd >= ed:
            planned = 100.0
        else:
            planned = (dd - sd).days / (ed - sd).days * 100.0
        counted += 1
        # An activity is "on pace" when actual is within 1pp of planned or
        # ahead. The 1pp slack absorbs integer-day rounding noise.
        if actual >= planned - 1.0:
            on_pace += 1

    if actuals:
        state.progress_pct = round(sum(actuals) / len(actuals), 1)
    if counted > 0:
        state.baseline_adherence_pct = round(on_pace / counted * 100.0, 1)
    elif actuals:
        # No activity had a usable span; fall back to mean progress so the KPI
        # is not stuck at zero for a schedule that genuinely has progress.
        state.baseline_adherence_pct = state.progress_pct


async def _collect_takeoff(
    session: AsyncSession,
    project_id: str,
) -> TakeoffState:
    """Collect takeoff / CAD domain state."""
    state = TakeoffState()
    try:
        doc_rows = (
            await session.execute(
                text("SELECT content_type, status FROM oe_takeoff_document WHERE project_id = :pid"),
                {"pid": project_id},
            )
        ).fetchall()

        state.files_uploaded = len(doc_rows)
        if state.files_uploaded == 0:
            return state

        formats_set: set[str] = set()
        processed = 0
        for row in doc_rows:
            if row[0]:
                formats_set.add(row[0])
            if row[1] in ("processed", "completed", "done"):
                processed += 1

        state.files_processed = processed
        state.formats = sorted(formats_set)

        # Count measurements
        meas_row = (
            await session.execute(
                text("SELECT COUNT(*) FROM oe_takeoff_measurement WHERE project_id = :pid"),
                {"pid": project_id},
            )
        ).first()
        state.quantities_extracted = (meas_row[0] or 0) if meas_row else 0

        # Completion
        if state.files_uploaded > 0:
            pct = 0.3  # files uploaded
            if state.files_processed > 0:
                pct += 0.3 * min(1.0, state.files_processed / state.files_uploaded)
            if state.quantities_extracted > 0:
                pct += 0.4
            state.completion_pct = min(1.0, pct)

    except Exception:
        logger.debug("Could not collect takeoff state for %s", project_id, exc_info=True)
    return state


async def _collect_validation(
    session: AsyncSession,
    project_id: str,
) -> ValidationState:
    """Collect validation domain state."""
    state = ValidationState()
    try:
        # Get the latest validation report for this project
        report = (
            await session.execute(
                text(
                    "SELECT created_at, error_count, warning_count, "
                    "  passed_count, total_rules, status "
                    "FROM oe_validation_report "
                    "WHERE project_id = :pid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"pid": project_id},
            )
        ).first()

        if not report:
            return state

        state.last_run = str(report[0]) if report[0] else None
        state.total_errors = report[1] or 0
        state.critical_errors = report[1] or 0  # all errors are treated as critical
        state.warnings = report[2] or 0
        state.passed_rules = report[3] or 0
        state.total_rules = report[4] or 0
        # Stable aliases for the dashboard widget (mirror the canonical fields).
        state.rules_passed = state.passed_rules
        state.rules_total = state.total_rules
        state.errors = state.critical_errors

        # Completion: 1.0 if no critical errors, scaled by passed/total otherwise
        if state.total_rules > 0:
            if state.critical_errors == 0:
                state.completion_pct = 1.0
            else:
                state.completion_pct = max(
                    0.0,
                    min(0.9, state.passed_rules / state.total_rules),
                )
        elif state.last_run:
            state.completion_pct = 0.5  # ran but no rules counted

    except Exception:
        logger.debug("Could not collect validation state for %s", project_id, exc_info=True)
    return state


async def _collect_risk(
    session: AsyncSession,
    project_id: str,
) -> RiskState:
    """Collect risk register domain state."""
    state = RiskState()
    try:
        risk_row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "  SUM(CASE WHEN impact_severity IN ('high', 'very_high', 'critical') "
                    "    AND (mitigation_strategy = '' OR mitigation_strategy IS NULL) "
                    "    THEN 1 ELSE 0 END), "
                    "  SUM(CASE WHEN contingency_plan != '' AND contingency_plan IS NOT NULL "
                    "    THEN 1 ELSE 0 END) "
                    "FROM oe_risk_register WHERE project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()

        if not risk_row or risk_row[0] == 0:
            return state

        state.register_exists = True
        state.total_risks = risk_row[0] or 0
        state.high_severity_unmitigated = risk_row[1] or 0
        state.contingency_set = (risk_row[2] or 0) > 0

        # Completion
        if state.total_risks > 0:
            pct = 0.4  # register exists
            mitigated = state.total_risks - state.high_severity_unmitigated
            pct += 0.4 * (mitigated / state.total_risks)
            if state.contingency_set:
                pct += 0.2
            state.completion_pct = min(1.0, pct)

    except Exception:
        logger.debug("Could not collect risk state for %s", project_id, exc_info=True)
    return state


async def _collect_tendering(
    session: AsyncSession,
    project_id: str,
) -> TenderingState:
    """Collect tendering domain state."""
    state = TenderingState()
    try:
        pkg_row = (
            await session.execute(
                text("SELECT COUNT(*) FROM oe_tendering_package WHERE project_id = :pid"),
                {"pid": project_id},
            )
        ).first()
        state.bid_packages = (pkg_row[0] or 0) if pkg_row else 0

        if state.bid_packages > 0:
            bid_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM oe_tendering_bid b "
                        "JOIN oe_tendering_package p ON b.package_id = p.id "
                        "WHERE p.project_id = :pid"
                    ),
                    {"pid": project_id},
                )
            ).first()
            state.bids_received = (bid_row[0] or 0) if bid_row else 0
            state.bids_compared = state.bids_received >= 2

        # Completion
        if state.bid_packages > 0:
            pct = 0.3
            if state.bids_received > 0:
                pct += 0.4
            if state.bids_compared:
                pct += 0.3
            state.completion_pct = min(1.0, pct)

    except Exception:
        logger.debug("Could not collect tendering state for %s", project_id, exc_info=True)
    return state


async def _collect_documents(
    session: AsyncSession,
    project_id: str,
) -> DocumentsState:
    """Collect documents domain state."""
    state = DocumentsState()
    try:
        # GROUP_CONCAT is SQLite-only; PostgreSQL spells the same aggregate
        # ``string_agg(category, ',')``. Without this branch the query raises
        # "function group_concat does not exist" on PG, which the bare except
        # below swallows - silently returning 0 files / no categories. Detect
        # the dialect from this session's bind (not the global engine, which can
        # differ from the session under test).
        dialect_name = session.bind.dialect.name if session.bind else "sqlite"
        concat = "GROUP_CONCAT(DISTINCT category)" if dialect_name == "sqlite" else "string_agg(DISTINCT category, ',')"
        doc_row = (
            await session.execute(
                text(
                    f"SELECT COUNT(*), {concat} "  # noqa: S608 - concat is a fixed literal, not user input
                    "FROM oe_documents_document WHERE project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()

        if doc_row:
            state.total_files = doc_row[0] or 0
            if doc_row[1]:
                state.categories_covered = [c.strip() for c in str(doc_row[1]).split(",") if c.strip()]

        if state.total_files > 0:
            state.completion_pct = min(1.0, 0.3 + 0.1 * len(state.categories_covered))

    except Exception:
        logger.debug("Could not collect documents state for %s", project_id, exc_info=True)
    return state


async def _collect_reports(
    session: AsyncSession,
    project_id: str,
) -> ReportsState:
    """Collect reports domain state."""
    state = ReportsState()
    try:
        rep_row = (
            await session.execute(
                text("SELECT COUNT(*), MAX(created_at) FROM oe_reporting_generated WHERE project_id = :pid"),
                {"pid": project_id},
            )
        ).first()

        if rep_row:
            state.reports_generated = rep_row[0] or 0
            state.last_report = str(rep_row[1]) if rep_row[1] else None

        if state.reports_generated > 0:
            state.completion_pct = min(1.0, 0.5 + 0.1 * state.reports_generated)

    except Exception:
        logger.debug("Could not collect reports state for %s", project_id, exc_info=True)
    return state


async def _collect_cost_model(
    session: AsyncSession,
    project_id: str,
) -> CostModelState:
    """Collect 5D cost model domain state."""
    state = CostModelState()
    try:
        # Check budget lines
        budget_row = (
            await session.execute(
                text("SELECT COUNT(*) FROM oe_costmodel_budget_line WHERE project_id = :pid"),
                {"pid": project_id},
            )
        ).first()
        has_budget = bool(budget_row and budget_row[0] > 0)
        state.budget_set = has_budget

        # Check EVM snapshots
        snap_row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "  SUM(CASE WHEN actual_cost != '0' AND actual_cost != '' THEN 1 ELSE 0 END), "
                    "  SUM(CASE WHEN earned_value != '0' AND earned_value != '' THEN 1 ELSE 0 END) "
                    "FROM oe_costmodel_snapshot WHERE project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()

        if snap_row and snap_row[0]:
            state.baseline_exists = snap_row[0] > 0
            state.actuals_linked = (snap_row[1] or 0) > 0
            state.earned_value_active = (snap_row[2] or 0) > 0

        # Completion
        pct = 0.0
        if state.budget_set:
            pct += 0.3
        if state.baseline_exists:
            pct += 0.3
        if state.actuals_linked:
            pct += 0.2
        if state.earned_value_active:
            pct += 0.2
        state.completion_pct = min(1.0, pct)

        # Latest predictive EVM forecast (TOP-30 #19). Read directly from
        # the full_evm table - additive, fail-soft. ``alert_status`` of
        # 'triggered' or 'snoozed' means a forecast threshold is currently
        # breached, which the forecast-gap rule turns into a critical gap.
        try:
            fc_row = (
                await session.execute(
                    text(
                        "SELECT eac, vac, alert_status FROM oe_evm_forecast "
                        "WHERE project_id = :pid "
                        "ORDER BY forecast_date DESC, created_at DESC LIMIT 1"
                    ),
                    {"pid": project_id},
                )
            ).first()
            if fc_row:
                state.forecast_eac = str(fc_row[0]) if fc_row[0] is not None else None
                state.forecast_vac = str(fc_row[1]) if fc_row[1] is not None else None
                state.forecast_alert_active = (fc_row[2] or "") in ("triggered", "snoozed")
        except Exception:
            logger.debug("Could not collect EVM forecast for %s", project_id, exc_info=True)

    except Exception:
        logger.debug("Could not collect cost model state for %s", project_id, exc_info=True)
    return state


# ── v1.4.6: 4 newly-wired collectors ──────────────────────────────────────


async def _collect_requirements(
    session: AsyncSession,
    project_id: str,
) -> RequirementsState:
    """Collect Requirements & Quality Gates domain state."""
    state = RequirementsState()
    try:
        # Count sets + items.  Items live under sets, so we join through.
        sets_row = (
            await session.execute(
                text(
                    "SELECT COUNT(DISTINCT s.id), COUNT(i.id), MAX(i.updated_at) "
                    "FROM oe_requirements_set s "
                    "LEFT JOIN oe_requirements_item i "
                    "  ON i.requirement_set_id = s.id "
                    "WHERE s.project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()
        if sets_row:
            state.total_sets = int(sets_row[0] or 0)
            state.total_items = int(sets_row[1] or 0)
            state.last_modified = str(sets_row[2]) if sets_row[2] else None

        if state.total_items > 0:
            # Count items linked to a BOQ position via the FK column.
            linked_boq_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(i.id) FROM oe_requirements_item i "
                        "JOIN oe_requirements_set s "
                        "  ON i.requirement_set_id = s.id "
                        "WHERE s.project_id = :pid "
                        "  AND i.linked_position_id IS NOT NULL"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.items_linked_to_boq = int(linked_boq_row or 0)

            # Count items pinned to BIM elements via the JSON metadata
            # array.  Cross-dialect: we can't use a JSON-array operator
            # so we fall back to LIKE on the serialised JSON which
            # works on both SQLite and PostgreSQL JSON-as-text columns.
            linked_bim_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(i.id) FROM oe_requirements_item i "
                        "JOIN oe_requirements_set s "
                        "  ON i.requirement_set_id = s.id "
                        "WHERE s.project_id = :pid "
                        "  AND CAST(i.metadata AS TEXT) LIKE '%\"bim_element_ids\"%'"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.items_linked_to_bim = int(linked_bim_row or 0)

        # Compute gate pass rate from the most recent gate result per gate.
        gate_row = (
            await session.execute(
                text(
                    "SELECT g.status FROM oe_requirements_gate_result g "
                    "JOIN oe_requirements_set s "
                    "  ON g.requirement_set_id = s.id "
                    "WHERE s.project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).all()
        if gate_row:
            passes = sum(1 for r in gate_row if r[0] == "pass")
            state.gate_pass_rate = round((passes / len(gate_row)) * 100.0, 1)

        # Completion: 0% if no requirements, 50% if at least one set,
        # +25% if any item is linked to BOQ, +25% if gates pass.
        if state.total_sets > 0:
            state.completion_pct = 50.0
            if state.items_linked_to_boq > 0:
                state.completion_pct += 25.0
            if state.gate_pass_rate >= 80.0:
                state.completion_pct += 25.0
    except Exception:
        logger.warning("Could not collect requirements state for %s", project_id, exc_info=True)
    return state


async def _collect_bim(
    session: AsyncSession,
    project_id: str,
) -> BIMState:
    """Collect BIM Hub domain state."""
    state = BIMState()
    try:
        models_row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "       SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END), "
                    "       MAX(updated_at) "
                    "FROM oe_bim_model WHERE project_id = :pid"
                ),
                {"pid": project_id},
            )
        ).first()
        if models_row:
            state.models_count = int(models_row[0] or 0)
            state.models_ready = int(models_row[1] or 0)
            state.last_modified = str(models_row[2]) if models_row[2] else None

        if state.models_count > 0:
            elements_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(e.id) FROM oe_bim_element e "
                        "JOIN oe_bim_model m ON e.model_id = m.id "
                        "WHERE m.project_id = :pid"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.elements_total = int(elements_row or 0)

            linked_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(DISTINCT l.bim_element_id) "
                        "FROM oe_bim_boq_link l "
                        "JOIN oe_bim_element e ON l.bim_element_id = e.id "
                        "JOIN oe_bim_model m ON e.model_id = m.id "
                        "WHERE m.project_id = :pid"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.elements_linked_to_boq = int(linked_row or 0)

        # Completion: scaled by ratio of ready models to total models +
        # bonus if at least one element is BOQ-linked.
        if state.models_count > 0:
            state.completion_pct = (state.models_ready / state.models_count) * 60.0
            if state.elements_linked_to_boq > 0:
                state.completion_pct += 40.0
            state.completion_pct = round(min(100.0, state.completion_pct), 1)
    except Exception:
        logger.warning("Could not collect bim state for %s", project_id, exc_info=True)
    return state


async def _collect_tasks(
    session: AsyncSession,
    project_id: str,
) -> TasksState:
    """Collect tasks / defects / inspections domain state."""
    state = TasksState()
    try:
        # ``due_date`` is a varchar holding an ISO ``YYYY-MM-DD`` string, so we
        # compare it lexicographically against today's ISO date passed as a
        # bound parameter. The previous ``due_date < date('now')`` compared a
        # varchar to a DATE, which raises InvalidDatetimeFormat on PostgreSQL
        # (the v6 default) and silently zeroed the whole tasks domain. ISO
        # date strings sort lexicographically, so string comparison is correct
        # on both PostgreSQL and SQLite.
        from datetime import date as _today_date

        today_iso = _today_date.today().isoformat()
        row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "       SUM(CASE WHEN status IN ('open', 'in_progress', 'draft') "
                    "                THEN 1 ELSE 0 END), "
                    "       SUM(CASE WHEN due_date IS NOT NULL "
                    "                AND due_date != '' "
                    "                AND due_date < :today "
                    "                AND status != 'completed' "
                    "                THEN 1 ELSE 0 END) "
                    "FROM oe_tasks_task WHERE project_id = :pid"
                ),
                {"pid": project_id, "today": today_iso},
            )
        ).first()
        if row:
            state.total_tasks = int(row[0] or 0)
            state.open_tasks = int(row[1] or 0)
            state.overdue_tasks = int(row[2] or 0)

        if state.total_tasks > 0:
            # Tasks linked to BIM via the JSON array column.
            linked_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM oe_tasks_task "
                        "WHERE project_id = :pid "
                        "  AND bim_element_ids IS NOT NULL "
                        "  AND CAST(bim_element_ids AS TEXT) NOT IN ('[]', '')"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.tasks_linked_to_bim = int(linked_row or 0)

        # Completion: 0% if no tasks, otherwise (closed/total) × 100.
        if state.total_tasks > 0:
            closed = state.total_tasks - state.open_tasks
            state.completion_pct = round((closed / state.total_tasks) * 100.0, 1)
    except Exception:
        logger.warning("Could not collect tasks state for %s", project_id, exc_info=True)
    return state


async def _collect_assemblies(
    session: AsyncSession,
    project_id: str,
) -> AssembliesState:
    """Collect assemblies / calculations domain state."""
    state = AssembliesState()
    try:
        # Project-scoped + template assemblies - templates are global
        # but available to every project, so we count both. ``is_template``
        # is a real boolean column; comparing it to the integer ``1`` raises
        # "operator does not exist: boolean = integer" on PostgreSQL (the v6
        # default), which silently zeroed the whole assemblies domain. We use
        # the boolean predicate directly (``is_template`` / ``NOT is_template``)
        # which is valid on both PostgreSQL and SQLite.
        row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "       SUM(CASE WHEN project_id = :pid THEN 1 ELSE 0 END), "
                    "       SUM(CASE WHEN is_template THEN 1 ELSE 0 END) "
                    "FROM oe_assemblies_assembly "
                    "WHERE project_id = :pid OR is_template"
                ),
                {"pid": project_id},
            )
        ).first()
        if row:
            state.total_assemblies = int(row[0] or 0)
            state.project_assemblies = int(row[1] or 0)
            state.template_assemblies = int(row[2] or 0)

        if state.project_assemblies > 0:
            comp_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(c.id) FROM oe_assemblies_component c "
                        "JOIN oe_assemblies_assembly a "
                        "  ON c.assembly_id = a.id "
                        "WHERE a.project_id = :pid"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            state.components_total = int(comp_row or 0)

        # Completion: 50% if at least one project assembly,
        # +50% if it has any components.
        if state.project_assemblies > 0:
            state.completion_pct = 50.0
            if state.components_total > 0:
                state.completion_pct += 50.0
    except Exception:
        logger.warning("Could not collect assemblies state for %s", project_id, exc_info=True)
    return state


# ── Main collector function ────────────────────────────────────────────────


async def _with_own_session(
    collector: Callable[[AsyncSession, str], Awaitable[Any]],
    project_id: str,
) -> Any:
    """Run a ``_collect_*`` coroutine on its own short-lived session.

    Each collector issues several SELECTs; on PostgreSQL one failing
    statement aborts the whole transaction. Sharing a single session
    across the concurrent ``asyncio.gather`` fan-out therefore lets one
    collector's failure poison every sibling. Giving each collector an
    isolated session contains failures and is concurrency-safe.
    """
    async with async_session_factory() as own_session:
        return await collector(own_session, project_id)


async def collect_project_state(
    session: AsyncSession,
    project_id: str,
) -> ProjectState:
    """Collect complete project state across all modules in parallel.

    Args:
        session: Async database session. Retained for API compatibility
            with the router; the per-domain collectors each open their
            own isolated session (see :func:`_with_own_session`) so a
            failing query in one cannot abort the others on PostgreSQL.
        project_id: UUID of the project.

    Returns:
        ProjectState with all domain states populated.
    """
    del session  # collectors use isolated sessions; see _with_own_session
    now = datetime.now(UTC).isoformat()

    # Run all collectors in parallel.  v1.4.6 added the last 4
    # entries (requirements / bim / tasks / assemblies) - the
    # collector was previously blind to these domains so the score
    # was a partial picture and the advisor could not surface gaps
    # like "no requirements defined" or "BIM elements not linked".
    #
    # Each collector gets its OWN short-lived AsyncSession rather than
    # sharing the request-scoped ``session``. An AsyncSession is not
    # safe for concurrent use, and on PostgreSQL (the v6 default) a
    # single failing query inside one collector aborts the shared
    # transaction - every concurrent sibling then dies with
    # InFailedSQLTransactionError, gets swallowed by its broad except,
    # and silently returns an empty default. Isolated sessions keep the
    # parallel fan-out (each session used by exactly one coroutine) and
    # contain any failure to the one collector that hit it.
    results = await asyncio.gather(
        _with_own_session(_collect_project_info, project_id),
        _with_own_session(_collect_boq, project_id),
        _with_own_session(_collect_schedule, project_id),
        _with_own_session(_collect_takeoff, project_id),
        _with_own_session(_collect_validation, project_id),
        _with_own_session(_collect_risk, project_id),
        _with_own_session(_collect_tendering, project_id),
        _with_own_session(_collect_documents, project_id),
        _with_own_session(_collect_reports, project_id),
        _with_own_session(_collect_cost_model, project_id),
        _with_own_session(_collect_requirements, project_id),
        _with_own_session(_collect_bim, project_id),
        _with_own_session(_collect_tasks, project_id),
        _with_own_session(_collect_assemblies, project_id),
        return_exceptions=True,
    )

    # Unpack results, replacing exceptions with defaults
    project_info = results[0] if not isinstance(results[0], Exception) else {}
    boq = results[1] if not isinstance(results[1], Exception) else BOQState()
    schedule = results[2] if not isinstance(results[2], Exception) else ScheduleState()
    takeoff = results[3] if not isinstance(results[3], Exception) else TakeoffState()
    validation = results[4] if not isinstance(results[4], Exception) else ValidationState()
    risk = results[5] if not isinstance(results[5], Exception) else RiskState()
    tendering = results[6] if not isinstance(results[6], Exception) else TenderingState()
    documents = results[7] if not isinstance(results[7], Exception) else DocumentsState()
    reports = results[8] if not isinstance(results[8], Exception) else ReportsState()
    cost_model = results[9] if not isinstance(results[9], Exception) else CostModelState()
    requirements = results[10] if not isinstance(results[10], Exception) else RequirementsState()
    bim = results[11] if not isinstance(results[11], Exception) else BIMState()
    tasks_state = results[12] if not isinstance(results[12], Exception) else TasksState()
    assemblies = results[13] if not isinstance(results[13], Exception) else AssembliesState()

    return ProjectState(
        project_id=project_id,
        project_type=project_info.get("project_type", ""),
        project_name=project_info.get("name", ""),
        region=project_info.get("region", ""),
        standard=project_info.get("standard", ""),
        currency=project_info.get("currency", ""),
        created_at=project_info.get("created_at", ""),
        collected_at=now,
        boq=boq,
        schedule=schedule,
        takeoff=takeoff,
        validation=validation,
        risk=risk,
        tendering=tendering,
        documents=documents,
        reports=reports,
        cost_model=cost_model,
        requirements=requirements,
        bim=bim,
        tasks=tasks_state,
        assemblies=assemblies,
    )
