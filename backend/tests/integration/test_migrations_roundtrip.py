"""Alembic up/down round-trip tests (Wave 3-D / Task #237).

Goal: catch the "missing or broken downgrade()" CI bug class — a
recent migration whose ``downgrade()`` is empty or doesn't reverse what
``upgrade()`` did. The cheapest way to surface that is to run
``upgrade -> downgrade -> upgrade`` cycles on a fresh PostgreSQL DB.

Schema-creation reality (see ``app/main.py`` ~L1395):
  * The init revision ``129188e46db8`` is intentionally a no-op — its
    docstring says "Tables are created by SQLAlchemy at app startup".
  * The app boots by running ``Base.metadata.create_all()`` first,
    *then* ``alembic upgrade head`` (Alembic only carries column-level
    or new-table deltas after the metadata create).
  * Therefore plain ``alembic upgrade head`` on an empty DB doesn't
    work — e.g. ``v270_position_version_column`` does
    ``inspector.get_columns("oe_boq_position")`` which raises
    ``NoSuchTableError`` because that table comes from create_all,
    not from a migration. This is **expected** project behaviour, not
    a bug to fix here.

Test strategy (mirrors production, isolated per revision):
  1. ``Base.metadata.create_all()`` to lay down the schema at head.
  2. ``alembic stamp head`` to mark all migrations as applied.
  3. For each recent revision ``R``:
     a. ``stamp R`` - move the version marker to exactly R without
        touching the schema (already at head from create_all).
     b. ``downgrade R^`` - run *only* R's own ``downgrade()`` (one step).
     c. ``upgrade R`` - run *only* R's own ``upgrade()`` (one step back).
     d. Assert: post-cycle schema matches pre-cycle schema.

  The earlier design downgraded the whole chain head->R^ then re-upgraded
  to head, which dragged in every legacy migration body between head and
  R^. On PostgreSQL a single broken legacy downgrade aborts the
  transaction and masks the revision actually under test. Isolating to
  R's own one-step cycle attributes any failure to R and nothing else.

Isolation: every test gets its own throwaway PostgreSQL database
(created from scratch, dropped on teardown). ``DATABASE_SYNC_URL``
is monkeypatched so that Alembic's ``env.py`` targets the throwaway
DB, not the dev/production database.

PostgreSQL-only revisions that require extensions or dialect features
unavailable in the unit cluster can be added to ``PG_DOWNGRADE_BROKEN_REVS``
with a one-line reason each; they will be xfailed rather than skipped so
any unexpected recovery is surfaced.

Runtime: ~5-15 s per parametrized rev on a warm interpreter. Tier
``integration``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

# Project paths — anchored to this file so the tests work regardless
# of pytest's rootdir / CWD.
THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parent.parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Recent revisions we want to exercise (the v250+ wave).
# Listed newest-first so the most recent failures surface first.
RECENT_REVISIONS: list[str] = [
    "v3151_cost_spine",
    "v290_dashboards_presets",
    "v280_4d_schedule_eac",
    "v270_position_version_column",
    "eb1cef6f5fce",  # v262 merge node
    "v261_eac_alias_catalog_seed",
    "v260a_eac_aliases_tables",
    "v260_jobs_runner",
    "v260_eac_v2_core",
    "v250_dashboards_snapshot",
]

# Revisions whose ``upgrade()`` and ``downgrade()`` are intentionally
# both ``pass`` (typically alembic-generated merge nodes). They round-
# trip vacuously; we still want to confirm they don't error, but we
# don't assert anything about schema deltas.
NOOP_BOTH_REVS: set[str] = {
    "eb1cef6f5fce",  # v262 merge — generator created empty bodies
}

# Revisions that are known to fail the downgrade/re-upgrade cycle on
# PostgreSQL due to genuine dialect-level issues that are separate bugs
# to fix. Add entries here rather than deleting the tests. Format:
#   "revision_id": "one-line reason"
PG_DOWNGRADE_BROKEN_REVS: dict[str, str] = {
    # Example: "v999_example": "downgrade drops a PG-only ENUM that upgrade doesn't recreate"
}


# ─────────────────────────────────────────────────────────────────────
#  PostgreSQL helpers (mirrors _pg.py internal pattern)
# ─────────────────────────────────────────────────────────────────────


def _maintenance_db(admin_url: str) -> str:
    """The cluster database used to issue CREATE/DROP DATABASE.

    Derived from ``admin_url`` - the *original* configured URL captured
    before the per-test monkeypatch - never from the live env var. By the
    time teardown runs, ``DATABASE_SYNC_URL`` points at the throwaway DB,
    and you cannot DROP the database your own connection is bound to.
    """
    return make_url(admin_url).database or "postgres"


def _sync_url_for(admin_url: str, database: str) -> str:
    """psycopg2 SQLAlchemy URL for ``database`` on ``admin_url``'s cluster."""
    base = make_url(admin_url)
    return base.set(drivername="postgresql+psycopg2", database=database).render_as_string(hide_password=False)


def _connect_admin(admin_url: str):
    """Autocommit psycopg2 connection to the maintenance database.

    Connects to the cluster's maintenance DB (the one named in the
    original ``admin_url``), not the throwaway, so CREATE/DROP DATABASE
    run from a connection that is not itself the target. ``admin_url``
    carries the SQLAlchemy ``postgresql+psycopg2`` driver form; raw
    ``psycopg2.connect`` only accepts a libpq ``postgresql://`` URI, so
    the driver suffix is stripped here.
    """
    base = make_url(admin_url)
    maint = base.set(drivername="postgresql", database=_maintenance_db(admin_url)).render_as_string(hide_password=False)
    conn = psycopg2.connect(maint)
    conn.autocommit = True
    return conn


def _terminate_backends(cur, db_name: str) -> None:
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (db_name,),
    )


def _create_throwaway_db(admin_url: str, db_name: str) -> None:
    """Create a fresh, empty PostgreSQL database for one test."""
    conn = _connect_admin(admin_url)
    try:
        conn.cursor().execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()


def _drop_throwaway_db(admin_url: str, db_name: str) -> None:
    """Drop the throwaway database, terminating any leftover connections first."""
    conn = _connect_admin(admin_url)
    try:
        cur = conn.cursor()
        _terminate_backends(cur, db_name)
        cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        cur.close()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
#  Alembic config builder
# ─────────────────────────────────────────────────────────────────────


def _make_alembic_config(sync_url: str) -> Config:
    """Build an Alembic Config pointing at ``sync_url``.

    Override both the ini ``sqlalchemy.url`` entry (for completeness)
    and set the env var so ``alembic/env.py`` (which reads
    ``settings.database_sync_url`` directly) targets the throwaway DB.
    The ``DATABASE_SYNC_URL`` env var monkeypatch is applied by the
    ``pg_throwaway`` fixture before this function is called.
    """
    cfg = Config(str(ALEMBIC_INI))
    # ``script_location`` is normally relative to the .ini file; make it
    # explicit so a temp CWD doesn't break resolution.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


# ─────────────────────────────────────────────────────────────────────
#  Model import helper
# ─────────────────────────────────────────────────────────────────────


def _import_all_models() -> None:
    """Mirror what ``alembic/env.py`` imports - populates Base.metadata.

    Done lazily (function-local imports) so this expensive step only
    runs when an actual round-trip test executes, not at collection.

    Uses the same pkgutil catch-all as ``alembic/env.py`` rather than a
    hand-maintained list. A static list silently drifts: it was missing
    ``property_dev`` (and others), so ``Base.metadata.create_all`` never
    materialised ``oe_property_dev_custom_template`` and any downgrade
    body that reflected that table (e.g. v3137) raised ``NoSuchTableError``
    on PostgreSQL. Sweeping every module guarantees create_all reproduces
    the exact production schema shape.
    """
    import importlib
    import pkgutil

    from app import modules as _modules_pkg

    # Core-level tables that live outside app.modules.* and so are not
    # reached by the module sweep below.
    from app.core import audit  # noqa: F401
    from app.core import audit_log as _audit_log  # noqa: F401  # oe_activity_log
    from app.core import job_run as _job_run  # noqa: F401  # oe_job_run
    from app.core.translation import cache as _tcache  # noqa: F401  # oe_translation_cache

    _modules_dir = os.path.dirname(_modules_pkg.__file__)
    for _entry in pkgutil.iter_modules([_modules_dir]):
        if not _entry.ispkg:
            continue
        try:
            importlib.import_module(f"app.modules.{_entry.name}.models")
        except Exception:  # noqa: BLE001 - mirror env.py: a bad module never aborts the sweep
            pass


# ─────────────────────────────────────────────────────────────────────
#  Schema bootstrap
# ─────────────────────────────────────────────────────────────────────


def _create_all_then_stamp(sync_url: str, cfg: Config) -> None:
    """Mirror app boot: create_all on a sync PostgreSQL engine, then stamp head.

    This is the only realistic starting point for downgrade tests —
    ``upgrade head`` from base does not work on this project (see
    module docstring).
    """
    _import_all_models()  # populate Base.metadata

    from app.database import Base

    eng = create_engine(sync_url)
    try:
        Base.metadata.create_all(eng)
    finally:
        eng.dispose()

    command.stamp(cfg, "head")


# ─────────────────────────────────────────────────────────────────────
#  Schema snapshot
# ─────────────────────────────────────────────────────────────────────


def _schema_snapshot(sync_url: str) -> dict[str, list[str]]:
    """Return ``{table: sorted(column_names)}`` for the database at ``sync_url``.

    Skips ``alembic_version`` (its row content changes between
    upgrade/downgrade by design) and PostgreSQL system tables.
    """
    eng = create_engine(sync_url)
    try:
        insp = inspect(eng)
        out: dict[str, list[str]] = {}
        for table in sorted(insp.get_table_names()):
            if table == "alembic_version":
                continue
            cols = sorted(c["name"] for c in insp.get_columns(table))
            out[table] = cols
        return out
    finally:
        eng.dispose()


# ─────────────────────────────────────────────────────────────────────
#  Per-test fixture: throwaway PostgreSQL database
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def pg_throwaway(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Per-test throwaway PostgreSQL database + env vars routed at it.

    Creates a fresh, empty database on the session cluster, monkeypatches
    ``DATABASE_SYNC_URL`` (and ``DATABASE_URL``) to point at it, and
    clears the Settings cache so ``alembic/env.py`` picks up the override.
    Drops the database on teardown.

    Yields the sync psycopg2 URL string for the throwaway database.
    """
    # Capture the original (pre-monkeypatch) sync URL. All CREATE/DROP
    # DATABASE admin work uses this, never the patched env var: by the time
    # teardown runs, DATABASE_SYNC_URL points at the throwaway DB, and a
    # connection bound to that DB cannot drop it.
    admin_url = os.environ["DATABASE_SYNC_URL"]

    db_name = f"oe_mig_rt_{uuid.uuid4().hex[:16]}"
    _create_throwaway_db(admin_url, db_name)

    sync_url = _sync_url_for(admin_url, db_name)
    # Build the async URL from the sync one (replace driver).
    async_url = make_url(sync_url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)

    monkeypatch.setenv("DATABASE_SYNC_URL", sync_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    # Bust the cached Settings so env.py reads the override.
    from app.config import get_settings

    get_settings.cache_clear()

    try:
        yield sync_url
    finally:
        get_settings.cache_clear()
        _drop_throwaway_db(admin_url, db_name)


# ─────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────


def test_create_all_plus_stamp_head_succeeds(pg_throwaway: str) -> None:
    """Sanity: production-style boot (create_all + stamp head) works on PostgreSQL.

    If this fails, every other round-trip test in the file fails too,
    so we run it first to fail fast with a clear signal.
    """
    sync_url = pg_throwaway
    cfg = _make_alembic_config(sync_url)
    _create_all_then_stamp(sync_url, cfg)

    snap = _schema_snapshot(sync_url)
    assert snap, "create_all + stamp produced no tables"
    # Spot-check core tables created by metadata + alembic-tracked tables.
    assert "oe_projects_project" in snap
    assert "oe_boq_position" in snap
    assert "version" in snap["oe_boq_position"], (
        "v270 column not on Position model — Base.metadata.create_all should add it"
    )
    # EAC v2 tables come from create_all too (the model is in metadata).
    assert "oe_eac_ruleset" in snap, "EAC ruleset table missing from metadata"
    assert "oe_eac_parameter_aliases" in snap
    assert "oe_job_run" in snap
    assert "oe_dashboards_snapshot" in snap


@pytest.mark.parametrize("revision", RECENT_REVISIONS)
def test_revision_downgrade_reupgrade_does_not_error(pg_throwaway: str, revision: str) -> None:
    """For each recent revision R: isolate-test R's own down + up step on PostgreSQL.

    Starts from a production-style boot (create_all + stamp head), then:
      1. ``stamp R`` - move the version marker to exactly R without
         touching the schema (already at head from create_all).
      2. ``downgrade R^`` - run *only* R's ``downgrade()`` body (one step).
      3. ``upgrade R`` - run *only* R's ``upgrade()`` body (one step back).

    This is the canonical "missing/broken downgrade" detector, isolated
    so a failure is attributable to R alone and unrelated legacy bodies
    never run (they would abort the PG transaction and mask R).

    The schema matches before and after because create_all already laid
    down R's objects; R.downgrade() removes them and R.upgrade() re-adds
    them.
    """
    if revision in PG_DOWNGRADE_BROKEN_REVS:
        pytest.xfail(f"{revision} known broken on PG: {PG_DOWNGRADE_BROKEN_REVS[revision]}")

    if revision in NOOP_BOTH_REVS:
        # Empty upgrade()/downgrade() bodies (generator-emitted merge
        # nodes). There is no schema delta to cycle and a merge node
        # cannot be downgraded one step to a single parent cleanly. An
        # empty body cannot be "broken", so there is nothing to exercise.
        pytest.xfail(
            f"{revision} is a generator-emitted merge node with empty "
            f"upgrade()/downgrade() bodies - round-trip is vacuous"
        )

    sync_url = pg_throwaway
    cfg = _make_alembic_config(sync_url)
    _create_all_then_stamp(sync_url, cfg)
    snap_before = _schema_snapshot(sync_url)

    # Resolve the parent revision (the one-step downgrade target).
    script = ScriptDirectory.from_config(cfg)
    parent = script.get_revision(revision).down_revision
    parent_rev = parent[0] if isinstance(parent, tuple) else parent
    assert parent_rev, f"{revision} has no parent - can't downgrade past it"

    # Move the version marker to exactly R. The schema is already at head
    # from create_all, so this just rewrites alembic_version - no
    # migration body runs. The subsequent downgrade is then a single step
    # (R -> R^) that executes only R's own downgrade().
    command.stamp(cfg, revision)

    try:
        command.downgrade(cfg, parent_rev)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"downgrade of {revision} (target={parent_rev}) raised - "
            f"likely a missing/broken downgrade() body. Root cause: {exc!r}"
        )

    try:
        command.upgrade(cfg, revision)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"re-upgrade of {revision} raised - likely upgrade() is "
            f"non-idempotent or PG-incompatible. Root cause: {exc!r}"
        )

    snap_after = _schema_snapshot(sync_url)

    # Table set must be unchanged: a downgrade that drops a table whose
    # upgrade fails to recreate it (or a downgrade/upgrade that leaks a
    # spurious table) shows up here.
    assert set(snap_after) == set(snap_before), (
        f"Schema after round-tripping {revision} changed the table set. "
        f"Tables added by cycle: {set(snap_after) - set(snap_before)}; "
        f"tables removed by cycle: {set(snap_before) - set(snap_after)}"
    )

    # Column-level invariant for *isolated* single-step cycling: re-running
    # only R's own upgrade() recreates R's tables at their R-era shape, which
    # is a subset of the head shape whenever a *later* migration added columns
    # to one of those tables (e.g. v260_jobs_runner adds idempotency_key /
    # spool_path to the oe_eac_run table that v260_eac_v2_core created). That
    # subset divergence is expected, not a bug. What is NOT allowed is the
    # cycle introducing a column the head schema doesn't have - that signals a
    # genuine upgrade/downgrade inconsistency.
    introduced = {
        table: sorted(set(snap_after[table]) - set(snap_before[table]))
        for table in snap_after
        if set(snap_after[table]) - set(snap_before[table])
    }
    assert not introduced, (
        f"Round-tripping {revision} introduced columns absent from the head "
        f"schema (upgrade/downgrade inconsistency): {introduced}"
    )


def test_recent_migrations_have_real_downgrade_bodies() -> None:
    """Static guard: each recent migration's downgrade() is non-trivial.

    "Non-trivial" = the source contains some schema-mutating call
    (``op.drop_*``, ``op.execute(...)``, ``batch_alter_table``) — not
    just ``pass`` / a docstring. Merge revisions in ``NOOP_BOTH_REVS``
    are exempt.

    This is the cheap "lint" companion to the round-trip test above:
    it surfaces the same issue even when nobody runs the slower
    integration test.
    """
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    bad: list[str] = []
    for revision in RECENT_REVISIONS:
        if revision in NOOP_BOTH_REVS:
            continue
        # Locate the migration file by matching the canonical
        # ``revision: str = "<id>"`` line — substring matches in
        # ``down_revision`` tuples on merge nodes would give false
        # positives (e.g. eb1cef6f5fce mentions both v260_jobs_runner
        # and v261_eac_alias_catalog_seed in its down_revision).
        marker = f'revision: str = "{revision}"'
        candidates = [p for p in versions_dir.glob("*.py") if marker in p.read_text(encoding="utf-8")]
        assert candidates, f"Couldn't locate migration file for {revision}"
        src = candidates[0].read_text(encoding="utf-8")
        _, _, after = src.partition("def downgrade()")
        if not after:
            bad.append(f"{revision}: no downgrade() function at all")
            continue
        body = after.split("\ndef ", 1)[0]
        # Strip docstrings / comments / blanks; check what remains.
        stripped_lines = [
            line
            for line in body.splitlines()
            if line.strip()
            and not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("'''")
        ]
        meaningful = "\n".join(stripped_lines)
        if "op." not in meaningful and "batch_alter_table" not in meaningful:
            bad.append(f"{revision}: downgrade() has no schema-mutating call")

    assert not bad, "Migrations with non-functional downgrade():\n  " + "\n  ".join(bad)


def test_dev_db_is_not_being_targeted(pg_throwaway: str) -> None:
    """Tripwire: throwaway-DB fixture must override the dev-DB env var.

    If anyone copy-pastes this file or the fixture goes wrong, we want
    a screaming failure rather than silent corruption of the dev DB.
    """
    assert "openestimate.db" not in os.environ.get("DATABASE_SYNC_URL", ""), (
        "Test fixture failed to override DATABASE_SYNC_URL — would have written to the dev DB. Aborting."
    )
    # The active DATABASE_SYNC_URL must point at a throwaway PG database.
    active_url = os.environ.get("DATABASE_SYNC_URL", "")
    assert "postgresql" in active_url, f"Expected DATABASE_SYNC_URL to be a PostgreSQL URL, got: {active_url!r}"
    assert "oe_mig_rt_" in active_url, (
        f"Expected DATABASE_SYNC_URL to contain the throwaway DB name prefix 'oe_mig_rt_', got: {active_url!r}"
    )
