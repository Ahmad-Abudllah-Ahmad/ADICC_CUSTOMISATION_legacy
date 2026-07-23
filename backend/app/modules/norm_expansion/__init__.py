# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Production-Norm Expansion module.

Expands a work item and its quantity into unpriced resource demand -
labor-hours, machine-hours and material quantities - from a library of
production-norm coefficients per unit. It gives the estimator the hours and
material takeoff behind a rate before any pricing is applied, and it stays
strictly unpriced so it never duplicates the assemblies module's priced
recipes.
"""

import logging

logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Module startup hook - register permissions and seed demo norms.

    The demo seed is best-effort: a missing table (schema not built yet) or a
    transient DB error logs a warning but never fails module boot. The seed is
    idempotent, so it is safe to re-run on every restart.
    """
    from app.modules.norm_expansion.permissions import register_norm_expansion_permissions

    register_norm_expansion_permissions()

    try:
        from app.database import async_session_factory
        from app.modules.norm_expansion.seed import seed_norm_expansion

        async with async_session_factory() as session:
            await seed_norm_expansion(session)
            await session.commit()
    except Exception:  # noqa: BLE001 - startup hook must never raise.
        logger.warning("Norm-expansion demo seed failed at startup", exc_info=True)
