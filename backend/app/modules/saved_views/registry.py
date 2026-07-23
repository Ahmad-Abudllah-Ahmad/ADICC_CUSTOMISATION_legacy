# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""SAFETY PRIMITIVE 2 - the per-entity column whitelist.

Only explicitly whitelisted columns can be filtered, sorted, grouped, or
returned for a given entity. A module opts an entity in by calling
:func:`register_queryable_entity` from its own ``on_startup`` - it never edits
this module. The registration is validated eagerly, so a misconfigured entity
(missing scoper, unknown column, ungroupable group target) fails the boot rather
than a request.

The actual whitelist enforcement at query time lives in
:meth:`app.modules.saved_views.schemas.FilterSpec.bind`, which only ever reads
``FieldSpec.column`` from an entity validated here - there is no path for an
arbitrary string to reach ``getattr`` on the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from app.database import Base
from app.modules.saved_views.errors import RegistrationError

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.saved_views.scoper import ScopeContext

FieldKind = Literal["string", "number", "money", "bool", "date", "uuid", "enum"]


@runtime_checkable
class EntityScoper(Protocol):
    """The mandatory scoper contract a registration must supply.

    See ``scoper.py`` for the full description and the built-in
    ``ProjectMemberScoper``. A registration without one is rejected at
    registration time.
    """

    async def scope(
        self,
        stmt: Select,
        model: type[Base],
        ctx: ScopeContext,
        session: AsyncSession,
    ) -> Select:
        """Return ``stmt`` with mandatory scope predicates ANDed in.

        MUST narrow, never widen. MUST raise
        :class:`app.modules.saved_views.errors.ScopeDenied` to refuse outright.
        """
        ...


@dataclass(frozen=True)
class FieldSpec:
    """One whitelisted column on a queryable entity.

    Attributes:
        name: The key the client uses in the FilterSpec.
        column: The real ORM attribute name on the model.
        kind: The value kind, drives coercion and the default operator set.
        filterable: May appear in ``where`` conditions.
        sortable: May appear in ``sort``.
        selectable: May appear in the returned ``columns``.
        groupable: May appear in ``group_by``. Only allowed on indexed columns.
        enum_values: Allowed values when ``kind == "enum"``.
        operators: Explicit allowed operator set; empty falls back to the kind
            default.
    """

    name: str
    column: str
    kind: FieldKind
    filterable: bool = True
    sortable: bool = True
    selectable: bool = True
    groupable: bool = False
    enum_values: tuple[str, ...] | None = None
    operators: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryableEntity:
    """A registered, queryable entity: a model plus its whitelist and scoper.

    Attributes:
        entity_type: Registry key, e.g. ``"ledger_entry"``.
        model: The SQLAlchemy model class.
        fields: Whitelisted columns keyed by ``FieldSpec.name``.
        project_fk_column: The model attribute the scoper pins to a project, or
            ``None`` when the project pin is reached indirectly (see
            ``project_subquery``).
        scoper: The MANDATORY scoper.
        default_sort: ``(field_name, "asc"|"desc")`` applied when no sort given.
        default_columns: Columns returned when the spec asks for none.
        max_rows: Entity-level override of the global row cap.
        default_page_size: Page size used when the request asks for none / zero.
        project_subquery: Optional callable ``(project_id) -> Select`` returning a
            scalar subquery of this model's primary keys that belong to a
            project, for entities with no direct project FK (e.g. boq_position
            reached through its BOQ).
    """

    entity_type: str
    model: type[Base]
    fields: dict[str, FieldSpec]
    scoper: EntityScoper
    default_sort: tuple[str, str]
    project_fk_column: str | None = None
    default_columns: tuple[str, ...] = ()
    max_rows: int = 500
    default_page_size: int = 50
    project_subquery: object | None = field(default=None)


class EntityRegistry:
    """Module-global singleton storing every registered queryable entity."""

    def __init__(self) -> None:
        self._entities: dict[str, QueryableEntity] = {}

    def register(self, entity: QueryableEntity) -> None:
        """Validate and store an entity. See :func:`register_queryable_entity`."""
        _validate_entity(entity)
        if entity.entity_type in self._entities:
            raise RegistrationError(f"Entity type {entity.entity_type!r} is already registered")
        self._entities[entity.entity_type] = entity

    def get(self, entity_type: str) -> QueryableEntity | None:
        """Return the entity for ``entity_type`` or ``None``."""
        return self._entities.get(entity_type)

    def require(self, entity_type: str) -> QueryableEntity:
        """Return the entity or raise ``KeyError`` (caller maps to 422)."""
        entity = self._entities.get(entity_type)
        if entity is None:
            raise KeyError(entity_type)
        return entity

    def list_types(self) -> list[str]:
        """Sorted list of registered entity types."""
        return sorted(self._entities.keys())

    def all(self) -> dict[str, QueryableEntity]:
        """A shallow copy of the registry map."""
        return dict(self._entities)

    def clear(self) -> None:
        """Remove every entity. Used in tests."""
        self._entities.clear()


def _model_has_attr(model: type[Base], attr: str) -> bool:
    """True iff ``attr`` is a real mapped column attribute on ``model``."""
    try:
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(model)
        return attr in mapper.columns.keys() or attr in {p.key for p in mapper.column_attrs}
    except Exception:  # noqa: BLE001 - any inspection failure means "not a column"
        return False


def _indexed_columns(model: type[Base]) -> set[str]:
    """Return the set of column names that participate in any index or PK.

    A column is considered indexed if it carries ``index=True`` (single-column
    index), is the primary key, or appears as the first member of any composite
    ``Index`` in ``__table_args__``. ``group_by`` is only allowed on these.
    """
    indexed: set[str] = set()
    try:
        table = model.__table__
    except AttributeError:
        return indexed
    for col in table.columns:
        if col.primary_key or col.index:
            indexed.add(col.name)
    for idx in table.indexes:
        cols = list(idx.columns)
        if cols:
            # The leading column of a composite index is usable for grouping.
            indexed.add(cols[0].name)
    return indexed


def _validate_entity(entity: QueryableEntity) -> None:
    """Reject an invalid entity at registration time.

    Raises:
        RegistrationError: missing scoper; a FieldSpec.column that is not a real
            mapped column; ``groupable=True`` on a non-indexed column; a
            ``project_fk_column`` absent from the model.
    """
    if entity.scoper is None:
        raise RegistrationError(
            f"Entity {entity.entity_type!r} registered without a scoper; every queryable entity must supply one"
        )
    if not isinstance(entity.scoper, EntityScoper):
        raise RegistrationError(f"Entity {entity.entity_type!r} scoper does not implement the EntityScoper protocol")

    indexed = _indexed_columns(entity.model)
    column_attrs = {c.name for c in entity.model.__table__.columns}

    for name, fs in entity.fields.items():
        if not _model_has_attr(entity.model, fs.column):
            raise RegistrationError(
                f"Field {name!r} on {entity.entity_type!r} maps to column "
                f"{fs.column!r}, which is not a mapped column on {entity.model.__name__}"
            )
        if fs.groupable and fs.column not in indexed:
            raise RegistrationError(
                f"Field {name!r} on {entity.entity_type!r} is groupable but its "
                f"column {fs.column!r} is not indexed; grouping on non-indexed "
                "columns is not allowed"
            )
        if fs.kind == "enum" and not fs.enum_values:
            raise RegistrationError(f"Field {name!r} on {entity.entity_type!r} is an enum but lists no enum_values")

    # project_fk_column must resolve, unless reached via a subquery or the model
    # IS the project itself (where the pin is on the primary key).
    if entity.project_fk_column is not None and entity.project_subquery is None:
        if entity.project_fk_column not in column_attrs and not _model_has_attr(entity.model, entity.project_fk_column):
            raise RegistrationError(
                f"Entity {entity.entity_type!r} declares project_fk_column "
                f"{entity.project_fk_column!r}, absent from {entity.model.__name__}"
            )
    if entity.project_fk_column is None and entity.project_subquery is None:
        raise RegistrationError(
            f"Entity {entity.entity_type!r} must declare either a "
            "project_fk_column or a project_subquery so the scoper can pin a project"
        )

    # default_sort must reference a sortable whitelisted field.
    sort_field, sort_dir = entity.default_sort
    fs = entity.fields.get(sort_field)
    if fs is None or not fs.sortable:
        raise RegistrationError(
            f"Entity {entity.entity_type!r} default_sort references {sort_field!r}, "
            "which is not a sortable whitelisted field"
        )
    if sort_dir not in ("asc", "desc"):
        raise RegistrationError(f"Entity {entity.entity_type!r} default_sort direction {sort_dir!r} is invalid")


# Module-global singleton.
entity_registry = EntityRegistry()


def register_queryable_entity(entity: QueryableEntity) -> None:
    """Register a queryable entity (the public opt-in API for any module).

    Validates and stores the entity. Raises :class:`RegistrationError` on a
    missing scoper, a duplicate entity type, a FieldSpec column that is not a
    real mapped column, ``groupable=True`` on a non-indexed column, or a
    ``project_fk_column`` absent from the model.

    Args:
        entity: The fully-built :class:`QueryableEntity`.

    Raises:
        RegistrationError: On any invalid registration.
    """
    entity_registry.register(entity)
