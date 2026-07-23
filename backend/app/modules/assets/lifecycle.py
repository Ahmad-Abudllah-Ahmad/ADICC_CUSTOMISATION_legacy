# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure lifecycle / warranty / maintenance computations.

Everything here is a pure function of an asset's ``asset_info`` blob plus
``today``. No DB, no I/O - so it is trivially unit-tested and reused by
both the per-asset detail view and the portfolio roll-up.

Date convention: all dates are ISO-8601 ``YYYY-MM-DD`` strings (the format
the BIM Hub already persists and the frontend ``<input type="date">``
emits). Anything unparseable is treated as "unknown" rather than raising,
because asset data is filled in incrementally by humans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

__all__ = [
    "WARRANTY_OK",
    "WARRANTY_EXPIRED",
    "WARRANTY_EXPIRING",
    "WARRANTY_UNKNOWN",
    "MAINT_OK",
    "MAINT_DUE",
    "MAINT_OVERDUE",
    "MAINT_UNKNOWN",
    "AssetHealth",
    "parse_iso_date",
    "compute_health",
]

# ── Warranty states ──────────────────────────────────────────────────────────
WARRANTY_OK = "ok"
WARRANTY_EXPIRING = "expiring"
WARRANTY_EXPIRED = "expired"
WARRANTY_UNKNOWN = "unknown"

# ── Maintenance states ───────────────────────────────────────────────────────
MAINT_OK = "ok"
MAINT_DUE = "due"
MAINT_OVERDUE = "overdue"
MAINT_UNKNOWN = "unknown"

# Default lead time for "expiring soon" classification.
DEFAULT_WARRANTY_LEAD_DAYS = 90
# Default lead time before a maintenance due date counts as "due soon".
DEFAULT_MAINT_LEAD_DAYS = 14


def parse_iso_date(value: Any) -> date | None:
    """Parse an ISO-8601 date string into a ``date``.

    Accepts ``YYYY-MM-DD`` and full ``YYYY-MM-DDTHH:MM:SS`` timestamps.
    Returns ``None`` for empty / unparseable input rather than raising -
    asset metadata is human-entered and often partial.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # Strip a trailing 'Z' and split off any time component.
    raw = raw.rstrip("Zz")
    head = raw.split("T", 1)[0].split(" ", 1)[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _days_between(a: date, b: date) -> int:
    """Signed day delta ``b - a`` (positive when ``b`` is in the future)."""
    return (b - a).days


@dataclass(slots=True)
class AssetHealth:
    """Computed operational health for a single asset."""

    warranty_status: str = WARRANTY_UNKNOWN
    warranty_until: str | None = None
    days_to_warranty_expiry: int | None = None  # negative => already expired

    maintenance_status: str = MAINT_UNKNOWN
    next_maintenance_due: str | None = None
    days_to_maintenance: int | None = None
    maintenance_interval_days: int | None = None
    last_serviced: str | None = None

    age_days: int | None = None
    age_years: float | None = None

    service_log_count: int = 0
    # Sortable severity 0-100 so the portfolio list can surface the worst
    # assets first. Higher = needs attention sooner.
    attention_score: int = 0
    issues: list[str] = field(default_factory=list)


def _coerce_int(value: Any) -> int | None:
    """Best-effort int coercion for human-entered interval fields."""
    if value is None or value == "":
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def compute_health(
    asset_info: dict[str, Any] | None,
    *,
    today: date | None = None,
    warranty_lead_days: int = DEFAULT_WARRANTY_LEAD_DAYS,
    maint_lead_days: int = DEFAULT_MAINT_LEAD_DAYS,
) -> AssetHealth:
    """Compute warranty / maintenance / lifecycle health from ``asset_info``.

    Recognised keys (all optional, all human-entered):
      - ``warranty_until``           ISO date
      - ``installation_date`` /
        ``commissioned_at``          ISO date (age basis; first non-empty wins)
      - ``maintenance_interval_days`` int (preventive-maintenance cadence)
      - ``service_log``              list[{date, note, ...}] of past services
      - ``last_serviced``            ISO date (fallback when no service_log)

    The next maintenance date is derived as ``last_service + interval`` when
    both are known, otherwise ``installation + interval``. ``attention_score``
    blends warranty + maintenance urgency so callers can rank a portfolio.
    """
    today = today or date.today()
    info = asset_info or {}
    health = AssetHealth()

    # ── Warranty ──────────────────────────────────────────────────────────
    warranty_until = parse_iso_date(info.get("warranty_until"))
    if warranty_until is not None:
        health.warranty_until = warranty_until.isoformat()
        delta = _days_between(today, warranty_until)
        health.days_to_warranty_expiry = delta
        if delta < 0:
            health.warranty_status = WARRANTY_EXPIRED
            health.issues.append("warranty_expired")
        elif delta <= warranty_lead_days:
            health.warranty_status = WARRANTY_EXPIRING
            health.issues.append("warranty_expiring")
        else:
            health.warranty_status = WARRANTY_OK
    else:
        health.warranty_status = WARRANTY_UNKNOWN

    # ── Age ───────────────────────────────────────────────────────────────
    installed = parse_iso_date(info.get("installation_date")) or parse_iso_date(info.get("commissioned_at"))
    if installed is not None:
        age = _days_between(installed, today)
        if age >= 0:
            health.age_days = age
            health.age_years = round(age / 365.25, 1)

    # ── Maintenance ───────────────────────────────────────────────────────
    interval = _coerce_int(info.get("maintenance_interval_days"))
    health.maintenance_interval_days = interval

    service_log = info.get("service_log")
    last_serviced: date | None = None
    if isinstance(service_log, list) and service_log:
        health.service_log_count = len(service_log)
        # Newest dated entry is the last service.
        dates = [parse_iso_date(e.get("date")) for e in service_log if isinstance(e, dict)]
        dates = [d for d in dates if d is not None]
        if dates:
            last_serviced = max(dates)
    if last_serviced is None:
        last_serviced = parse_iso_date(info.get("last_serviced"))
    if last_serviced is not None:
        health.last_serviced = last_serviced.isoformat()

    if interval is not None:
        basis = last_serviced or installed
        if basis is not None:
            from datetime import timedelta

            next_due = basis + timedelta(days=interval)
            health.next_maintenance_due = next_due.isoformat()
            delta = _days_between(today, next_due)
            health.days_to_maintenance = delta
            if delta < 0:
                health.maintenance_status = MAINT_OVERDUE
                health.issues.append("maintenance_overdue")
            elif delta <= maint_lead_days:
                health.maintenance_status = MAINT_DUE
                health.issues.append("maintenance_due")
            else:
                health.maintenance_status = MAINT_OK
        else:
            # Interval known but no basis date to anchor it.
            health.maintenance_status = MAINT_UNKNOWN
    else:
        health.maintenance_status = MAINT_UNKNOWN

    # ── Attention score (0-100, higher = more urgent) ─────────────────────
    score = 0
    if health.warranty_status == WARRANTY_EXPIRED:
        score += 40
    elif health.warranty_status == WARRANTY_EXPIRING:
        # Ramp 10..30 as expiry approaches.
        d = health.days_to_warranty_expiry or warranty_lead_days
        score += int(10 + 20 * (1 - d / max(warranty_lead_days, 1)))
    if health.maintenance_status == MAINT_OVERDUE:
        score += 45
    elif health.maintenance_status == MAINT_DUE:
        d = health.days_to_maintenance or maint_lead_days
        score += int(10 + 15 * (1 - d / max(maint_lead_days, 1)))
    status = (info.get("operational_status") or "").lower()
    if status in {"decommissioned", "retired"}:
        # A retired/decommissioned asset should not nag for attention -
        # its warranty and maintenance are no longer actionable.
        score = 0
    elif status == "under_maintenance":
        score += 5
    health.attention_score = max(0, min(100, score))

    return health
