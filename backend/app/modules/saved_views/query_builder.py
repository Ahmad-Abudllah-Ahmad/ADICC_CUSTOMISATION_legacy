# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The safe query builder and SAFETY PRIMITIVE 3 (the result budget).

``SafeQueryBuilder`` compiles an already-scoped base statement plus a bound,
whitelisted spec into a bounded parameterized ``Select``. It NEVER opens a
session and NEVER applies scope itself - that separation is what makes "you
cannot build without scoping" structurally true: the scope arrives baked into
``base_stmt``, produced only by the service via the entity scoper.

The result budget is enforced here in two static layers, both BEFORE the DB is
touched:

    1. ROW CAP - the builder always appends ``.limit(cap + 1)`` where
       ``cap = min(page_size, entity.max_rows, GLOBAL_MAX_ROWS)``; the ``+ 1`` is
       the sentinel the service uses to detect truncation. There is no
       "unlimited" branch: ``page_size <= 0`` is impossible (Pydantic ``ge=1``)
       and is additionally clamped to the entity default.
    2. COMPLEXITY CEILING - ``estimate_cost`` scores the spec shape and the
       service refuses (``BudgetError``) above ``MAX_COMPLEXITY`` before any
       round-trip.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, and_, func, or_, select

from app.modules.saved_views.errors import BudgetError
from app.modules.saved_views.schemas import FilterCondition, FilterGroup, FilterSpec

if TYPE_CHECKING:
    from app.modules.saved_views.registry import FieldSpec, QueryableEntity


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Global, env-overridable ceilings.
GLOBAL_MAX_ROWS: int = _env_int("SAVED_VIEWS_MAX_ROWS", 500)
MAX_COMPLEXITY: int = _env_int("SAVED_VIEWS_MAX_COMPLEXITY", 12)

# LIKE special characters escaped so a user value cannot inject a wildcard.
_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a user value matches literally."""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    )


class SafeQueryBuilder:
    """Compile a bound spec into a bounded, parameterized ``Select``."""

    def __init__(self, entity: QueryableEntity) -> None:
        self.entity = entity

    # ── Budget: the static complexity ceiling (primitive 3) ─────────────

    def estimate_cost(self, spec: FilterSpec) -> int:
        """Score the spec shape: ``n_filters + 3*n_group_by + 2*(distinct)``.

        Static - it never touches the database, so it cannot be evaded by data
        volume. The service compares the result against :data:`MAX_COMPLEXITY`.
        """
        n_filters = _count_conditions(spec.where)
        n_group_by = len(spec.group_by)
        distinct_term = 2 if spec.distinct else 0
        return n_filters + 3 * n_group_by + distinct_term

    def row_cap(self, page_size: int) -> int:
        """The effective hard row cap for a requested page size.

        ``min(page_size, entity.max_rows, GLOBAL_MAX_ROWS)``, never zero or
        unbounded. A non-positive ``page_size`` clamps to the entity default.
        """
        if page_size <= 0:
            page_size = self.entity.default_page_size
        return max(1, min(page_size, self.entity.max_rows, GLOBAL_MAX_ROWS))

    # ── Compilation ─────────────────────────────────────────────────────

    def build(self, base_stmt: Select, spec: FilterSpec) -> Select:
        """Compile the user spec onto the already-scoped ``base_stmt``.

        Steps: resolve whitelisted fields to real ORM attributes, compile the
        filter tree into ``and_``/``or_`` of bind-param comparisons, apply sort,
        apply group_by + a count aggregate, apply distinct, and ALWAYS append the
        hard row cap. Never touches scope.

        Args:
            base_stmt: A ``select()`` already narrowed by the scoper.
            spec: The user filter spec (already bound / whitelisted).

        Returns:
            A bounded ``Select`` ready to execute.
        """
        model = self.entity.model
        stmt = base_stmt

        predicate = self._compile_group(spec.where)
        if predicate is not None:
            stmt = stmt.where(predicate)

        if spec.group_by:
            # Group over a subquery that already carries the scope + filters, so
            # the aggregate can never widen past the scoped row set. The grouped
            # columns are the whitelisted, groupable (indexed) fields.
            sub = base_stmt
            if predicate is not None:
                sub = sub.where(predicate)
            sub_alias = sub.subquery()
            grouped = [getattr(sub_alias.c, self.entity.fields[name].column) for name in spec.group_by]
            stmt = select(*grouped, func.count().label("count")).select_from(sub_alias).group_by(*grouped)

        if spec.sort and not spec.group_by:
            order_terms = []
            for sort in spec.sort:
                col = self._resolve_column(sort.field)
                order_terms.append(col.desc() if sort.direction == "desc" else col.asc())
            stmt = stmt.order_by(*order_terms)
        elif not spec.group_by:
            field_name, direction = self.entity.default_sort
            col = self._resolve_column(field_name)
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc())

        if spec.distinct and not spec.group_by:
            stmt = stmt.distinct()

        cap = self.row_cap(spec.page_size)
        offset = (spec.page - 1) * cap
        # +1 sentinel: a (cap + 1)-row result signals "more rows exist".
        stmt = stmt.offset(offset).limit(cap + 1)
        return stmt

    def build_count(self, base_stmt: Select, spec: FilterSpec) -> Select:
        """Build a capped count query over the scoped+filtered rows.

        The inner subquery is itself row-capped so a count cannot scan
        unboundedly: it counts at most ``cap + 1`` rows and the service reports
        ``truncated`` when the cap is hit.
        """
        predicate = self._compile_group(spec.where)
        sub = base_stmt
        if predicate is not None:
            sub = sub.where(predicate)
        cap = self.row_cap(spec.page_size)
        sub_capped = sub.limit(cap + 1).subquery()
        return select(func.count()).select_from(sub_capped)

    # ── Internals ───────────────────────────────────────────────────────

    def _resolve_column(self, field_name: str):  # noqa: ANN202
        """Resolve a whitelisted field name to its real ORM attribute.

        ``getattr`` is only ever applied to ``FieldSpec.column`` from the bound
        entity, never to a raw client string.
        """
        fs = self.entity.fields[field_name]
        return getattr(self.entity.model, fs.column)

    def _compile_group(self, group: FilterGroup):  # noqa: ANN202
        """Compile a filter group into a single SQLAlchemy boolean expression."""
        terms: list[Any] = []
        for cond in group.conditions:
            terms.append(self._compile_condition(cond))
        for sub in group.groups:
            compiled = self._compile_group(sub)
            if compiled is not None:
                terms.append(compiled)
        if not terms:
            return None
        if group.join == "or":
            return or_(*terms)
        return and_(*terms)

    def _compile_condition(self, cond: FilterCondition):  # noqa: ANN202
        """Map one condition to a bind-parameterized column expression."""
        fs = self.entity.fields[cond.field]
        col = getattr(self.entity.model, fs.column)
        op = cond.op

        if op == "is_null":
            return col.is_(None)
        if op == "not_null":
            return col.isnot(None)
        if op == "eq":
            return col == self._coerce(fs, cond.value)
        if op == "neq":
            return col != self._coerce(fs, cond.value)
        if op == "lt":
            return col < self._coerce(fs, cond.value)
        if op == "lte":
            return col <= self._coerce(fs, cond.value)
        if op == "gt":
            return col > self._coerce(fs, cond.value)
        if op == "gte":
            return col >= self._coerce(fs, cond.value)
        if op == "contains":
            escaped = _escape_like(str(cond.value))
            return col.ilike(f"%{escaped}%", escape=_LIKE_ESCAPE)
        if op == "startswith":
            escaped = _escape_like(str(cond.value))
            return col.ilike(f"{escaped}%", escape=_LIKE_ESCAPE)
        if op == "in":
            values = [self._coerce(fs, v) for v in cond.value]
            return col.in_(values)
        if op == "between":
            lo, hi = cond.value
            return col.between(self._coerce(fs, lo), self._coerce(fs, hi))
        # Unreachable: bind() already rejected unknown operators.
        raise BudgetError(f"Unsupported operator {op!r}")

    @staticmethod
    def _coerce(fs: FieldSpec, value: Any) -> Any:
        """Coerce a value to the field kind for the bind parameter."""
        kind = fs.kind
        if value is None:
            return None
        if kind in ("number", "money"):
            return Decimal(str(value))
        if kind == "bool":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1")
        # uuid / date / enum / string: SQLAlchemy + the column type handle the
        # bind; the GUID type accepts a str, dates are ISO strings on these
        # models, enums are plain strings.
        return value


def _count_conditions(group: FilterGroup) -> int:
    """Total number of leaf conditions across a filter group tree."""
    total = len(group.conditions)
    for sub in group.groups:
        total += _count_conditions(sub)
    return total


def assert_within_budget(builder: SafeQueryBuilder, spec: FilterSpec) -> None:
    """Raise ``BudgetError`` when the spec exceeds the static complexity ceiling.

    Called by the service BEFORE any database round-trip.
    """
    cost = builder.estimate_cost(spec)
    if cost > MAX_COMPLEXITY:
        raise BudgetError(
            f"Query is too complex (score {cost} > {MAX_COMPLEXITY}); reduce the number of filters or grouping columns"
        )
