"""Hook registry, re-exported from the platform core.

Hooks change data and inject side effects at named points that the core chooses
to expose. There are two kinds. Filters transform a value through a chain of
handlers in priority order, and their errors propagate because a filter sits on
a data path. Actions are fire-and-forget side effects whose errors are logged
and swallowed, so a failing action never breaks the operation it hangs off.

There is one process-global registry, ``hooks``. Register with
``@hooks.filter("name", priority=10)`` or ``@hooks.action("name")``; the core
runs them with ``await hooks.apply_filters(...)`` and ``await hooks.do_actions(...)``.
See ``app.core.hooks`` for the implementation.
"""

from __future__ import annotations

from app.core.hooks import HookRegistry, hooks

__all__ = ["hooks", "HookRegistry"]
