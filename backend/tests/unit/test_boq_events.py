"""Unit tests for BOQ event wiring + vector-indexing error logging (v2.4.0).

Two audit findings are exercised here:

1. The wildcard activity-log handler is registered at import time. (It
   used to be skipped on SQLite to avoid ``MissingGreenlet``; the app is
   PostgreSQL-only now, so the handler is always registered.)

2. Vector-indexing failures used to log at DEBUG, meaning a broken
   embedding service silently stopped indexing in production.  They
   now route through a :class:`_RateLimitedLogger` at WARNING — one
   line per ``(op, error-type)`` per 60 s so an outage produces
   signal without flooding.

Pattern mirrors :mod:`tests.unit.test_cache_logging`.
"""

from __future__ import annotations

import importlib
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import cache as cache_mod
from app.core.events import Event, event_bus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_boq_events(database_url: str):
    """Re-import :mod:`app.modules.boq.events` under a monkeypatched
    ``database_url`` so the module-level ``_register_handlers()`` call
    observes the dialect we want.

    Clears the global event bus first so we have a clean slate — tests
    that follow rely on the handler list being deterministic.
    """
    event_bus.clear()
    # Also reset the process-wide rate limiter so warnings don't get
    # collapsed across tests.  Mirrors test_cache_logging's
    # ``fresh_cache`` fixture.
    import app.modules.boq.events as boq_events_mod  # noqa: I001

    stub_settings = MagicMock()
    stub_settings.database_url = database_url
    with patch("app.config.get_settings", return_value=stub_settings):
        importlib.reload(boq_events_mod)
    boq_events_mod._vector_warn = cache_mod._RateLimitedLogger(window_seconds=60.0)
    return boq_events_mod


# ---------------------------------------------------------------------------
# Activity-log wildcard handler registration
# ---------------------------------------------------------------------------


class TestWildcardHandlerRegistration:
    def test_wildcard_handler_is_registered(self):
        """The activity-log wildcard handler is always registered.

        The app is PostgreSQL-only, so the old SQLite skip path is gone and the
        handler is registered unconditionally at import time, alongside the
        per-event vector handlers.
        """
        mod = _reload_boq_events("postgresql+asyncpg://oe:oe@localhost:5432/openestimate")

        assert mod._log_boq_activity in event_bus._wildcard_handlers
        assert mod._on_position_created in event_bus._handlers.get("boq.position.created", [])
        assert mod._on_position_updated in event_bus._handlers.get("boq.position.updated", [])
        assert mod._on_position_deleted in event_bus._handlers.get("boq.position.deleted", [])


# ---------------------------------------------------------------------------
# Vector-indexing failure path
# ---------------------------------------------------------------------------


class TestVectorIndexFailureLogging:
    @pytest.mark.asyncio
    async def test_single_failure_logs_at_warning(self, caplog):
        mod = _reload_boq_events("postgresql+asyncpg://oe:oe@localhost:5432/openestimate")

        # Make the inner index call blow up — the key thing we want to
        # assert is that the failure surfaces at WARNING, not DEBUG.
        with (
            caplog.at_level(logging.WARNING, logger="app.core.cache"),
            patch.object(
                mod,
                "vector_index_one",
                AsyncMock(side_effect=ConnectionError("embeddings-down")),
            ),
            patch.object(mod, "async_session_factory") as session_factory,
        ):
            fake_row = MagicMock(boq=MagicMock(project_id=uuid.uuid4()))
            fake_session = AsyncMock()
            fake_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_row))
            )
            session_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
            session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            pid = uuid.uuid4()
            evt = Event(name="boq.position.created", data={"position_id": str(pid)})
            await mod._on_position_created(evt)

        records = [
            rec
            for rec in caplog.records
            if "boq.vector.index" in rec.getMessage() and "ConnectionError" in rec.getMessage()
        ]
        assert records, "vector-index failure was not logged"
        assert records[0].levelno == logging.WARNING

    @pytest.mark.asyncio
    async def test_duplicate_failure_within_window_is_suppressed(self, caplog):
        """Second identical failure within 60 s must not produce a log line."""
        mod = _reload_boq_events("postgresql+asyncpg://oe:oe@localhost:5432/openestimate")

        # Install a fresh rate limiter scoped to this test, with 60s
        # window — we'll call the handler twice and expect exactly one
        # emission.
        mod._vector_warn = cache_mod._RateLimitedLogger(window_seconds=60.0)

        with (
            caplog.at_level(logging.WARNING, logger="app.core.cache"),
            patch.object(
                mod,
                "vector_index_one",
                AsyncMock(side_effect=ConnectionError("embeddings-down")),
            ),
            patch.object(mod, "async_session_factory") as session_factory,
        ):
            fake_row = MagicMock(boq=MagicMock(project_id=uuid.uuid4()))
            fake_session = AsyncMock()
            fake_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_row))
            )
            session_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
            session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            for _ in range(5):
                evt = Event(
                    name="boq.position.created",
                    data={"position_id": str(uuid.uuid4())},
                )
                await mod._on_position_created(evt)

        records = [rec for rec in caplog.records if "boq.vector.index" in rec.getMessage()]
        assert len(records) == 1, f"expected exactly one collapsed WARNING, got {len(records)}"

    @pytest.mark.asyncio
    async def test_delete_failure_logs_distinct_operation(self, caplog):
        """Index and delete are separate buckets in the limiter."""
        mod = _reload_boq_events("postgresql+asyncpg://oe:oe@localhost:5432/openestimate")
        mod._vector_warn = cache_mod._RateLimitedLogger(window_seconds=60.0)

        with (
            caplog.at_level(logging.WARNING, logger="app.core.cache"),
            patch.object(
                mod,
                "vector_delete_one",
                AsyncMock(side_effect=RuntimeError("delete-boom")),
            ),
        ):
            evt = Event(
                name="boq.position.deleted",
                data={"position_id": str(uuid.uuid4())},
            )
            await mod._on_position_deleted(evt)

        records = [rec for rec in caplog.records if "boq.vector.delete" in rec.getMessage()]
        assert records
        assert records[0].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# Cleanup — restore module to its natural (settings-driven) state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def _reset_after_module():
    """After these tests run, reload boq.events with the real settings
    so the global ``event_bus`` ends up in the same shape that app
    startup would produce.  Mirrors test_cache_logging's discipline of
    not leaving the module bus in a test-specific state.
    """
    yield
    event_bus.clear()
    import app.modules.boq.events as boq_events_mod  # noqa: I001

    importlib.reload(boq_events_mod)
