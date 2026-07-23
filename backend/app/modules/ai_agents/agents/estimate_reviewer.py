# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate Reviewer - audits an EXISTING BOQ for pricing gaps and quality issues.

The user supplies a ``boq_id`` in the prompt; the agent reviews that BOQ and
reports concrete quality problems. It NEVER writes or mutates anything - it is a
read-only auditor over real project data.

Tools (declarative - wired into the global registry on import):

* ``read_boq(boq_id)``          - loads the BOQ and its positions via the real
                                  ``boq.service.BOQService.get_boq_with_positions``
                                  (the same canonical totals the BOQ detail
                                  endpoint serves, markups included). Returns a
                                  compact, token-bounded summary with the
                                  per-currency grand total.
* ``check_boq_quality(boq_id)`` - runs the platform's real
                                  :data:`validation_engine` over the
                                  ``boq_quality`` rule set (the exact rules the
                                  ``POST /boq/{id}/validate`` endpoint fires:
                                  missing/zero quantity & rate, duplicate
                                  ordinals, total mismatch, unrealistic/outlier
                                  rates, empty unit, negative values …) and
                                  returns the failing findings as a structured
                                  list grouped for the LLM.

Data integrity (no-stubs rule): both tools read REAL rows. If no DB session can
be opened in the current process (e.g. a unit test instantiating a tool
directly) the tool returns an explicit ``{"error": "unavailable", ...}``
observation so the LLM can never invent positions, rates, or findings. Money is
carried with its ISO 4217 currency code and is never blended across currencies.

Access control (IDOR defence): each BOQ is resolved to its owning project and
the run's invoking user - threaded in via the trusted ``__agent_context__``
(the runner strips any LLM-forged context and re-injects the real one) - must
own or belong to that project. On denial, or when no user is in scope, the tool
returns the ``not_found`` / ``unavailable`` observation, so the LLM never reads
another tenant's BOQ and a cross-tenant id is indistinguishable from a missing
one (existence is never leaked).
"""

from __future__ import annotations

import logging
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


# Cap the number of line items echoed back into the LLM context so a large BOQ
# (thousands of positions) cannot blow up the next-step prompt cost. The quality
# tool still analyses EVERY position - only the human-readable line dump is
# truncated, with an explicit note when rows are dropped.
_MAX_LINE_ITEMS = 60


SYSTEM_PROMPT = (
    "You are a senior construction-cost estimator auditing an existing Bill of "
    "Quantities for quality before it goes to tender. The user gives you a "
    "boq_id. Always work in this order:\n"
    "1. Call read_boq(boq_id) to load the real positions and the grand total.\n"
    "2. Call check_boq_quality(boq_id) to run the boq_quality validation rules.\n"
    "3. Reply with a concise markdown audit grouped by severity: an 'Errors' "
    "section (blocking problems) and a 'Warnings' section (flags). For each "
    "finding cite the concrete position ordinal it refers to and recommend a "
    "specific fix. End with a one-line verdict.\n\n"
    "Never invent positions, rates, or issues: report only what the tools "
    "return. Quote money with the currency code from read_boq and never combine "
    "amounts of different currencies into one total. If read_boq returns an "
    "error (the BOQ could not be read), say so plainly and stop rather than "
    "guessing."
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _row_type(unit: Any, quantity: Any, unit_rate: Any) -> str:
    """Classify a position as a ``section`` header or a real ``position``.

    Mirrors ``boq.service._is_section`` semantics so the boq_quality leaf-rules
    skip section headers (which legitimately have no unit/quantity/rate) instead
    of false-positively flagging every header as a missing-quantity error. A row
    with an empty/"section" unit AND zero quantity AND zero rate is a header.
    """
    unit_clean = (str(unit or "")).strip().lower()
    try:
        qty = float(quantity or 0)
        rate = float(unit_rate or 0)
    except (TypeError, ValueError):
        qty = rate = 0.0
    if unit_clean in ("", "section") and qty == 0.0 and rate == 0.0:
        return "section"
    return "position"


def _position_currency(metadata: Any, fallback: str) -> str:
    """Resolve a single position's currency from its metadata, else ``fallback``.

    Mirrors ``boq.service._position_currency``: per-position ``metadata.currency``
    is authoritative, with ``position_currency`` / ``project_currency`` accepted
    as legacy fallbacks. Empty → the project (base) currency so the line is never
    reported without a currency code (money rule).
    """
    meta = metadata if isinstance(metadata, dict) else {}
    for key in ("currency", "position_currency", "project_currency"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().upper()
    return fallback


# ── Tool implementations ────────────────────────────────────────────────────


def _boq_not_found(raw_id: str) -> dict[str, Any]:
    """The canonical ``not_found`` observation for a BOQ tool.

    Used for BOTH a genuinely missing BOQ and an access-denied one so a
    cross-tenant id is indistinguishable from a non-existent one (IDOR
    defence - never reveal existence).
    """
    return {
        "boq_id": raw_id,
        "error": "not_found",
        "detail": ("No BOQ with that id exists. Tell the user the id could not be found and ask them to check it."),
    }


async def _tool_read_boq(
    boq_id: str,
    __agent_context__: dict | None = None,  # noqa: N803 - runner-injected key
) -> dict[str, Any]:
    """Load a BOQ and its positions as a compact, token-bounded summary.

    Reads the real BOQ via ``boq.service.BOQService.get_boq_with_positions``
    (the same canonical figures the detail endpoint serves: ``grand_total``
    already includes active markups) and resolves the project currency via
    ``BOQService._resolve_project_currency``.

    Access control: the BOQ is resolved to its owning project and the invoking
    user (from the trusted ``__agent_context__``) must own or belong to that
    project. A denied or unknown user yields the same ``not_found`` observation
    as a missing BOQ, so cross-tenant existence is never revealed.

    Args:
        boq_id: The UUID of the BOQ to read (string form, as the user pasted it).
        __agent_context__: Runner-injected trusted context carrying ``user_id``.

    Returns:
        A summary dict with ``position_count``, ``grand_total`` (Decimal as
        string), ``currency`` (ISO 4217), and up to ~60 ``line_items`` (each with
        ordinal, description, unit, quantity, unit_rate, total, currency). If the
        BOQ id is malformed, the BOQ does not exist, the user has no access, or no
        DB session can be opened, returns
        ``{"error": "unavailable" | "not_found" | "bad_id", ...}`` so the LLM
        never fabricates positions or rates.
    """
    raw_id = (boq_id or "").strip()
    if not raw_id:
        return {
            "error": "bad_id",
            "detail": "No boq_id was provided. Ask the user for the BOQ id.",
        }

    # Fail closed: without a trusted user we cannot authorize a cross-tenant
    # read, so report the BOQ as unreadable rather than serving its data.
    user_uuid = coerce_user_id(__agent_context__)
    if user_uuid is None:
        return {
            "boq_id": raw_id,
            "error": "unavailable",
            "detail": (
                "No authenticated user in scope - the BOQ could not be read. Do not invent positions or totals."
            ),
        }

    import uuid

    try:
        boq_uuid = uuid.UUID(raw_id)
    except (ValueError, AttributeError, TypeError):
        return {
            "error": "bad_id",
            "detail": (f"'{raw_id}' is not a valid BOQ id (expected a UUID). Ask the user to paste the BOQ id again."),
        }

    try:
        from app.database import async_session_factory
        from app.modules.boq.service import BOQService

        async with async_session_factory() as session:
            service = BOQService(session)
            boq = await service.get_boq_with_positions(boq_uuid)
            # IDOR guard: resolve the BOQ's owning project, then verify access
            # BEFORE returning any positions/rates. Denied access maps to the
            # not_found shape so a cross-tenant BOQ is indistinguishable from a
            # missing one.
            if not await assert_user_can_access_project(session, boq.project_id, user_uuid):
                return _boq_not_found(raw_id)
            currency = (await service._resolve_project_currency(boq_uuid)) or ""  # noqa: SLF001
    except Exception as exc:  # pragma: no cover - DB unavailable / not found
        # get_boq_with_positions raises HTTPException(404) for a missing BOQ.
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            return _boq_not_found(raw_id)
        logger.debug("read_boq unavailable for %s: %s", raw_id, exc)
        return {
            "boq_id": raw_id,
            "error": "unavailable",
            "detail": (
                "The BOQ database is not reachable in this context. Do not "
                "invent positions or totals; report that the BOQ could not be "
                "read."
            ),
        }

    base_currency = currency.strip().upper()
    line_items: list[dict[str, Any]] = []
    for pos in boq.positions[:_MAX_LINE_ITEMS]:
        line_items.append(
            {
                "ordinal": pos.ordinal,
                "description": pos.description,
                "unit": pos.unit,
                # PositionResponse exposes these as exact Decimals; str() keeps
                # the value lossless and locale-neutral for the LLM.
                "quantity": str(pos.quantity),
                "unit_rate": str(pos.unit_rate),
                "total": str(pos.total),
                "currency": _position_currency(pos.metadata, base_currency),
            }
        )

    truncated = len(boq.positions) > _MAX_LINE_ITEMS
    summary: dict[str, Any] = {
        "boq_id": raw_id,
        "name": boq.name,
        "status": boq.status,
        "position_count": boq.position_count,
        # grand_total already includes active markups (matches the detail
        # endpoint). Decimal-as-string so large totals round-trip exactly.
        "grand_total": str(boq.grand_total),
        "direct_cost_total": str(boq.direct_cost_total),
        "currency": base_currency,
        "line_items": line_items,
        "line_items_shown": len(line_items),
    }
    if truncated:
        summary["note"] = (
            f"Only the first {_MAX_LINE_ITEMS} of {len(boq.positions)} positions "
            "are listed here to bound size; check_boq_quality still analyses "
            "every position."
        )
    return summary


async def _tool_check_boq_quality(
    boq_id: str,
    __agent_context__: dict | None = None,  # noqa: N803 - runner-injected key
) -> dict[str, Any]:
    """Run the real ``boq_quality`` validation rules over a BOQ's positions.

    Reuses the platform's :data:`app.core.validation.engine.validation_engine`
    and its registered ``boq_quality`` rule set - the exact rules the
    ``POST /boq/{id}/validate`` endpoint fires (missing/zero quantity & rate,
    duplicate ordinals, total mismatch, unrealistic and outlier rates, empty
    unit, negative values, section-without-items, cost concentration …). The
    positions are projected into the same dict shape the router feeds the engine
    so rule behaviour is identical. This is real analysis of real data, not a
    re-implemented stub.

    Access control: the BOQ is resolved to its owning project and the invoking
    user (from the trusted ``__agent_context__``) must own or belong to that
    project; a denied or unknown user yields the ``not_found`` observation, so
    cross-tenant existence is never revealed.

    Args:
        boq_id: The UUID of the BOQ to check (string form).
        __agent_context__: Runner-injected trusted context carrying ``user_id``.

    Returns:
        A dict with a ``summary`` count block and an ``issues`` list, each issue
        being ``{issue_type, position_ordinal, message, severity}`` (only failing
        findings are returned). On a malformed id / missing BOQ / no access /
        unreachable DB, returns ``{"error": ...}`` so the LLM never fabricates
        findings.
    """
    raw_id = (boq_id or "").strip()
    if not raw_id:
        return {
            "error": "bad_id",
            "detail": "No boq_id was provided. Ask the user for the BOQ id.",
        }

    # Fail closed: without a trusted user we cannot authorize a cross-tenant
    # read, so report quality as uncheckable rather than analysing the BOQ.
    user_uuid = coerce_user_id(__agent_context__)
    if user_uuid is None:
        return {
            "boq_id": raw_id,
            "error": "unavailable",
            "detail": ("No authenticated user in scope - BOQ quality could not be checked. Do not invent findings."),
        }

    import uuid

    try:
        boq_uuid = uuid.UUID(raw_id)
    except (ValueError, AttributeError, TypeError):
        return {
            "error": "bad_id",
            "detail": f"'{raw_id}' is not a valid BOQ id (expected a UUID).",
        }

    try:
        from app.core.validation.engine import validation_engine
        from app.database import async_session_factory
        from app.modules.boq.service import BOQService

        async with async_session_factory() as session:
            service = BOQService(session)
            boq = await service.get_boq_with_positions(boq_uuid)
            # IDOR guard: verify the invoking user can access the BOQ's owning
            # project BEFORE running any analysis. Denied access maps to the
            # not_found shape so a cross-tenant BOQ is indistinguishable from a
            # missing one.
            if not await assert_user_can_access_project(session, boq.project_id, user_uuid):
                return _boq_not_found(raw_id)

            # Project positions into the shape the boq_quality rules read. A
            # row's "type" is derived so section headers are skipped by the
            # leaf-position rules (matches the validate-endpoint contract).
            positions_data = [
                {
                    "id": str(pos.id),
                    "parent_id": (str(pos.parent_id) if pos.parent_id else None),
                    "ordinal": pos.ordinal,
                    "description": pos.description,
                    "unit": pos.unit,
                    # Rules were written against the historical float contract.
                    "quantity": float(pos.quantity),
                    "unit_rate": float(pos.unit_rate),
                    "total": float(pos.total),
                    "classification": pos.classification,
                    "source": pos.source,
                    "type": _row_type(pos.unit, pos.quantity, pos.unit_rate),
                }
                for pos in boq.positions
            ]

            # Universal quality rule set only - no DIN/NRM/region bias. These
            # are the platform's own boq_quality rules, executed by the shared
            # engine (single source of truth).
            report = await validation_engine.validate(
                data={"positions": positions_data},
                rule_sets=["boq_quality"],
                target_type="boq",
                target_id=raw_id,
                project_id=str(boq.project_id),
            )
    except Exception as exc:  # pragma: no cover - DB unavailable / not found
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            # Identical shape to the access-denied path so a cross-tenant BOQ
            # cannot be told apart from a genuinely missing one.
            return _boq_not_found(raw_id)
        logger.debug("check_boq_quality unavailable for %s: %s", raw_id, exc)
        return {
            "boq_id": raw_id,
            "error": "unavailable",
            "detail": (
                "The BOQ database / validation engine is not reachable in this "
                "context. Do not invent findings; report that quality could not "
                "be checked."
            ),
        }

    # Map only the FAILING compliance results into the structured issue list.
    # Engine-error (infrastructure) rows are surfaced separately so a rule crash
    # never masquerades as a data-quality problem.
    ordinal_by_ref = {str(p.id): p.ordinal for p in boq.positions}
    issues: list[dict[str, Any]] = []
    for r in report.results:
        if r.passed or r.is_engine_error:
            continue
        ordinal = ordinal_by_ref.get(str(r.element_ref or ""))
        issues.append(
            {
                "issue_type": r.rule_id,
                "position_ordinal": ordinal,
                "message": r.message,
                "severity": r.severity.value,
                "suggestion": r.suggestion,
            }
        )

    engine_errors = [{"issue_type": r.rule_id, "message": r.message} for r in report.engine_errors]

    return {
        "boq_id": raw_id,
        "rule_set": "boq_quality",
        "summary": {
            "positions_checked": boq.position_count,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "infos": len(report.infos),
            "status": report.status.value,
            "score": report.score,
        },
        "issues": issues,
        "engine_errors": engine_errors,
    }


# ── Registration ────────────────────────────────────────────────────────────


def register_estimate_reviewer() -> None:
    """Idempotent registration of the Estimate-reviewer agent and its tools."""
    global_tool_registry.register(
        FunctionTool(
            name="read_boq",
            description=(
                "Load an existing BOQ and its positions by boq_id. Returns "
                "position_count, grand_total (with markups, Decimal as string), "
                "the ISO currency code and up to ~60 line items (ordinal, "
                "description, unit, quantity, unit_rate, total, currency). Call "
                "this FIRST. Returns an error object if the id is invalid, the "
                "BOQ is missing, or the database is unreachable - never invent "
                "positions or rates."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "boq_id": {
                        "type": "string",
                        "description": "UUID of the BOQ to review",
                    },
                },
                "required": ["boq_id"],
            },
            func=_tool_read_boq,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="check_boq_quality",
            description=(
                "Run the platform's boq_quality validation rules over every "
                "position of a BOQ (missing/zero quantities and rates, duplicate "
                "ordinals, total mismatches, unrealistic or outlier rates, empty "
                "units, negative values, and more). Returns a count summary plus "
                "a list of failing issues, each with issue_type, "
                "position_ordinal, message and severity. Returns an error object "
                "if the BOQ cannot be read - never fabricate findings."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "boq_id": {
                        "type": "string",
                        "description": "UUID of the BOQ to audit",
                    },
                },
                "required": ["boq_id"],
            },
            func=_tool_check_boq_quality,
        )
    )

    register_agent(
        Agent(
            name="estimate_reviewer",
            display_name="Estimate Reviewer",
            category="quality",
            icon="shield-check",
            tagline="Audit a BOQ for pricing gaps and quality issues",
            description=(
                "Reviews an existing BOQ against the platform's boq_quality "
                "rules and reports missing prices, zero quantities, duplicates "
                "and outlier rates, grouped by severity with concrete position "
                "references and recommended fixes."
            ),
            example_prompts=[
                "Review BOQ <paste-boq-id> for missing prices, zero quantities and duplicate positions.",
                "Audit the quality of BOQ <id> and tell me which lines need attention before tender.",
                "Check BOQ <id> for outlier unit rates and total mismatches, grouped by severity.",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["read_boq", "check_boq_quality"],
        )
    )
