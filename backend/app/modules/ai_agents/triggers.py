# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI-agent automation: tool catalogue + event-trigger registry (Item 29).

This module is the single source of truth for two things a user-authored
("custom") agent's automation envelope needs:

1. **Tool permission map** - every runner tool has an associated platform
   permission an operator must already hold before that tool can be added to
   a custom agent. We NEVER widen a user's reach through an agent: a viewer who
   cannot write the BOQ cannot build an agent that calls ``create_position``.
   The map is consulted both at setup (``service.set_tools``) and is the
   contract the frontend tool picker renders ("you lack ``boq.write``").

2. **Event-trigger catalogue** - the set of platform events a custom agent may
   subscribe to (e.g. fire when an RFI is created). Storing the subscription is
   implemented now; the actual event-bus wiring that fires the run is a later
   wave (see module docstring of :mod:`app.modules.ai_agents.scheduler`), so the
   catalogue is the stable surface the builder UI lists and validates against.

Both are pure data + small pure helpers - no DB, no I/O - so they import
cheaply from the service, the router and the tests.
"""

from __future__ import annotations

# ── Tool → required-permission map ──────────────────────────────────────────
# Maps a runner tool slug to the platform permission an operator must hold to
# attach it to a custom agent. A tool absent from this map is treated as
# requiring ``ai_agents.run`` (the baseline an agent author already holds), so
# a newly-shipped read-only tool is usable without a code change here, while a
# tool that performs (or proposes) a privileged action MUST be listed with the
# permission of the module it touches.
#
# Note on ``create_position``: the BOQ-drafter tool only structures a PROPOSAL
# (it never writes the DB - the user confirms in the review panel). We still
# gate it on ``boq.create`` so that the *capability to draft BOQ lines* is only
# offered to operators who could create those lines themselves; this keeps the
# permission story honest end to end.
TOOL_PERMISSIONS: dict[str, str] = {
    # BOQ-drafter
    "search_costs": "costs.read",
    "suggest_assembly": "assemblies.read",
    "create_position": "boq.create",
    # estimate-reviewer
    "read_boq": "boq.read",
    "check_boq_quality": "boq.read",
    # cost-classifier
    "classify_item": "costs.read",
    # document-analyst
    "search_documents": "documents.read",
    # project-analyst
    "project_cost_summary": "projects.read",
    # rate-benchmarker
    "benchmark_rate": "costs.read",
}

# The permission required for a tool that is registered with the runner but not
# explicitly mapped above. ``ai_agents.run`` is the right floor: it is exactly
# the permission an agent author already holds, so an unmapped read-only tool is
# usable, while anything privileged is expected to be listed in TOOL_PERMISSIONS.
DEFAULT_TOOL_PERMISSION = "ai_agents.run"


def required_permission_for_tool(tool_name: str) -> str:
    """Return the platform permission needed to attach ``tool_name`` to an agent."""
    return TOOL_PERMISSIONS.get(tool_name, DEFAULT_TOOL_PERMISSION)


# ── Event-trigger catalogue ──────────────────────────────────────────────────
# The events a custom agent may subscribe to. ``name`` is the stable slug stored
# in ``automation.triggers``; ``label`` / ``description`` are English defaults
# the frontend localises. The event-bus subscription that actually fires a
# subscribed agent lives in :mod:`app.modules.ai_agents.events`. A trigger whose
# platform event is wired carries ``available=True``; one whose source event is
# not yet published carries ``available=False`` so the UI can label it "coming
# soon" instead of implying an action that does not yet happen.


class EventTrigger:
    """A platform event a custom agent can be wired to react to."""

    __slots__ = ("name", "label", "description", "available")

    def __init__(self, name: str, label: str, description: str, *, available: bool = False) -> None:
        self.name = name
        self.label = label
        self.description = description
        self.available = available

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "available": self.available,
        }


EVENT_TRIGGERS: tuple[EventTrigger, ...] = (
    EventTrigger(
        "rfi_created",
        "When an RFI is created",
        "Fire the agent with the new RFI as context (e.g. draft a first reply).",
        available=True,
    ),
    EventTrigger(
        "document_uploaded",
        "When a document is uploaded",
        "Fire the agent when a new document lands (e.g. summarise or classify it).",
        available=True,
    ),
    EventTrigger(
        "schedule_variance_recorded",
        "When a schedule variance is recorded",
        "Fire the agent when a programme variance is logged (e.g. draft a delay note).",
    ),
)

VALID_TRIGGER_NAMES: frozenset[str] = frozenset(t.name for t in EVENT_TRIGGERS)


def list_event_triggers() -> list[dict[str, object]]:
    """Return the serialisable event-trigger catalogue for the API/UI."""
    return [t.to_dict() for t in EVENT_TRIGGERS]


def normalise_triggers(names: list[str]) -> list[str]:
    """Keep only known trigger slugs, de-duplicated, in catalogue order.

    Unknown names are dropped rather than rejected so a stale frontend can
    never persist a trigger the backend would silently ignore.
    """
    requested = {str(n).strip() for n in names if str(n).strip()}
    return [t.name for t in EVENT_TRIGGERS if t.name in requested]
