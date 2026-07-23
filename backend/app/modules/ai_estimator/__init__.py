# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder module.

A full AI-driven precise estimate from any source. The agent understands the
data, groups quantities, finds exact logical rates with resource breakdowns,
and assembles a validated estimate the user confirms. Rates always come from
the cost database, never invented by the LLM.
"""


async def on_startup() -> None:
    """Module startup hook (called by the module loader after mount).

    Registers the module permissions, the module-specific validation rules
    (used alongside ``boq_quality`` + the project's regional set), and the
    grounded precise-match agent + its tools into the global agent/tool
    registries. All registrations are idempotent (overwrite by name/id) so a
    hot reload is safe.
    """
    from app.modules.ai_estimator.permissions import register_ai_estimator_permissions
    from app.modules.ai_estimator.tools import register_precise_match_agent
    from app.modules.ai_estimator.validators import register_ai_estimator_rules

    register_ai_estimator_permissions()
    register_ai_estimator_rules()
    register_precise_match_agent()
