# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Progress Reporter - writes a short human narrative for a progress report.

Two surfaces share one prompt-assembly + LLM-call core:

* An :class:`Agent` descriptor (catalogue entry, mirrors ``project_analyst``)
  so the no-code agent UI lists "Progress Reporter" alongside the others.
* :func:`generate_progress_narrative` - the function the reporting module
  calls as an OPTIONAL enrichment when a progress-report template opts in.
  It takes the snapshot produced by ``ReportingService._build_default_snapshot``
  and returns a short narrative covering schedule status, cost status, key
  activities and risks.

AI-augmented, human-confirmed (architecture guide): the narrative is a
SUGGESTION. The renderer marks it clearly as AI-generated with a
confidence note, and the report still reads fine without it.

Graceful degradation (no-stubs rule): when no API key is configured the
function returns ``None`` and the report renders without a narrative - it
never raises, never blocks generation, and never invents project facts.
The model is told to write only from the snapshot it is given.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from app.modules.ai_agents.base import Agent, register_agent

logger = logging.getLogger(__name__)


# Confidence stamped on the narrative. The agent is constrained to the
# snapshot it is handed, so the figures are trustworthy, but prose framing
# (tone, emphasis, what counts as a "risk") is a judgement the human must
# confirm - hence a deliberately middling default rather than near-1.0.
NARRATIVE_CONFIDENCE = 0.6

# Single-shot narrative cap. A client progress summary is a few short
# paragraphs; a tight cap keeps cost and latency down.
NARRATIVE_MAX_TOKENS = 600


SYSTEM_PROMPT = (
    "You are a construction project manager writing a short progress update "
    "for the project owner or client. You are given a JSON snapshot of the "
    "current project status. Write a concise narrative (3 to 5 short "
    "paragraphs, plain prose, no markdown headings) covering, in this order: "
    "overall schedule status, cost status, the key activities reflected in "
    "the data, and any risks the data points to.\n\n"
    "Write ONLY from the snapshot you are given. Never invent figures, dates, "
    "milestones, or risks that are not present in the data. Quote every money "
    "amount with the currency code from the snapshot and never combine "
    "different currencies into one total. If a section has no data, say so "
    "briefly rather than guessing. Keep the tone factual and calm; this goes "
    "to a client, not an internal team."
)


# Type of the injectable LLM call - matches ``ai.ai_client.call_ai``'s
# ``(text, tokens)`` return so tests can supply a stub without the network.
LLMCall = Callable[..., Awaitable[tuple[str, int]]]


def build_narrative_prompt(snapshot: dict[str, Any]) -> str:
    """Assemble the user prompt from a report snapshot.

    The snapshot is serialised as pretty JSON so the model sees exactly the
    figures the report is built from (same source of truth as the rendered
    tables). Exposed at module scope so the prompt assembly is unit-testable
    without an LLM.
    """
    payload = json.dumps(snapshot or {}, ensure_ascii=False, indent=2, default=str)
    return (
        "Here is the project progress snapshot as JSON. Write the client "
        "progress narrative described in your instructions, using only these "
        "figures.\n\n"
        f"{payload}"
    )


async def generate_progress_narrative(
    snapshot: dict[str, Any],
    *,
    settings: Any | None = None,
    call_llm: LLMCall | None = None,
) -> dict[str, Any] | None:
    """Produce an AI narrative for a progress-report snapshot, or ``None``.

    Resolves an AI provider + key from ``settings`` (falling back to the
    environment / CLI config when ``settings`` is ``None``). When no key is
    configured the function returns ``None`` so report generation proceeds
    without a narrative - it never raises.

    Args:
        snapshot: The report data snapshot (output of
            ``ReportingService._build_default_snapshot``).
        settings: Optional AISettings ORM object. When ``None`` the resolver
            scans environment variables and the CLI config file.
        call_llm: Optional injected LLM call (signature of
            ``ai.ai_client.call_ai``). Used by tests to avoid the network;
            never call a real provider in tests.

    Returns:
        ``{"text", "confidence", "ai_generated", "provider", "model"}`` on
        success, or ``None`` when no key is configured or the call fails.
    """
    if not snapshot:
        return None

    try:
        from app.modules.ai.ai_client import call_ai, resolve_provider_key_model
    except Exception as exc:  # pragma: no cover - import safety
        logger.debug("AI module unavailable for progress narrative: %s", exc)
        return None

    # Resolve provider + key. A missing key raises ValueError by contract -
    # that is the graceful "no narrative" path, not an error to surface.
    try:
        provider, api_key, model = resolve_provider_key_model(settings)
    except ValueError:
        logger.debug("No AI key configured; progress report renders without narrative")
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("AI key resolution failed for progress narrative: %s", exc)
        return None

    caller: LLMCall = call_llm or call_ai
    prompt = build_narrative_prompt(snapshot)

    try:
        text, _tokens = await caller(
            provider=provider,
            api_key=api_key,
            system=SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=NARRATIVE_MAX_TOKENS,
            model=model,
        )
    except Exception as exc:
        logger.warning("Progress narrative generation failed: %s", exc, exc_info=True)
        return None

    cleaned = (text or "").strip()
    if not cleaned:
        return None

    return {
        "text": cleaned,
        "confidence": NARRATIVE_CONFIDENCE,
        "ai_generated": True,
        "provider": provider,
        "model": model,
    }


def register_progress_reporter() -> None:
    """Idempotent registration of the Progress-reporter agent descriptor.

    The narrative is produced through :func:`generate_progress_narrative`
    (an enrichment call from the reporting module), so the catalogue entry
    carries no tools - it documents the capability for the no-code UI and
    keeps the agent list complete.
    """
    register_agent(
        Agent(
            name="progress_reporter",
            display_name="Progress Reporter",
            category="analytics",
            icon="file-text",
            tagline="Write a client progress narrative from a report snapshot",
            description=(
                "Turns a project progress snapshot into a short, client-ready "
                "narrative covering schedule status, cost status, key "
                "activities and risks. It writes only from the data it is "
                "given and never invents figures. Used as an optional "
                "enrichment when a progress-report template opts in; the "
                "narrative is always marked AI-generated for human review."
            ),
            example_prompts=[
                "Summarize this week's progress for the client.",
                "Write a short owner update from the latest progress data.",
                "What does the current snapshot say about schedule and cost?",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=1,
            allowed_tools=[],
        )
    )
