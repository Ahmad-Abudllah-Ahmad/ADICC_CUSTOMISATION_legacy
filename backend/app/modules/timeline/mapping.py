# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure event-to-timeline mapping (no app.* imports, py3.11-testable).

The unified project timeline is built on top of the existing activity-log
store (``oe_activity_log``). A bridge subscriber listens to the in-memory
event bus and persists the *significant* cross-module domain events so the
timeline survives a restart (the event bus itself is in-memory only).

This module is deliberately dependency-free: it imports only the standard
library so it can be unit-tested under Python 3.11 without standing up the
application, a database, or the event bus. Every function is defensive and
never raises - a malformed event must never break the publisher.

Naming contract
---------------
Events follow dot-notation ``{module}.{entity}.{action}`` (see
``app.core.events``), e.g. ``changeorder.approved``, ``rfi.created``,
``schedule.baseline.set``. We treat an event as significant when its name
starts with one of :data:`ALLOWLIST_PREFIXES`. The allowlist is intentionally
narrow so high-volume, low-signal chatter (``boq.position.created``,
``cad.import.progress``, ...) never floods the timeline.
"""

from __future__ import annotations

from typing import Any

# Significant cross-module domain-event prefixes. An event is recorded on the
# project timeline only when its dotted name starts with one of these. Keep
# this list narrow - it is the single knob that controls timeline volume.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "changeorder.",
    "variation.",
    "rfi.",
    "moc.",
    "approval.",
    "ncr.",
    "transmittal.",
    "correspondence.",
    "submittal.",
    "schedule.",
    "delay.",
    "cost.",
    "handover.",
    "inspection.",
    "clash.",
    "budget.",
)

# Common keys an event payload uses to carry the affected entity's id, tried
# in order. ``{module}_id`` is resolved dynamically against the derived module.
_ENTITY_ID_KEYS: tuple[str, ...] = ("id", "entity_id")

# Keys an event payload uses to carry the umbrella project id.
_PROJECT_ID_KEYS: tuple[str, ...] = ("project_id", "projectId")


def is_significant(event_name: str) -> bool:
    """Return True when *event_name* is a significant cross-module event.

    Significance is decided purely from the name prefix against
    :data:`ALLOWLIST_PREFIXES`. Defensive: a non-string or empty name is
    simply not significant (never raises).
    """
    if not event_name or not isinstance(event_name, str):
        return False
    return event_name.startswith(ALLOWLIST_PREFIXES)


def _derive_module(event_name: str) -> str:
    """First dotted token of the event name (the logical module)."""
    return event_name.split(".", 1)[0]


def _derive_entity_type(event_name: str) -> str:
    """Logical entity type for the row.

    Uses the first dotted token, or ``first.second`` when the event has at
    least three tokens (``module.entity.action``) so a richer name like
    ``schedule.baseline.set`` records ``entity_type="schedule.baseline"``
    while a two-token name like ``rfi.created`` records ``entity_type="rfi"``.
    """
    parts = event_name.split(".")
    if len(parts) >= 3:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


def _coerce_id(value: Any) -> str | None:
    """Best-effort coercion of an id-like value to a non-empty string."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    # ints, UUIDs, and anything else with a sensible str() form.
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text or None


def _extract_entity_id(module: str, data: dict[str, Any]) -> str | None:
    """Pull the affected entity id from common payload keys.

    Tries, in order: ``id``, ``{module}_id`` (derived), then ``entity_id``.
    """
    keys: tuple[str, ...] = ("id", f"{module}_id", "entity_id")
    for key in keys:
        if key in data:
            coerced = _coerce_id(data.get(key))
            if coerced is not None:
                return coerced
    return None


def _extract_project_id(data: dict[str, Any]) -> str | None:
    """Pull the umbrella project id from common payload keys."""
    for key in _PROJECT_ID_KEYS:
        if key in data:
            coerced = _coerce_id(data.get(key))
            if coerced is not None:
                return coerced
    return None


def map_event(event_name: str, data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map an event to an activity-log row payload, or None if not significant.

    Returns a dict with the keys ``entity_type``, ``entity_id``, ``action``,
    ``module``, ``parent_entity_type``, ``parent_entity_id`` and ``metadata``
    when the event is significant; otherwise ``None``.

    Derivations:
        module             - first dotted token of the event name.
        entity_type        - first token, or ``first.second`` for 3+ tokens.
        action             - the full event name (verbatim).
        entity_id          - from ``id`` / ``{module}_id`` / ``entity_id``.
        parent_entity_type - ``"project"`` when a project id is present, else
                             ``None``.
        parent_entity_id   - from ``project_id`` / ``projectId``.
        metadata           - a shallow copy of the original payload so the
                             timeline keeps the full event context.

    Defensive: never raises. A non-dict ``data`` is treated as empty.
    """
    if not is_significant(event_name):
        return None

    payload: dict[str, Any] = data if isinstance(data, dict) else {}

    module = _derive_module(event_name)
    entity_type = _derive_entity_type(event_name)
    entity_id = _extract_entity_id(module, payload)
    project_id = _extract_project_id(payload)

    parent_entity_type: str | None = "project" if project_id is not None else None

    # Shallow copy so callers can safely augment without mutating the event.
    metadata: dict[str, Any] = dict(payload)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": event_name,
        "module": module,
        "parent_entity_type": parent_entity_type,
        "parent_entity_id": project_id,
        "metadata": metadata,
    }
