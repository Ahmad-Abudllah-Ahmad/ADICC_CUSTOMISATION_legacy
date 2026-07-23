# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Server-side grouped / filtered / paged activity grid (T2.3).

The grouped grid is computed in the database, not the browser, so a
20,000-activity schedule slices by area / discipline / subcontractor without
shipping the whole set. Two phases:

* PHASE 1 - a cheap, indexed group-counts query collapses the activities into a
  banded tree with per-band counts (an unassigned activity falls into a
  ``(none)`` band, so the band counts always sum to the total).
* PHASE 2 - a single page of leaf rows for the requested page, with codes and
  UDF values attached in one batched round trip each (no N+1).

The static-column filter rides the audited ``saved_views`` whitelist +
``FilterSpec.bind`` path; a non-whitelisted column never reaches the database
and grouping on an unindexed static column is rejected. The dynamic code/UDF
predicates are isolated here.

:func:`build_band_tree` is pure and unit-tested on the local interpreter; the
resolver itself is async DB work exercised in CI.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.saved_views.errors import WhitelistError
from app.modules.schedule.codes_bandtree import NONE_KEY as _NONE_KEY
from app.modules.schedule.codes_bandtree import build_band_tree
from app.modules.schedule.codes_bandtree import group_key as _group_key
from app.modules.schedule.codes_models import (
    CodeAssignment,
    CodeDictionary,
    CodeValue,
    ScheduleUdf,
    ScheduleUdfValue,
)
from app.modules.schedule.codes_schemas import LayoutSpec, UdfFilter, parse_layout_key
from app.modules.schedule.codes_valuecoerce import udf_value_readback
from app.modules.schedule.models import Activity

__all__ = ["build_band_tree", "resolve_grouped_layout"]


def _udf_value_col(value_type: str) -> str:
    """Map a UDF ``value_type`` to its typed value column name.

    The same mapping the EXISTS filter uses, named so the grouping path can pull
    the column off an aliased value row with ``getattr``.
    """
    if value_type in ("text", "enum"):
        return "value_text"
    if value_type == "number":
        return "value_number"
    if value_type == "date":
        return "value_date"
    return "value_bool"


def _udf_exists_predicate(uf: UdfFilter, value_type: str):  # noqa: ANN202 - SQLAlchemy expression
    """Build an EXISTS predicate over a UDF value for one activity."""
    sv = aliased(ScheduleUdfValue)
    base = [sv.activity_id == Activity.id, sv.udf_id == uf.udf_id]
    col = getattr(sv, _udf_value_col(value_type))

    if uf.op == "is_null":
        return ~exists(select(sv.id).where(*base, col.isnot(None)))
    if uf.op == "not_null":
        return exists(select(sv.id).where(*base, col.isnot(None)))

    from decimal import Decimal

    val: Any = uf.value
    if value_type == "number" and val is not None:
        val = Decimal(str(val))
    if value_type == "bool" and val is not None:
        val = str(val).strip().lower() in ("true", "1", "yes", "y", "on")

    if uf.op == "eq":
        pred = col == val
    elif uf.op == "neq":
        pred = col != val
    elif uf.op == "lt":
        pred = col < val
    elif uf.op == "lte":
        pred = col <= val
    elif uf.op == "gt":
        pred = col > val
    elif uf.op == "gte":
        pred = col >= val
    elif uf.op == "contains":
        pred = col.ilike(f"%{val}%")
    else:  # pragma: no cover - schema constrains op
        raise WhitelistError(f"Unsupported UDF operator {uf.op!r}")
    return exists(select(sv.id).where(*base, pred))


async def resolve_grouped_layout(
    session: AsyncSession,
    schedule_id: uuid.UUID,
    project_id: uuid.UUID,
    spec: LayoutSpec,
    *,
    page: int,
    page_size: int,
    expanded_groups: list[str],
) -> dict[str, Any]:
    """Resolve a layout into a grouped tree + a page of leaf rows."""
    from app.modules.saved_views.query_builder import SafeQueryBuilder
    from app.modules.schedule.saved_view_entity import build_activity_entity

    entity = build_activity_entity()
    # Validate + compile the STATIC-column filter on the audited whitelist path.
    spec.filter.bind(entity)
    builder = SafeQueryBuilder(entity)
    static_pred = builder._compile_group(spec.filter.where)

    # ── resolve the group levels (code: dicts and groupable static columns) ──
    level_specs: list[dict[str, Any]] = []
    for gb in spec.group_by:
        kind, ref = parse_layout_key(gb.key)
        if kind == "static":
            fs = entity.fields.get(ref)
            if fs is None:
                raise WhitelistError(f"Group field {ref!r} is not available", field=ref)
            if not fs.groupable:
                raise WhitelistError(f"Field {ref!r} is not groupable (not indexed)", field=ref)
            level_specs.append({"kind": "static", "column": fs.column})
        elif kind == "code":
            dict_id = uuid.UUID(str(ref))
            d = await session.get(CodeDictionary, dict_id)
            if d is None or d.project_id != project_id:
                raise WhitelistError("Group dictionary is not in this project", field=gb.key)
            level_specs.append({"kind": "code", "dictionary_id": dict_id})
        else:  # kind == "udf"
            udf_id = uuid.UUID(str(ref))
            udf = await session.get(ScheduleUdf, udf_id)
            if udf is None or udf.project_id != project_id:
                raise WhitelistError("Group UDF is not in this project", field=gb.key)
            level_specs.append(
                {
                    "kind": "udf",
                    "udf_id": udf_id,
                    "value_col": _udf_value_col(udf.value_type),
                    "value_type": udf.value_type,
                }
            )

    # ── common WHERE: schedule scope + static filter + code/udf predicates ──
    where_terms: list[Any] = [Activity.schedule_id == schedule_id]
    if static_pred is not None:
        where_terms.append(static_pred)
    for cf in spec.code_filter:
        if cf.value_ids:
            ca = aliased(CodeAssignment)
            where_terms.append(
                exists(
                    select(ca.id).where(
                        ca.activity_id == Activity.id,
                        ca.dictionary_id == cf.dictionary_id,
                        ca.value_id.in_(list(cf.value_ids)),
                    )
                )
            )
    if spec.udf_filter:
        udf_ids = [uf.udf_id for uf in spec.udf_filter]
        udf_rows = (await session.execute(select(ScheduleUdf).where(ScheduleUdf.id.in_(udf_ids)))).scalars().all()
        udf_types = {u.id: u.value_type for u in udf_rows if u.project_id == project_id}
        for uf in spec.udf_filter:
            if uf.udf_id not in udf_types:
                raise WhitelistError("UDF filter references an unknown field", field=str(uf.udf_id))
            where_terms.append(_udf_exists_predicate(uf, udf_types[uf.udf_id]))

    # ── group-level column expressions + the LEFT JOINs they need ──
    level_exprs: list[Any] = []
    joins: list[tuple[Any, Any]] = []
    for i, level in enumerate(level_specs):
        if level["kind"] == "code":
            ca = aliased(CodeAssignment, name=f"ca_grp_{i}")
            joins.append((ca, and_(ca.activity_id == Activity.id, ca.dictionary_id == level["dictionary_id"])))
            level_exprs.append(ca.value_id.label(f"g{i}"))
        elif level["kind"] == "udf":
            suv = aliased(ScheduleUdfValue, name=f"suv_grp_{i}")
            joins.append((suv, and_(suv.activity_id == Activity.id, suv.udf_id == level["udf_id"])))
            level_exprs.append(getattr(suv, level["value_col"]).label(f"g{i}"))
        else:
            level_exprs.append(getattr(Activity, level["column"]).label(f"g{i}"))

    # ── PHASE 1: counts per level combination ──
    if level_exprs:
        count_stmt = select(*level_exprs, func.count(func.distinct(Activity.id)).label("cnt")).select_from(Activity)
        for ca, on in joins:
            count_stmt = count_stmt.outerjoin(ca, on)
        count_stmt = count_stmt.where(*where_terms).group_by(*level_exprs)
        rows = (await session.execute(count_stmt)).all()
        count_rows: list[tuple[tuple[str | None, ...], int]] = []
        for row in rows:
            keys = tuple(_group_key(row[i]) for i in range(len(level_specs)))
            count_rows.append((keys, int(row[-1])))
        meta = await _code_value_meta(session, level_specs, count_rows)
        bands, total = build_band_tree(count_rows, len(level_specs), meta)
    else:
        total = int((await session.execute(select(func.count(Activity.id)).where(*where_terms))).scalar() or 0)
        bands = []

    # ── PHASE 2: a page of leaf rows (optionally only for expanded groups) ──
    page_stmt = select(Activity, *level_exprs).select_from(Activity)
    for ca, on in joins:
        page_stmt = page_stmt.outerjoin(ca, on)
    page_stmt = page_stmt.where(*where_terms)
    order_terms = [*[expr for expr in level_exprs], Activity.sort_order, Activity.wbs_code]
    page_stmt = page_stmt.order_by(*order_terms).offset((page - 1) * page_size).limit(page_size)
    page_result = (await session.execute(page_stmt)).all()

    activities = [r[0] for r in page_result]
    page_paths: dict[uuid.UUID, list[str]] = {}
    for r in page_result:
        act = r[0]
        # A None key (unassigned) maps to the same (none) band PHASE 1 emits; an
        # empty-but-present value keeps its own key so the row still nests.
        path = []
        for i in range(len(level_specs)):
            k = _group_key(r[i + 1])
            path.append(_NONE_KEY if k is None else k)
        page_paths[act.id] = path

    activity_ids = [a.id for a in activities]
    codes_by_activity = await _codes_for_activities(session, activity_ids)
    udfs_by_activity = await _udf_values_for_activities(session, activity_ids)

    rows_out: list[dict[str, Any]] = []
    for act in activities:
        rows_out.append(
            {
                "id": act.id,
                "name": act.name,
                "wbs_code": act.wbs_code,
                "start_date": act.start_date,
                "end_date": act.end_date,
                "duration_days": act.duration_days,
                "progress_pct": _safe_float(act.progress_pct),
                "status": act.status,
                "total_float": act.total_float,
                "is_critical": bool(act.is_critical),
                "group_path": page_paths.get(act.id, []),
                "codes": codes_by_activity.get(act.id, []),
                "udf_values": udfs_by_activity.get(act.id, []),
            }
        )

    return {"groups": bands, "rows": rows_out, "page": page, "page_size": page_size, "total_estimate": total}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def _code_value_meta(
    session: AsyncSession,
    level_specs: list[dict[str, Any]],
    count_rows: list[tuple[tuple[str | None, ...], int]],
) -> dict[tuple[int, str], dict[str, str]]:
    """Resolve code value ids appearing in the count rows to label + color."""
    wanted: set[uuid.UUID] = set()
    for keys, _ in count_rows:
        for i, level in enumerate(level_specs):
            if level["kind"] == "code" and i < len(keys) and keys[i] is not None:
                wanted.add(uuid.UUID(keys[i]))
    meta: dict[tuple[int, str], dict[str, str]] = {}
    if not wanted:
        return meta
    values = (await session.execute(select(CodeValue).where(CodeValue.id.in_(wanted)))).scalars().all()
    by_id = {str(v.id): v for v in values}
    for i, level in enumerate(level_specs):
        if level["kind"] != "code":
            continue
        for keys, _ in count_rows:
            key = keys[i] if i < len(keys) else None
            if key is not None and key in by_id:
                v = by_id[key]
                meta[(i, key)] = {"label": f"{v.code} {v.label}".strip(), "color": v.color}
    return meta


async def _codes_for_activities(
    session: AsyncSession, activity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if not activity_ids:
        return out
    rows = await session.execute(
        select(CodeAssignment, CodeValue)
        .join(CodeValue, CodeValue.id == CodeAssignment.value_id, isouter=True)
        .where(CodeAssignment.activity_id.in_(activity_ids))
    )
    for a, v in rows.all():
        out.setdefault(a.activity_id, []).append(
            {
                "dictionary_id": a.dictionary_id,
                "value_id": a.value_id,
                "code": v.code if v is not None else "",
                "label": v.label if v is not None else "",
            }
        )
    return out


async def _udf_values_for_activities(
    session: AsyncSession, activity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    from decimal import Decimal

    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if not activity_ids:
        return out
    rows = await session.execute(
        select(ScheduleUdfValue, ScheduleUdf)
        .join(ScheduleUdf, ScheduleUdf.id == ScheduleUdfValue.udf_id)
        .where(ScheduleUdfValue.activity_id.in_(activity_ids))
    )
    for val_row, udf in rows.all():
        value = udf_value_readback(udf.value_type, val_row)
        if isinstance(value, Decimal):
            value = float(value)
        out.setdefault(val_row.activity_id, []).append({"udf_id": udf.id, "value_type": udf.value_type, "value": value})
    return out
