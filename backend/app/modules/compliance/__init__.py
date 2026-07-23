# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Compliance DSL module - user-authored validation rules.

Wraps :mod:`app.core.validation.dsl` with persistence + a REST surface
so projects can author their own validation rules as YAML/JSON snippets
and have them registered into the global rule registry alongside the
hand-coded built-ins.
"""

from app.modules.compliance.manifest import manifest


async def on_startup() -> None:
    """Module startup hook - register permissions and persisted DSL rules."""
    from app.modules.compliance.permissions import (
        register_compliance_permissions,
    )

    register_compliance_permissions()

    # Re-register every active user-authored DSL rule from the database into
    # the in-memory rule registry. The registry is rebuilt empty on each boot,
    # so without this persisted compliance rules silently vanish on restart and
    # stop firing during validation. Best-effort: a DB that is not ready yet, or
    # a single malformed rule, must never block module startup. This runs after
    # create_all/migrations (module on_startup hooks fire post schema setup), so
    # the rule table is present by the time we query it.
    import logging

    logger = logging.getLogger(__name__)
    try:
        from app.database import async_session_factory
        from app.modules.compliance.repository import ComplianceDSLRepository
        from app.modules.compliance.service import register_active_rules

        async with async_session_factory() as session:
            count = await register_active_rules(ComplianceDSLRepository(session))
        if count:
            logger.info("compliance: re-registered %d persisted DSL rule(s) at startup", count)
    except Exception:
        logger.warning(
            "compliance: could not re-register persisted DSL rules at startup",
            exc_info=True,
        )


__all__ = ["manifest", "on_startup"]
