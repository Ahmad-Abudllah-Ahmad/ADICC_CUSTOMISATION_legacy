# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Clash AI Triage module.

LLM-assisted triage of clash detection results. The competitive move:
Commercial coordination tools monetise AI clash triage as a paid black box. We ship the
prompt VISIBLE in the repo (user-tunable per project), persist the full
prompt + raw response for audit, and surface a defensible confidence
score on every verdict.

Read-only against the clash module:
    * inputs are ``ClashResult`` rows (and the optional ``ClashIssue``)
    * outputs are persisted on this module's own ``oe_clash_triage_result``
    * no clash columns mutated

Honest about cost: ``cost_usd_estimate`` is derived from token counts and
a hard-coded per-1k-token rate table (see ``service.py``). When the LLM
returns unparseable JSON twice in a row, we persist ``category="unclear"``
with the raw response intact rather than hallucinate a verdict.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.clash_ai_triage.permissions import (
        register_clash_ai_triage_permissions,
    )

    register_clash_ai_triage_permissions()
