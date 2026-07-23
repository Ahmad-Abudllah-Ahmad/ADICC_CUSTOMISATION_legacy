"""Shared test fixtures.

Test isolation
~~~~~~~~~~~~~~
Per ``feedback_test_isolation.md``: backend tests must NEVER touch the
production database. Several integration suites
(``test_api_smoke``, ``test_boq_regression``, ``test_boq_import_safety``,
``test_boq_cycle_detection``, ``test_boq_cost_item_link``) construct the
FastAPI app via ``create_app()`` which imports ``app.database`` and
binds ``async_session_factory`` to whatever ``DATABASE_URL`` is set at
that moment — so the env vars have to point at a throwaway PostgreSQL
cluster *before* any ``from app...`` import runs.

Doing it here in ``tests/conftest.py`` (which pytest loads before any
test module) guarantees the override beats every test-module import
order, regardless of which suite is collected first. Tests that already
self-redirect (``test_tenant_isolation``, ``test_register_bootstrap``,
etc.) are still fine — they overwrite this with their own connection.
"""

import os

# ── Windows asyncpg event-loop policy ──────────────────────────────────────
# On Windows the default ProactorEventLoop leaves asyncpg socket transports to
# be finalized by the GC after the per-test loop has closed, surfacing as a
# noisy "RuntimeError: Event loop is closed" at teardown. The SelectorEventLoop
# policy (the default on Linux/macOS) closes them deterministically. Must run
# before any event loop is created.
import sys as _sys  # noqa: E402
import tempfile
from pathlib import Path

if _sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

# ── Per-session PostgreSQL isolation (must run before app imports) ──────────
# The app is PostgreSQL-only at runtime, so the test suite runs on PostgreSQL
# too. Two ways to provide it:
#   * CI sets ``DATABASE_URL`` (a postgres service container) — honour it as-is.
#   * Otherwise boot a throwaway embedded PostgreSQL 16 cluster (no Docker) into
#     a temp data dir for the session. ``embedded_pg.boot`` points
#     ``DATABASE_URL`` / ``DATABASE_SYNC_URL`` at the embedded cluster and is
#     registered for shutdown via ``atexit`` so the postmaster is stopped when
#     the run ends (the temp dir is reclaimed by the OS regardless).
# This must happen before any ``from app...`` import that pulls in
# ``app.database`` (which builds the engine from ``settings.database_url`` at
# import time).
if not os.environ.get("DATABASE_URL", "").strip():
    import atexit

    from app.core import embedded_pg

    _PG_DATA_DIR = Path(tempfile.mkdtemp(prefix="oe-tests-pg-"))
    if not embedded_pg.boot(_PG_DATA_DIR):
        raise RuntimeError(
            "could not boot embedded PostgreSQL for the test session; set "
            "DATABASE_URL to point the suite at an external PostgreSQL instead"
        )
    atexit.register(embedded_pg.shutdown)

# ── Rate-limiter relaxation for tests ──────────────────────────────────────
# The integration suites repeatedly hit ``/auth/register`` and ``/auth/login``
# from the same in-process ``test`` client. The default 10/min login limit
# (and 100/min API limit) is fine for production but makes whole-suite
# runs flake with 429s long before the relevant assertion fires. Tests
# don't measure rate-limiter behaviour itself (those tests stand up their
# own ``RateLimiter(...)`` instance), so we lift the bucket here.
os.environ.setdefault("LOGIN_RATE_LIMIT", "10000")
os.environ.setdefault("API_RATE_LIMIT", "100000")
os.environ.setdefault("AI_RATE_LIMIT", "10000")

# ── Open registration for the suite ────────────────────────────────────────
# The default registration mode is "admin-approve" (every registrant after the
# first bootstrap admin is created inactive and cannot log in). The integration
# suites register a fresh user per module and immediately log in, so under the
# default they get a 401 and the auth fixture errors out. Open mode keeps every
# registrant active. The two mode-specific suites (test_register_modes,
# test_register_bootstrap) set the mode themselves and are unaffected.
os.environ.setdefault("REGISTRATION_MODE", "open")

# ── Skip demo account seeding for tests ───────────────────────────────────
# The startup lifespan creates demo@openconstructionerp.com (and two sibling
# accounts) every time create_app() boots. Although has_admin() is designed
# to exclude those demo emails from the bootstrap check, the seeding still
# costs time and writes rows that can interact with per-module auth fixtures.
# test_demo_login_endpoint.py sets SEED_DEMO=true inside its own fixture and
# is unaffected. All other suites work without the demo accounts.
os.environ.setdefault("SEED_DEMO", "false")

# ── Fast app startup for tests ─────────────────────────────────────────────
# Each integration module stands up its own FastAPI app via create_app() and
# runs the full lifespan. In production that lifespan connects to the vector
# backend, loads the embedding model (~35s) and installs the flagship showcase
# project (6640 elements + ~16MB of geometry). None of that is needed by the
# test suite, and paid per module it is the dominant cost of the whole run.
# This flag skips the vector init/warm-up and the flagship seed; vector
# endpoints still work because the embedder loads lazily on first use.
os.environ.setdefault("OE_TEST_FAST_STARTUP", "1")

# ── NullPool for the shared app engine under tests ─────────────────────────
# pytest-asyncio runs each test in its own event loop. asyncpg connections are
# loop-bound, so a connection pooled on one test's loop and reused on the next
# raises "Task ... attached to a different loop". The production engine uses a
# sized QueuePool; here we tell the engine factory to use NullPool so every
# checkout opens a fresh connection on the current loop. Must be set before the
# first ``import app...`` below builds the engine. The fast per-test isolation
# helpers in ``tests/_pg.py`` already use NullPool for the same reason.
os.environ.setdefault("OE_TEST_NULLPOOL", "1")

import pytest  # noqa: E402

import app.core.audit  # noqa: E402,F401

# Audit-log model needs to be registered with Base.metadata before
# create_all() so the FSM audit-log writes have somewhere to land.
import app.core.audit_log  # noqa: E402,F401
import app.modules.bim_hub.models  # noqa: E402,F401
import app.modules.boq.models  # noqa: E402,F401
import app.modules.eac.models  # noqa: E402,F401

# ── Eagerly register all module ORM tables ─────────────────────────────────
# Without this, test-order pollution can leave Base.metadata holding a
# fragmentary view: e.g. a test that imports `schedule.models` but not
# `projects.models` registers `oe_schedule_schedule` with a dangling FK
# to the unloaded `oe_projects_project`. The next test that calls
# `Base.metadata.create_all()` then fails with NoReferencedTableError.
# Importing every module's models here once before any test runs
# guarantees a coherent metadata snapshot regardless of suite order.
import app.modules.projects.models  # noqa: E402,F401
import app.modules.schedule.models  # noqa: E402,F401
import app.modules.takeoff.models  # noqa: E402,F401
import app.modules.users.models  # noqa: E402,F401

# ── Synchronous event publishing in tests ──────────────────────────────────
# Production wraps ``event_bus.publish`` in ``asyncio.create_task`` via
# :meth:`EventBus.publish_detached` so the database connection isn't
# held by the request session while subscribers open theirs. Tests, however,
# typically do ``await service.X()`` then immediately assert on a captured
# events fixture — the scheduled task hasn't yielded to the loop yet. To
# preserve pre-v2.6.47 sync semantics for tests we shim ``publish_detached``
# to use an immediate ``ensure_future`` + a ``run`` of pending callbacks
# before returning, so when control comes back to the test's next line the
# event has already fanned out to subscribers.
from app.core.events import event_bus as _event_bus  # noqa: E402

# Handlers that perform real async I/O - they open their own DB session
# (webhook dispatch), write an activity-log row (BOQ) or persist a timeline
# ActivityLog row (timeline bridge). These are the three ``"*"`` wildcard
# subscribers in the codebase, so each is present for *every* event once the
# full app has started (i.e. in integration tests). Manually stepping a
# coroutine that does real asyncpg I/O via ``coro.send(None)`` corrupts the
# connection ("await wasn't used with future") and poisons the test's session,
# so whenever one of these is registered we let the event loop drive the publish
# instead. NOTE: keep this in sync with every ``event_bus.subscribe("*", ...)``
# in app/ - a wildcard handler missing here is half-stepped and silently
# poisons whichever unit test happens to publish first (manifests as a
# ``GeneratorExit`` deep in asyncpg on the next DB op).
_ASYNC_IO_EVENT_HANDLERS = {"_dispatch_to_webhooks", "_log_boq_activity", "_record_event"}

# Keep strong references to scheduled publish tasks so the loop can't garbage-
# collect them mid-flight (which would raise "Task was destroyed but it is
# pending"). The done-callback drops each task once it finishes.
_pending_event_tasks: set = set()


def _schedule_publish(coro):
    import asyncio as __asyncio

    task = __asyncio.ensure_future(coro)
    _pending_event_tasks.add(task)
    task.add_done_callback(_pending_event_tasks.discard)
    return task


def _sync_publish_detached(name, data=None, source_module=None):
    """Test-time replacement for :meth:`EventBus.publish_detached`.

    Two regimes, distinguished by whether a real-I/O wildcard handler is wired:

    * **Unit tests** subscribe a pure-Python recorder to the bus, call a
      service that fires ``publish_detached`` and then immediately assert on the
      captured events. No I/O handler is registered, so we drive the publish
      coroutine to completion in-line — pure subscribers finish on the first
      ``send(None)`` — preserving that synchronous contract exactly.

    * **Integration tests** run the full app, which registers wildcard handlers
      that open their own DB session (webhook dispatch, BOQ activity log). Those
      do real asyncpg I/O; stepping them by hand corrupts the connection. When
      such a handler is registered for the event we instead schedule the publish
      as a detached task, exactly as production does, so the loop drives the I/O
      correctly.

    Either way an awaitable is returned for callers/tests that use it.
    """
    import asyncio as __asyncio

    handlers = list(_event_bus._handlers.get(name, ())) + list(_event_bus._wildcard_handlers)
    needs_loop = any(getattr(h, "__name__", "") in _ASYNC_IO_EVENT_HANDLERS for h in handlers)
    if needs_loop:
        try:
            return _schedule_publish(_event_bus.publish(name, data, source_module=source_module))
        except RuntimeError:
            pass  # no running loop (rare) — fall through to the synchronous drive

    coro = _event_bus.publish(name, data, source_module=source_module)
    fut: __asyncio.Future = __asyncio.Future()
    try:
        # Pure subscribers (no real I/O) finish in a single send.
        coro.send(None)
    except StopIteration as stop:
        fut.set_result(stop.value)
        return fut
    except BaseException as exc:
        fut.set_exception(exc)
        return fut
    # A subscriber yielded for real I/O but no recognised wildcard handler was
    # registered (e.g. a module-specific handler imported without the full app).
    # NEVER hand a half-stepped coroutine to the loop — that is exactly what
    # corrupts asyncpg. Discard it and re-publish cleanly as a detached task.
    coro.close()
    try:
        return _schedule_publish(_event_bus.publish(name, data, source_module=source_module))
    except RuntimeError:
        fut.set_result(None)
        return fut


_event_bus.publish_detached = _sync_publish_detached  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _keep_validation_rules_registered():
    """Guard the process-global validation registry against cross-test pollution.

    A few suites swap the module-level ``validation_engine`` or replace/empty its
    registry to exercise edge cases; without a restore, a later test that runs a
    real rule set - inline BOQ-import validation, the pipeline graph gate - finds
    an empty registry and reports every requested set as ``unsupported``. After
    each test put the engine and its registry back, and re-register the built-ins
    if they went missing (``register_builtin_rules`` is idempotent).
    """
    import app.core.validation.engine as _eng

    engine = _eng.validation_engine
    registry = engine.registry
    try:
        yield
    finally:
        _eng.validation_engine = engine
        engine.registry = registry
        if "boq_quality" not in registry.list_rule_sets():
            from app.core.validation.rules import register_builtin_rules

            register_builtin_rules()


@pytest.fixture
def sample_boq_data():
    """Sample BOQ data for validation tests."""
    return {
        "positions": [
            {
                "id": "pos-001",
                "ordinal": "01.01.0010",
                "description": "Stahlbeton C30/37 für Fundamente",
                "unit": "m3",
                "quantity": 44.30,
                "unit_rate": 185.00,
                "classification": {"din276": "330", "masterformat": "03 30 00"},
            },
            {
                "id": "pos-002",
                "ordinal": "01.01.0020",
                "description": "Schalung für Fundamente",
                "unit": "m2",
                "quantity": 120.0,
                "unit_rate": 42.50,
                "classification": {"din276": "330"},
            },
            {
                "id": "pos-003",
                "ordinal": "01.02.0010",
                "description": "Betonstahl BSt 500 S",
                "unit": "kg",
                "quantity": 3200.0,
                "unit_rate": 1.85,
                "classification": {"din276": "330"},
            },
        ]
    }


@pytest.fixture
def sample_boq_data_with_issues():
    """BOQ data with validation issues."""
    return {
        "positions": [
            {
                "id": "pos-001",
                "ordinal": "01.01.0010",
                "description": "Good position",
                "unit": "m3",
                "quantity": 10.0,
                "unit_rate": 100.0,
                "classification": {"din276": "330"},
            },
            {
                "id": "pos-002",
                "ordinal": "01.01.0010",  # DUPLICATE ordinal
                "description": "",  # MISSING description
                "unit": "m2",
                "quantity": 0,  # ZERO quantity
                "unit_rate": 0,  # ZERO rate
                "classification": {},  # MISSING classification
            },
            {
                "id": "pos-003",
                "ordinal": "01.02.0010",
                "description": "Overpriced item",
                "unit": "pcs",
                "quantity": 5.0,
                "unit_rate": 999999.0,  # ANOMALY
                "classification": {"din276": "999"},  # INVALID code
            },
        ]
    }


@pytest.fixture
def sample_cad_elements():
    """Sample CAD canonical format elements."""
    return [
        {
            "id": "elem_001",
            "category": "wall",
            "classification": {"din276": "330"},
            "geometry": {
                "type": "extrusion",
                "length_m": 12.43,
                "height_m": 3.0,
                "thickness_m": 0.24,
                "area_m2": 37.29,
                "volume_m3": 8.95,
            },
            "properties": {"material": "concrete_c30_37"},
            "quantities": {"area": 37.29, "volume": 8.95},
        },
        {
            "id": "elem_002",
            "category": "floor",
            "classification": {"din276": "350"},
            "geometry": {
                "type": "slab",
                "area_m2": 85.0,
                "thickness_m": 0.20,
                "volume_m3": 17.0,
            },
            "properties": {"material": "concrete_c25_30"},
            "quantities": {"area": 85.0, "volume": 17.0},
        },
    ]
