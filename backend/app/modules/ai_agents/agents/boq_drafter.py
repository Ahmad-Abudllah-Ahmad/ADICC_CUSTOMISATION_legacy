# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ Drafter - sample agent that drafts a BOQ from a brief.

Tools (declarative - wired into the global registry on import):

* ``search_costs(q, region)``     - proxy over ``costs.matcher.match_cwicr_items``
* ``suggest_assembly(description)`` - looks up the platform-wide
                                    ``AssemblyTemplate`` library
                                    (``assemblies.repository``).
* ``create_position(boq_id, description, unit, qty, unit_rate, currency)``
  - does NOT hit the BOQ tables. Per the architecture guide
  "AI-augmented, human-confirmed", the runner only RETURNS a proposal; the
  user reviews it in the UI before any real position is created. The tool
  just structures the proposal payload.

Data integrity (no-stubs rule): the cost/assembly tools NEVER fabricate
priced rows. If the database is unreachable in the current process (no
async context - e.g. a unit test instantiating a tool directly) the tool
returns an explicit ``{"error": ...}`` observation so the LLM cannot
ground a "real" BOQ proposal on invented money or recipes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.ai_agents.base import (
    Agent,
    FunctionTool,
    global_tool_registry,
    register_agent,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a construction-cost estimator drafting a Bill of Quantities. "
    "Use the available tools to look up real cost rates and assembly recipes, "
    "then propose BOQ positions via create_position. Once the proposal is "
    "complete, reply with a concise markdown summary of the positions for the "
    "user to review. Never invent fictitious unit rates - call search_costs, "
    "and pass the ISO currency code from the match into create_position. If "
    "search_costs returns an error or no matches, say pricing could not be "
    "looked up rather than guessing a rate. Never combine rates of different "
    "currencies into one total."
)


# ── Tool implementations ────────────────────────────────────────────────────


async def _tool_search_costs(q: str, region: str | None = None) -> dict[str, Any]:
    """Query the cost database via ``costs.matcher.match_cwicr_items``.

    Returns up to 5 real catalogue matches, each with its ISO ``currency``
    code. If no DB session can be opened (e.g. a unit test instantiating
    the tool directly), the tool returns an explicit ``{"error": ...}``
    observation rather than a fabricated priced row - the LLM must never
    ground an estimate on invented money (no-stubs / data-integrity rule).
    """
    q_clean = (q or "").strip()
    if not q_clean:
        return {"query": q_clean, "matches": [], "note": "empty query"}

    try:
        from app.database import async_session_factory
        from app.modules.costs.matcher import match_cwicr_items

        async with async_session_factory() as session:
            results = await match_cwicr_items(
                session,
                q_clean,
                top_k=5,
                region=region or None,
            )
        matches = [
            {
                "code": r.code,
                "description": r.description,
                "unit": r.unit,
                "unit_rate": float(r.unit_rate),
                "currency": r.currency,
                "score": float(r.score),
            }
            for r in results
        ]
        return {"query": q_clean, "region": region or "", "matches": matches}
    except Exception as exc:  # pragma: no cover - DB unavailable
        logger.debug("search_costs unavailable: %s", exc)
        return {
            "query": q_clean,
            "region": region or "",
            "matches": [],
            "error": "unavailable",
            "detail": (
                "Cost database is not reachable in this context. No rates "
                "available - do not invent unit rates; report that pricing "
                "could not be looked up."
            ),
        }


async def _tool_suggest_assembly(description: str) -> dict[str, Any]:
    """Suggest a real assembly template that matches ``description``.

    Queries the platform-wide :class:`AssemblyTemplate` library via
    ``assemblies.repository.AssemblyTemplateRepository``. Returns the
    best-matching template (name, category, unit, components,
    classification). If the library is unreachable or has no match the
    tool returns an explicit ``{"suggestion": None}`` / ``{"error": ...}``
    observation - it NEVER fabricates a recipe (no-stubs rule).
    """
    desc = (description or "").strip()
    if not desc:
        return {"description": desc, "suggestion": None, "note": "empty description"}

    try:
        from app.database import async_session_factory
        from app.modules.assemblies.repository import AssemblyTemplateRepository

        async with async_session_factory() as session:
            templates, _total = await AssemblyTemplateRepository(session).list_all(
                q=desc,
                limit=1,
            )
    except Exception as exc:  # pragma: no cover - DB unavailable
        logger.debug("suggest_assembly unavailable: %s", exc)
        return {
            "description": desc,
            "suggestion": None,
            "error": "unavailable",
            "detail": (
                "Assembly template library is not reachable in this context. "
                "No recipe available - do not invent assembly components."
            ),
        }

    if not templates:
        return {
            "description": desc,
            "suggestion": None,
            "note": "no_match",
        }

    tpl = templates[0]
    return {
        "description": desc,
        "suggestion": {
            "name": tpl.name,
            "category": tpl.category,
            "unit": tpl.unit,
            "components": tpl.components or [],
            "classification": tpl.classification or {},
        },
    }


async def _tool_create_position(
    boq_id: str | None = None,
    description: str = "",
    unit: str = "m2",
    qty: float = 0.0,
    unit_rate: float = 0.0,
    currency: str = "",
) -> dict[str, Any]:
    """Build a structured BOQ-position PROPOSAL - NEVER writes the DB.

    Per the architecture guide the runner only returns proposals; the user confirms
    them in the review panel before anything lands in the project.

    ``currency`` carries the ISO 4217 code of ``unit_rate`` - it MUST be
    the same currency the rate came from in ``search_costs`` (money rule:
    a priced proposal without its currency is meaningless, and rates from
    different currencies must never be combined into one total).
    """
    try:
        qty_f = float(qty or 0.0)
    except (TypeError, ValueError):
        qty_f = 0.0
    try:
        rate_f = float(unit_rate or 0.0)
    except (TypeError, ValueError):
        rate_f = 0.0

    currency_code = (currency or "").strip().upper()

    total = round(qty_f * rate_f, 2)
    proposal: dict[str, Any] = {
        "kind": "boq_position_proposal",
        "boq_id": boq_id,
        "description": (description or "").strip(),
        "unit": (unit or "m2").strip(),
        "qty": round(qty_f, 4),
        "unit_rate": round(rate_f, 4),
        "total": total,
        "currency": currency_code,
        # The frontend wires "Apply" to a confirmed POST - not done here.
        "confirmed": False,
    }
    if not currency_code:
        # Surface the gap so the LLM re-calls search_costs for the ISO code
        # instead of silently proposing an un-priced line.
        proposal["warning"] = "missing currency - re-run search_costs and supply the ISO currency code of the unit_rate"
    return proposal


# ── Registration ────────────────────────────────────────────────────────────


def register_boq_drafter() -> None:
    """Idempotent registration of the BOQ-drafter agent and its tools."""
    global_tool_registry.register(
        FunctionTool(
            name="search_costs",
            description=(
                "Look up cost-database items that match a free-form query. "
                "Returns up to 5 candidates with code, description, unit, "
                "unit_rate and currency. Use this before create_position to "
                "avoid inventing rates."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Search query"},
                    "region": {
                        "type": "string",
                        "description": "Optional region code (e.g. DE_BERLIN)",
                    },
                },
                "required": ["q"],
            },
            func=_tool_search_costs,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="suggest_assembly",
            description=(
                "Suggest a real assembly recipe (multi-component template) "
                "from the platform library that matches the description. "
                "Returns the assembly name, category, unit, components and "
                "classification, or suggestion=null when nothing matches. "
                "Never returns a fabricated recipe."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                },
                "required": ["description"],
            },
            func=_tool_suggest_assembly,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="create_position",
            description=(
                "Append a BOQ position PROPOSAL to the run output. This does NOT "
                "modify the project - the user must approve every proposal in the "
                "review panel. Call this once per line item. The 'currency' field "
                "is the ISO 4217 code of the unit_rate (take it from the "
                "search_costs match you used) - never mix rates of different "
                "currencies in one estimate."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "boq_id": {"type": "string"},
                    "description": {"type": "string"},
                    "unit": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit_rate": {"type": "number"},
                    "currency": {
                        "type": "string",
                        "description": "ISO 4217 currency code of unit_rate, e.g. EUR",
                    },
                },
                "required": ["description", "unit", "qty", "unit_rate", "currency"],
            },
            func=_tool_create_position,
        )
    )

    register_agent(
        Agent(
            name="boq_drafter",
            display_name="BOQ Drafter",
            category="estimating",
            icon="calculator",
            tagline="Turn a scope brief into priced BOQ positions",
            description=(
                "Drafts BOQ positions from a free-form brief, grounding rates "
                "in the cost database and suggesting reusable assemblies."
            ),
            example_prompts=[
                "Draft BOQ positions for a 120 m2 single-storey extension: "
                "strip foundations, C30/37 ground slab, blockwork walls and a "
                "timber pitched roof.",
                "Price the groundworks for a 500 m2 warehouse slab including "
                "excavation, hardcore, DPM and a power-floated concrete floor.",
                "Draft the finishes for an office fit-out: suspended ceilings, "
                "carpet tiles and painted plasterboard partitions over 300 m2.",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["search_costs", "suggest_assembly", "create_position"],
        )
    )
