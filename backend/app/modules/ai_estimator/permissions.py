# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder permission definitions.

Three permissions gate the run lifecycle, mirroring the ai_agents module's
``register_module_permissions`` shape. Every permission below is enforced by a
real endpoint - there are no declared-but-unused (dead) permissions:

* ``ai_estimator.read``   - view runs, groups, progress, previews, meta
                            (every GET endpoint) (VIEWER).
* ``ai_estimator.run``    - create a run and drive the pipeline stages
                            (analyze / group / match / confirm) (EDITOR).
* ``ai_estimator.apply``  - write the assembled estimate to a BOQ (EDITOR -
                            same level as run; the apply itself is gated
                            additionally on the human-confirm checkpoint and a
                            clean validation report).
"""

from app.core.permissions import Role, permission_registry


def register_ai_estimator_permissions() -> None:
    """Register permissions for the AI Estimate Builder module."""
    permission_registry.register_module_permissions(
        "ai_estimator",
        {
            "ai_estimator.read": Role.VIEWER,
            "ai_estimator.run": Role.EDITOR,
            "ai_estimator.apply": Role.EDITOR,
        },
    )
