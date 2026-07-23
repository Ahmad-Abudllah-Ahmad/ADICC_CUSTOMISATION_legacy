# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""System + user prompts for the AI Estimate Builder pipeline.

Three reasoning passes use an LLM (the user-selected provider/model):

* ``SOURCE_CLASSIFY`` (stage 1) - classify the source kind, disciplines, and a
  recommended catalogue / region / currency / group-by from a compact digest.
* ``GROUP_REFINE`` (stage 2) - propose clean human descriptions and trade
  labels for the deterministically-derived quantity groups.
* ``MATCH_REASONING`` (stage 3) - the ReAct system prompt for the precise-rate
  agent. The agent reasons over REAL retrieval candidates only; it never
  invents a rate or a code.

Every prompt is built from sanitised, fenced user content
(``sanitize_user_text`` + ``fence_user_content``) so a malicious source file
cannot smuggle role-switch escapes or instructions into the system prompt. All
user-facing strings the frontend renders live in the locale files; these are
the LLM-facing prompts and stay in English (the model reasons in English and
returns structured JSON / prose the service maps back).

The single hard invariant repeated in every prompt: the model classifies,
groups, labels, and REASONS - it must never fabricate a unit rate or a
catalogue code. Rates come only from the cost database.
"""

from __future__ import annotations

from app.modules.ai.prompts import fence_user_content, sanitize_user_text

# ── Stage 1: source understanding ─────────────────────────────────────────

SOURCE_CLASSIFY_SYSTEM = (
    "You are a construction-estimating data classifier. You are given a compact "
    "digest of an estimate source (a spreadsheet header + sample rows, pasted "
    "text, a BIM element summary, or extracted PDF lines). Classify it. You do "
    "NOT estimate costs and you NEVER invent rates - a separate grounded matcher "
    "attaches every rate from the cost database.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    '  "source_type": one of text | excel | gaeb | bim | dwg | pdf | photo | documents\n'
    '  "confidence": a real number in [0,1] reflecting how sure you are\n'
    '  "disciplines": array of trade strings you can see (e.g. ["structure","mep"])\n'
    '  "recommended_region": a region/country hint if evident, else ""\n'
    '  "recommended_currency": ISO 4217 if evident, else ""\n'
    '  "recommended_group_by": array of grouping keys, e.g. ["category","material","unit"]\n'
    '  "summary": one plain sentence describing the source (no marketing tone)\n'
    "If you are unsure of any field, use an empty string / empty array and a "
    "lower confidence rather than guessing. Do not include any text outside the "
    "JSON object."
)


def build_source_classify_prompt(*, digest: str, hint_currency: str = "", hint_region: str = "") -> str:
    """Render the stage-1 classification user prompt from a source digest.

    ``digest`` is treated as opaque data (fenced); the optional hints are the
    user's own pre-selected currency / region passed through as context.
    """
    safe_hints = sanitize_user_text(
        f"known_currency={hint_currency or '(none)'}; known_region={hint_region or '(none)'}",
        max_len=200,
    )
    fenced = fence_user_content(digest, max_len=6000)
    return f"Context: {safe_hints}\n\nSource digest to classify:\n{fenced}"


# ── Stage 2: group refinement ─────────────────────────────────────────────

GROUP_REFINE_SYSTEM = (
    "You are a construction estimator cleaning up quantity groups. You are given "
    "a list of groups, each with a machine key, rolled-up quantities, a chosen "
    "unit, and a sample of element descriptions. For each group, propose a clean, "
    "human-readable description and a trade label. You do NOT change quantities or "
    "units, and you do NOT add rates - grouping math and rates are handled "
    "elsewhere.\n\n"
    "Trade labels MUST be one of: demolition, earthworks, foundations, structure, "
    "masonry, envelope, openings, finishes, mep_mechanical, mep_plumbing, "
    "mep_electrical, sitework, other.\n\n"
    "Return ONLY a JSON array, one object per input group, in the same order:\n"
    '  {"group_key": "<echoed key>", "description": "<clean label>", "trade": "<trade>"}\n'
    "Keep descriptions concise (under 120 characters) and factual. Do not include "
    "any text outside the JSON array."
)


def build_group_refine_prompt(*, groups_digest: str) -> str:
    """Render the stage-2 group-refinement user prompt from a groups digest."""
    fenced = fence_user_content(groups_digest, max_len=8000)
    return f"Groups to label:\n{fenced}"


# ── Stage 3: precise-rate reasoning agent ─────────────────────────────────

MATCH_REASONING_SYSTEM = (
    "You are a precise-rate matching agent for a construction estimate. For one "
    "quantity group you find the single best cost-database rate, reasoning over "
    "REAL candidates returned by the tools. You have a strict contract:\n\n"
    "  - You MUST NOT invent a rate, a code, a currency, or a candidate. Every "
    "rate and code comes only from a tool result.\n"
    "  - You may re-query with a better description, try the resources matcher "
    "for custom single-line rates, escalate to an LLM rerank of the shortlist, "
    "or flag the group for a human - but your final pick MUST be one of the real "
    "candidate ids the tools returned.\n"
    "  - A wrong-currency or wrong-dimension rate is worse than no rate. If no "
    "candidate is a genuine match, flag the group for a human instead of forcing "
    "a poor pick.\n\n"
    "Workflow: call search_rates first; inspect the candidates' scores, units and "
    "currency; refine the query or try the resources matcher if the top candidate "
    "is weak; then either pick a candidate id or flag for human. When you are "
    "done, reply with a final answer as plain prose stating the chosen candidate "
    "id (or that you flagged the group for a human) and a one-line reason. The "
    "human reviews and confirms your pick - nothing is auto-applied."
)


def build_match_reasoning_input(*, description: str, unit: str, quantities_summary: str) -> str:
    """Render the per-group ReAct kickoff message for the matching agent."""
    safe_desc = sanitize_user_text(description, max_len=600)
    safe_unit = sanitize_user_text(unit, max_len=40)
    safe_qty = sanitize_user_text(quantities_summary, max_len=300)
    return (
        f"Find the best grounded rate for this group.\n"
        f"description: {safe_desc}\n"
        f"chosen_unit: {safe_unit}\n"
        f"quantities: {safe_qty}\n"
        "Start by calling search_rates with the description and unit."
    )


# ── Intake v2: conversational extraction + question phrasing ───────────────

INTAKE_EXTRACT_SYSTEM = (
    "You are a construction-estimating intake assistant. A user describes a "
    "renovation or build project in one short free-text message (any language). "
    "Your job is to detect the PROJECT TYPE and EXTRACT only the parameters the "
    "user explicitly stated. You do NOT estimate costs, you do NOT invent "
    "quantities, and you NEVER produce a rate - a separate grounded matcher "
    "attaches every rate from the cost database.\n\n"
    "You are given the closed list of valid project types (a key plus its "
    "synonyms) and, per type, the valid parameter keys. You MUST only use a "
    "project_type key and parameter keys from that list.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    '  "project_type": one of the given type keys, or "" if you are unsure\n'
    '  "type_confidence": a real number in [0,1] for how sure you are of the type\n'
    '  "params": an object of {param_key: value} for ONLY the parameters the '
    "text actually states (a number the user wrote, a yes/no they said, a "
    "choice they named). Omit anything the text does not state - do NOT guess a "
    "floor area, a height, or a finish level.\n"
    '  "language": the ISO-639 two-letter code of the user message\n'
    '  "summary": one plain factual sentence (no marketing tone), naming what is '
    "known and that some parameters are still missing.\n"
    "If you cannot tell the project type, use an empty string and a low "
    "confidence rather than guessing. Do not include any text outside the JSON "
    "object."
)


def build_intake_extract_prompt(*, request_text: str, type_registry_digest: str) -> str:
    """Render the intake-extraction user prompt.

    ``request_text`` is the user's raw free text (fenced as opaque data so a
    crafted message cannot smuggle instructions into the system prompt).
    ``type_registry_digest`` is the compact, already-safe summary of the project
    type registry (keys + synonyms + per-type param keys) the service builds
    from :mod:`project_types`.
    """
    fenced = fence_user_content(request_text, max_len=2000)
    safe_registry = sanitize_user_text(type_registry_digest, max_len=6000)
    return f"Project type registry:\n{safe_registry}\n\nUser request to classify and extract:\n{fenced}"


INTAKE_QUESTIONS_SYSTEM = (
    "You are a construction-estimating intake assistant phrasing a SMALL batch "
    "of clarification questions for one round of a guided dialogue. You are "
    "given the project type and a fixed list of parameters to ask about this "
    "round (each with its key, kind, unit, and any choices). You MUST ask "
    "exactly those parameters - never add, drop, merge, or invent a parameter, "
    "and never ask more than you were given. You do NOT ask about price, and "
    "you do NOT state any quantity yourself.\n\n"
    "Return ONLY a JSON array, one object per input parameter, in the same "
    "order:\n"
    '  {"param_key": "<echoed key>", "prompt": "<one short human question in '
    "the user's language>\"}\n"
    "Keep each prompt under 120 characters, friendly and concrete (mention the "
    "unit for a number, list the choices for a choice). Do not include any text "
    "outside the JSON array."
)


def build_intake_questions_prompt(*, language: str, params_digest: str) -> str:
    """Render the intake-question phrasing user prompt for one round.

    ``params_digest`` is the safe, service-built summary of the round's
    parameters (key, kind, unit, choices); ``language`` is the user's detected
    language so the model phrases the questions in it.
    """
    safe_lang = sanitize_user_text(language or "en", max_len=8)
    safe_params = sanitize_user_text(params_digest, max_len=4000)
    return f"User language: {safe_lang}\n\nParameters to ask this round:\n{safe_params}"
