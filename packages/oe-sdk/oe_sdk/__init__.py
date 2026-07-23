"""OpenConstructionERP module SDK.

One clean import surface for building a module on the platform. Everything here
is a faithful re-export of the stable core primitives, plus a few thin helpers
that shave off boilerplate. There is no reimplementation: a value you import
from ``oe_sdk`` is the same object the running platform uses, so registering a
rule, an event handler or a permission through the SDK registers it on the very
registry the platform dispatches through.

What you get in one place:

- Manifest: ``ModuleManifest`` and the ``module_manifest`` builder.
- Events: ``event_bus``, ``Event``, ``EventResult`` and the ``on`` / ``publish``
  / ``publish_detached`` / ``subscribe`` conveniences.
- Hooks: the ``hooks`` registry (filters and actions).
- Validation: ``ValidationRule``, ``RuleResult``, ``ValidationContext``,
  ``Severity``, ``RuleCategory``, ``ValidationStatus``, the ``rule_registry``
  and ``validation_engine`` singletons, and the ``register_rule`` helper.
- Permissions: ``Role``, the ``permission_registry`` singleton, and the
  ``register_permissions`` helper.
- Web and data layer: ``Base`` and ``GUID`` for models, and the router
  dependencies ``SessionDep``, ``CurrentUserId``, ``RequirePermission``,
  ``verify_project_access`` and friends.
- Schemas: the optional ``ORMModel`` base for response schemas.

Import cost: the manifest, event, hook, validation and permission primitives are
imported eagerly and touch no database. The web and data-layer names live in
``oe_sdk.web``, which imports ``app.database`` and ``app.dependencies``; those
build the SQLAlchemy engine at import time and need a configured PostgreSQL
``DATABASE_URL``. To keep ``import oe_sdk`` cheap and free of side effects, those
names are resolved lazily the first time you access them (for example
``oe_sdk.SessionDep``). Inside a running deployment the database is always
configured by then.

See docs/platform/how-it-works-for-builders.md and
docs/platform/first-module-in-10-minutes.md for the full walkthrough.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from oe_sdk.events import (
    Event,
    EventBus,
    EventResult,
    event_bus,
    on,
    publish,
    publish_detached,
    subscribe,
)
from oe_sdk.hooks import HookRegistry, hooks
from oe_sdk.manifest import ModuleManifest, module_manifest
from oe_sdk.permissions import (
    PermissionRegistry,
    Role,
    permission_registry,
    register_permissions,
)
from oe_sdk.scaffold import scaffold
from oe_sdk.schemas import ORMModel
from oe_sdk.validation import (
    RuleCategory,
    RuleRegistry,
    RuleResult,
    Severity,
    ValidationContext,
    ValidationEngine,
    ValidationReport,
    ValidationRule,
    ValidationStatus,
    register_rule,
    rule_registry,
    validation_engine,
)

__version__ = "0.1.0"

# Web and data-layer names live in oe_sdk.web. That module imports app.database
# and app.dependencies, which build the SQLAlchemy engine at import time and
# require a configured PostgreSQL DATABASE_URL. Importing them lazily via
# __getattr__ keeps `import oe_sdk` cheap and free of side effects, so the pure
# primitives above are usable even before a database is configured. The web
# names resolve the moment they are accessed, which inside a running deployment
# is always after the app is configured.
_LAZY_WEB = frozenset(
    {
        "Base",
        "GUID",
        "SessionDep",
        "CurrentUserId",
        "CurrentUserPayload",
        "OptionalUserPayload",
        "RequirePermission",
        "RequirePermissionOrApiKey",
        "RequireRole",
        "verify_project_access",
        "get_session",
        "get_current_user_id",
    }
)

if TYPE_CHECKING:
    # Make the lazily-resolved names visible to type checkers and IDEs.
    from oe_sdk.web import (
        GUID,
        Base,
        CurrentUserId,
        CurrentUserPayload,
        OptionalUserPayload,
        RequirePermission,
        RequirePermissionOrApiKey,
        RequireRole,
        SessionDep,
        get_current_user_id,
        get_session,
        verify_project_access,
    )


def __getattr__(name: str) -> Any:
    """Resolve web and data-layer names lazily (PEP 562)."""
    if name in _LAZY_WEB:
        from oe_sdk import web

        return getattr(web, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    # manifest
    "ModuleManifest",
    "module_manifest",
    # events
    "event_bus",
    "Event",
    "EventResult",
    "EventBus",
    "on",
    "publish",
    "publish_detached",
    "subscribe",
    # hooks
    "hooks",
    "HookRegistry",
    # validation
    "ValidationRule",
    "RuleResult",
    "ValidationContext",
    "ValidationReport",
    "Severity",
    "RuleCategory",
    "ValidationStatus",
    "rule_registry",
    "validation_engine",
    "register_rule",
    "RuleRegistry",
    "ValidationEngine",
    # permissions
    "Role",
    "permission_registry",
    "register_permissions",
    "PermissionRegistry",
    # schemas
    "ORMModel",
    # scaffolding
    "scaffold",
    # web and data layer (resolved lazily)
    "Base",
    "GUID",
    "SessionDep",
    "CurrentUserId",
    "CurrentUserPayload",
    "OptionalUserPayload",
    "RequirePermission",
    "RequirePermissionOrApiKey",
    "RequireRole",
    "verify_project_access",
    "get_session",
    "get_current_user_id",
    # meta
    "__version__",
]
