# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Forms & Checklists module.

A user-defined template builder plus a reusable, versioned library of forms and
checklists, and the project-scoped submissions filled against them. Existing
checklists elsewhere in the platform (inspections, QMS) are fixed; this module
is where a user *composes* their own from ordered fields and fills them in on
site, then exports the result to PDF.

The core validation logic lives in :mod:`app.modules.forms.validation`, which is
pure (stdlib only) so it is unit-testable without a database or the app graph.
Permission registration and one-time starter-template seeding are deferred to
:func:`on_startup`, called by the module loader after the schema is created.
"""

import logging

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Module startup hook - register permissions and seed starter templates."""
    from app.modules.forms.permissions import register_forms_permissions

    register_forms_permissions()

    # Seed the built-in starter templates once, in their own session. Never let
    # a seeding hiccup break startup - the next boot retries.
    try:
        from app.database import async_session_factory
        from app.modules.forms.service import seed_starter_templates_if_empty

        async with async_session_factory() as session:
            await seed_starter_templates_if_empty(session)
    except Exception:  # noqa: BLE001 - seeding is best-effort, never fatal
        logger.debug("forms: starter-template seeding skipped this startup", exc_info=True)
