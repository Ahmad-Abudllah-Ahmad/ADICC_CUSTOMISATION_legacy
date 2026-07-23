# OpenEstimate Module Template

Cookiecutter-style skeleton for new modules. Each module is a self-contained
Python package that the loader picks up from `backend/app/modules/`.

## Scaffold a new module

```bash
make module-new NAME=oe_my_module
```

The target validates the name (`oe_` prefix + snake_case), copies this
directory to `backend/app/modules/my_module/` (note: the `oe_` prefix
is stripped — manifests carry the full name, but the package directory
matches the existing core convention `oe_projects` ⇄ `modules/projects/`),
and substitutes the `{{module_name}}` / `{{module_short}}` /
`{{display_name}}` / `{{author}}` placeholders inside every file and
in the test filename.

After the copy:

1. Edit `manifest.py` — set `author`, `description`, `depends`.
2. Set `down_revision` in `migrations/v0001_initial.py` to the current head
   (find it via `cd backend && alembic current`), then move the file into
   `backend/alembic/versions/` and run `make migrate`.
3. Run `make test-backend` — the bundled smoke test in
   `tests/test_<module_name>.py` should pass on a fresh checkout.

## File layout

```
oe-module-template/
├── manifest.py            # ModuleManifest — name, version, depends, category
├── __init__.py            # on_startup() hook
├── models.py              # SQLAlchemy ORM (one stub Item table)
├── schemas.py             # Pydantic Create / Update / Read trio
├── repository.py          # async CRUD against the DB
├── service.py             # business logic + event publishing
├── router.py              # FastAPI router — mounted at /api/v1/<name>/
├── migrations/
│   └── v0001_initial.py   # Alembic migration for the stub table
├── tests/
│   └── test_<short>.py    # Smoke test (no DB required)
└── README.md              # this file
```

## Conventions

- Table names: `oe_<module_name>_<entity>` (the migration assumes this).
- Routes: mounted automatically at `/api/v1/<module_name>/`.
- Events: publish via `event_bus.publish_detached("<module>.<entity>.<verb>", ...)`.
- Permissions: register them inside `on_startup()` so they survive reloads.

## Distribute

Zip the directory (skip `__pycache__`) and drop the archive into another
deployment's `modules/` folder, then restart. The loader discovers the
manifest on next boot.

```bash
zip -r oe-my-module-0.1.0.zip oe-module-template -x "*__pycache__*"
```
