# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Rate Benchmarker - sanity-checks a proposed unit rate against the catalogue.

Tools (declarative - wired into the global registry on import):

* ``benchmark_rate(description, proposed_rate, currency, region)`` - looks up
  real catalogue items via ``costs.matcher.match_cwicr_items`` and compares the
  user's proposed unit rate against the distribution of matches **within a
  single ISO currency**. Returns sample_size, min / median / max and a
  ``delta_pct`` plus a verdict (``under`` / ``in_range`` / ``over``).
* ``search_costs(q, region)`` - the same cost-database proxy the BOQ drafter
  uses, so the agent can inspect the raw matches behind a benchmark.

Money rule (CRITICAL): the benchmark is computed **strictly within one
currency**. The tool keeps only the matches whose ISO ``currency`` equals the
user-supplied ``currency`` and NEVER converts or blends rates from other
currencies. If there is no same-currency match, the tool says so explicitly
rather than falling back to a foreign-currency rate.

Data integrity (no-stubs rule): if the cost database is unreachable in the
current process the tool returns an explicit ``{"error": "unavailable"}``
observation so the LLM cannot ground a verdict on invented money.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

from app.modules.ai_agents.base import (
    Agent,
    FunctionTool,
    global_tool_registry,
    register_agent,
)

logger = logging.getLogger(__name__)


# Threshold (percent) for classifying a proposed rate as out of range. A rate
# more than this far below the catalogue median reads as "under" (likely
# under-priced / scope gap); more than this far above reads as "over".
_OUT_OF_RANGE_PCT = 25.0


SYSTEM_PROMPT = (
    "You are a construction-cost estimator who benchmarks a user's PROPOSED "
    "unit rate honestly against real catalogue data. Call benchmark_rate with "
    "the work description, the proposed rate, and its ISO currency code (e.g. "
    "EUR, GBP, USD). Always state the sample size the benchmark used so the "
    "user can judge confidence. Compare rates STRICTLY within one currency: "
    "never convert between currencies and never compare a rate in one currency "
    "against catalogue rates in another. If benchmark_rate reports no "
    "same-currency benchmark exists, say so plainly and do not improvise a "
    "cross-currency comparison. If the cost database is unavailable, tell the "
    "user the rate could not be benchmarked rather than guessing."
)


# ── Tool implementations ────────────────────────────────────────────────────


async def _tool_search_costs(q: str, region: str | None = None) -> dict[str, Any]:
    """Query the cost database via ``costs.matcher.match_cwicr_items``.

    Returns up to 5 real catalogue matches, each with its ISO ``currency``
    code. If no DB session can be opened (e.g. a unit test instantiating
    the tool directly), the tool returns an explicit ``{"error": ...}``
    observation rather than a fabricated priced row (no-stubs rule).
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
                "available - do not invent unit rates; report that the rate "
                "could not be benchmarked."
            ),
        }


async def _tool_benchmark_rate(
    description: str,
    proposed_rate: float,
    currency: str,
    region: str | None = None,
) -> dict[str, Any]:
    """Benchmark a proposed unit rate against the catalogue, single-currency.

    Looks up catalogue items via ``costs.matcher.match_cwicr_items`` (the same
    call the BOQ drafter uses), keeps ONLY the matches whose ISO ``currency``
    equals ``currency`` (uppercased), and computes the sample size plus the
    min / median / max unit rate and ``delta_pct`` of the proposed rate against
    the median.

    Money rule: comparison is strictly within one currency. Rates in any other
    currency are discarded - never converted, never blended. If there are zero
    same-currency matches the tool returns ``verdict="no_benchmark"`` with a
    note and does NOT fall back to a foreign currency.

    Returns ``{"error": "unavailable"}`` when the cost database is unreachable.
    """
    desc = (description or "").strip()
    currency_code = (currency or "").strip().upper()

    # Coerce the proposed rate defensively - the LLM may hand us a string.
    try:
        proposed = float(proposed_rate)
    except (TypeError, ValueError):
        return {
            "description": desc,
            "currency": currency_code,
            "error": "bad_proposed_rate",
            "detail": "proposed_rate must be a number, e.g. 145 or 145.50.",
        }

    if not desc:
        return {
            "description": desc,
            "currency": currency_code,
            "error": "empty_description",
            "detail": "Provide a work description to benchmark against.",
        }
    if not currency_code:
        return {
            "description": desc,
            "currency": currency_code,
            "error": "missing_currency",
            "detail": (
                "Provide the ISO 4217 currency code of the proposed rate "
                "(e.g. EUR). Benchmarking is done strictly within one currency."
            ),
        }

    try:
        from app.database import async_session_factory
        from app.modules.costs.matcher import match_cwicr_items

        async with async_session_factory() as session:
            results = await match_cwicr_items(
                session,
                desc,
                top_k=20,
                region=region or None,
            )
    except Exception as exc:  # pragma: no cover - DB unavailable
        logger.debug("benchmark_rate unavailable: %s", exc)
        return {
            "description": desc,
            "currency": currency_code,
            "region": region or "",
            "error": "unavailable",
            "detail": (
                "Cost database is not reachable in this context. The rate "
                "could not be benchmarked - do not invent a benchmark."
            ),
        }

    # MONEY RULE: keep only same-currency matches. Never convert or blend.
    same_currency = [r for r in results if (r.currency or "").strip().upper() == currency_code]
    other_currencies = sorted(
        {
            (r.currency or "").strip().upper()
            for r in results
            if (r.currency or "").strip().upper() and (r.currency or "").strip().upper() != currency_code
        }
    )

    proposed_rounded = round(proposed, 4)

    if not same_currency:
        note = (
            f"No catalogue items priced in {currency_code} matched this "
            f"description, so no same-currency benchmark exists. "
        )
        if other_currencies:
            note += (
                "Matches exist in other currencies "
                f"({', '.join(other_currencies)}) but they are intentionally "
                "NOT used - rates are never converted or compared across "
                "currencies."
            )
        else:
            note += "No priced matches were found at all."
        return {
            "description": desc,
            "region": region or "",
            "currency": currency_code,
            "proposed_rate": {"value": proposed_rounded, "currency": currency_code},
            "sample_size": 0,
            "verdict": "no_benchmark",
            "note": note,
        }

    rates = [float(r.unit_rate) for r in same_currency]
    sample_size = len(rates)
    min_rate = min(rates)
    max_rate = max(rates)
    median_rate = statistics.median(rates)

    # delta_pct of the proposal vs the catalogue median. Undefined when the
    # median is zero (free / unparseable rows) - report it explicitly rather
    # than dividing by zero.
    if median_rate == 0:
        delta_pct: float | None = None
        verdict = "no_benchmark"
        note = (
            f"{sample_size} {currency_code} match(es) found but their median "
            "rate is 0, so a percentage comparison is undefined."
        )
    else:
        delta_pct = round((proposed - median_rate) / median_rate * 100.0, 2)
        if delta_pct < -_OUT_OF_RANGE_PCT:
            verdict = "under"
        elif delta_pct > _OUT_OF_RANGE_PCT:
            verdict = "over"
        else:
            verdict = "in_range"
        note = (
            f"Benchmarked against {sample_size} catalogue item(s) priced in "
            f"{currency_code}. Verdict is relative to the catalogue median "
            f"with a +/-{_OUT_OF_RANGE_PCT:g}% in-range band."
        )

    samples = [
        {
            "code": r.code,
            "description": r.description,
            "unit": r.unit,
            "unit_rate": round(float(r.unit_rate), 4),
            "currency": currency_code,
            "score": round(float(r.score), 4),
        }
        for r in same_currency[:5]
    ]

    return {
        "description": desc,
        "region": region or "",
        "currency": currency_code,
        "proposed_rate": {"value": proposed_rounded, "currency": currency_code},
        "sample_size": sample_size,
        "min": {"value": round(min_rate, 4), "currency": currency_code},
        "median": {"value": round(median_rate, 4), "currency": currency_code},
        "max": {"value": round(max_rate, 4), "currency": currency_code},
        "delta_pct": delta_pct,
        "verdict": verdict,
        "note": note,
        "samples": samples,
    }


# ── Registration ────────────────────────────────────────────────────────────


def register_rate_benchmarker() -> None:
    """Idempotent registration of the rate-benchmarker agent and its tools."""
    global_tool_registry.register(
        FunctionTool(
            name="benchmark_rate",
            description=(
                "Benchmark a PROPOSED unit rate against real cost-database "
                "items, strictly within one ISO currency. Returns sample_size, "
                "min/median/max unit_rate, delta_pct vs the median and a verdict "
                "(under / in_range / over). Never converts or compares across "
                "currencies; if no same-currency match exists it says so."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Work item description to benchmark",
                    },
                    "proposed_rate": {
                        "type": "number",
                        "description": "The unit rate the user wants to sanity-check",
                    },
                    "currency": {
                        "type": "string",
                        "description": (
                            "ISO 4217 currency code of proposed_rate, e.g. EUR. "
                            "Comparison is done only within this currency."
                        ),
                    },
                    "region": {
                        "type": "string",
                        "description": "Optional region code (e.g. DE_BERLIN)",
                    },
                },
                "required": ["description", "proposed_rate", "currency"],
            },
            func=_tool_benchmark_rate,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="search_costs",
            description=(
                "Look up cost-database items that match a free-form query. "
                "Returns up to 5 candidates with code, description, unit, "
                "unit_rate and currency. Use this to inspect the raw matches "
                "behind a benchmark."
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

    register_agent(
        Agent(
            name="rate_benchmarker",
            display_name="Rate Benchmarker",
            category="estimating",
            icon="scale",
            tagline="Sanity-check a unit rate against the cost database",
            description=(
                "Benchmarks a proposed unit rate against real catalogue data "
                "within a single currency, reporting min / median / max, the "
                "percentage delta and an honest under / in-range / over verdict."
            ),
            example_prompts=[
                "Is 145 EUR/m2 reasonable for plastered and painted internal walls?",
                "Benchmark 320 GBP/m3 for C30/37 ready-mix concrete.",
                "Check whether 55 USD/m2 for carpet tiles is in range.",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["benchmark_rate", "search_costs"],
        )
    )
