# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Phase-1 node runners for the Pipeline Builder.

This file is autodiscovered by the module loader (the same mechanism it
uses for ``hooks.py`` / ``events.py``): importing it at module-load time
registers every Phase-1 node type into the global Node Capability
Registry. The executor only ever calls *registered* runners (§3.5).

The spine ``trigger.manual → source.boq → gate.validation →
action.export.excel`` plus a wider working set of estimator-facing nodes:

    trigger.manual        entry / no-op seed
    source.project        load project meta (IDs + name only)
    source.boq            load a project's BOQ positions (IDs + counts +
                          a small sample - NEVER the full universe)
    source.cost_catalog   load priced cost-catalog items as rows
    transform.filter      filter the upstream rows by a simple predicate
    transform.markup      raise / discount every unit rate by a percent
    transform.aggregate   group rows by a field and total each group
    transform.rollup      sum quantity x unit_rate into one total
    transform.sort        order rows by a field (numeric or alphabetic)
    transform.limit       keep only the first N rows (top-N with sort)
    transform.dedupe      drop rows repeating a value in a key field
    gate.validation       run the validation engine; continue unless errors
    gate.budget           stop the run if the total exceeds a budget ceiling
    gate.completeness     flag / stop on rows missing a quantity or a rate
    gate.count            stop the run unless the row count is in range
    flow.merge            combine the rows from two branches into one set
    action.export.excel   reuse the existing openpyxl util → a file ref
                          (side_effecting=False - it writes a file, not DB)
    action.export.csv     write the rows to a .csv file reference

Aggregates, totals and gates compute over the FULL row set: a BOQ
envelope carries ``row_ids`` and ``_resolve_full_rows`` re-reads the
positions, so a total is never just the 25-row preview. Money stays
Decimal-as-string end to end. Every envelope still obeys §3.2 hard rule
1: IDs + small previews on the wire, the big payload stays in its table.
"""

from __future__ import annotations

import io
import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.core.pipeline.registry import NodeContext, register_node

logger = logging.getLogger(__name__)

MODULE = "oe_pipelines"

# A small, bounded sample size - never stream the element universe through
# the run rows (this is what protects the 2 GB-RAM / SQLite target).
_SAMPLE_LIMIT = 25
# Hard cap on the id-list that node-state envelopes can carry. Without
# this a 100k-position project would JSON-encode 100k UUIDs into the
# oe_pipeline_node_state.output column on every node hop - a slow
# memory-bomb. ``count`` keeps the honest cardinality.
_ROW_IDS_CAP = 5000


def _resolve_project_id(ctx: NodeContext) -> uuid.UUID | None:
    """Resolve the project id from node params or the run scope."""
    raw = ctx.params.get("project_id") or ctx.project_id
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


# ── money / row helpers (Decimal-as-string end to end) ───────────────────


def _to_decimal(value: Any) -> Decimal | None:
    """Parse a money / quantity value into a Decimal, or None.

    Accepts the platform's Decimal-as-string wire values, native Decimals
    (as they come straight off an ORM row) and ints; anything blank or
    non-numeric returns None so callers can decide the fallback. The value
    is never rounded here - precision is preserved.
    """
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _line_total(row: dict[str, Any]) -> Decimal:
    """quantity x unit_rate for a row, treating missing parts as zero."""
    qty = _to_decimal(row.get("quantity")) or Decimal(0)
    rate = _to_decimal(row.get("unit_rate")) or Decimal(0)
    return qty * rate


def _row_value(row: dict[str, Any], path: str) -> Any:
    """Read a possibly dotted key path from a row (e.g. ``classification.din276``)."""
    cur: Any = row
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


async def _resolve_full_rows(ctx: NodeContext, upstream: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the full row set behind an envelope, not just the wire sample.

    A node only receives a bounded ``rows`` preview on the wire, but a BOQ
    envelope also carries ``row_ids`` (the real, capped universe). So an
    aggregate / total / gate can re-read the full positions from the
    database and compute over every row rather than the 25-row sample.

    Order of preference:
      1. ``mutated`` envelopes (a what-if transform such as markup changed
         the values in place) - use the rows as given, re-reading the DB
         would throw the change away.
      2. ``row_ids`` present - re-read those BOQ positions in full.
      3. otherwise - fall back to the wire sample (e.g. a non-BOQ source).
    """
    if upstream.get("mutated"):
        return list(upstream.get("rows") or [])
    row_ids = upstream.get("row_ids") or []
    if not row_ids:
        return list(upstream.get("rows") or [])

    from app.modules.boq.models import Position

    ids: list[uuid.UUID] = []
    for rid in row_ids:
        try:
            ids.append(uuid.UUID(str(rid)))
        except (ValueError, TypeError):
            continue
    if not ids:
        return list(upstream.get("rows") or [])

    positions = (await ctx.db.execute(select(Position).where(Position.id.in_(ids)))).scalars().all()
    return [
        {
            "id": str(p.id),
            "ordinal": p.ordinal,
            "description": p.description,
            "unit": p.unit,
            "quantity": p.quantity,
            "unit_rate": p.unit_rate,
            "classification": dict(p.classification or {}),
        }
        for p in positions
    ]


# ── trigger.manual ───────────────────────────────────────────────────────


async def _run_trigger_manual(ctx: NodeContext) -> dict[str, Any]:
    """Entry node - seeds the run with the trigger context. No I/O."""
    return {
        "trigger": "manual",
        "actor_id": ctx.actor_id,
        "summary": "Manual run started",
    }


# ── source.project ───────────────────────────────────────────────────────


async def _run_source_project(ctx: NodeContext) -> dict[str, Any]:
    """Load minimal project metadata (id + name)."""
    from app.modules.projects.models import Project

    pid = _resolve_project_id(ctx)
    if pid is None:
        return {"project": None, "summary": "No project bound"}
    project = await ctx.db.get(Project, pid)
    if project is None:
        return {"project": None, "summary": f"Project {pid} not found"}
    return {
        "project": {"id": str(project.id), "name": project.name},
        "summary": f"Project: {project.name}",
    }


# ── source.boq ───────────────────────────────────────────────────────────


async def _run_source_boq(ctx: NodeContext) -> dict[str, Any]:
    """Load a project's BOQ positions as rows (IDs + counts + sample).

    The envelope carries ``row_ids`` (every position id) so a downstream
    write node can act on the full set, plus a bounded ``sample`` for the
    UI preview. The full Position payload stays in ``oe_boq_position``.
    """
    from app.modules.boq.models import BOQ, Position

    pid = _resolve_project_id(ctx)
    if pid is None:
        return {"rows": [], "row_ids": [], "count": 0, "summary": "No project"}

    boq_ids = (await ctx.db.execute(select(BOQ.id).where(BOQ.project_id == pid))).scalars().all()
    if not boq_ids:
        return {"rows": [], "row_ids": [], "count": 0, "summary": "No BOQ"}

    positions = (
        (await ctx.db.execute(select(Position).where(Position.boq_id.in_(boq_ids)).order_by(Position.sort_order.asc())))
        .scalars()
        .all()
    )
    rows = [
        {
            "id": str(p.id),
            "ordinal": p.ordinal,
            "description": p.description,
            "unit": p.unit,
            "quantity": p.quantity,
            "unit_rate": p.unit_rate,
            "classification": dict(p.classification or {}),
        }
        for p in positions
    ]
    all_ids = [r["id"] for r in rows]
    return {
        "rows": rows[:_SAMPLE_LIMIT],
        "row_ids": all_ids[:_ROW_IDS_CAP],
        "row_ids_truncated": len(all_ids) > _ROW_IDS_CAP,
        "count": len(rows),
        "sample_truncated": len(rows) > _SAMPLE_LIMIT,
        "summary": f"{len(rows)} BOQ positions across {len(boq_ids)} BOQ(s)",
    }


# ── transform.filter ─────────────────────────────────────────────────────


def _matches(row: dict[str, Any], field: str, op: str, value: Any) -> bool:
    """Tiny, safe predicate - no eval, just a fixed operator set."""
    actual = row.get(field)
    if op in ("eq", "=="):
        return actual == value
    if op in ("ne", "!="):
        return actual != value
    if op == "contains":
        return value is not None and str(value).lower() in str(actual).lower()
    if op in ("gt", "gte", "lt", "lte"):
        try:
            a = float(actual)
            b = float(value)
        except (TypeError, ValueError):
            return False
        return {
            "gt": a > b,
            "gte": a >= b,
            "lt": a < b,
            "lte": a <= b,
        }[op]
    if op == "exists":
        return actual not in (None, "", [], {})
    return False


async def _run_transform_filter(ctx: NodeContext) -> dict[str, Any]:
    """Keep upstream rows matching a simple ``{field, op, value}`` predicate.

    Params: ``field`` (str), ``op`` (eq|ne|contains|gt|gte|lt|lte|exists),
    ``value`` (any). An empty predicate is an identity pass-through.
    """
    upstream = ctx.first_input()
    rows: list[dict[str, Any]] = list(upstream.get("rows") or [])
    field = ctx.params.get("field")
    op = ctx.params.get("op", "eq")
    value = ctx.params.get("value")

    if not field:
        kept = rows
    else:
        kept = [r for r in rows if _matches(r, field, op, value)]

    kept_ids = [r.get("id") for r in kept if r.get("id")]
    return {
        "rows": kept[:_SAMPLE_LIMIT],
        "row_ids": kept_ids[:_ROW_IDS_CAP],
        "row_ids_truncated": len(kept_ids) > _ROW_IDS_CAP,
        "count": len(kept),
        "dropped": len(rows) - len(kept),
        "summary": (
            f"Kept {len(kept)} of {len(rows)} rows ({field} {op} {value!r})"
            if field
            else f"Pass-through ({len(rows)} rows)"
        ),
    }


# ── gate.validation ──────────────────────────────────────────────────────


async def _run_gate_validation(ctx: NodeContext) -> dict[str, Any]:
    """Run the validation engine over the upstream rows.

    Params: ``rule_sets`` (list[str], default ``["boq_quality"]``). The
    gate *continues* (status ``done``) unless the report has blocking
    errors, in which case it raises so the run records an error and every
    downstream (write) node is skipped - the structural "AI proposes,
    human confirms" contract enforced at run time.
    """
    from app.core.validation.engine import validation_engine

    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    rule_sets = ctx.params.get("rule_sets") or ["boq_quality"]

    report = await validation_engine.validate(
        data={"positions": rows},
        rule_sets=list(rule_sets),
        target_type="pipeline.gate",
    )
    summary = report.summary()
    if report.has_errors:
        msgs = "; ".join(r.message for r in report.errors[:5])
        raise ValueError(f"Validation gate failed ({summary['counts']}): {msgs}")

    # Pass the rows through unchanged so a downstream action still has them.
    return {
        "rows": rows[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": len(rows),
        "validation": summary,
        "summary": (
            f"Validation {summary['status']} (score={summary['score']}, warnings={summary['counts']['warnings']})"
        ),
    }


# ── action.export.excel ──────────────────────────────────────────────────


async def _run_action_export_excel(ctx: NodeContext) -> dict[str, Any]:
    """Export the upstream rows to an .xlsx using the EXISTING openpyxl dep.

    No new dependency (LIGHTWEIGHT is a hard rule): ``openpyxl`` is already
    used by ``boq.cad_import`` / ``requirements.excel_io`` / many routers.
    ``side_effecting=False`` - it produces a downloadable file, it does not
    mutate any DB row, so it does not require a preceding gate.
    """
    import openpyxl

    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    columns = ctx.params.get("columns") or [
        "ordinal",
        "description",
        "unit",
        "quantity",
        "unit_rate",
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append([str(c) for c in columns])
    for r in rows:
        ws.append([r.get(c, "") for c in columns])

    buf = io.BytesIO()
    wb.save(buf)
    size = buf.tell()

    # The bytes themselves are NOT put on the wire (§3.2). We return a
    # reference + metadata; a later phase persists the buffer to MinIO /
    # the file store and swaps this for a real download URL.
    return {
        "file": {
            "filename": ctx.params.get("filename", "pipeline-export.xlsx"),
            "content_type": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "size_bytes": size,
            "row_count": len(rows),
            "columns": list(columns),
        },
        "summary": f"Exported {len(rows)} rows → Excel ({size} bytes)",
    }


# ── source.cost_catalog ──────────────────────────────────────────────────


async def _run_source_cost_catalog(ctx: NodeContext) -> dict[str, Any]:
    """Load cost-catalog items as rows (code, description, unit, rate).

    Params: ``query`` (optional text match on code or description),
    ``limit`` (optional int, default 200). Rates cross the wire as
    Decimal-as-string, like every other money value. Lets a pipeline pull
    priced reference items to compare against or price a BOQ from.
    """
    from app.modules.costs.models import CostItem

    query = (ctx.params.get("query") or "").strip()
    try:
        limit = int(ctx.params.get("limit") or 200)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, _ROW_IDS_CAP))

    stmt = select(CostItem)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(CostItem.code.ilike(like) | CostItem.description.ilike(like))
    stmt = stmt.order_by(CostItem.code.asc()).limit(limit)

    items = (await ctx.db.execute(stmt)).scalars().all()
    rows = [
        {
            "id": str(it.id),
            "code": it.code,
            "description": it.description,
            "unit": it.unit,
            "unit_rate": it.rate,
            "currency": it.currency,
            "classification": dict(it.classification or {}),
        }
        for it in items
    ]
    all_ids = [r["id"] for r in rows]
    return {
        "rows": rows[:_SAMPLE_LIMIT],
        "row_ids": all_ids[:_ROW_IDS_CAP],
        "count": len(rows),
        "sample_truncated": len(rows) > _SAMPLE_LIMIT,
        "summary": (f"{len(rows)} cost items" + (f" matching '{query}'" if query else "")),
    }


# ── transform.markup ─────────────────────────────────────────────────────


async def _run_transform_markup(ctx: NodeContext) -> dict[str, Any]:
    """Apply a percentage markup (or discount) to every row's unit rate.

    Params: ``percent`` (number, negative = discount). Recomputes each
    row's ``total`` from the new rate. A what-if transform: it changes the
    rows in place (``mutated``) for preview and downstream totals, it does
    not write back to the BOQ. Money stays Decimal-as-string.
    """
    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    pct = _to_decimal(ctx.params.get("percent")) or Decimal(0)
    factor = Decimal(1) + pct / Decimal(100)

    out: list[dict[str, Any]] = []
    for r in rows:
        new = dict(r)
        rate = _to_decimal(r.get("unit_rate"))
        if rate is not None:
            new_rate = rate * factor
            new["unit_rate"] = str(new_rate)
            qty = _to_decimal(r.get("quantity"))
            if qty is not None:
                new["total"] = str(qty * new_rate)
        out.append(new)

    return {
        "rows": out[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": upstream.get("count", len(out)),
        "mutated": True,
        "markup_percent": str(pct),
        "summary": f"Applied {pct}% markup to {len(out)} sample rows",
    }


# ── transform.aggregate ──────────────────────────────────────────────────


async def _run_transform_aggregate(ctx: NodeContext) -> dict[str, Any]:
    """Group rows by a field and sum quantity x unit_rate per group.

    Params: ``group_by`` (a row key, dotted for nested e.g.
    ``classification.din276``; default ``unit``). Computes over the FULL
    row set (re-reading the BOQ when the envelope carries ids), so the
    breakdown reflects every position, not just the sample.
    """
    upstream = ctx.first_input()
    rows = await _resolve_full_rows(ctx, upstream)
    group_by = ctx.params.get("group_by") or "unit"

    buckets: dict[str, dict[str, Any]] = {}
    grand = Decimal(0)
    for r in rows:
        key = _row_value(r, group_by)
        key_str = "(none)" if key in (None, "") else str(key)
        bucket = buckets.setdefault(key_str, {"group": key_str, "count": 0, "_total": Decimal(0)})
        bucket["count"] += 1
        line = _line_total(r)
        bucket["_total"] += line
        grand += line

    grouped = sorted(buckets.values(), key=lambda b: b["_total"], reverse=True)
    out_rows = [{"group": b["group"], "count": b["count"], "total": str(b["_total"])} for b in grouped]
    return {
        "rows": out_rows[:_SAMPLE_LIMIT],
        "count": len(out_rows),
        "group_by": group_by,
        "grand_total": str(grand),
        "row_count": len(rows),
        "mutated": True,
        "summary": (f"{len(out_rows)} groups by '{group_by}' over {len(rows)} rows, total {grand}"),
    }


# ── transform.rollup ─────────────────────────────────────────────────────


async def _run_transform_rollup(ctx: NodeContext) -> dict[str, Any]:
    """Sum quantity x unit_rate across all rows into a single total.

    Computes over the FULL row set (re-reads the BOQ when the envelope
    carries ids). Emits one summary row plus a ``total`` on the envelope so
    a gate or export downstream can use it. Money stays Decimal-as-string.
    """
    upstream = ctx.first_input()
    rows = await _resolve_full_rows(ctx, upstream)

    total = Decimal(0)
    priced = 0
    for r in rows:
        line = _line_total(r)
        total += line
        if line != 0:
            priced += 1

    return {
        "rows": [
            {
                "metric": "Total",
                "count": len(rows),
                "priced": priced,
                "total": str(total),
            }
        ],
        "count": len(rows),
        "priced": priced,
        "total": str(total),
        "mutated": True,
        "summary": f"Total across {len(rows)} rows = {total} ({priced} priced)",
    }


# ── gate.budget ──────────────────────────────────────────────────────────


async def _run_gate_budget(ctx: NodeContext) -> dict[str, Any]:
    """Stop the run when the rows' total exceeds a budget ceiling.

    Params: ``max_total`` (number, required to gate; 0 / blank = no cap).
    Computes the total over the FULL row set. On breach it raises, so the
    run records an error and downstream nodes are skipped - the same
    "human confirms" contract as the validation gate.
    """
    upstream = ctx.first_input()
    rows = await _resolve_full_rows(ctx, upstream)
    total = sum((_line_total(r) for r in rows), Decimal(0))
    cap = _to_decimal(ctx.params.get("max_total"))

    if cap is not None and cap > 0 and total > cap:
        over = total - cap
        raise ValueError(f"Budget gate failed: total {total} exceeds cap {cap} by {over} (over {len(rows)} rows)")

    return {
        "rows": (upstream.get("rows") or [])[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": len(rows),
        "total": str(total),
        "budget": str(cap) if cap is not None else None,
        "summary": (f"Within budget: total {total}" + (f" of {cap}" if cap is not None and cap > 0 else "")),
    }


# ── gate.completeness ────────────────────────────────────────────────────


async def _run_gate_completeness(ctx: NodeContext) -> dict[str, Any]:
    """Flag rows with a missing quantity or a zero / missing unit rate.

    Params: ``mode`` (``warn`` (default) or ``block``). Computes over the
    FULL row set. In ``block`` mode any incomplete row raises and stops the
    run; in ``warn`` mode the run continues but the counts and the first
    offending ordinals are reported so the estimator can fix them.
    """
    upstream = ctx.first_input()
    rows = await _resolve_full_rows(ctx, upstream)
    mode = (ctx.params.get("mode") or "warn").strip().lower()

    missing_qty: list[str] = []
    missing_rate: list[str] = []
    for r in rows:
        label = str(r.get("ordinal") or r.get("code") or r.get("id") or "?")
        qty = _to_decimal(r.get("quantity"))
        rate = _to_decimal(r.get("unit_rate"))
        if qty is None or qty <= 0:
            missing_qty.append(label)
        if rate is None or rate <= 0:
            missing_rate.append(label)

    incomplete = len(set(missing_qty) | set(missing_rate))
    if mode == "block" and incomplete > 0:
        raise ValueError(
            f"Completeness gate failed: {len(missing_qty)} rows missing quantity, "
            f"{len(missing_rate)} missing a unit rate (e.g. {(missing_qty + missing_rate)[:5]})"
        )

    return {
        "rows": (upstream.get("rows") or [])[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": len(rows),
        "missing_quantity": len(missing_qty),
        "missing_unit_rate": len(missing_rate),
        "complete": incomplete == 0,
        "summary": (
            f"Complete: all {len(rows)} rows have a quantity and a rate"
            if incomplete == 0
            else (
                f"{incomplete} of {len(rows)} rows incomplete ({len(missing_qty)} no qty, {len(missing_rate)} no rate)"
            )
        ),
    }


# ── flow.merge ───────────────────────────────────────────────────────────


async def _run_flow_merge(ctx: NodeContext) -> dict[str, Any]:
    """Combine the rows from every connected upstream node into one set.

    Params: ``dedupe`` (bool, default true - drop rows whose ``id`` was
    already seen). Fills the ``flow`` category so two branches (e.g. two
    filtered subsets, or a BOQ plus catalog rows) can be brought back
    together before an export or total.
    """
    dedupe = ctx.params.get("dedupe", True)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    all_ids: list[str] = []
    total_count = 0

    for env in ctx.inputs.values():
        if not isinstance(env, dict):
            continue
        rows = env.get("rows") or []
        total_count += int(env.get("count", len(rows)) or 0)
        for rid in env.get("row_ids") or []:
            all_ids.append(str(rid))
        for r in rows:
            rid = r.get("id")
            if dedupe and rid:
                if rid in seen:
                    continue
                seen.add(rid)
            merged.append(r)

    return {
        "rows": merged[:_SAMPLE_LIMIT],
        "row_ids": all_ids[:_ROW_IDS_CAP],
        "count": len(merged) if dedupe else total_count,
        "inputs_merged": len(ctx.inputs),
        "summary": f"Merged {len(ctx.inputs)} inputs into {len(merged)} rows",
    }


# ── transform.sort ───────────────────────────────────────────────────────


async def _run_transform_sort(ctx: NodeContext) -> dict[str, Any]:
    """Sort rows by a field, numerically when possible else alphabetically.

    Params: ``field`` (row key, dotted allowed), ``descending`` (bool).
    Marks the envelope ``mutated`` so the order (and any downstream top-N)
    is preserved. Pass-through when no field is given.
    """
    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    field = ctx.params.get("field")
    desc = bool(ctx.params.get("descending", False))

    if field:

        def _key(r: dict[str, Any]) -> tuple[int, Any]:
            value = _row_value(r, field)
            num = _to_decimal(value)
            if num is not None:
                return (0, num)
            return (1, str(value).lower() if value is not None else "")

        rows = sorted(rows, key=_key, reverse=desc)

    return {
        "rows": rows[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": upstream.get("count", len(rows)),
        "mutated": True,
        "summary": (
            f"Sorted by {field} ({'high to low' if desc else 'low to high'})"
            if field
            else f"No sort field ({len(rows)} rows)"
        ),
    }


# ── transform.limit ──────────────────────────────────────────────────────


async def _run_transform_limit(ctx: NodeContext) -> dict[str, Any]:
    """Keep only the first N rows (pair with sort for a top-N).

    Params: ``count`` (int, default 10).
    """
    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    try:
        n = int(ctx.params.get("count") or 10)
    except (TypeError, ValueError):
        n = 10
    n = max(0, n)
    kept = rows[:n]
    kept_ids = [r.get("id") for r in kept if r.get("id")]
    return {
        "rows": kept[:_SAMPLE_LIMIT],
        "row_ids": kept_ids[:_ROW_IDS_CAP],
        "count": len(kept),
        "mutated": True,
        "summary": f"Kept first {len(kept)} of {len(rows)} rows",
    }


# ── transform.dedupe ─────────────────────────────────────────────────────


async def _run_transform_dedupe(ctx: NodeContext) -> dict[str, Any]:
    """Drop rows that repeat a value in a key field.

    Params: ``field`` (row key, default ``id``). Keeps first occurrence.
    """
    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    field = ctx.params.get("field") or "id"

    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for r in rows:
        key = str(_row_value(r, field))
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)

    kept_ids = [r.get("id") for r in kept if r.get("id")]
    return {
        "rows": kept[:_SAMPLE_LIMIT],
        "row_ids": kept_ids[:_ROW_IDS_CAP],
        "count": len(kept),
        "dropped": len(rows) - len(kept),
        "mutated": True,
        "summary": f"Kept {len(kept)} unique of {len(rows)} rows by {field}",
    }


# ── gate.count ───────────────────────────────────────────────────────────


async def _run_gate_count(ctx: NodeContext) -> dict[str, Any]:
    """Require the row count to sit within a range, else stop the run.

    Params: ``min_rows`` (int, default 1), ``max_rows`` (int, 0 = no cap).
    Uses the envelope's full ``count`` (not just the preview), so an empty
    or oversized upstream is caught before a downstream action.
    """
    upstream = ctx.first_input()
    count = int(upstream.get("count") or len(upstream.get("rows") or []))
    raw_min = ctx.params.get("min_rows")
    try:
        min_rows = int(raw_min if raw_min is not None else 1)
    except (TypeError, ValueError):
        min_rows = 1
    try:
        max_rows = int(ctx.params.get("max_rows") or 0)
    except (TypeError, ValueError):
        max_rows = 0

    if count < min_rows:
        raise ValueError(f"Count gate failed: {count} rows is below the minimum {min_rows}")
    if max_rows and count > max_rows:
        raise ValueError(f"Count gate failed: {count} rows is above the maximum {max_rows}")

    return {
        "rows": (upstream.get("rows") or [])[:_SAMPLE_LIMIT],
        "row_ids": upstream.get("row_ids") or [],
        "count": count,
        "summary": f"Count OK: {count} rows",
    }


# ── action.export.csv ────────────────────────────────────────────────────


async def _run_action_export_csv(ctx: NodeContext) -> dict[str, Any]:
    """Export the upstream rows to a CSV file using the stdlib csv module.

    No new dependency. Like the Excel action it returns a file reference +
    metadata (the bytes are persisted by a later phase), so it does not
    mutate the database and needs no preceding gate.
    """
    import csv

    upstream = ctx.first_input()
    rows = list(upstream.get("rows") or [])
    columns = ctx.params.get("columns") or [
        "ordinal",
        "description",
        "unit",
        "quantity",
        "unit_rate",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([str(c) for c in columns])
    for r in rows:
        writer.writerow([r.get(c, "") for c in columns])
    size = len(buf.getvalue().encode("utf-8"))

    return {
        "file": {
            "filename": ctx.params.get("filename", "pipeline-export.csv"),
            "content_type": "text/csv",
            "size_bytes": size,
            "row_count": len(rows),
            "columns": list(columns),
        },
        "summary": f"Exported {len(rows)} rows → CSV ({size} bytes)",
    }


# ── Registration (import-time, autodiscovered by the module loader) ──────


def register_pipeline_nodes() -> None:
    """Register every Phase-1 node type. Idempotent (last write wins)."""
    register_node(
        type="trigger.manual",
        module=MODULE,
        category="trigger",
        label="Manual trigger",
        description="Start the pipeline from a REST call. No inputs.",
        runner=_run_trigger_manual,
        inputs=[],
        outputs=["trigger"],
        params_schema={},
        side_effecting=False,
    )
    register_node(
        type="source.project",
        module=MODULE,
        category="source",
        label="Get project",
        description="Load the bound project's id + name.",
        runner=_run_source_project,
        inputs=["trigger"],
        outputs=["project"],
        params_schema={"project_id": {"type": "string", "title": "Project id (optional)"}},
        side_effecting=False,
    )
    register_node(
        type="source.boq",
        module=MODULE,
        category="source",
        label="Get BOQ positions",
        description=("Load every BOQ position for the project as rows (ids + a small sample)."),
        runner=_run_source_boq,
        inputs=["trigger", "project"],
        outputs=["rows"],
        params_schema={"project_id": {"type": "string", "title": "Project id (optional)"}},
        side_effecting=False,
    )
    register_node(
        type="transform.filter",
        module=MODULE,
        category="transform",
        label="Filter rows",
        description="Keep only rows matching a simple field/op/value test.",
        runner=_run_transform_filter,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "field": {"type": "string", "title": "Field"},
            "op": {
                "type": "string",
                "title": "Operator",
                "enum": [
                    "eq",
                    "ne",
                    "contains",
                    "gt",
                    "gte",
                    "lt",
                    "lte",
                    "exists",
                ],
            },
            "value": {"title": "Value"},
        },
        side_effecting=False,
    )
    register_node(
        type="gate.validation",
        module=MODULE,
        category="gate",
        label="Validation gate",
        description=("Run the validation engine over the rows; stop the run on blocking errors."),
        runner=_run_gate_validation,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "rule_sets": {
                "type": "array",
                "title": "Rule sets",
                "items": {"type": "string"},
                "default": ["boq_quality"],
            }
        },
        side_effecting=False,
    )
    register_node(
        type="action.export.excel",
        module=MODULE,
        category="action",
        label="Export to Excel",
        description=("Write the rows to an .xlsx file (returns a download reference; does not mutate the database)."),
        runner=_run_action_export_excel,
        inputs=["rows"],
        outputs=["file"],
        params_schema={
            "filename": {"type": "string", "title": "File name"},
            "columns": {
                "type": "array",
                "title": "Columns",
                "items": {"type": "string"},
            },
        },
        # Produces a file, not a DB mutation - so it needs no preceding gate.
        side_effecting=False,
    )
    register_node(
        type="source.cost_catalog",
        module=MODULE,
        category="source",
        label="Get cost items",
        description="Load priced cost-catalog items as rows (optionally text-filtered).",
        runner=_run_source_cost_catalog,
        inputs=["trigger"],
        outputs=["rows"],
        params_schema={
            "query": {"type": "string", "title": "Search (code or description)"},
            "limit": {"type": "number", "title": "Max items"},
        },
        side_effecting=False,
    )
    register_node(
        type="transform.markup",
        module=MODULE,
        category="transform",
        label="Apply markup",
        description="Raise (or discount) every unit rate by a percent and recompute totals.",
        runner=_run_transform_markup,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={"percent": {"type": "number", "title": "Markup %"}},
        side_effecting=False,
    )
    register_node(
        type="transform.aggregate",
        module=MODULE,
        category="transform",
        label="Group and total",
        description="Group rows by a field and sum quantity x unit rate for each group.",
        runner=_run_transform_aggregate,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "group_by": {
                "type": "string",
                "title": "Group by field",
                "description": "e.g. unit, or classification.din276",
            }
        },
        side_effecting=False,
    )
    register_node(
        type="transform.rollup",
        module=MODULE,
        category="transform",
        label="Total cost",
        description="Sum quantity x unit rate across all rows into a single total.",
        runner=_run_transform_rollup,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={},
        side_effecting=False,
    )
    register_node(
        type="gate.budget",
        module=MODULE,
        category="gate",
        label="Budget gate",
        description="Stop the run if the rows' total cost exceeds a budget ceiling.",
        runner=_run_gate_budget,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={"max_total": {"type": "number", "title": "Budget ceiling"}},
        side_effecting=False,
    )
    register_node(
        type="gate.completeness",
        module=MODULE,
        category="gate",
        label="Completeness gate",
        description="Flag or stop on rows missing a quantity or a unit rate.",
        runner=_run_gate_completeness,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "mode": {
                "type": "string",
                "title": "On incomplete",
                "enum": ["warn", "block"],
                "default": "warn",
            }
        },
        side_effecting=False,
    )
    register_node(
        type="flow.merge",
        module=MODULE,
        category="flow",
        label="Merge rows",
        description="Combine the rows from two upstream branches into one set.",
        runner=_run_flow_merge,
        inputs=["rows_a", "rows_b"],
        outputs=["rows"],
        params_schema={"dedupe": {"type": "boolean", "title": "Drop duplicate ids", "default": True}},
        side_effecting=False,
    )
    register_node(
        type="transform.sort",
        module=MODULE,
        category="transform",
        label="Sort rows",
        description="Order rows by a field, numerically or alphabetically.",
        runner=_run_transform_sort,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "field": {"type": "string", "title": "Sort by field"},
            "descending": {"type": "boolean", "title": "High to low", "default": False},
        },
        side_effecting=False,
    )
    register_node(
        type="transform.limit",
        module=MODULE,
        category="transform",
        label="Keep top N",
        description="Keep only the first N rows (pair with Sort for a top-N).",
        runner=_run_transform_limit,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={"count": {"type": "number", "title": "How many rows"}},
        side_effecting=False,
    )
    register_node(
        type="transform.dedupe",
        module=MODULE,
        category="transform",
        label="Remove duplicates",
        description="Drop rows that repeat a value in a key field.",
        runner=_run_transform_dedupe,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={"field": {"type": "string", "title": "Key field (default id)"}},
        side_effecting=False,
    )
    register_node(
        type="gate.count",
        module=MODULE,
        category="gate",
        label="Count gate",
        description="Stop the run unless the row count is within a range.",
        runner=_run_gate_count,
        inputs=["rows"],
        outputs=["rows"],
        params_schema={
            "min_rows": {"type": "number", "title": "Minimum rows"},
            "max_rows": {"type": "number", "title": "Maximum rows (0 = no cap)"},
        },
        side_effecting=False,
    )
    register_node(
        type="action.export.csv",
        module=MODULE,
        category="action",
        label="Export to CSV",
        description="Write the rows to a .csv file (returns a download reference).",
        runner=_run_action_export_csv,
        inputs=["rows"],
        outputs=["file"],
        params_schema={
            "filename": {"type": "string", "title": "File name"},
            "columns": {"type": "array", "title": "Columns", "items": {"type": "string"}},
        },
        side_effecting=False,
    )


register_pipeline_nodes()
