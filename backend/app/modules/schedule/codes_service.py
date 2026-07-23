# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Persistence service for activity codes, UDFs and saved layouts (T2.3).

Async DB glue over the six ``oe_schedule_code_*`` / ``oe_schedule_udf*`` /
``oe_schedule_layout`` tables. Access control (project scoping / IDOR) is
enforced at the router via ``verify_project_access``; the methods here take an
already-verified ``project_id`` where a cross-project check is needed and refuse
to write a code/UDF/value that belongs to a different project.

The pure :func:`coerce_udf_value` helper (typed-value validation) is unit-tested
on the local runner; everything else is async DB work exercised in CI.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.schedule.codes_models import (
    CodeAssignment,
    CodeDictionary,
    CodeValue,
    ScheduleLayout,
    ScheduleUdf,
    ScheduleUdfValue,
)
from app.modules.schedule.codes_schemas import (
    CodeAssignmentItem,
    CodeDictionaryCreate,
    CodeDictionaryPatch,
    CodeValueCreate,
    CodeValuePatch,
    LayoutCreate,
    LayoutPatch,
    LayoutSpec,
    UdfCreate,
    UdfPatch,
    UdfValueItem,
)
from app.modules.schedule.codes_valuecoerce import coerce_udf_value, udf_value_readback
from app.modules.schedule.models import Activity, Schedule

# Re-exported for the router (kept here so existing imports stay stable).
__all__ = ["ConflictError", "ScheduleCodesService", "coerce_udf_value", "udf_value_readback"]


class ConflictError(Exception):
    """A uniqueness conflict (duplicate name / key / sibling code). Maps to 409."""


class ScheduleCodesService:
    """CRUD for code dictionaries/values/assignments, UDFs and saved layouts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── code dictionaries ────────────────────────────────────────────────────

    async def _dict_name_exists(self, project_id: uuid.UUID, name: str) -> bool:
        row = await self.session.execute(
            select(CodeDictionary.id).where(CodeDictionary.project_id == project_id, CodeDictionary.name == name)
        )
        return row.first() is not None

    async def create_dictionary(self, project_id: uuid.UUID, data: CodeDictionaryCreate) -> CodeDictionary:
        if await self._dict_name_exists(project_id, data.name):
            raise ConflictError(f"A code dictionary named {data.name!r} already exists in this project")
        d = CodeDictionary(
            project_id=project_id,
            is_library=False,
            name=data.name,
            description=data.description,
            color_band=data.color_band,
            sort_order=data.sort_order,
        )
        self.session.add(d)
        await self.session.flush()
        return d

    async def list_dictionaries(self, project_id: uuid.UUID) -> list[CodeDictionary]:
        rows = await self.session.execute(
            select(CodeDictionary)
            .where(CodeDictionary.project_id == project_id)
            .order_by(CodeDictionary.sort_order.asc(), CodeDictionary.name.asc())
        )
        return list(rows.scalars().all())

    async def list_library_dictionaries(self) -> list[CodeDictionary]:
        rows = await self.session.execute(
            select(CodeDictionary).where(CodeDictionary.is_library.is_(True)).order_by(CodeDictionary.name.asc())
        )
        return list(rows.scalars().all())

    async def get_dictionary(self, dict_id: uuid.UUID) -> CodeDictionary | None:
        return await self.session.get(CodeDictionary, dict_id)

    async def patch_dictionary(self, d: CodeDictionary, data: CodeDictionaryPatch) -> CodeDictionary:
        payload = data.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] != d.name:
            if d.project_id is not None and await self._dict_name_exists(d.project_id, payload["name"]):
                raise ConflictError(f"A code dictionary named {payload['name']!r} already exists in this project")
        for field, value in payload.items():
            setattr(d, field, value)
        await self.session.flush()
        return d

    async def delete_dictionary(self, d: CodeDictionary) -> None:
        await self.session.execute(delete(CodeAssignment).where(CodeAssignment.dictionary_id == d.id))
        await self.session.execute(delete(CodeValue).where(CodeValue.dictionary_id == d.id))
        await self.session.delete(d)
        await self.session.flush()

    async def import_library(self, library: CodeDictionary, target_project_id: uuid.UUID) -> CodeDictionary:
        """Copy a library dictionary + its value tree into a project as NEW rows."""
        if await self._dict_name_exists(target_project_id, library.name):
            raise ConflictError(f"A code dictionary named {library.name!r} already exists in this project")
        new_dict = CodeDictionary(
            project_id=target_project_id,
            is_library=False,
            name=library.name,
            description=library.description,
            color_band=library.color_band,
            sort_order=library.sort_order,
        )
        self.session.add(new_dict)
        await self.session.flush()
        # Ordered by depth so a parent's new id exists before its children copy.
        old_values = (
            (
                await self.session.execute(
                    select(CodeValue)
                    .where(CodeValue.dictionary_id == library.id)
                    .order_by(CodeValue.depth.asc(), CodeValue.sort_order.asc())
                )
            )
            .scalars()
            .all()
        )
        id_map: dict[uuid.UUID, uuid.UUID] = {}
        for ov in old_values:
            new_parent = id_map.get(ov.parent_id) if ov.parent_id else None
            nv = CodeValue(
                dictionary_id=new_dict.id,
                parent_id=new_parent,
                code=ov.code,
                label=ov.label,
                color=ov.color,
                depth=ov.depth,
                sort_order=ov.sort_order,
            )
            self.session.add(nv)
            await self.session.flush()
            id_map[ov.id] = nv.id
        return new_dict

    # ── code values ──────────────────────────────────────────────────────────

    async def list_values(self, dictionary_id: uuid.UUID) -> list[CodeValue]:
        rows = await self.session.execute(
            select(CodeValue)
            .where(CodeValue.dictionary_id == dictionary_id)
            .order_by(CodeValue.depth.asc(), CodeValue.sort_order.asc(), CodeValue.code.asc())
        )
        return list(rows.scalars().all())

    async def _sibling_code_exists(
        self, dictionary_id: uuid.UUID, parent_id: uuid.UUID | None, code: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        stmt = select(CodeValue.id).where(
            CodeValue.dictionary_id == dictionary_id,
            CodeValue.parent_id.is_(None) if parent_id is None else CodeValue.parent_id == parent_id,
            CodeValue.code == code,
        )
        if exclude_id is not None:
            stmt = stmt.where(CodeValue.id != exclude_id)
        return (await self.session.execute(stmt)).first() is not None

    async def add_value(self, d: CodeDictionary, data: CodeValueCreate) -> CodeValue:
        depth = 0
        if data.parent_id is not None:
            parent = await self.session.get(CodeValue, data.parent_id)
            if parent is None or parent.dictionary_id != d.id:
                raise ValueError("parent value does not belong to this dictionary")
            depth = parent.depth + 1
        if await self._sibling_code_exists(d.id, data.parent_id, data.code):
            raise ConflictError(f"A sibling value with code {data.code!r} already exists")
        v = CodeValue(
            dictionary_id=d.id,
            parent_id=data.parent_id,
            code=data.code,
            label=data.label,
            color=data.color,
            depth=depth,
            sort_order=data.sort_order,
        )
        self.session.add(v)
        await self.session.flush()
        return v

    async def get_value(self, value_id: uuid.UUID) -> CodeValue | None:
        return await self.session.get(CodeValue, value_id)

    async def patch_value(self, v: CodeValue, data: CodeValuePatch) -> CodeValue:
        payload = data.model_dump(exclude_unset=True)
        if "code" in payload and payload["code"] != v.code:
            if await self._sibling_code_exists(v.dictionary_id, v.parent_id, payload["code"], exclude_id=v.id):
                raise ConflictError(f"A sibling value with code {payload['code']!r} already exists")
        for field, value in payload.items():
            setattr(v, field, value)
        await self.session.flush()
        return v

    async def delete_value(self, v: CodeValue) -> None:
        """Delete a value, its descendant subtree and any assignments to it."""
        children = (await self.session.execute(select(CodeValue).where(CodeValue.parent_id == v.id))).scalars().all()
        for child in children:
            await self.delete_value(child)
        await self.session.execute(delete(CodeAssignment).where(CodeAssignment.value_id == v.id))
        await self.session.delete(v)
        await self.session.flush()

    # ── per-activity code assignments ─────────────────────────────────────────

    async def project_id_for_activity(self, activity_id: uuid.UUID) -> uuid.UUID | None:
        row = await self.session.execute(
            select(Schedule.project_id)
            .join(Activity, Activity.schedule_id == Schedule.id)
            .where(Activity.id == activity_id)
        )
        return row.scalar_one_or_none()

    async def list_activity_code_pairs(self, activity_id: uuid.UUID) -> list[tuple[CodeAssignment, CodeValue | None]]:
        rows = await self.session.execute(
            select(CodeAssignment, CodeValue)
            .join(CodeValue, CodeValue.id == CodeAssignment.value_id, isouter=True)
            .where(CodeAssignment.activity_id == activity_id)
        )
        return [(a, v) for a, v in rows.all()]

    async def set_activity_codes(
        self, activity_id: uuid.UUID, project_id: uuid.UUID, items: list[CodeAssignmentItem]
    ) -> list[tuple[CodeAssignment, CodeValue | None]]:
        seen: set[uuid.UUID] = set()
        for it in items:
            if it.dictionary_id in seen:
                raise ValueError("two values supplied for the same dictionary")
            seen.add(it.dictionary_id)
            d = await self.session.get(CodeDictionary, it.dictionary_id)
            if d is None or d.project_id != project_id:
                raise ValueError("dictionary does not belong to this project")
            val = await self.session.get(CodeValue, it.value_id)
            if val is None or val.dictionary_id != it.dictionary_id:
                raise ValueError("value does not belong to the dictionary")
        for it in items:
            await self.session.execute(
                delete(CodeAssignment).where(
                    CodeAssignment.activity_id == activity_id,
                    CodeAssignment.dictionary_id == it.dictionary_id,
                )
            )
            self.session.add(
                CodeAssignment(activity_id=activity_id, dictionary_id=it.dictionary_id, value_id=it.value_id)
            )
        await self.session.flush()
        return await self.list_activity_code_pairs(activity_id)

    async def bulk_assign(self, d: CodeDictionary, value_id: uuid.UUID, activity_ids: list[uuid.UUID]) -> int:
        val = await self.session.get(CodeValue, value_id)
        if val is None or val.dictionary_id != d.id:
            raise ValueError("value does not belong to the dictionary")
        unique_ids = list(dict.fromkeys(activity_ids))
        valid = (
            (
                await self.session.execute(
                    select(Activity.id)
                    .join(Schedule, Schedule.id == Activity.schedule_id)
                    .where(Activity.id.in_(unique_ids), Schedule.project_id == d.project_id)
                )
            )
            .scalars()
            .all()
        )
        if set(valid) != set(unique_ids):
            raise ValueError("some activities are not in this project")
        await self.session.execute(
            delete(CodeAssignment).where(
                CodeAssignment.dictionary_id == d.id,
                CodeAssignment.activity_id.in_(unique_ids),
            )
        )
        self.session.add_all(
            [CodeAssignment(activity_id=aid, dictionary_id=d.id, value_id=value_id) for aid in unique_ids]
        )
        await self.session.flush()
        return len(unique_ids)

    # ── user-defined fields ───────────────────────────────────────────────────

    async def _udf_key_exists(self, project_id: uuid.UUID, key: str) -> bool:
        row = await self.session.execute(
            select(ScheduleUdf.id).where(ScheduleUdf.project_id == project_id, ScheduleUdf.key == key)
        )
        return row.first() is not None

    async def create_udf(self, project_id: uuid.UUID, data: UdfCreate) -> ScheduleUdf:
        if await self._udf_key_exists(project_id, data.key):
            raise ConflictError(f"A UDF with key {data.key!r} already exists in this project")
        u = ScheduleUdf(
            project_id=project_id,
            key=data.key,
            label=data.label,
            value_type=data.value_type,
            enum_values=list(data.enum_values),
            sort_order=data.sort_order,
        )
        self.session.add(u)
        await self.session.flush()
        return u

    async def list_udfs(self, project_id: uuid.UUID) -> list[ScheduleUdf]:
        rows = await self.session.execute(
            select(ScheduleUdf)
            .where(ScheduleUdf.project_id == project_id)
            .order_by(ScheduleUdf.sort_order.asc(), ScheduleUdf.key.asc())
        )
        return list(rows.scalars().all())

    async def get_udf(self, udf_id: uuid.UUID) -> ScheduleUdf | None:
        return await self.session.get(ScheduleUdf, udf_id)

    async def patch_udf(self, u: ScheduleUdf, data: UdfPatch) -> ScheduleUdf:
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            setattr(u, field, value)
        await self.session.flush()
        return u

    async def delete_udf(self, u: ScheduleUdf) -> None:
        await self.session.execute(delete(ScheduleUdfValue).where(ScheduleUdfValue.udf_id == u.id))
        await self.session.delete(u)
        await self.session.flush()

    async def list_activity_udf_pairs(self, activity_id: uuid.UUID) -> list[tuple[ScheduleUdfValue, ScheduleUdf]]:
        rows = await self.session.execute(
            select(ScheduleUdfValue, ScheduleUdf)
            .join(ScheduleUdf, ScheduleUdf.id == ScheduleUdfValue.udf_id)
            .where(ScheduleUdfValue.activity_id == activity_id)
        )
        return [(val, udf) for val, udf in rows.all()]

    async def set_activity_udf_values(
        self, activity_id: uuid.UUID, project_id: uuid.UUID, items: list[UdfValueItem]
    ) -> list[tuple[ScheduleUdfValue, ScheduleUdf]]:
        for it in items:
            udf = await self.session.get(ScheduleUdf, it.udf_id)
            if udf is None or udf.project_id != project_id:
                raise ValueError("UDF does not belong to this project")
            cols = coerce_udf_value(udf.value_type, udf.enum_values, it.value)
            await self.session.execute(
                delete(ScheduleUdfValue).where(
                    ScheduleUdfValue.activity_id == activity_id,
                    ScheduleUdfValue.udf_id == it.udf_id,
                )
            )
            self.session.add(ScheduleUdfValue(activity_id=activity_id, udf_id=it.udf_id, **cols))
        await self.session.flush()
        return await self.list_activity_udf_pairs(activity_id)

    # ── saved layouts ─────────────────────────────────────────────────────────

    def _bind_layout_filter(self, spec: LayoutSpec) -> None:
        """Validate the static-column filter against the activity whitelist.

        Raises ``WhitelistError`` (router -> 422) on a non-whitelisted column,
        an ungroupable group target, etc. Keeps an illegal identifier out of the
        DB entirely (the audited saved_views bind path).
        """
        from app.modules.schedule.saved_view_entity import build_activity_entity

        entity = build_activity_entity()
        # Static filter conditions + sort + any static (non code:/udf:) group/columns.
        spec.filter.bind(entity)

    async def _layout_name_exists(
        self, owner_id: uuid.UUID, schedule_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        stmt = select(ScheduleLayout.id).where(
            ScheduleLayout.owner_id == owner_id,
            ScheduleLayout.schedule_id == schedule_id,
            ScheduleLayout.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(ScheduleLayout.id != exclude_id)
        return (await self.session.execute(stmt)).first() is not None

    async def _clear_other_defaults(self, owner_id: uuid.UUID, schedule_id: uuid.UUID, keep_id: uuid.UUID) -> None:
        rows = (
            (
                await self.session.execute(
                    select(ScheduleLayout).where(
                        ScheduleLayout.owner_id == owner_id,
                        ScheduleLayout.schedule_id == schedule_id,
                        ScheduleLayout.is_default.is_(True),
                        ScheduleLayout.id != keep_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.is_default = False

    async def create_layout(
        self, owner_id: uuid.UUID, schedule_id: uuid.UUID, project_id: uuid.UUID, data: LayoutCreate
    ) -> ScheduleLayout:
        self._bind_layout_filter(data.spec)
        if await self._layout_name_exists(owner_id, schedule_id, data.name):
            raise ConflictError(f"You already have a layout named {data.name!r} on this schedule")
        layout = ScheduleLayout(
            owner_id=owner_id,
            schedule_id=schedule_id,
            project_id=project_id,
            name=data.name,
            share_scope=data.share_scope,
            is_default=data.is_default,
            spec=data.spec.model_dump(mode="json"),
        )
        self.session.add(layout)
        await self.session.flush()
        if layout.is_default:
            await self._clear_other_defaults(owner_id, schedule_id, layout.id)
            await self.session.flush()
        return layout

    async def list_layouts(
        self, owner_id: uuid.UUID, schedule_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> list[ScheduleLayout]:
        """A user's own layouts plus those shared to the project or workspace."""
        from sqlalchemy import and_, or_

        visible = or_(
            ScheduleLayout.owner_id == owner_id,
            ScheduleLayout.share_scope == "workspace",
            and_(ScheduleLayout.share_scope == "project", ScheduleLayout.project_id == project_id),
        )
        rows = await self.session.execute(
            select(ScheduleLayout)
            .where(ScheduleLayout.schedule_id == schedule_id, visible)
            .order_by(ScheduleLayout.is_default.desc(), ScheduleLayout.name.asc())
        )
        return list(rows.scalars().all())

    async def get_layout(self, layout_id: uuid.UUID) -> ScheduleLayout | None:
        return await self.session.get(ScheduleLayout, layout_id)

    async def patch_layout(self, layout: ScheduleLayout, data: LayoutPatch) -> ScheduleLayout:
        payload = data.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] != layout.name:
            if await self._layout_name_exists(
                layout.owner_id, layout.schedule_id, payload["name"], exclude_id=layout.id
            ):
                raise ConflictError(f"You already have a layout named {payload['name']!r} on this schedule")
        if data.spec is not None:
            self._bind_layout_filter(data.spec)
            layout.spec = data.spec.model_dump(mode="json")
        for field in ("name", "share_scope", "is_default"):
            if field in payload:
                setattr(layout, field, payload[field])
        await self.session.flush()
        if layout.is_default:
            await self._clear_other_defaults(layout.owner_id, layout.schedule_id, layout.id)
            await self.session.flush()
        return layout

    async def delete_layout(self, layout: ScheduleLayout) -> None:
        await self.session.delete(layout)
        await self.session.flush()
