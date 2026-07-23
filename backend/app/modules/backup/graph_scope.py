"""Schema-driven derivation of the per-user backup scope.

The original backup covered a curated set of 19 tables via a hand-written
``_BACKUP_SCOPE``. Any user-owned table added since then (equipment logs, CRM
rows, portal data, HSE records and so on) silently fell outside a personal
backup, so a restore on a fresh machine quietly dropped that data. This module
closes that gap by deriving the FULL set of user-owned tables straight from the
mapped schema, rooted at the users and projects tables.

The rule is a fixpoint over the foreign-key / naming graph. A table is in scope
when any of the following holds:

  - it carries an owner-ish user column by NAME (see ``USER_OWNER_COLUMNS``) -
    real FK constraints to the users table are frequently absent because those
    columns are string GUIDs, so the name is the reliable signal;
  - it carries a ``project_id`` column (the dominant per-project convention,
    also often without a declared FK);
  - it has a real foreign key into a table already proven to be in scope
    (children such as positions -> boqs -> projects).

Reference, catalog and global tables (cost catalogs, FX rates, i18n data,
equipment master data, index series) have none of these and stay excluded,
exactly as before. Predicates are OR'd at query time, so every ownership path a
table exposes is captured and a row is backed up if it matches any of them.

The derivation was validated against the 19 hand-written scopes: all 19 are
reproduced (each hand predicate is a subset of the derived predicate set) and no
excluded table carries a ``project_id`` or user-owner column, i.e. the wider net
never drops a row the curated set would have kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import MetaData, Table

USERS_TABLE = "oe_users_user"
PROJECTS_TABLE = "oe_projects_project"

# Columns whose NAME means "this row belongs to a user". FK constraints to the
# users table are often missing (string GUID columns), so name matching is the
# reliable ownership signal.
USER_OWNER_COLUMNS: tuple[str, ...] = (
    "owner_id",
    "created_by",
    "created_by_id",
    "user_id",
    "author_id",
    "uploaded_by",
)

# A scope predicate is one of:
#   ("self",)                      -> the users row itself (root)
#   ("eq", column)                 -> column == the backing user id
#   ("in", fk_column, parent_key)  -> fk_column in the set of in-scope parent ids
Predicate = tuple[str, ...]


@dataclass(frozen=True)
class BackupGraph:
    """Result of deriving the backup scope from a schema.

    Attributes:
        table_defs: ``(key, tablename)`` pairs for every in-scope table, in a
            deterministic order (users first, then alphabetical by table name).
        scope: ``key -> list[Predicate]`` in the same key space as
            ``key_for_table``. Predicates are OR'd by the query builder.
        key_for_table: ``tablename -> key``. Historically scoped tables keep
            their friendly key (``projects``, ``boqs`` ...) so existing backup
            manifests still restore; every other table keys off its own name.
    """

    table_defs: list[tuple[str, str]]
    scope: dict[str, list[Predicate]]
    key_for_table: dict[str, str]


def _user_owner_columns(table: Table) -> list[str]:
    """Owner-ish columns present on ``table``, matched by name."""
    present = {c.name for c in table.columns}
    return [c for c in USER_OWNER_COLUMNS if c in present]


def _column_names(table: Table) -> set[str]:
    return {c.name for c in table.columns}


def _fk_edges(table: Table) -> list[tuple[str, str]]:
    """``(local_column, target_table)`` for every FK not pointing at users/self."""
    edges: list[tuple[str, str]] = []
    for fk in table.foreign_keys:
        target = fk.column.table.name
        if target not in (USERS_TABLE, table.name):
            edges.append((fk.parent.name, target))
    return edges


def _topological_order(
    scope: dict[str, list[Predicate]],
    keys: list[str],
    users_key: str | None,
) -> list[str]:
    """Order ``keys`` so every ``("in", _, parent)`` parent precedes its child.

    Restore inserts tables in this order (a parent row exists before any row that
    references it) and clears them in reverse (children before parents), so the
    order must be a topological sort over the parent edges encoded in the scope
    predicates. Kahn's algorithm by levels: the users root leads, remaining ties
    break alphabetically so the order is deterministic. A dependency cycle (none
    exist in today's schema, but a future two-table loop could form one) cannot
    stall the sort - when no node can be emitted the remainder is appended in
    alphabetical order, and the resilient multi-pass importer still lands those
    rows once their parents are in.
    """
    keyset = set(keys)
    parents: dict[str, set[str]] = {}
    for key in keyset:
        deps: set[str] = set()
        for predicate in scope.get(key, []):
            if predicate[0] == "in":
                parent = predicate[2]
                if parent in keyset and parent != key:
                    deps.add(parent)
        parents[key] = deps

    ordered: list[str] = []
    emitted: set[str] = set()
    if users_key is not None and users_key in keyset:
        ordered.append(users_key)
        emitted.add(users_key)

    remaining = sorted(k for k in keyset if k not in emitted)
    while remaining:
        ready = [k for k in remaining if parents[k] <= emitted]
        if not ready:
            # Cycle: emit the remainder deterministically rather than loop forever.
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        emitted.update(ready)
        remaining = [k for k in remaining if k not in emitted]
    return ordered


def derive_backup_graph(
    metadata: MetaData,
    mapped_tables: set[str],
    friendly_keys: dict[str, str] | None = None,
) -> BackupGraph:
    """Derive the full user-owned backup scope from ``metadata``.

    Args:
        metadata: SQLAlchemy metadata holding every registered table.
        mapped_tables: table names that have a mapped ORM class. Pure
            association/secondary tables (no class to serialize) are skipped.
        friendly_keys: optional ``tablename -> key`` overrides so the
            historically curated tables keep their stable keys. Any table not
            listed keys off its own table name.

    Returns:
        A :class:`BackupGraph` whose predicates reference parents by key.
    """
    friendly = dict(friendly_keys or {})
    tables = dict(metadata.tables)

    # Fixpoint: keep unioning predicates onto every candidate table until no new
    # predicate appears. Membership is settled the first time a table gains any
    # predicate; later passes only enrich existing members with further
    # ownership paths (e.g. an FK whose parent joined the scope in a later pass).
    preds: dict[str, set[Predicate]] = {}
    in_scope: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, table in tables.items():
            if name == USERS_TABLE:
                continue
            found: set[Predicate] = {("eq", col) for col in _user_owner_columns(table)}
            if "project_id" in _column_names(table) and name != PROJECTS_TABLE:
                found.add(("in", "project_id", PROJECTS_TABLE))
            for local_col, target in _fk_edges(table):
                if target in in_scope:
                    found.add(("in", local_col, target))
            if not found:
                continue
            previous = preds.get(name, set())
            if name not in in_scope or (found - previous):
                in_scope.add(name)
                preds[name] = previous | found
                changed = True

    # Key space: friendly key where known, table name otherwise. The full map
    # (every in-scope table, mapped or not) is used to translate predicate
    # parents; only backed-up tables are exposed on the result.
    def key_of(table_name: str) -> str:
        return friendly.get(table_name, table_name)

    resolve_key: dict[str, str] = {USERS_TABLE: friendly.get(USERS_TABLE, "users")}
    for name in in_scope:
        resolve_key[name] = key_of(name)

    scope: dict[str, list[Predicate]] = {}
    key_for_table: dict[str, str] = {}
    key_to_table: dict[str, str] = {}

    users_key: str | None = None
    if USERS_TABLE in tables and USERS_TABLE in mapped_tables:
        users_key = resolve_key[USERS_TABLE]
        scope[users_key] = [("self",)]
        key_for_table[USERS_TABLE] = users_key
        key_to_table[users_key] = USERS_TABLE

    for name in sorted(in_scope):
        if name not in mapped_tables:
            continue
        key = resolve_key[name]
        translated: list[Predicate] = []
        for predicate in sorted(preds[name]):
            if predicate[0] == "in":
                _, fk_col, parent_table = predicate
                translated.append(("in", fk_col, resolve_key.get(parent_table, parent_table)))
            else:
                translated.append(predicate)
        scope[key] = translated
        key_for_table[name] = key
        key_to_table[key] = name

    # Emit parents before children so a restore is FK-safe (see
    # ``_topological_order``). The users root leads; the historically hand-ordered
    # curated tables keep an equivalent relative order because it is the same
    # dependency chain (projects -> boqs -> positions ...).
    ordered_keys = _topological_order(scope, list(key_to_table), users_key)
    table_defs = [(key, key_to_table[key]) for key in ordered_keys]

    return BackupGraph(table_defs=table_defs, scope=scope, key_for_table=key_for_table)
