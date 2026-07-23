# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The saved-views orchestrator.

``SavedViewService`` is the only place that wires the three safety primitives
together for every entry point. ``_scoped_base`` is the single producer of a base
statement: it builds ``select(entity.model)`` and hands it to the entity scoper,
so there is no way to reach the query builder without first applying the scope.
Every public read path - ``run_view``, ``run_adhoc``, ``count_for_reminder``,
``to_export`` - flows through scope, then whitelist, then budget. There is no
sixth path.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_merge import merge_metadata
from app.modules.saved_views.errors import (
    BudgetError,
    ScopeDenied,
    WhitelistError,
)
from app.modules.saved_views.models import SavedView, SavedViewRun
from app.modules.saved_views.query_builder import SafeQueryBuilder, assert_within_budget
from app.modules.saved_views.registry import entity_registry
from app.modules.saved_views.repository import SavedViewRepository
from app.modules.saved_views.schemas import (
    CountResponse,
    FilterSpec,
    RunResponse,
    SavedViewCreate,
    SavedViewUpdate,
)
from app.modules.saved_views.scoper import ScopeContext

if TYPE_CHECKING:
    from app.modules.saved_views.registry import QueryableEntity

import os


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


STATEMENT_TIMEOUT_MS: int = _env_int("SAVED_VIEWS_TIMEOUT_MS", 4000)


class SavedViewService:
    """Save, run, count, and export saved views under the three gates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SavedViewRepository(session)

    # ── The scope choke point (primitive 1) ─────────────────────────────

    async def _scoped_base(
        self,
        entity: QueryableEntity,
        ctx: ScopeContext,
    ) -> Select:
        """Build ``select(entity.model)`` and hand it to the entity scoper.

        The ONLY producer of a base statement. Private, but it is the choke point
        the whole safety story rests on: the builder requires a base statement
        and only this method makes one.
        """
        base = select(entity.model)
        return await entity.scoper.scope(base, entity.model, ctx, self.session)

    # ── Run a stored view (all three gates) ─────────────────────────────

    async def run_view(
        self,
        view_id: uuid.UUID,
        ctx: ScopeContext,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> RunResponse:
        """Run a stored saved view through scope, whitelist, and budget."""
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        self._assert_view_visible(view, ctx)

        entity = self._require_entity(view.entity_type)
        spec = self._load_spec(view.spec)
        if page is not None:
            spec = spec.model_copy(update={"page": page})
        if page_size is not None:
            spec = spec.model_copy(update={"page_size": page_size})
        return await self._execute(entity, spec, ctx, saved_view_id=view.id)

    async def run_adhoc(
        self,
        entity_type: str,
        spec: FilterSpec,
        ctx: ScopeContext,
    ) -> RunResponse:
        """Run an inline spec without a stored row (the preview-before-save UX)."""
        entity = self._require_entity(entity_type)
        return await self._execute(entity, spec, ctx, saved_view_id=None)

    async def _execute(
        self,
        entity: QueryableEntity,
        spec: FilterSpec,
        ctx: ScopeContext,
        *,
        saved_view_id: uuid.UUID | None,
    ) -> RunResponse:
        """Compile + run a spec under all three gates, recording the run."""
        builder = SafeQueryBuilder(entity)
        start = time.perf_counter()
        try:
            # 2. WHITELIST - reject non-whitelisted fields / operators / values.
            spec.bind(entity)
            # 3. BUDGET (static) - refuse pathological specs before any DB hit.
            assert_within_budget(builder, spec)
            # 1. SCOPE - the base statement is scoped here, nowhere else.
            base = await self._scoped_base(entity, ctx)
            stmt = builder.build(base, spec)

            rows, truncated = await self._run_capped(stmt, builder.row_cap(spec.page_size))
        except WhitelistError:
            await self._record(saved_view_id, entity, ctx, 0, False, start, "whitelist")
            raise
        except BudgetError:
            await self._record(saved_view_id, entity, ctx, 0, False, start, "budget")
            raise
        except ScopeDenied:
            await self._record(saved_view_id, entity, ctx, 0, False, start, "scope")
            raise

        columns = self._result_columns(entity, spec)
        serialized = [self._serialize_row(entity, spec, r, columns) for r in rows]
        await self._record(saved_view_id, entity, ctx, len(serialized), truncated, start, "ok")
        return RunResponse(
            rows=serialized,
            columns=columns,
            total_estimate=None,
            truncated=truncated,
            page=spec.page,
            page_size=builder.row_cap(spec.page_size),
        )

    async def _run_capped(self, stmt: Select, cap: int) -> tuple[list[Any], bool]:
        """Execute under a statement timeout, trim the +1 sentinel."""
        try:
            await self._apply_statement_timeout()
            result = await self.session.execute(stmt)
            fetched = list(result.all())
        except Exception as exc:  # noqa: BLE001 - DB timeout / planner refusal
            if self._is_timeout(exc):
                raise BudgetError("The query took too long and was stopped; narrow your filter") from exc
            raise
        truncated = len(fetched) > cap
        return (fetched[:cap], truncated)

    async def _apply_statement_timeout(self) -> None:
        """Set a per-transaction ``statement_timeout`` on PostgreSQL.

        Bounds any query that somehow slips the static guards. No-op on a backend
        that does not support it. Never raises.
        """
        try:
            dialect = self.session.bind.dialect.name if self.session.bind else ""
            if dialect == "postgresql":
                await self.session.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
        except Exception:  # noqa: BLE001 - timeout is best-effort, never fatal
            return

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        """Heuristically detect a statement-timeout / cancel error."""
        text_blob = f"{type(exc).__name__}:{exc}".lower()
        return any(
            token in text_blob for token in ("statement_timeout", "canceling statement", "querycanceled", "timeout")
        )

    # ── Count for a reminder badge (capped) ─────────────────────────────

    async def count_for_reminder(
        self,
        view_id: uuid.UUID,
        ctx: ScopeContext,
    ) -> CountResponse:
        """Capped count for a reminder badge or dashboard tile."""
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        self._assert_view_visible(view, ctx)
        entity = self._require_entity(view.entity_type)
        spec = self._load_spec(view.spec)
        builder = SafeQueryBuilder(entity)
        spec.bind(entity)
        assert_within_budget(builder, spec)
        base = await self._scoped_base(entity, ctx)
        count_stmt = builder.build_count(base, spec)
        await self._apply_statement_timeout()
        try:
            result = await self.session.execute(count_stmt)
            count = int(result.scalar_one())
        except Exception as exc:  # noqa: BLE001
            if self._is_timeout(exc):
                raise BudgetError("The count took too long and was stopped") from exc
            raise
        cap = builder.row_cap(spec.page_size)
        truncated = count > cap
        return CountResponse(count=min(count, cap), truncated=truncated)

    # ── Export (chunked, capped) ────────────────────────────────────────

    async def to_export(
        self,
        view_id: uuid.UUID,
        ctx: ScopeContext,
        fmt: str = "csv",
    ) -> AsyncIterator[bytes]:
        """Stream a capped export (CSV) in chunks; never one unbounded fetch.

        Each page re-applies the row cap, honouring the 2GB-core rule. ``parquet``
        falls back to CSV bytes when pandas is unavailable; the CSV path is pure
        stdlib so it always works.
        """
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        self._assert_view_visible(view, ctx)
        entity = self._require_entity(view.entity_type)
        spec = self._load_spec(view.spec)
        spec.bind(entity)
        builder = SafeQueryBuilder(entity)
        assert_within_budget(builder, spec)
        columns = self._result_columns(entity, spec)

        import csv
        import io

        header = io.StringIO()
        csv.writer(header).writerow(columns)
        yield header.getvalue().encode("utf-8")

        page = 1
        cap = builder.row_cap(spec.page_size)
        while True:
            page_spec = spec.model_copy(update={"page": page})
            base = await self._scoped_base(entity, ctx)
            stmt = builder.build(base, page_spec)
            rows, truncated = await self._run_capped(stmt, cap)
            if not rows:
                break
            buf = io.StringIO()
            writer = csv.writer(buf)
            for r in rows:
                serialized = self._serialize_row(entity, page_spec, r, columns)
                writer.writerow([serialized.get(c, "") for c in columns])
            yield buf.getvalue().encode("utf-8")
            if not truncated:
                break
            page += 1

    # ── CRUD ────────────────────────────────────────────────────────────

    async def save_view(self, ctx: ScopeContext, payload: SavedViewCreate) -> SavedView:
        """Create a saved view after validating entity + spec + share grant."""
        entity = self._require_entity(payload.entity_type)
        # Re-validate the spec binds cleanly before persisting.
        payload.spec.bind(entity)
        self._assert_can_grant_share(payload.share_scope, ctx)
        view = SavedView(
            owner_id=ctx.user_id,
            project_id=payload.project_id,
            entity_type=payload.entity_type,
            name=payload.name,
            description=payload.description,
            spec=payload.spec.model_dump(mode="json"),
            share_scope=payload.share_scope,
            is_pinned=payload.is_pinned,
            metadata_=payload.metadata_,
        )
        return await self.repo.create(view)

    async def update_view(
        self,
        view_id: uuid.UUID,
        ctx: ScopeContext,
        payload: SavedViewUpdate,
    ) -> SavedView:
        """Update a view (owner or admin only)."""
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        self._assert_can_mutate(view, ctx)
        entity = self._require_entity(view.entity_type)
        fields: dict[str, Any] = {}
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.description is not None:
            fields["description"] = payload.description
        if payload.spec is not None:
            payload.spec.bind(entity)
            fields["spec"] = payload.spec.model_dump(mode="json")
        if payload.share_scope is not None:
            self._assert_can_grant_share(payload.share_scope, ctx)
            fields["share_scope"] = payload.share_scope
        if payload.is_pinned is not None:
            fields["is_pinned"] = payload.is_pinned
        if payload.metadata_ is not None:
            fields["metadata_"] = (
                merge_metadata(getattr(view, "metadata_", None), payload.metadata_)
                if isinstance(payload.metadata_, dict)
                else payload.metadata_
            )
        return await self.repo.update_fields(view, fields)

    async def delete_view(self, view_id: uuid.UUID, ctx: ScopeContext) -> None:
        """Delete a view (owner or admin only)."""
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        self._assert_can_mutate(view, ctx)
        await self.repo.delete(view)

    async def list_views(
        self,
        ctx: ScopeContext,
        *,
        entity_type: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[SavedView]:
        """List the caller's own views plus shared views in the project."""
        own = await self.repo.list_for_owner(ctx.user_id, entity_type=entity_type, project_id=project_id)
        shared: list[SavedView] = []
        if project_id is not None:
            shared = await self.repo.list_shared_in_project(project_id, entity_type=entity_type)
        merged: dict[uuid.UUID, SavedView] = {v.id: v for v in own}
        for v in shared:
            merged.setdefault(v.id, v)
        return list(merged.values())

    async def get_view(self, view_id: uuid.UUID, ctx: ScopeContext) -> SavedView:
        """Fetch one definition the caller may see.

        Unlike run / count / export, this path never flows through the scoper
        (it returns the stored definition, it does not run the stored spec), so
        the project-access check the scoper performs for those paths has to be
        applied here explicitly. A ``project`` / ``workspace`` shared view is
        readable only by a real member (owner / admin / team-member) of the
        view's OWN project, resolved via ``verify_project_access(view.project_id,
        ...)``. Trusting ``ctx.project_id`` - a caller-supplied query parameter -
        would let any holder of ``saved_views.read`` read a shared definition of
        a project they cannot access simply by echoing that project's id back in
        the request (there is no scoper on this path to catch it).
        """
        view = await self.repo.get_by_id(view_id)
        if view is None:
            raise ScopeDenied("Saved view not found")
        # Owner / admin: always visible.
        if ctx.is_admin or view.owner_id == ctx.user_id:
            return view
        # Shared (project / workspace): visible only to a real member of the
        # view's own project - never derived from the caller-supplied
        # ctx.project_id. Mirrors the scoper's access check on the run path.
        if view.share_scope in ("project", "workspace") and view.project_id is not None:
            from app.dependencies import verify_project_access

            try:
                await verify_project_access(view.project_id, str(ctx.user_id), self.session)
            except Exception as exc:  # noqa: BLE001 - normalise to a scope refusal
                from fastapi import HTTPException

                if isinstance(exc, HTTPException) and exc.status_code == 404:
                    raise ScopeDenied("Saved view not found") from exc
                raise
            return view
        # Private, or a shared view with no project pin: owner / admin only.
        raise ScopeDenied("Saved view not found")

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _require_entity(entity_type: str) -> QueryableEntity:
        entity = entity_registry.get(entity_type)
        if entity is None:
            raise WhitelistError(f"Unknown entity type {entity_type!r}", field="entity_type")
        return entity

    @staticmethod
    def _load_spec(raw: dict | None) -> FilterSpec:
        """Re-validate the stored spec JSON through Pydantic, never trust as-is."""
        return FilterSpec.model_validate(raw or {})

    def _assert_view_visible(self, view: SavedView, ctx: ScopeContext) -> None:
        """Refuse to read a definition the caller may not see.

        Owner always; ``project``/``workspace`` views to anyone pinned to the
        same project (record access is still gated by the row scoper at run time).
        Admin may read any definition.
        """
        if ctx.is_admin or view.owner_id == ctx.user_id:
            return
        if view.share_scope in ("project", "workspace") and view.project_id == ctx.project_id:
            return
        raise ScopeDenied("Saved view not found")

    def _assert_can_mutate(self, view: SavedView, ctx: ScopeContext) -> None:
        """Only the owner or an admin may update / delete a definition."""
        if ctx.is_admin or view.owner_id == ctx.user_id:
            return
        raise ScopeDenied("Saved view not found")

    def _assert_can_grant_share(self, share_scope: str, ctx: ScopeContext) -> None:
        """Only a project owner / admin may create a ``workspace``-shared view."""
        if share_scope != "workspace":
            return
        # role is the canonical, DB-rehydrated role; manager+ or admin may grant
        # a workspace share. A plain editor / viewer cannot.
        if ctx.is_admin or ctx.role in ("manager", "owner"):
            return
        raise WhitelistError(
            "Only a project owner or admin may create a workspace-shared view",
            field="share_scope",
        )

    @staticmethod
    def _result_columns(entity: QueryableEntity, spec: FilterSpec) -> list[str]:
        """Resolve the output column names for a spec."""
        if spec.group_by:
            return [*spec.group_by, "count"]
        if spec.columns:
            return list(spec.columns)
        if entity.default_columns:
            return list(entity.default_columns)
        return [name for name, fs in entity.fields.items() if fs.selectable]

    @staticmethod
    def _serialize_row(
        entity: QueryableEntity,
        spec: FilterSpec,
        row: Any,
        columns: Iterable[str],
    ) -> dict[str, Any]:
        """Project a result row to a JSON-friendly dict of whitelisted columns."""
        out: dict[str, Any] = {}
        if spec.group_by:
            # Grouped rows are SQLAlchemy Row objects: group cols + count.
            mapping = row._mapping if hasattr(row, "_mapping") else {}
            for name in spec.group_by:
                column = entity.fields[name].column
                out[name] = _jsonable(mapping.get(column))
            out["count"] = int(mapping.get("count", 0) or 0)
            return out
        # Non-grouped rows: a ``select(model)`` yields a Row whose first element
        # is the ORM instance. Unwrap it whether the driver hands back a Row, a
        # tuple, or (defensively) the bare instance.
        if isinstance(row, entity.model):
            obj = row
        elif hasattr(row, "_mapping") or isinstance(row, (tuple, list)):
            obj = row[0]
        else:
            obj = row
        for name in columns:
            fs = entity.fields.get(name)
            if fs is None:
                continue
            out[name] = _jsonable(getattr(obj, fs.column, None))
        return out

    async def _record(
        self,
        saved_view_id: uuid.UUID | None,
        entity: QueryableEntity,
        ctx: ScopeContext,
        row_count: int,
        truncated: bool,
        start: float,
        outcome: str,
    ) -> None:
        """Append a ``SavedViewRun`` audit row. Never raises into the caller."""
        try:
            elapsed = int((time.perf_counter() - start) * 1000)
            run = SavedViewRun(
                saved_view_id=saved_view_id,
                owner_id=ctx.user_id,
                entity_type=entity.entity_type,
                row_count=row_count,
                truncated=truncated,
                elapsed_ms=elapsed,
                outcome=outcome,
            )
            await self.repo.record_run(run)
        except Exception:  # noqa: BLE001 - telemetry must never break a request
            return


def _jsonable(value: Any) -> Any:
    """Coerce a column value to a JSON-friendly scalar."""
    import datetime as _dt
    from decimal import Decimal

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return str(value)
