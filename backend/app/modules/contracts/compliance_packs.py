# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Compliance rule packs for contract gates.

A *rule pack* is a jurisdiction-scoped bundle of validation rule-SET ids
(the same set names the core :class:`ValidationEngine` already knows -
``boq_quality``, ``din276``, ``gaeb``, ``nrm``, ``masterformat`` …). Each
pack also declares which workflow gates enforce it (currently only
``contract_signature``).

These packs are deterministic seed data, not user-authored DSL - they map a
project's region to a concrete, runnable set of validation rules so the
compliance gate that runs on a contract ``draft → active`` transition has
something real to execute. A project picks which packs it enforces via the
``Project.compliance_rule_packs`` JSON column; the gate resolves the union
of every pack's ``rule_sets`` and feeds them to the validation engine.

Design choices:
    * ``rule_sets`` reference rule sets that genuinely exist in the engine's
      registry. Unknown set names are simply skipped by the engine
      (``get_rules_for_sets`` ignores them), so a pack can declare an
      aspirational set without crashing - but the shipped packs only list
      sets we actually register, so the gate always evaluates real rules.
    * The ``universal`` pack is the safe default for any project with no
      region match - it enforces the cross-market ``boq_quality`` rule set.
    * Region → pack auto-mapping is a *suggestion*; projects can override.
"""

from __future__ import annotations

from typing import Any

# ── Workflow gate identifiers ──────────────────────────────────────────────

WORKFLOW_CONTRACT_SIGNATURE = "contract_signature"


# ── Pack registry ──────────────────────────────────────────────────────────
#
# ``rule_sets`` are the names the ValidationEngine resolves via
# ``rule_registry.get_rules_for_sets``. Keep every entry pointing at a set
# that is registered in app.core.validation.rules so the gate always runs
# real checks.

RULE_PACKS: dict[str, dict[str, Any]] = {
    "universal": {
        "id": "universal",
        "name": "Universal Compliance",
        "description": "Cross-market quality and completeness checks applied "
        "to the contract's schedule of values before signature.",
        "jurisdiction": None,
        "enforced_workflows": [WORKFLOW_CONTRACT_SIGNATURE],
        "rule_sets": ["boq_quality"],
    },
    "de_compliance": {
        "id": "de_compliance",
        "name": "Germany / DACH Compliance",
        "description": "DIN 276 cost-group structure and GAEB tender-format "
        "checks plus the universal quality baseline.",
        "jurisdiction": "DE",
        "enforced_workflows": [WORKFLOW_CONTRACT_SIGNATURE],
        "rule_sets": ["boq_quality", "din276", "gaeb"],
    },
    "uk_compliance": {
        "id": "uk_compliance",
        "name": "United Kingdom Compliance",
        "description": "NRM measurement-rule compliance plus the universal quality baseline.",
        "jurisdiction": "GB",
        "enforced_workflows": [WORKFLOW_CONTRACT_SIGNATURE],
        "rule_sets": ["boq_quality", "nrm"],
    },
    "us_compliance": {
        "id": "us_compliance",
        "name": "United States Compliance",
        "description": "MasterFormat classification checks plus the universal quality baseline.",
        "jurisdiction": "US",
        "enforced_workflows": [WORKFLOW_CONTRACT_SIGNATURE],
        "rule_sets": ["boq_quality", "masterformat"],
    },
    "mx_compliance": {
        "id": "mx_compliance",
        "name": "Mexico Compliance",
        "description": "APU unit-price completeness, IVA and CFDI invoicing, and "
        "subcontract retencion checks for LOPSRM public works plus the "
        "universal quality baseline.",
        "jurisdiction": "MX",
        "enforced_workflows": [WORKFLOW_CONTRACT_SIGNATURE],
        "rule_sets": ["boq_quality", "mexico"],
    },
}

#: Default pack every project falls back to when nothing else matches.
DEFAULT_PACK_ID = "universal"

#: Coarse region tag → pack suggestion. Regions in this product are coarse
#: (``DACH`` / ``UK`` / ``US`` / ``EU`` …) so we match case-insensitively on
#: a prefix substring rather than an exact code. Used only to seed a new
#: project's default selection - never to override an explicit choice.
_REGION_PACK_HINTS: tuple[tuple[str, str], ...] = (
    ("dach", "de_compliance"),
    ("germany", "de_compliance"),
    ("de", "de_compliance"),
    ("austria", "de_compliance"),
    ("uk", "uk_compliance"),
    ("united kingdom", "uk_compliance"),
    ("gb", "uk_compliance"),
    ("britain", "uk_compliance"),
    ("us", "us_compliance"),
    ("usa", "us_compliance"),
    ("united states", "us_compliance"),
    ("america", "us_compliance"),
    ("mx", "mx_compliance"),
    ("mexico", "mx_compliance"),
    ("méxico", "mx_compliance"),
)


def get_rule_pack(pack_id: str) -> dict[str, Any] | None:
    """Return the rule-pack definition for ``pack_id`` (or ``None``)."""
    return RULE_PACKS.get(pack_id)


def list_rule_packs() -> list[dict[str, Any]]:
    """Return every known rule pack as a list (stable order)."""
    return list(RULE_PACKS.values())


def valid_pack_ids(pack_ids: list[str]) -> list[str]:
    """Filter ``pack_ids`` down to the ones that actually exist.

    Order-preserving and de-duplicating. Used to validate a project's
    requested pack selection before persisting it so a typo never silently
    disables the gate.
    """
    seen: set[str] = set()
    out: list[str] = []
    for pid in pack_ids:
        if pid in RULE_PACKS and pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def suggest_pack_for_region(region: str | None) -> str:
    """Suggest a single default pack id for a coarse ``region`` tag.

    Falls back to :data:`DEFAULT_PACK_ID` when nothing matches. Pure and
    deterministic - case-insensitive prefix/substring match against
    :data:`_REGION_PACK_HINTS`.
    """
    if not region:
        return DEFAULT_PACK_ID
    needle = region.strip().lower()
    for token, pack_id in _REGION_PACK_HINTS:
        if token in needle:
            return pack_id
    return DEFAULT_PACK_ID


def resolve_rule_sets(
    pack_ids: list[str],
    *,
    workflow: str = WORKFLOW_CONTRACT_SIGNATURE,
) -> list[str]:
    """Resolve the union of validation rule-set names for ``pack_ids``.

    Only packs that enforce ``workflow`` contribute their rule sets. Unknown
    pack ids are skipped. The result is order-preserving and de-duplicated so
    the validation engine receives a clean, stable list.
    """
    seen: set[str] = set()
    out: list[str] = []
    for pid in pack_ids:
        pack = RULE_PACKS.get(pid)
        if pack is None:
            continue
        if workflow not in pack.get("enforced_workflows", []):
            continue
        for rs in pack.get("rule_sets", []):
            if rs not in seen:
                seen.add(rs)
                out.append(rs)
    return out
