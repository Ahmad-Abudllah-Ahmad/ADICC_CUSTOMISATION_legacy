# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design Options module.

Generate and compare alternative design options for a project. Each option pairs
a source model or document with its own priced bill of quantities, so the team
can compare a full set of options on total cost, by-trade deltas and cost per m2,
pick a baseline and get a fairness-checked recommendation before committing to
one.

The comparison and validation logic is filled in by later phases; this package
only wires the module into the loader and leaves a single, obvious place for the
validation phase to register the design_options validation rule set.
"""


async def on_startup() -> None:
    """Module startup hook (called by the module loader after mount).

    Registers the module's validation rules into the core rule registry under the
    ``design_options`` rule set, so the comparison aggregator can run
    ``design_options`` alongside ``boq_quality`` and return a per-option
    traffic-light status plus a set-level fairness banner. Idempotent - the
    registry overwrites a rule by id, so a hot reload re-registers cleanly.
    """
    from app.modules.design_options.validators import register_design_options_rules

    register_design_options_rules()
