# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""SQLite -> PostgreSQL data migration.

One-shot copier that moves every row from the SQLite database into a freshly
created PostgreSQL database using the application's own SQLAlchemy metadata, so
column types, JSON handling and foreign keys all match the live schema.

The target schema is built with ``Base.metadata.create_all`` (NOT the Alembic
chain), which means the JSONB ``@compiles`` hook and the FK/GIN/composite
indexes from ``app.core.performance_indexes`` are emitted on the PostgreSQL
side exactly as a fresh install would get them.

Usage (run from the ``backend`` directory)::

    # 1. dry run -- counts only, never connects to write
    python -m app.scripts.migrate_sqlite_to_postgres \\
        --source sqlite:////root/OpenConstructionERP/data/openestimate.db \\
        --target postgresql+psycopg2://oe:PASS@localhost/openestimate \\
        --dry-run

    # 2. real migration into an empty (or --truncate) target
    python -m app.scripts.migrate_sqlite_to_postgres \\
        --source sqlite:////root/OpenConstructionERP/data/openestimate.db \\
        --target postgresql+psycopg2://oe:PASS@localhost/openestimate \\
        --truncate

Notes:
  * The SQLite source URL needs FOUR slashes for an absolute path.
  * The target database must already exist. The script refuses to write into a
    target that already holds rows unless ``--truncate`` is given.
  * Rows are streamed in batches (bounded memory) and copied in foreign-key
    order. Any row the target rejects (e.g. a not-yet-inserted self-referential
    parent) is deferred and retried in later passes; genuinely bad rows are
    skipped and counted, never aborting the whole run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator

from sqlalchemy import JSON as _JSON
from sqlalchemy import column as _column
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine

#: Rows per INSERT batch. Small enough to bound memory on a constrained VPS even
#: when a table carries large JSON/geometry blobs, large enough to keep the copy
#: fast for the many small tables.
DEFAULT_BATCH_SIZE = 1000

#: How many full retry passes to make over rows the target initially rejected
#: (covers self-referential FKs where a child is seen before its parent).
MAX_RETRY_PASSES = 5


def _load_metadata():
    """Import every model so ``Base.metadata`` is fully populated, return Base.

    Models are NOT registered by importing ``app.main`` -- they live in each
    module's ``models`` submodule and are only imported at app startup (or by
    Alembic). Replicate Alembic's discovery: walk ``app.modules.*`` and import
    every ``<module>.models``, then pull in the core registry. This is the same
    routine ``backend/alembic/env.py`` uses, so the metadata here is identical
    to what ``create_all`` / migrations produce.
    """
    import importlib
    import pkgutil

    # Core models (CostItem, User, BIMElement, etc.) registered centrally.
    try:
        import app.core.models_registry  # noqa: F401
    except Exception:  # noqa: BLE001
        pass

    # ``audit_log`` defines ``oe_activity_log`` and lives outside app.modules.*
    try:
        import app.core.audit_log  # noqa: F401
    except Exception:  # noqa: BLE001
        pass

    import app.modules as _mods

    imported = 0
    for _finder, name, _ispkg in pkgutil.iter_modules(_mods.__path__):
        try:
            importlib.import_module(f"app.modules.{name}.models")
            imported += 1
        except ModuleNotFoundError:
            # Module has no models.py -- fine, skip it.
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"warning: importing app.modules.{name}.models raised {exc!r}", file=sys.stderr)

    from app.database import Base

    print(f"model discovery: imported {imported} module model packages; {len(Base.metadata.tables)} tables registered")
    return Base


def _tolerant_json_deserializer(value: object) -> object:
    """Parse a JSON column without aborting on legacy/malformed scalars.

    Mirrors ``app.database._tolerant_json_loads``: some historical SQLite rows
    hold a bare scalar (``construction`` instead of ``["construction"]``) which
    the default ``json.loads`` would raise on during result processing. Return
    the raw value instead so the copy never dies on one bad row.
    """
    try:
        return json.loads(value)  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError, ValueError):
        return value


def _coerce_sync_url(url: str) -> str:
    """Coerce async driver URLs to their sync equivalents for this script."""
    repl = {
        "postgresql+asyncpg": "postgresql+psycopg2",
        "sqlite+aiosqlite": "sqlite",
    }
    for a, b in repl.items():
        if url.startswith(a):
            return url.replace(a, b, 1)
    return url


def _make_source_engine(url: str) -> Engine:
    """Build the SQLite read engine with the same tolerant JSON handling the app
    uses, so JSON columns come back as Python objects (dict/list) and the target
    side re-serialises them once into JSONB instead of double-encoding a string.
    """
    return create_engine(url, json_deserializer=_tolerant_json_deserializer)


def _iter_batches(src: Engine, table, batch_size: int, columns=None) -> Iterator[list[dict]]:
    """Yield rows of ``table`` from the source in memory-bounded batches.

    ``columns`` restricts the SELECT to a subset of the table's columns. This is
    how a cross-version copy stays alive: the new release may have added columns
    that the older source table does not have, so selecting the full metadata
    column set would raise "no such column". Selecting only the columns the
    source actually has lets the target fill the new ones from their defaults.

    The read is done with UNTYPED column expressions so SQLAlchemy does not run
    the metadata's typed result processors on the source value. SQLite is loosely
    typed: a ``Numeric``/``Float`` column can hold a stored *string* (e.g. a rate
    persisted as ``"10.0"``), and the strict ``Decimal``/``float`` result
    processor raises ``TypeError: must be real number, not str`` on such a row,
    aborting the whole copy. Reading raw text and letting the target's bind
    processor coerce on insert mirrors the tolerant-JSON handling and survives
    every legacy scalar.
    """
    cols = columns if columns is not None else list(table.columns)
    selectable = select(*[_column(c.name) for c in cols]).select_from(table)
    with src.connect() as sconn:
        result = sconn.execution_options(stream_results=True, yield_per=batch_size).execute(selectable)
        while True:
            chunk = result.fetchmany(batch_size)
            if not chunk:
                break
            yield [dict(r._mapping) for r in chunk]


def _coerce_row(row: dict, table) -> dict:
    """Patch the residual case where a JSON column still arrives as a ``str`` so
    the JSONB bind processor does not double-encode it. The source is read with
    untyped expressions, so JSON columns come back as raw text; this parses them
    once. The target bind processors coerce the remaining scalar types
    (bool/Decimal/datetime) on insert.
    """
    for col in table.columns:
        name = col.name
        if name not in row or row[name] is None:
            continue
        if isinstance(col.type, _JSON) and isinstance(row[name], str):
            row[name] = _tolerant_json_deserializer(row[name])
    return row


def _source_columns(src: Engine, table):
    """Return the table columns that actually exist in the source database.

    The new release's metadata can carry columns an older source table lacks
    (a migration added them after the source was last upgraded). Copying only
    the intersection keeps the SELECT valid; the missing columns are populated
    on the target by their server_default / Python default during insert.
    """
    src_col_names = {c["name"] for c in inspect(src).get_columns(table.name)}
    return [c for c in table.columns if c.name in src_col_names]


def _copy_table(src: Engine, dst: Engine, table, batch_size: int) -> tuple[int, list[dict]]:
    """Copy one table. Returns (rows_copied, rows_deferred).

    Batched insert with per-row fault isolation: if a batch insert fails (most
    commonly a self-referential FK whose parent is not in yet), fall back to
    inserting that batch row by row. Rows that fail individually are returned as
    *deferred* for a later retry pass.
    """
    copied = 0
    deferred: list[dict] = []
    columns = _source_columns(src, table)
    for batch in _iter_batches(src, table, batch_size, columns):
        batch = [_coerce_row(r, table) for r in batch]
        try:
            with dst.begin() as dconn:
                dconn.execute(table.insert(), batch)
            copied += len(batch)
        except Exception:  # noqa: BLE001 -- isolate the offending row(s)
            for row in batch:
                try:
                    with dst.begin() as dconn:
                        dconn.execute(table.insert(), [row])
                    copied += 1
                except Exception:  # noqa: BLE001
                    deferred.append(row)
    return copied, deferred


def _retry_deferred(dst: Engine, table, rows: list[dict]) -> tuple[int, list[dict]]:
    """Retry deferred rows once. Returns (rows_copied, rows_still_failing)."""
    copied = 0
    still: list[dict] = []
    for row in rows:
        try:
            with dst.begin() as dconn:
                dconn.execute(table.insert(), [row])
            copied += 1
        except Exception:  # noqa: BLE001
            still.append(row)
    return copied, still


def _target_has_rows(dst: Engine, base) -> str | None:
    """Return the name of the first target table that already holds rows, if any."""
    with dst.connect() as dconn:
        existing = set(inspect(dconn).get_table_names())
        for table in base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            n = dconn.execute(select(func.count()).select_from(table)).scalar() or 0
            if n:
                return table.name
    return None


def _copy_all(src: Engine, dst: Engine, base, batch_size: int) -> int:
    """Copy every table in FK order, then retry deferred rows until they settle.

    Returns the number of rows that could not be inserted (skipped).
    """
    total_copied = 0
    deferred_by_table: dict[str, tuple[object, list[dict]]] = {}

    # The app metadata is the schema of the NEW release; the source SQLite is an
    # OLDER database. Any table a newer module added does not exist in the source
    # yet, so selecting from it raises "no such table" and would abort the whole
    # copy. Read the source's real table set once and skip the absent ones; the
    # target already has them (empty) from create_all, which is the correct state.
    with src.connect() as sconn:
        source_tables = set(inspect(sconn).get_table_names())
    missing = [t.name for t in base.metadata.sorted_tables if t.name not in source_tables]
    if missing:
        print(f"skipping {len(missing)} tables absent from source (new in this release): {', '.join(missing)}")

    for table in base.metadata.sorted_tables:
        if table.name not in source_tables:
            continue
        copied, deferred = _copy_table(src, dst, table, batch_size)
        total_copied += copied
        if copied or deferred:
            note = f"  {table.name}: {copied} rows"
            if deferred:
                note += f" ({len(deferred)} deferred)"
            print(note)
        if deferred:
            deferred_by_table[table.name] = (table, deferred)

    for pass_no in range(1, MAX_RETRY_PASSES + 1):
        if not deferred_by_table:
            break
        progress = 0
        next_round: dict[str, tuple[object, list[dict]]] = {}
        for tname, (table, rows) in deferred_by_table.items():
            copied, still = _retry_deferred(dst, table, rows)
            total_copied += copied
            progress += copied
            if still:
                next_round[tname] = (table, still)
        print(f"retry pass {pass_no}: recovered {progress} deferred rows")
        deferred_by_table = next_round
        if progress == 0:
            break  # no forward progress -- remaining rows are genuinely bad

    skipped = sum(len(rows) for _t, rows in deferred_by_table.values())
    if skipped:
        print(f"WARNING: {skipped} rows could not be inserted and were skipped:", file=sys.stderr)
        for tname, (_t, rows) in deferred_by_table.items():
            print(f"  {tname}: {len(rows)} skipped", file=sys.stderr)

    print(f"total rows copied: {total_copied}; rows skipped: {skipped}")
    return skipped


def _reset_sequences(dst: Engine, base) -> None:
    """Defensively realign integer IDENTITY/serial sequences after a bulk copy.

    The app uses string UUID primary keys (``GUID`` -> ``String(36)``), so most
    tables have no sequence and this is a no-op; it only matters for the rare
    integer autoincrement table (e.g. ``oe_feedback``). Never errors the run.
    """
    if dst.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    with dst.connect() as dconn:
        for table in base.metadata.sorted_tables:
            for col in table.columns:
                if not col.primary_key:
                    continue
                try:
                    is_int = col.type.python_type is int
                except (NotImplementedError, AttributeError):
                    is_int = False
                if not is_int:
                    continue
                try:
                    seq = dconn.execute(
                        text("SELECT pg_get_serial_sequence(:t, :c)"),
                        {"t": table.name, "c": col.name},
                    ).scalar()
                    if not seq:
                        continue
                    dconn.execute(
                        text(f"SELECT setval('{seq}', COALESCE((SELECT MAX({col.name}) FROM {table.name}), 1))")
                    )
                    dconn.commit()
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"  sequence reset skipped for {table.name}.{col.name}: {exc!r}",
                        file=sys.stderr,
                    )


def _dry_run(src: Engine, base) -> int:
    """Count rows per table on the source without touching the target."""
    total = 0
    with src.connect() as sconn:
        for table in base.metadata.sorted_tables:
            try:
                n = sconn.execute(select(func.count()).select_from(table)).scalar() or 0
            except Exception as exc:  # noqa: BLE001 -- table may not exist in source
                print(f"  {table.name}: count failed ({exc!r})", file=sys.stderr)
                n = 0
            total += n
    print(f"tables in metadata: {len(base.metadata.sorted_tables)}; total source rows: {total}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument("--source", required=True, help="SQLite URL (4 slashes for abs path)")
    parser.add_argument("--target", required=True, help="PostgreSQL SQLAlchemy URL")
    parser.add_argument("--truncate", action="store_true", help="Delete target rows before copy")
    parser.add_argument("--dry-run", action="store_true", help="Count source rows only; no writes")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per insert batch (default {DEFAULT_BATCH_SIZE})",
    )
    args = parser.parse_args(argv)

    source_url = _coerce_sync_url(args.source)
    target_url = _coerce_sync_url(args.target)

    base = _load_metadata()
    src = _make_source_engine(source_url)
    print(f"connected to source: {source_url}")

    if args.dry_run:
        return _dry_run(src, base)

    dst = create_engine(target_url)
    print(f"connected to target: {target_url}")

    # Build the schema (JSONB columns + FK/GIN/composite indexes) on the target.
    base.metadata.create_all(dst)

    populated = _target_has_rows(dst, base)
    if populated and not args.truncate:
        print(
            f"ERROR: target already has rows (e.g. table '{populated}'). "
            f"Pass --truncate to overwrite, or point at an empty database.",
            file=sys.stderr,
        )
        return 2

    if args.truncate:
        # TRUNCATE ... CASCADE clears every table in one statement, handling FK
        # order that an ordered DELETE cannot: self-referential FKs (e.g. BOQ
        # ``position.parent_id``) and circular cross-module FKs make a per-table
        # DELETE fail even in reverse ``sorted_tables`` order. RESTART IDENTITY
        # also resets sequences so the later ``_reset_sequences`` starts clean.
        print("truncating target tables (TRUNCATE ... RESTART IDENTITY CASCADE)...")
        table_list = ", ".join(f'"{t.name}"' for t in base.metadata.sorted_tables)
        if table_list:
            with dst.begin() as dconn:
                dconn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))

    skipped = _copy_all(src, dst, base, args.batch_size)
    _reset_sequences(dst, base)

    if skipped:
        print(f"migration finished with {skipped} skipped rows -- review the warnings above.")
        return 1
    print("migration finished cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
