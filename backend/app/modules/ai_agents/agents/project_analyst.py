# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project Analyst - summarizes a project's budget vs committed vs actual.

The agent produces a concise executive cost summary for one project: total
budget, committed, actual, the variance of committed/actual against budget, and
the percentage spent. The user normally just asks "how is this project tracking
against budget?" - the project id comes from the run context (the project the
user is looking at), or can be pasted into the prompt.

Tool (declarative - wired into the global registry on import):

* ``project_cost_summary(project_id=None, __agent_context__=None)`` - reads the
  REAL 5D cost dashboard for the project via
  ``costmodel.service.CostModelService.get_dashboard`` (the same aggregation the
  ``GET /5d/{project_id}/dashboard`` endpoint serves) and the project's name +
  base currency via ``projects.repository.ProjectRepository.get_by_id``. When no
  ``project_id`` is passed it is taken from ``__agent_context__``.

Data integrity (no-stubs rule): the tool reads real budget-line aggregates. If
no DB session can be opened, the project does not exist, or no project id is
available, it returns an explicit ``{"error": ...}`` observation so the LLM can
never invent figures.

Access control (IDOR defence): the run's invoking user is threaded into the
tool via the trusted ``__agent_context__`` (the runner strips any LLM-forged
context and re-injects the real one). Before reading any figures the tool
verifies that user owns or belongs to the target project via
:func:`._access.assert_user_can_access_project`; on denial - or when no user is
in scope - it returns the ``not_found`` / ``unavailable`` error shape so the
LLM never reads another tenant's cost data and existence is never leaked.

Money rule: amounts are carried as Decimal-as-string with their ISO 4217
currency code. The dashboard sets ``mixed_currency`` when the project's budget
lines span more than one currency (a missing fx_rate may have left a foreign
amount unconverted and silently blended into the totals). When that flag is set,
the tool does NOT compute a blended variance across currencies - it surfaces a
clear warning and returns the raw per-aggregate sums so the model presents the
currencies separately instead of trusting a fictitious combined total.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.ai_agents.agents._access import (
    assert_user_can_access_project,
    coerce_user_id,
)
from app.modules.ai_agents.base import (
    Agent,
    FunctionTool,
    global_tool_registry,
    register_agent,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a construction cost controller writing a concise executive summary "
    "of how a project is tracking against budget. Always start by calling "
    "project_cost_summary to load the real figures (the project id comes from "
    "the run context when the user does not paste one). Then write a short, "
    "plain summary covering: total budget, committed, actual, the variance of "
    "committed and actual against budget, and the percentage of budget spent "
    "(actual / budget). Quote every amount with its ISO currency code.\n\n"
    "Never invent or estimate figures: report only what the tool returns. If the "
    "tool reports mixed_currency=true, the project's budget lines span more than "
    "one currency, so a single combined total or variance would be meaningless. "
    "In that case state clearly that the project mixes currencies, present the "
    "amounts as-returned with a warning that they should not be read as one "
    "blended total, and do NOT compute a cross-currency variance. If the tool "
    "returns an error (no project, unreachable data, or no project id), say so "
    "plainly and stop rather than guessing."
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _to_decimal(value: Any) -> Decimal:
    """Parse a value into an exact Decimal, defaulting to 0 on bad input.

    Money round-trips as Decimal-as-string throughout the cost model, so we
    parse straight to Decimal rather than via float to keep the figures exact.
    """
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _money_str(value: Decimal) -> str:
    """Render a Decimal money amount as a plain, locale-neutral string.

    Mirrors the cost-model schema's ``_serialise_money`` contract (fixed-point,
    no exponent) so the figure the LLM sees matches what the dashboard endpoint
    emits.
    """
    if not value.is_finite():
        return "0"
    return format(value, "f")


def _resolve_project_id(project_id: str | None, context: dict | None) -> str:
    """Pick the project id from the explicit arg, else the run context.

    Returns an empty string when neither source supplies one so the caller can
    surface a ``missing_project`` error instead of querying with a blank id.
    """
    raw = (project_id or "").strip()
    if raw:
        return raw
    if isinstance(context, dict):
        ctx_pid = context.get("project_id")
        if ctx_pid not in (None, ""):
            return str(ctx_pid).strip()
    return ""


# ── Tool implementation ───────────────────────────────────────────────────


async def _tool_project_cost_summary(
    project_id: str | None = None,
    __agent_context__: dict | None = None,
) -> dict[str, Any]:
    """Summarize a project's budget vs committed vs actual from real data.

    Reads the project's 5D cost dashboard via
    ``CostModelService.get_dashboard`` and the project name + base currency via
    ``ProjectRepository.get_by_id``. When ``project_id`` is omitted it is taken
    from ``__agent_context__`` (the project the user is currently looking at).

    Returns a dict with the project name, ISO currency, ``total_budget``,
    ``committed``, ``actual`` (all Decimal-as-string), the ``mixed_currency``
    flag, and - only when the project is single-currency - the
    ``committed_vs_budget`` / ``actual_vs_budget`` variances and the
    ``percent_spent``. When ``mixed_currency`` is true a ``warning`` is included
    and no blended variance is computed (money rule: never combine currencies).
    On a missing project id, a missing project, or an unreachable database it
    returns ``{"error": ...}`` so the LLM never fabricates figures.
    """
    # The trusted invoking user is threaded into __agent_context__ by the
    # runner (the LLM cannot forge it - any model-supplied context is stripped
    # and the real one re-injected). Fail closed: with no user in scope we
    # cannot authorize a cross-tenant read, so report the data as unreadable.
    user_uuid = coerce_user_id(__agent_context__)
    if user_uuid is None:
        return {
            "error": "unavailable",
            "detail": ("No authenticated user in scope - the cost summary could not be loaded. Do not invent figures."),
        }

    pid = _resolve_project_id(project_id, __agent_context__)
    if not pid:
        return {
            "error": "missing_project",
            "detail": (
                "No project id was supplied and none is available in the run "
                "context. Ask the user which project to summarize."
            ),
        }

    import uuid

    try:
        project_uuid = uuid.UUID(pid)
    except (ValueError, AttributeError, TypeError):
        return {
            "error": "bad_id",
            "detail": f"'{pid}' is not a valid project id (expected a UUID).",
        }

    try:
        from app.database import async_session_factory
        from app.modules.costmodel.service import CostModelService
        from app.modules.projects.repository import ProjectRepository

        async with async_session_factory() as session:
            project = await ProjectRepository(session).get_by_id(project_uuid)
            # IDOR guard: deny when the project is missing OR the invoking user
            # has no access to it. Both return the SAME not_found shape so a
            # cross-tenant project is indistinguishable from a non-existent one
            # (never leak existence) and no figures are read.
            if project is None or not await assert_user_can_access_project(session, project_uuid, user_uuid):
                return {
                    "project_id": pid,
                    "error": "not_found",
                    "detail": (
                        "No project with that id exists. Tell the user the id "
                        "could not be found and ask them to check it."
                    ),
                }
            project_name = project.name
            dashboard = await CostModelService(session).get_dashboard(project_uuid)
    except Exception as exc:  # pragma: no cover - DB unavailable
        logger.debug("project_cost_summary unavailable for %s: %s", pid, exc)
        return {
            "project_id": pid,
            "error": "unavailable",
            "detail": (
                "The cost-model database is not reachable in this context. Do "
                "not invent figures; report that the cost summary could not be "
                "loaded."
            ),
        }

    # Currency reported by the dashboard is data-driven (the project's base);
    # it may be blank when the project has no currency configured.
    currency = (dashboard.currency or "").strip().upper()
    mixed = bool(dashboard.mixed_currency)

    total_budget = _to_decimal(dashboard.total_budget)
    committed = _to_decimal(dashboard.total_committed)
    actual = _to_decimal(dashboard.total_actual)

    summary: dict[str, Any] = {
        "project_id": pid,
        "project_name": project_name,
        "currency": currency,
        "total_budget": _money_str(total_budget),
        "committed": _money_str(committed),
        "actual": _money_str(actual),
        "mixed_currency": mixed,
    }

    if mixed:
        # Money rule: the budget lines span more than one currency, so a missing
        # fx_rate may have left a foreign amount unconverted in these sums.
        # Refuse to derive a blended variance - surface a warning and present
        # the amounts separately instead.
        summary["warning"] = (
            "This project's budget lines use more than one currency. The amounts "
            "above may blend unconverted foreign values, so they must not be "
            "read as a single combined total. Present the figures with this "
            "caveat and do not compute a cross-currency variance."
        )
        return summary

    # Single-currency project - variance and % spent are meaningful. Variance is
    # expressed as budget minus the spend measure (positive = under budget).
    committed_variance = total_budget - committed
    actual_variance = total_budget - actual

    summary["committed_vs_budget"] = _money_str(committed_variance)
    summary["actual_vs_budget"] = _money_str(actual_variance)
    summary["percent_spent"] = round(float(actual / total_budget) * 100.0, 2) if total_budget > 0 else 0.0
    summary["status"] = dashboard.status
    return summary


# ── Registration ────────────────────────────────────────────────────────────


def register_project_analyst() -> None:
    """Idempotent registration of the Project-analyst agent and its tool."""
    global_tool_registry.register(
        FunctionTool(
            name="project_cost_summary",
            description=(
                "Summarize a project's budget vs committed vs actual from the "
                "real 5D cost dashboard. Returns the project name, ISO currency, "
                "total_budget, committed and actual (Decimal as string), the "
                "mixed_currency flag, and - only when the project uses a single "
                "currency - committed_vs_budget / actual_vs_budget variances and "
                "percent_spent. When mixed_currency is true it returns a warning "
                "and NO blended variance (currencies must not be combined). The "
                "project_id is optional: when omitted it is taken from the run "
                "context. Returns an error object if there is no project id, the "
                "project is missing, or the database is unreachable - never "
                "invent figures."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": (
                            "UUID of the project to summarize. Optional - defaults to the project in the run context."
                        ),
                    },
                },
                "required": [],
            },
            func=_tool_project_cost_summary,
        )
    )

    register_agent(
        Agent(
            name="project_analyst",
            display_name="Project Analyst",
            category="analytics",
            icon="bar-chart-3",
            tagline="Summarize a project's budget vs committed vs actual",
            description=(
                "Produces a concise executive cost summary for a project - "
                "budget vs committed vs actual with variance and percentage "
                "spent - respecting currency isolation and clearly flagging when "
                "the project mixes currencies. It never invents figures."
            ),
            example_prompts=[
                "How is this project tracking against budget?",
                "Give me a one-paragraph cost status summary for the steering committee.",
                "What is the committed-vs-budget variance so far?",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["project_cost_summary"],
        )
    )
