# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Extract and apply BOQ-position proposals from a finished agent run.

The BOQ-drafter agent's whole value is "turn a scope brief into priced BOQ
positions". The runner emits each line item as a ``create_position`` tool
observation (a ``boq_position_proposal`` dict: description, unit, qty,
unit_rate, total, currency) during the ReAct loop, but the run's
``final_output`` is a human markdown summary - so the structured proposals
were computed and then thrown away. Nothing ever turned them into real BOQ
rows; the UI could only deep-link to the BOQ editor and ask the user to
re-type every line by hand.

This module closes that gap WITHOUT crossing the "AI-augmented,
human-confirmed" line:

* :func:`extract_proposals` recovers the structured proposals from a run's
  persisted steps (the ``create_position`` observations), falling back to a
  JSON ``final_output`` when an agent emitted the proposals there instead.
  It NEVER fabricates a line - it only surfaces what the agent already
  produced and grounded in the cost database.
* :func:`apply_proposals_to_boq` is invoked only when the user explicitly
  clicks Apply against a BOQ they can access. It creates REAL positions
  through the BOQ module's own ``add_position`` service (so locking, ordinal
  uniqueness, totals, and provenance stamping all behave exactly as a manual
  add would), tags each line ``source="ai_match"`` with the run id, and
  refuses to silently blend currencies.

Money rule: a proposal with no ISO currency code, or a target BOQ whose
project currency differs from the proposal's, is reported as skipped with a
reason rather than applied with a wrong or missing currency.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# Marker the BOQ-drafter's ``create_position`` tool stamps on every proposal.
PROPOSAL_KIND = "boq_position_proposal"

# Hard cap on how many positions a single Apply will create, so a runaway
# proposal list (or a forged final_output) can never spam thousands of rows
# into a BOQ in one click. The user can run the agent again for more.
MAX_APPLY_POSITIONS = 200


@dataclass
class PositionProposal:
    """One structured BOQ-position proposal recovered from a run.

    Mirrors the ``boq_position_proposal`` payload the drafter's
    ``create_position`` tool produces. ``currency`` is the ISO 4217 code of
    ``unit_rate`` (never blended across proposals).
    """

    description: str
    unit: str
    qty: float
    unit_rate: Decimal
    currency: str
    total: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "unit": self.unit,
            "qty": self.qty,
            "unit_rate": str(self.unit_rate),
            "currency": self.currency,
            "total": str(self.total),
        }


@dataclass
class ApplyOutcome:
    """Result of applying a run's proposals to a BOQ."""

    created: int = 0
    skipped: int = 0
    currency: str | None = None
    created_ordinals: list[str] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _coerce_proposal(raw: Any) -> PositionProposal | None:
    """Turn a candidate dict into a :class:`PositionProposal`, or None.

    A candidate must at least carry a non-empty description and a unit; a
    proposal with neither is noise (e.g. a warning-only observation) and is
    dropped. ``qty``/``unit_rate``/``total`` are coerced defensively.
    """
    if not isinstance(raw, dict):
        return None
    description = str(raw.get("description") or "").strip()
    unit = str(raw.get("unit") or "").strip()
    if not description or not unit:
        return None
    qty = _to_float(raw.get("qty") if raw.get("qty") is not None else raw.get("quantity"))
    unit_rate = _to_decimal(raw.get("unit_rate") if raw.get("unit_rate") is not None else raw.get("rate"))
    currency = str(raw.get("currency") or "").strip().upper()
    # Trust an explicit total when present and numeric, else derive it exactly.
    total_raw = raw.get("total")
    total = _to_decimal(total_raw) if total_raw not in (None, "") else (Decimal(str(qty)) * unit_rate)
    return PositionProposal(
        description=description,
        unit=unit,
        qty=qty,
        unit_rate=unit_rate,
        currency=currency,
        total=total,
    )


def _candidates_from_object(obj: dict[str, Any]) -> list[Any]:
    """Pull a proposal list out of a dict (single proposal or wrapper)."""
    # A single proposal object?
    if obj.get("kind") == PROPOSAL_KIND or ("description" in obj and "unit" in obj):
        return [obj]
    # A wrapper carrying a list under a common key.
    for key in ("positions", "proposals", "items"):
        arr = obj.get(key)
        if isinstance(arr, list):
            return arr
    return []


def extract_proposals(steps: list[Any], final_output: str | None) -> list[PositionProposal]:
    """Recover the structured BOQ-position proposals a run produced.

    Primary source: every ``observation`` step whose content is a
    ``boq_position_proposal`` dict (what ``create_position`` returns). These
    are the proposals the agent actually grounded in the cost database, so they
    are authoritative.

    Fallback: when no proposal observations exist (an agent that emitted the
    structured list in its final answer instead), parse a JSON ``final_output``
    for a proposal / proposal list. A markdown final answer yields nothing here
    - and that is correct: there is nothing structured to apply.

    The two sources are mutually exclusive in practice; if both are present the
    observation steps win (they are the grounded source). De-duplicates on
    (description, unit, unit_rate) so a re-issued ``create_position`` for the
    same line is not applied twice.

    Args:
        steps: the run's persisted :class:`AgentStep` rows (any order; only
            ``role``/``content`` are read).
        final_output: the run's final markdown/JSON answer.

    Returns:
        The recovered proposals (possibly empty), de-duplicated, in order.
    """
    found: list[PositionProposal] = []

    for step in steps:
        if getattr(step, "role", None) != "observation":
            continue
        content = getattr(step, "content", None)
        if isinstance(content, dict) and content.get("kind") == PROPOSAL_KIND:
            prop = _coerce_proposal(content)
            if prop is not None:
                found.append(prop)

    if not found and final_output:
        trimmed = final_output.strip()
        if trimmed.startswith("{") or trimmed.startswith("["):
            try:
                parsed = json.loads(trimmed)
            except (ValueError, TypeError):
                parsed = None
            candidates: list[Any] = []
            if isinstance(parsed, list):
                candidates = parsed
            elif isinstance(parsed, dict):
                candidates = _candidates_from_object(parsed)
            for c in candidates:
                prop = _coerce_proposal(c)
                if prop is not None:
                    found.append(prop)

    # De-dupe on the line's identity so a model that re-emitted the same
    # create_position call does not produce two identical BOQ rows.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[PositionProposal] = []
    for p in found:
        key = (p.description.lower(), p.unit.lower(), str(p.unit_rate))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def proposal_currencies(proposals: list[PositionProposal]) -> set[str]:
    """The distinct non-empty ISO currency codes across the proposals."""
    return {p.currency for p in proposals if p.currency}


async def apply_proposals_to_boq(
    *,
    session: Any,
    proposals: list[PositionProposal],
    boq_id: uuid.UUID,
    run_id: uuid.UUID,
    project_currency: str,
) -> ApplyOutcome:
    """Create real BOQ positions from a run's proposals into ``boq_id``.

    Each proposal is created through the BOQ module's own
    ``BOQService.add_position`` so every invariant a manual add enforces
    (BOQ-lock check, ordinal uniqueness, total = qty x rate, provenance
    stamping) is honoured - we never write the Position table directly.

    Money guard: a proposal is SKIPPED (not applied) when it carries no
    currency code, or when its currency differs from the target BOQ's project
    currency. Applying a EUR rate into a USD project, or an un-priced line,
    would corrupt the BOQ's totals (currencies must never be blended), so we
    surface the skip with a reason instead.

    Each created position is tagged ``source="ai_match"`` with
    ``confidence`` and a ``metadata.ai_agent_run_id`` back-link so the line is
    traceable to the run that proposed it.

    Args:
        session: the active async session (the caller owns commit/rollback).
        proposals: the proposals to apply (already extracted from the run).
        boq_id: the target BOQ. Caller must have verified access.
        run_id: the run the proposals came from (stamped into metadata).
        project_currency: the BOQ's project base currency (ISO 4217), used to
            reject cross-currency applies.

    Returns:
        An :class:`ApplyOutcome` summarising created vs skipped lines.
    """
    from app.modules.boq.schemas import PositionCreate
    from app.modules.boq.service import BOQService

    boq_service = BOQService(session)
    outcome = ApplyOutcome()

    base_currency = (project_currency or "").strip().upper()
    # The currency we will actually apply: the project's when known, else the
    # single shared currency of the proposals. A mixed-currency proposal set is
    # never applied wholesale (each off-currency line is skipped below).
    applied_currency = base_currency or (
        next(iter(proposal_currencies(proposals))) if len(proposal_currencies(proposals)) == 1 else None
    )
    outcome.currency = applied_currency

    # Seed the ordinal counter from the existing position count so we never
    # collide with manual rows; add_position still 409-guards, and we retry on
    # the (rare) race by bumping the suffix.
    existing = await boq_service.position_repo.get_max_sort_order(boq_id)
    ordinal_seq = max(existing + 1, 1)

    for prop in proposals[:MAX_APPLY_POSITIONS]:
        # ── Money guards ──────────────────────────────────────────────────
        if not prop.currency:
            outcome.skipped += 1
            outcome.skipped_reasons.append(f"'{prop.description[:60]}' has no currency code")
            continue
        if base_currency and prop.currency != base_currency:
            outcome.skipped += 1
            outcome.skipped_reasons.append(
                f"'{prop.description[:60]}' is in {prop.currency}, project is {base_currency}"
            )
            continue

        # Find a free ordinal in this BOQ (auto-numbered AI block).
        ordinal = await _next_free_ordinal(boq_service, boq_id, ordinal_seq)
        ordinal_seq += 1

        try:
            await boq_service.add_position(
                PositionCreate(
                    boq_id=boq_id,
                    ordinal=ordinal,
                    description=prop.description,
                    unit=prop.unit,
                    quantity=prop.qty,
                    unit_rate=prop.unit_rate,
                    source="ai_match",
                    confidence=0.6,
                    metadata={
                        "currency": prop.currency,
                        "ai_agent_run_id": str(run_id),
                        "ai_proposed": True,
                    },
                )
            )
            outcome.created += 1
            outcome.created_ordinals.append(ordinal)
        except Exception as exc:  # noqa: BLE001 - one bad line never aborts the rest
            logger.warning("apply_proposals: position '%s' failed: %s", prop.description[:60], exc)
            outcome.skipped += 1
            detail = getattr(exc, "detail", None) or str(exc)
            outcome.skipped_reasons.append(f"'{prop.description[:60]}' could not be added ({detail})")

    return outcome


async def _next_free_ordinal(boq_service: Any, boq_id: uuid.UUID, start: int) -> str:
    """Return an ordinal not yet used in the BOQ, scanning up from ``start``.

    AI-applied lines are numbered ``AI.<n>`` so they read as one cohesive block
    and never clash with a user's hand-typed ``01.02.003`` ordinals. Bounded so
    a pathological collision streak cannot loop forever.
    """
    n = max(start, 1)
    for _ in range(MAX_APPLY_POSITIONS + 50):
        candidate = f"AI.{n}"
        if not await boq_service.position_repo.ordinal_exists(boq_id, candidate):
            return candidate
        n += 1
    # Extremely unlikely fallback: a UUID-suffixed ordinal is guaranteed unique.
    return f"AI.{uuid.uuid4().hex[:8]}"
