# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure (DB-free) helpers for the unified approvals/alerts inbox.

This module deliberately imports **nothing** from SQLAlchemy or
``app.database`` so the normalise / merge / sort / scope logic can be unit
tested on any Python without a database (mirrors the dashboard module's
"don't break the page" posture and the project's no-DB-import unit-test
rule).

The DB query layer (``inbox.py``) fetches rows from the existing per-module
stores - file-approval steps, change-order approval steps, and the caller's
unread notifications - normalises each into the small ``dict`` shape the
functions here expect, then calls :func:`build_inbox` to produce the final,
deterministically-sorted, project-scoped payload the router returns.

Item shape (one entry in the merged list)::

    {
        "id": str,            # stable per-source id (prefixed by kind)
        "kind": "approval" | "alert",
        "source": str,        # module of origin, e.g. "file_approval"
        "title": str,         # already-resolved English text OR i18n key
        "title_key": str|None,# present for notification-sourced alerts
        "body_context": dict, # interpolation vars for title_key (alerts)
        "project_id": str|None,
        "project_name": str|None,
        "entity_type": str|None,
        "entity_id": str|None,
        "action_url": str|None,
        "severity": "info" | "warning" | "critical",
        "created_at": str|None,  # ISO-8601; drives the sort
    }
"""

from __future__ import annotations

from typing import Any

# Inbox item kinds.
KIND_APPROVAL = "approval"
KIND_ALERT = "alert"

# Severity ranking - higher sorts first when timestamps tie.
_SEVERITY_RANK: dict[str, int] = {"critical": 3, "warning": 2, "info": 1}

# Notification ``notification_type`` substrings that imply a non-info
# severity. Kept here (not in the DB layer) so the mapping is unit-testable.
_CRITICAL_HINTS: tuple[str, ...] = (
    "overdue",
    "rejected",
    "failed",
    "breach",
    "critical",
    "escalat",
)
_WARNING_HINTS: tuple[str, ...] = (
    "due",
    "expiring",
    "pending",
    "reminder",
    "warning",
    "approval",
    "review",
)


def severity_for_notification(notification_type: str | None) -> str:
    """Map a notification ``notification_type`` to an inbox severity.

    Pure string heuristic - critical hints win over warning hints, and the
    default is ``info``. Matching is case-insensitive and substring-based so
    families like ``rfi.overdue`` / ``compliance.doc_expiring`` classify
    without an exhaustive enum.
    """
    nt = (notification_type or "").lower()
    if any(h in nt for h in _CRITICAL_HINTS):
        return "critical"
    if any(h in nt for h in _WARNING_HINTS):
        return "warning"
    return "info"


def normalize_severity(value: str | None) -> str:
    """Clamp an arbitrary string to one of the three known severities."""
    v = (value or "").lower()
    return v if v in _SEVERITY_RANK else "info"


def sort_inbox_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return items sorted newest-first, breaking ties by severity then id.

    Deterministic: equal ``(created_at, severity)`` rows fall back to ``id``
    so the order is stable across calls (important for the ETag-style cache
    the frontend relies on and for snapshot-free tests).
    """

    def key(it: dict[str, Any]) -> tuple[str, int, str]:
        created = it.get("created_at") or ""
        sev = _SEVERITY_RANK.get(normalize_severity(it.get("severity")), 1)
        return (str(created), sev, str(it.get("id") or ""))

    # Newest first (created desc), highest severity first, then id desc for
    # a fully deterministic tiebreak.
    return sorted(items, key=key, reverse=True)


def scope_items_to_projects(
    items: list[dict[str, Any]],
    accessible_project_ids: set[str] | None,
) -> list[dict[str, Any]]:
    """Drop any item tied to a project the caller cannot access.

    IDOR posture (mirrors :func:`app.dependencies.accessible_project_ids`):

    * ``accessible_project_ids is None`` -> caller is an admin / unscoped;
      keep everything.
    * otherwise keep an item when EITHER it carries no ``project_id`` (a
      user-global alert, e.g. a system notification) OR its ``project_id`` is
      in the accessible set. An item whose ``project_id`` is set but NOT in
      the set is silently dropped - never surfaced, never an error.

    A user-global alert (no project) is always the caller's own row (the DB
    layer only ever fetches notifications for ``user_id == caller``), so
    keeping it does not leak anything cross-tenant.
    """
    if accessible_project_ids is None:
        return list(items)
    out: list[dict[str, Any]] = []
    for it in items:
        pid = it.get("project_id")
        if not pid or str(pid) in accessible_project_ids:
            out.append(it)
    return out


def build_inbox(
    approvals: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    *,
    accessible_project_ids: set[str] | None,
    limit: int = 50,
) -> dict[str, Any]:
    """Merge, scope, sort and cap the two streams into the inbox payload.

    Parameters
    ----------
    approvals, alerts:
        Pre-normalised item dicts (see module docstring for the shape).
    accessible_project_ids:
        Project ids the caller may see, or ``None`` for admin/unscoped.
        Used as a defence-in-depth second filter even though the DB layer
        already scopes its queries - so a future caller can't accidentally
        feed unscoped rows in.
    limit:
        Maximum number of items in the returned ``items`` list (the counts
        reflect the full, pre-cap scoped totals).

    Returns
    -------
    dict with::

        {
            "items": [...],            # capped, sorted (newest first)
            "total": int,              # scoped count across both streams
            "approvals_count": int,    # scoped pending-approval count
            "alerts_count": int,       # scoped alert count
        }
    """
    safe_limit = max(0, int(limit))
    scoped_approvals = scope_items_to_projects(approvals, accessible_project_ids)
    scoped_alerts = scope_items_to_projects(alerts, accessible_project_ids)

    merged = sort_inbox_items([*scoped_approvals, *scoped_alerts])

    return {
        "items": merged[:safe_limit],
        "total": len(scoped_approvals) + len(scoped_alerts),
        "approvals_count": len(scoped_approvals),
        "alerts_count": len(scoped_alerts),
    }


__all__ = [
    "KIND_ALERT",
    "KIND_APPROVAL",
    "build_inbox",
    "normalize_severity",
    "scope_items_to_projects",
    "severity_for_notification",
    "sort_inbox_items",
]
