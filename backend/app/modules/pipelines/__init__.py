# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pipeline Builder module.

A thin orchestration layer that turns the platform's existing async
``JobRun`` runner, validation engine and per-module services into a
user-authored, gate-able node DAG. Phase 1 ships the smallest spine that
proves the whole flow end-to-end:

    trigger.manual → source.boq → gate.validation → action.export.excel

See the internal pipeline design notes for the canonical
design (the module deliberately reuses, never reinvents, infrastructure).
"""


async def on_startup() -> None:
    """Module startup hook.

    Binds the ``pipeline.run`` JobRun handler (idempotent - also bound at
    executor import) so a fresh process always has it before the first
    run is enqueued.
    """
    from app.core.pipeline.executor import register_pipeline_job_handler

    register_pipeline_job_handler()
