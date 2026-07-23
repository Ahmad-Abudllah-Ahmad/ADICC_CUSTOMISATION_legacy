# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-audit orchestration helpers.

Pure, database-free logic that turns the raw validation-engine output over a
finished Bill of Quantities into grouped, actionable audit findings - each with
a concrete one-click fix - and computes the per-position validation-status
roll-up used to accent the estimate grid.

Kept side-effect free (no ORM, no session, no engine) so it is unit-testable
without a database. The :class:`ValidationModuleService` calls these helpers
around a normal engine run.

Finding groups (mirrored in the frontend):

* ``missing_items``   - lines with no quantity, empty sections.
* ``wrong_units``     - lines with no unit of measurement.
* ``duplicates``      - repeated ordinals (a line-number collision).
* ``price_outliers``  - missing rates and rates far above the BOQ median.

Each finding carries at most one concrete fix:

* ``set_rate_to_median``  - write the BOQ median unit rate onto the line.
* ``switch_unit``         - set the line's unit to the BOQ's dominant unit.
* ``merge_duplicate``     - renumber the redundant duplicate lines so ordinals
  become unique again (non-destructive - no line is deleted).
* ``add_companion_line``  - add a first child line under an empty section.
"""

import logging
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# ── Logical rule set + engine expansion ─────────────────────────────────────

#: Logical rule-set name the one-click estimate audit is exposed under. There is
#: no separately-registered ``estimate_audit`` rule body; the audit runs the
#: universal ``boq_quality`` checks (missing quantities, zero / anomalous rates,
#: empty units, duplicate ordinals, empty sections) - exactly the hygiene a
#: finished estimate must pass. :func:`build_rule_sets` expands the logical name
#: to these concrete, registered sets.
ESTIMATE_AUDIT_RULE_SET = "estimate_audit"
_AUDIT_ENGINE_RULE_SETS: tuple[str, ...] = ("boq_quality",)

# ── Finding groups ──────────────────────────────────────────────────────────

GROUP_MISSING = "missing_items"
GROUP_WRONG_UNIT = "wrong_units"
GROUP_DUPLICATE = "duplicates"
GROUP_PRICE_OUTLIER = "price_outliers"

#: Stable display order for the grouped findings panel.
GROUP_ORDER: tuple[str, ...] = (
    GROUP_MISSING,
    GROUP_WRONG_UNIT,
    GROUP_DUPLICATE,
    GROUP_PRICE_OUTLIER,
)

# ── Fix types ───────────────────────────────────────────────────────────────

FIX_SET_RATE = "set_rate_to_median"
FIX_SWITCH_UNIT = "switch_unit"
FIX_MERGE_DUPLICATE = "merge_duplicate"
FIX_ADD_COMPANION = "add_companion_line"
#: Sentinel meaning "no safe one-click fix - review manually".
FIX_NONE = ""

#: Maps an engine ``rule_id`` to ``(group, fix_type)``. Only these rules are
#: surfaced as actionable audit findings; every other engine result is ignored
#: by the audit (it still contributes to the persisted report + score).
_RULE_MAP: dict[str, tuple[str, str]] = {
    "boq_quality.position_has_quantity": (GROUP_MISSING, FIX_NONE),
    "boq_quality.position_has_description": (GROUP_MISSING, FIX_NONE),
    "boq_quality.section_without_items": (GROUP_MISSING, FIX_ADD_COMPANION),
    "boq_quality.empty_unit": (GROUP_WRONG_UNIT, FIX_SWITCH_UNIT),
    "boq_quality.no_duplicate_ordinals": (GROUP_DUPLICATE, FIX_MERGE_DUPLICATE),
    "boq_quality.position_has_unit_rate": (GROUP_PRICE_OUTLIER, FIX_SET_RATE),
    "boq_quality.unit_rate_in_range": (GROUP_PRICE_OUTLIER, FIX_SET_RATE),
    "boq_quality.unrealistic_rate": (GROUP_PRICE_OUTLIER, FIX_SET_RATE),
}

_RULE_DUPLICATE = "boq_quality.no_duplicate_ordinals"

# Validation-status roll-up ranking (worst wins). Mirrors the Position
# ``validation_status`` enum: pending < passed < warnings < errors.
_STATUS_RANK: dict[str, int] = {"pending": 0, "passed": 1, "warnings": 2, "errors": 3}


def build_rule_sets(requested: list[str]) -> list[str]:
    """Expand logical audit rule-set names into concrete engine rule sets.

    ``estimate_audit`` is expanded to the universal ``boq_quality`` set (the
    checks the audit is built on); any already-concrete rule-set name passes
    through unchanged. Order is preserved and duplicates are collapsed so the
    result can be handed straight to the validation engine.

    Args:
        requested: Rule-set names requested by the caller (typically
            ``["estimate_audit"]``).

    Returns:
        The concrete, registered rule-set names to run.
    """
    expanded: list[str] = []
    for name in requested:
        targets = _AUDIT_ENGINE_RULE_SETS if name == ESTIMATE_AUDIT_RULE_SET else (name,)
        for target in targets:
            if target not in expanded:
                expanded.append(target)
    return expanded


# ── Numeric helpers ─────────────────────────────────────────────────────────


def _to_decimal(value: Any) -> Decimal | None:
    """Parse a money/quantity value (str/int/float/Decimal) to ``Decimal``.

    Returns ``None`` for blank or unparseable input so callers can skip it.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _dec_str(value: Decimal) -> str:
    """Format a Decimal as a 2-dp money string (locale-neutral)."""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def median_unit_rate(positions: list[dict[str, Any]]) -> Decimal | None:
    """Median of the positive unit rates across ``positions``.

    Zero / missing / unparseable rates are excluded (they are exactly the lines
    the audit wants to *set*, so they must not drag the median down). Returns
    ``None`` when no priced line exists.
    """
    rates: list[Decimal] = []
    for pos in positions:
        rate = _to_decimal(pos.get("unit_rate"))
        if rate is not None and rate > 0:
            rates.append(rate)
    if not rates:
        return None
    rates.sort()
    mid = len(rates) // 2
    if len(rates) % 2 == 1:
        return rates[mid]
    return (rates[mid - 1] + rates[mid]) / Decimal(2)


def dominant_unit(positions: list[dict[str, Any]]) -> str:
    """Most common non-empty unit of measurement across ``positions``.

    Returns an empty string when no line carries a unit.
    """
    counter: Counter[str] = Counter()
    for pos in positions:
        unit = str(pos.get("unit") or "").strip()
        if unit:
            counter[unit] += 1
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


# ── Result -> position mapping ──────────────────────────────────────────────


def _result_position_ids(result: dict[str, Any]) -> list[str]:
    """Position ids a single engine result refers to.

    Most rules reference one line via ``element_ref``; the duplicate-ordinal
    rule reports every colliding line in ``details.duplicate_ids`` so all of
    them can be accented, not just the first.
    """
    if result.get("rule_id") == _RULE_DUPLICATE and not result.get("passed"):
        details = result.get("details") or {}
        dup_ids = details.get("duplicate_ids")
        if isinstance(dup_ids, list) and dup_ids:
            return [str(d) for d in dup_ids if d]
    ref = result.get("element_ref")
    return [str(ref)] if ref else []


def build_status_map(results: list[dict[str, Any]]) -> dict[str, str]:
    """Roll engine results up into a per-position ``validation_status``.

    Every non-engine-error result contributes: a passing result marks its lines
    ``passed``, a failing ERROR marks them ``errors`` and a failing WARNING/INFO
    marks them ``warnings``. The worst status per line wins, so a line that
    passes one rule but fails another is reported by its most severe finding.

    Args:
        results: Engine result dicts (``rule_id``, ``severity``, ``passed``,
            ``element_ref``, ``details``, ``is_engine_error``).

    Returns:
        Mapping of ``position_id -> status`` for every checked line.
    """
    worst: dict[str, str] = {}
    for result in results:
        if result.get("is_engine_error"):
            continue
        if result.get("passed"):
            status = "passed"
        else:
            status = "errors" if result.get("severity") == "error" else "warnings"
        rank = _STATUS_RANK[status]
        for pid in _result_position_ids(result):
            if rank > _STATUS_RANK.get(worst.get(pid, "pending"), 0):
                worst[pid] = status
    return worst


# ── Fix construction ────────────────────────────────────────────────────────


def _build_fix(
    fix_type: str,
    result: dict[str, Any],
    pos: dict[str, Any],
    median: Decimal | None,
    dom_unit: str,
) -> dict[str, Any] | None:
    """Build the concrete one-click fix payload for a finding, or ``None``.

    ``None`` means the finding has no safe automatic fix and must be reviewed
    by hand (honouring "AI proposes, human confirms").
    """
    if fix_type == FIX_SET_RATE:
        if median is None or median <= 0:
            return None
        return {"type": FIX_SET_RATE, "params": {"unit_rate": _dec_str(median)}}

    if fix_type == FIX_SWITCH_UNIT:
        unit = dom_unit or "pcs"
        return {"type": FIX_SWITCH_UNIT, "params": {"unit": unit}}

    if fix_type == FIX_MERGE_DUPLICATE:
        details = result.get("details") or {}
        dup_ids = [str(d) for d in (details.get("duplicate_ids") or []) if d]
        if len(dup_ids) < 2:
            return None
        return {
            "type": FIX_MERGE_DUPLICATE,
            "params": {
                "keep_position_id": dup_ids[0],
                "duplicate_position_ids": dup_ids[1:],
            },
        }

    if fix_type == FIX_ADD_COMPANION:
        section_id = pos.get("id") or result.get("element_ref")
        if not section_id:
            return None
        params: dict[str, Any] = {
            "section_id": str(section_id),
            "unit": dom_unit or "pcs",
            "quantity": 1,
        }
        if median is not None and median > 0:
            params["unit_rate"] = _dec_str(median)
        return {"type": FIX_ADD_COMPANION, "params": params}

    return None


def build_findings(
    results: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn failing engine results into grouped, actionable audit findings.

    Args:
        results: Engine result dicts from a ``boq_quality`` run.
        positions: The BOQ positions in loader dict form (``id``, ``ordinal``,
            ``description``, ``unit``, ``unit_rate`` ...), used to compute the
            suggested median rate / dominant unit and to enrich each finding.

    Returns:
        A list of finding dicts, blocking errors first, each with an optional
        ``fix`` payload.
    """
    median = median_unit_rate(positions)
    dom_unit = dominant_unit(positions)
    pos_by_id = {str(p.get("id")): p for p in positions if p.get("id")}

    findings: list[dict[str, Any]] = []
    for result in results:
        if result.get("passed") or result.get("is_engine_error"):
            continue
        mapping = _RULE_MAP.get(str(result.get("rule_id")))
        if mapping is None:
            continue
        group, fix_type = mapping
        element_ref = result.get("element_ref")
        pos = pos_by_id.get(str(element_ref), {}) if element_ref else {}
        fix = _build_fix(fix_type, result, pos, median, dom_unit)
        findings.append(
            {
                "id": f"{result.get('rule_id')}:{element_ref or ''}",
                "group": group,
                "rule_id": result.get("rule_id"),
                "severity": result.get("severity") or "warning",
                "message": result.get("message") or "",
                "ordinal": pos.get("ordinal") or "",
                "description": pos.get("description") or "",
                "position_id": str(element_ref) if element_ref else None,
                "position_ids": _result_position_ids(result),
                "fix": fix,
            }
        )

    findings.sort(key=lambda f: 0 if f["severity"] == "error" else 1)
    return findings


def summarize_groups(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-group summary (key, count, worst severity) in stable display order."""
    buckets: dict[str, dict[str, Any]] = {}
    for finding in findings:
        group = finding["group"]
        bucket = buckets.setdefault(group, {"key": group, "count": 0, "severity": "warning"})
        bucket["count"] += 1
        if finding["severity"] == "error":
            bucket["severity"] = "error"
    return [buckets[g] for g in GROUP_ORDER if g in buckets]


def build_position_audit_meta(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compact per-position finding summary for ``Position.metadata.audit``.

    Args:
        findings: Findings from :func:`build_findings`.

    Returns:
        Mapping ``position_id -> {"groups": [...], "count": N}`` covering every
        line touched by a finding (duplicate lines included).
    """
    meta: dict[str, dict[str, Any]] = {}
    for finding in findings:
        pids = finding.get("position_ids") or ([finding["position_id"]] if finding.get("position_id") else [])
        for pid in pids:
            if not pid:
                continue
            entry = meta.setdefault(str(pid), {"groups": [], "count": 0})
            if finding["group"] not in entry["groups"]:
                entry["groups"].append(finding["group"])
            entry["count"] += 1
    return meta
