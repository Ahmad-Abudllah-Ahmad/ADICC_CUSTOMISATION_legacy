# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Built-in queryable-entity registrations.

These are the reference adapters wired by ``saved_views.on_startup``. A
third-party module registers the same way (calling
``register_queryable_entity`` from its own ``on_startup``) without touching this
package. Registration is idempotent-guarded so a re-import (hot reload, repeated
startup in tests) does not raise a duplicate-registration error, but a genuine
misconfiguration (a missing scoper, an unknown column) still fails the boot.
"""

from __future__ import annotations

import logging

from app.modules.saved_views.registry import entity_registry

logger = logging.getLogger(__name__)


def register_builtin_entities() -> None:
    """Register the project / boq_position / ledger_entry built-in entities.

    Each adapter builds its :class:`QueryableEntity` and calls
    ``register_queryable_entity``. A duplicate registration (already present in
    the singleton from a prior startup) is treated as a no-op; any other
    ``RegistrationError`` propagates so a misconfigured entity fails the boot.
    """
    from app.modules.saved_views.entities.boq_entity import (
        ENTITY_TYPE as BOQ_TYPE,
    )
    from app.modules.saved_views.entities.boq_entity import (
        register as register_boq,
    )
    from app.modules.saved_views.entities.finance_entity import (
        ENTITY_TYPE as LEDGER_TYPE,
    )
    from app.modules.saved_views.entities.finance_entity import (
        register as register_finance,
    )
    from app.modules.saved_views.entities.projects_entity import (
        ENTITY_TYPE as PROJECT_TYPE,
    )
    from app.modules.saved_views.entities.projects_entity import (
        register as register_projects,
    )

    for entity_type, register in (
        (PROJECT_TYPE, register_projects),
        (BOQ_TYPE, register_boq),
        (LEDGER_TYPE, register_finance),
    ):
        if entity_registry.get(entity_type) is not None:
            continue  # already registered this process - idempotent no-op
        register()
