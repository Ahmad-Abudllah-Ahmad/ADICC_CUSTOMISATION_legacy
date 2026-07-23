# oe-sdk

The module SDK for OpenConstructionERP. It gives a module author one clean
import surface for the platform building blocks: the manifest, the event bus,
the hook registry, the validation engine, the RBAC registry and the shared
router dependencies.

The SDK is a thin, faithful facade. Every name you import from `oe_sdk` is the
same object the running platform uses. When you register a validation rule, an
event handler or a permission through the SDK, it lands on the very registry the
platform dispatches through. There is no second implementation to drift out of
sync, and nothing here hides the core: `from oe_sdk import event_bus` and
`from app.core.events import event_bus` give you the same singleton.

## Install

The SDK re-exports the platform core (the `app` package), which ships with the
OpenConstructionERP backend. Install the backend, then the SDK.

For local work in the monorepo, install both editable so nothing is downloaded:

```bash
pip install -e ./backend
pip install -e ./packages/oe-sdk
```

Standalone, the SDK pulls the backend in as a dependency:

```bash
pip install oe-sdk
```

Check that the core resolved:

```bash
oe-sdk info
```

## Your first module

A module is a Python package under `backend/app/modules/<short>/` with a
`manifest.py`. Scaffold the full package (models, schemas, repository, service,
router, a migration and tests) with the CLI, which wraps the platform's own
server-side generator:

```bash
oe-sdk new oe_site_log
```

Then the two files that show the SDK surface. The manifest:

```python
# backend/app/modules/site_log/manifest.py
from oe_sdk import module_manifest

manifest = module_manifest(
    "oe_site_log",
    "0.1.0",
    "Site Log",
    description="Per-project site log of daily entries.",
    depends=["oe_projects"],
)
```

And one validation rule, registered at import time (the loader auto-imports a
module's `validators.py` on boot):

```python
# backend/app/modules/site_log/validators.py
from oe_sdk import RuleCategory, RuleResult, Severity, ValidationContext, ValidationRule, register_rule


class SiteLogEntryHasNoteRule(ValidationRule):
    rule_id = "site_log.entry_has_note"
    name = "Site log entry has a note"
    standard = "site_log"
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        items = context.data.get("items", []) if isinstance(context.data, dict) else []
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=self.severity,
                category=self.category,
                passed=bool((item.get("description") or "").strip()),
                message="OK" if (item.get("description") or "").strip() else "Entry has no note.",
                element_ref=str(item.get("id")),
            )
            for item in items
        ]


register_rule(SiteLogEntryHasNoteRule(), "site_log", "project_completeness")
```

Restart the backend. The loader discovers the package, mounts its router at
`/api/v1/site-log/` and runs your rule for its rule sets. You did not edit a
central list and you did not add an `include_router` call anywhere.

The full walkthrough, including the model, the migration and the permissions, is
in [docs/platform/first-module-in-10-minutes.md](../../docs/platform/first-module-in-10-minutes.md).

## The import surface

Everything below is importable directly from `oe_sdk`.

| Area | Names |
| --- | --- |
| Manifest | `ModuleManifest`, `module_manifest` |
| Events | `event_bus`, `Event`, `EventResult`, `on`, `publish`, `publish_detached`, `subscribe` |
| Hooks | `hooks` |
| Validation | `ValidationRule`, `RuleResult`, `ValidationContext`, `ValidationReport`, `Severity`, `RuleCategory`, `ValidationStatus`, `rule_registry`, `validation_engine`, `register_rule` |
| Permissions | `Role`, `permission_registry`, `register_permissions` |
| Models | `Base`, `GUID` |
| Router deps | `SessionDep`, `CurrentUserId`, `CurrentUserPayload`, `OptionalUserPayload`, `RequirePermission`, `RequirePermissionOrApiKey`, `RequireRole`, `verify_project_access` |
| Schemas | `ORMModel` |
| Scaffolding | `scaffold` |

The manifest, event, hook, validation and permission names are imported eagerly
and touch no database. The model and router-dependency names live in `oe_sdk.web`
and are resolved lazily, because importing them builds the SQLAlchemy engine and
needs a configured PostgreSQL `DATABASE_URL`. That means a bare `import oe_sdk`
works before a database is configured, and `oe_sdk.SessionDep` pulls the engine
in the moment you reach for it. Inside a running deployment the database is
always configured by then.

Three thin helpers reduce boilerplate without hiding anything:

- `module_manifest(...)` builds a `ModuleManifest` with `category` defaulting to
  `"community"` and the collection fields accepting `None`.
- `register_rule(rule, *rule_sets)` calls `rule_registry.register(rule, [...])`
  with the set names as positional arguments.
- `register_permissions(module_name, perms)` calls
  `permission_registry.register_module_permissions(...)`.

Use the raw core objects (`ModuleManifest`, `rule_registry.register`,
`permission_registry.register_module_permissions`) directly whenever you prefer.
The SDK adds sugar, never a wall.

## The CLI

```
oe-sdk new <oe_name> [author]     scaffold a new module (alias: scaffold)
oe-sdk info                       show the SDK version and core import status
```

`oe-sdk new` delegates to the platform's server-side scaffolder. It copies the
in-repo template and substitutes placeholders. It does not generate code of its
own and it runs nothing from the new module, so the command is a thin, auditable
front end over a trusted generator. Scaffolding needs the platform core to be
importable from a repository checkout, because the generator resolves the
template directory relative to the installed `app` package.

## Where to go next

- [How the platform works for builders](../../docs/platform/how-it-works-for-builders.md)
- [Your first module in 10 minutes](../../docs/platform/first-module-in-10-minutes.md)
- [Extend, do not fork](../../docs/platform/extend-dont-fork.md)

## License

AGPL-3.0-or-later, the same as the platform. Built by Data Driven Construction.
