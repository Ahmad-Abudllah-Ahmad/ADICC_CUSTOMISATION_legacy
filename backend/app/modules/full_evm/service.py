# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Full EVM service - advanced Earned Value Management with forecasting.

Stateless service layer.  Extends the basic EVM in the finance module
with ETC, EAC, VAC, TCPI calculations and S-curve data.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.full_evm.models import EVMForecast
from app.modules.full_evm.repository import EVMForecastRepository
from app.modules.full_evm.schemas import EVMForecastCreate

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
QUANTIZE = Decimal("0.01")
# Upper bound for money values. A finite-but-absurd magnitude (e.g. '1e400')
# survives Decimal() and then overflows quantize() in calculate_forecast,
# aborting the whole batch; clamp such inputs to ZERO at the _dec() choke point.
_MONEY_MAX = Decimal("1e15")

# Event published when a freshly-computed forecast breaches a project
# AlertRule. Item #24 (risk/task auto-escalation) subscribes to this - we
# only emit it here; we never auto-escalate.
FORECAST_ALERT_EVENT = "forecast.alert_triggered"

# KPI codes an AlertRule may target against an EVM forecast. The batch job
# resolves each to a comparable Decimal from the forecast + its source
# snapshot metadata, then applies the rule's condition/threshold. Anything
# outside this set is silently ignored (forecasts can only speak to EVM
# metrics - other KPIs are bi_dashboards' job, not ours).
FORECAST_KPI_CODES = frozenset(
    {"cpi", "spi", "eac", "vac", "etc", "tcpi", "eac_over_bac"},
)


def _dec(value: str) -> Decimal:
    """Safely convert a string to a finite, bounded Decimal.

    Returns ZERO for unparseable, non-finite (NaN/Infinity) or absurd-magnitude
    input so a downstream quantize() in calculate_forecast can never raise
    InvalidOperation and abort the whole forecast batch.
    """
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError):
        return ZERO
    if not d.is_finite() or abs(d) >= _MONEY_MAX:
        return ZERO
    return d


@dataclass
class ForecastBreach:
    """A single AlertRule that a forecast breached.

    Carries everything the event payload and the notification need without
    re-querying the rule - stays decoupled from the bi_dashboards ORM.
    """

    rule_id: str
    rule_name: str
    kpi_code: str
    condition: str
    threshold: Decimal
    observed: Decimal
    severity: str
    recipients: list[str]
    channels: list[str]


def _compare(condition: str, observed: Decimal, threshold: Decimal) -> bool:
    """Apply an AlertRule comparison operator.

    Mirrors the operator grammar in ``bi_dashboards.service.evaluate_alert``
    (``above`` / ``below`` / ``equals`` / ``not_equals``); ``changed_by_…``
    needs history we don't track for forecasts, so it never fires here.
    """
    if condition == "above":
        return observed > threshold
    if condition == "below":
        return observed < threshold
    if condition == "equals":
        return observed == threshold
    if condition == "not_equals":
        return observed != threshold
    return False


class EVMService:
    """Business logic for advanced EVM forecasting."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.forecasts = EVMForecastRepository(session)

    async def list_forecasts(
        self,
        *,
        project_id: uuid.UUID | None = None,
    ) -> tuple[list[EVMForecast], int]:
        """List EVM forecasts for a project."""
        return await self.forecasts.list(project_id=project_id)

    async def create_forecast(self, data: EVMForecastCreate) -> EVMForecast:
        """Create an EVM forecast record manually."""
        forecast = EVMForecast(
            project_id=data.project_id,
            forecast_date=data.forecast_date,
            etc_=data.etc,
            eac=data.eac,
            vac=data.vac,
            tcpi=data.tcpi,
            forecast_method=data.forecast_method,
            confidence_range_low=data.confidence_range_low,
            confidence_range_high=data.confidence_range_high,
            notes=data.notes,
            metadata_=data.metadata,
        )
        forecast = await self.forecasts.create(forecast)
        logger.info("EVM forecast created: project=%s date=%s", data.project_id, data.forecast_date)
        return forecast

    async def calculate_forecast(
        self,
        project_id: uuid.UUID,
        forecast_method: str = "cpi",
    ) -> EVMForecast:
        """Calculate EVM forecast from latest finance EVM snapshot.

        Formulas:
            ETC (CPI method)     = (BAC - EV) / CPI
            ETC (SPI*CPI method) = (BAC - EV) / (SPI * CPI)
            EAC                  = AC + ETC
            VAC                  = BAC - EAC
            TCPI                 = (BAC - EV) / (BAC - AC)
        """
        # Get latest EVM snapshot from finance module
        from sqlalchemy import select

        from app.modules.finance.models import EVMSnapshot

        stmt = (
            select(EVMSnapshot)
            .where(EVMSnapshot.project_id == project_id)
            .order_by(EVMSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No EVM snapshots found for this project. Create a snapshot first.",
            )

        bac = _dec(snapshot.bac)
        ev = _dec(snapshot.ev)
        ac = _dec(snapshot.ac)
        cpi = _dec(snapshot.cpi)
        spi = _dec(snapshot.spi)

        # Calculate ETC based on method
        remaining = bac - ev
        if forecast_method == "spi_cpi" and spi != ZERO and cpi != ZERO:
            etc = (remaining / (spi * cpi)).quantize(QUANTIZE, rounding=ROUND_HALF_UP)
        elif cpi != ZERO:
            etc = (remaining / cpi).quantize(QUANTIZE, rounding=ROUND_HALF_UP)
        else:
            etc = remaining

        eac = (ac + etc).quantize(QUANTIZE, rounding=ROUND_HALF_UP)
        vac = (bac - eac).quantize(QUANTIZE, rounding=ROUND_HALF_UP)

        # TCPI = (BAC - EV) / (BAC - AC)
        # Denominator-zero edge case: BAC == AC means the project has already
        # consumed its entire budget. If any work remains (remaining > 0) the
        # true TCPI is mathematically infinite - returning 0 (the previous
        # behaviour) would falsely imply "no effort needed". We store the
        # sentinel "inf" so downstream consumers can render it as
        # "Not Achievable" / unbounded rather than treating it as a healthy 0.
        denominator = bac - ac
        if denominator != ZERO:
            tcpi = (remaining / denominator).quantize(QUANTIZE, rounding=ROUND_HALF_UP)
        elif remaining > ZERO:
            tcpi = None  # rendered as "inf" sentinel in the forecast row below
        else:
            tcpi = ZERO

        # Confidence range: +/- 10% of EAC
        range_factor = Decimal("0.10")
        conf_low = (eac * (1 - range_factor)).quantize(QUANTIZE, rounding=ROUND_HALF_UP)
        conf_high = (eac * (1 + range_factor)).quantize(QUANTIZE, rounding=ROUND_HALF_UP)

        forecast = EVMForecast(
            project_id=project_id,
            forecast_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            etc_=str(etc),
            eac=str(eac),
            vac=str(vac),
            tcpi="inf" if tcpi is None else str(tcpi),
            forecast_method=forecast_method,
            confidence_range_low=str(conf_low),
            confidence_range_high=str(conf_high),
            notes=f"Auto-calculated from snapshot {snapshot.snapshot_date} using {forecast_method}",
            metadata_={
                "source_snapshot_id": str(snapshot.id),
                "source_snapshot_date": snapshot.snapshot_date,
                "bac": str(bac),
                "ev": str(ev),
                "ac": str(ac),
                "cpi": str(cpi),
                "spi": str(spi),
            },
        )
        forecast = await self.forecasts.create(forecast)
        logger.info(
            "EVM forecast calculated: project=%s method=%s EAC=%s",
            project_id,
            forecast_method,
            eac,
        )
        return forecast

    async def get_s_curve_data(
        self,
        project_id: uuid.UUID,
    ) -> dict:
        """Return S-curve data combining EVM snapshots and forecasts."""
        from sqlalchemy import select

        from app.modules.finance.models import EVMSnapshot

        # Fetch all snapshots ordered by date
        snap_stmt = (
            select(EVMSnapshot).where(EVMSnapshot.project_id == project_id).order_by(EVMSnapshot.snapshot_date.asc())
        )
        snap_result = await self.session.execute(snap_stmt)
        snapshots = list(snap_result.scalars().all())

        # Fetch all forecasts ordered by date
        forecasts, _ = await self.forecasts.list(project_id=project_id)

        return {
            "project_id": str(project_id),
            "snapshots": [
                {
                    "date": s.snapshot_date,
                    "pv": s.pv,
                    "ev": s.ev,
                    "ac": s.ac,
                    "bac": s.bac,
                }
                for s in snapshots
            ],
            "forecasts": [
                {
                    "date": f.forecast_date,
                    "eac": f.eac,
                    "etc": f.etc_,
                    "vac": f.vac,
                    "tcpi": f.tcpi,
                    "method": f.forecast_method,
                    "confidence_low": f.confidence_range_low,
                    "confidence_high": f.confidence_range_high,
                }
                for f in sorted(forecasts, key=lambda x: x.forecast_date)
            ],
        }

    # ── Predictive alert evaluation (TOP-30 #19) ────────────────────────────

    async def _load_alert_rules(self, project_id: uuid.UUID) -> list[dict]:
        """Read enabled forecast-relevant AlertRules for a project.

        AlertRule lives in the ``bi_dashboards`` module which this module
        does not own; we read its table directly via raw SQL (the same
        cross-module-decoupled pattern ``project_intelligence.collector``
        uses) rather than importing its service. Project-scoped rules
        (``scope_project_id = pid``) and global rules (NULL scope) both
        apply. Failures degrade to "no rules" so a missing/renamed table
        never breaks forecast computation.
        """
        try:
            rows = (
                await self.session.execute(
                    text(
                        "SELECT id, name, kpi_code, condition, threshold_value, "
                        "       severity, recipients_json, channels_json "
                        "FROM oe_bi_dashboards_alert_rule "
                        "WHERE enabled = TRUE "
                        "  AND (scope_project_id = :pid OR scope_project_id IS NULL)"
                    ),
                    {"pid": str(project_id)},
                )
            ).fetchall()
        except Exception:
            logger.debug("full_evm: could not read alert rules for %s", project_id, exc_info=True)
            return []

        rules: list[dict] = []
        for r in rows:
            kpi = (r[2] or "").strip().lower()
            if kpi not in FORECAST_KPI_CODES:
                continue
            rules.append(
                {
                    "id": str(r[0]),
                    "name": r[1] or kpi,
                    "kpi_code": kpi,
                    "condition": (r[3] or "below").strip().lower(),
                    "threshold": _dec(str(r[4])) if r[4] is not None else ZERO,
                    "severity": (r[5] or "warning").strip().lower(),
                    "recipients": list(r[6] or []),
                    "channels": list(r[7] or []),
                }
            )
        return rules

    def _forecast_kpi_values(self, forecast: EVMForecast) -> dict[str, Decimal]:
        """Resolve every forecast KPI code to a comparable Decimal.

        ``cpi`` / ``spi`` come from the source snapshot stashed in the
        forecast metadata; ``eac`` / ``vac`` / ``etc`` / ``tcpi`` are the
        forecast's own fields. ``eac_over_bac`` is the overrun ratio
        (>1 means the project is forecast to finish over budget). The
        ``tcpi`` "inf" sentinel maps to a large finite Decimal so an
        ``above`` rule still fires on an unachievable to-complete index.
        """
        meta = forecast.metadata_ or {}
        bac = _dec(str(meta.get("bac", "0")))
        eac = _dec(forecast.eac)
        values: dict[str, Decimal] = {
            "cpi": _dec(str(meta.get("cpi", "0"))),
            "spi": _dec(str(meta.get("spi", "0"))),
            "eac": eac,
            "vac": _dec(forecast.vac),
            "etc": _dec(forecast.etc_),
            "eac_over_bac": (eac / bac) if bac != ZERO else ZERO,
        }
        values["tcpi"] = Decimal("9999") if forecast.tcpi == "inf" else _dec(forecast.tcpi)
        return values

    async def evaluate_forecast_against_rules(
        self,
        forecast: EVMForecast,
        project_id: uuid.UUID,
    ) -> list[ForecastBreach]:
        """Return the AlertRules a forecast breaches (empty == healthy).

        Deterministic threshold evaluation - no AI, no side effects. The
        batch job uses this; the unit tests call it directly.
        """
        rules = await self._load_alert_rules(project_id)
        if not rules:
            return []
        kpi_values = self._forecast_kpi_values(forecast)
        breaches: list[ForecastBreach] = []
        for rule in rules:
            observed = kpi_values.get(rule["kpi_code"])
            if observed is None:
                continue
            if _compare(rule["condition"], observed, rule["threshold"]):
                breaches.append(
                    ForecastBreach(
                        rule_id=rule["id"],
                        rule_name=rule["name"],
                        kpi_code=rule["kpi_code"],
                        condition=rule["condition"],
                        threshold=rule["threshold"],
                        observed=observed,
                        severity=rule["severity"],
                        recipients=rule["recipients"],
                        channels=rule["channels"],
                    )
                )
        return breaches

    async def _project_owner_id(self, project_id: uuid.UUID) -> str | None:
        """Look up the project owner - the default alert recipient."""
        try:
            row = (
                await self.session.execute(
                    text("SELECT owner_id FROM oe_projects_project WHERE id = :pid"),
                    {"pid": str(project_id)},
                )
            ).first()
            return str(row[0]) if row and row[0] else None
        except Exception:
            logger.debug("full_evm: owner lookup failed for %s", project_id, exc_info=True)
            return None

    async def _dispatch_alert_notifications(
        self,
        project_id: uuid.UUID,
        forecast: EVMForecast,
        breaches: list[ForecastBreach],
    ) -> None:
        """Send one in-app notification per recipient summarising the breach.

        Recipients are the union of every breached rule's ``recipients_json``;
        when a rule lists none we fall back to the project owner so the alert
        is never silently dropped. Uses the existing ``NotificationService``
        (pref-aware, throttled by the user's own digest settings). Best-effort:
        a notification failure never blocks the forecast batch.
        """
        recipients: set[str] = set()
        for breach in breaches:
            recipients.update(str(r) for r in breach.recipients if r)
        if not recipients:
            owner = await self._project_owner_id(project_id)
            if owner:
                recipients.add(owner)
        if not recipients:
            return

        worst = max(breaches, key=lambda b: _SEVERITY_RANK.get(b.severity, 0))
        kpi_label = worst.kpi_code.upper()
        try:
            from app.modules.notifications.service import NotificationService

            svc = NotificationService(self.session)
            for uid in recipients:
                await svc.create(
                    user_id=uid,
                    notification_type="forecast.alert_triggered",
                    title_key="notifications.forecast.alert.title",
                    body_key="notifications.forecast.alert.body",
                    body_context={
                        "kpi": kpi_label,
                        "observed": str(worst.observed),
                        "threshold": str(worst.threshold),
                        "count": len(breaches),
                    },
                    entity_type="evm_forecast",
                    entity_id=str(forecast.id),
                    action_url=f"/project-intelligence?project_id={project_id}&tab=forecasts",
                    metadata={
                        "severity": worst.severity,
                        "project_id": str(project_id),
                        "breaches": [
                            {
                                "rule_id": b.rule_id,
                                "kpi_code": b.kpi_code,
                                "observed": str(b.observed),
                                "threshold": str(b.threshold),
                            }
                            for b in breaches
                        ],
                    },
                )
        except Exception:
            logger.warning(
                "full_evm: alert notification dispatch failed for project %s",
                project_id,
                exc_info=True,
            )

    async def compute_project_forecasts_batch(
        self,
        project_ids: list[uuid.UUID],
        *,
        forecast_method: str = "cpi",
    ) -> list[dict]:
        """Compute a fresh forecast per project, evaluate alerts, dispatch.

        For each project:
            1. Recompute the forecast from the latest EVM snapshot.
            2. Evaluate it against the project's AlertRules.
            3. On a breach: stamp ``alert_status='triggered'`` + ``triggered_at``,
               publish ``forecast.alert_triggered`` (item #24 consumes it), and
               dispatch in-app notifications to the recipients.

        Projects without a snapshot are skipped (no forecast possible yet).
        Returns a per-project result summary for the job runner / tests.
        Caller owns the transaction - we ``flush`` but never ``commit`` so the
        batch is atomic with whatever drove it.
        """
        results: list[dict] = []
        for pid in project_ids:
            try:
                forecast = await self.calculate_forecast(pid, forecast_method=forecast_method)
            except HTTPException:
                # No snapshot for this project - nothing to forecast yet.
                results.append({"project_id": str(pid), "status": "no_snapshot"})
                continue
            except ArithmeticError:
                # A poisoned stored value (non-finite / overflow -> an
                # InvalidOperation, which is an ArithmeticError) must not abort
                # the whole batch; skip just this project. _dec() guards new
                # inputs - this covers legacy / raw-written rows.
                logger.exception("Forecast computation failed for project %s", pid)
                results.append({"project_id": str(pid), "status": "error"})
                continue

            breaches = await self.evaluate_forecast_against_rules(forecast, pid)
            if not breaches:
                results.append({"project_id": str(pid), "status": "ok", "alerts": 0})
                continue

            worst = max(breaches, key=lambda b: _SEVERITY_RANK.get(b.severity, 0))
            forecast.alert_status = "triggered"
            forecast.triggered_at = datetime.now(UTC)
            # Stash a compact breach summary on the forecast row so the
            # read endpoint can render the alert reason without re-querying
            # the (cross-module) AlertRule table. Sorted worst-first.
            meta = dict(forecast.metadata_ or {})
            meta["alert_breaches"] = [
                {
                    "rule_id": b.rule_id,
                    "rule_name": b.rule_name,
                    "kpi_code": b.kpi_code,
                    "condition": b.condition,
                    "threshold": str(b.threshold),
                    "observed": str(b.observed),
                    "severity": b.severity,
                }
                for b in sorted(
                    breaches,
                    key=lambda b: _SEVERITY_RANK.get(b.severity, 0),
                    reverse=True,
                )
            ]
            meta["alert_severity"] = worst.severity
            forecast.metadata_ = meta
            await self.session.flush()

            event_bus.publish_detached(
                FORECAST_ALERT_EVENT,
                {
                    "project_id": str(pid),
                    "forecast_id": str(forecast.id),
                    "severity": worst.severity,
                    "eac": forecast.eac,
                    "vac": forecast.vac,
                    "tcpi": forecast.tcpi,
                    "breaches": [
                        {
                            "rule_id": b.rule_id,
                            "rule_name": b.rule_name,
                            "kpi_code": b.kpi_code,
                            "condition": b.condition,
                            "threshold": str(b.threshold),
                            "observed": str(b.observed),
                            "severity": b.severity,
                        }
                        for b in breaches
                    ],
                },
                source_module="oe_full_evm",
            )
            await self._dispatch_alert_notifications(pid, forecast, breaches)
            results.append(
                {
                    "project_id": str(pid),
                    "status": "alerted",
                    "alerts": len(breaches),
                    "forecast_id": str(forecast.id),
                    "severity": worst.severity,
                }
            )
        return results

    async def acknowledge_alert(self, forecast_id: uuid.UUID) -> EVMForecast | None:
        """Resolve a triggered/snoozed forecast alert.

        Sets ``alert_status='acknowledged'``. Returns the row (None if the
        forecast does not exist). Caller owns IDOR + the transaction.
        """
        forecast = await self.forecasts.get(forecast_id)
        if forecast is None:
            return None
        forecast.alert_status = "acknowledged"
        await self.session.flush()
        logger.info("EVM forecast alert acknowledged: forecast=%s", forecast_id)
        return forecast

    async def snooze_alert(self, forecast_id: uuid.UUID, hours: int) -> EVMForecast | None:
        """Snooze a forecast alert for ``hours`` from now.

        Sets ``alert_status='snoozed'`` and records the snooze-until time in
        the forecast metadata so the UI can show a countdown. The next batch
        run re-triggers on the same condition; an elapsed snooze becomes a
        fresh trigger then.
        """
        forecast = await self.forecasts.get(forecast_id)
        if forecast is None:
            return None
        snooze_until = datetime.now(UTC) + timedelta(hours=max(1, hours))
        forecast.alert_status = "snoozed"
        meta = dict(forecast.metadata_ or {})
        meta["snoozed_until"] = snooze_until.isoformat()
        forecast.metadata_ = meta
        await self.session.flush()
        logger.info(
            "EVM forecast alert snoozed: forecast=%s until=%s",
            forecast_id,
            snooze_until.isoformat(),
        )
        return forecast


# Severity ranking - higher number == louder. Used to pick the "worst"
# breach when several rules fire on one forecast.
_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
}
