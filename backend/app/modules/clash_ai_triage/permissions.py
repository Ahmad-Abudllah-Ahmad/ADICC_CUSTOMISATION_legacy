# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Clash AI Triage module permission definitions.

Three verbs:

* ``clash_triage.read`` - list triage history + read the current prompt
  templates. Viewer-level: anyone who can read clashes can audit the AI
  layer's verdicts and inspect the prompt they were produced with.
* ``clash_triage.execute`` - actually call the LLM (single + batch +
  replay). Editor-level because it has a real cost (LLM tokens) and
  produces a persisted triage row.
* ``clash_triage.manage_prompts`` - reserved for a future prompt-editor
  UI (currently the prompt is read-only in-app; tuning is a deploy-time
  edit to ``prompts.py``). Manager-level so a future write surface
  cannot widen accidentally.
"""

from app.core.permissions import Role, permission_registry


def register_clash_ai_triage_permissions() -> None:
    """Register RBAC permissions for the clash AI triage module."""
    permission_registry.register_module_permissions(
        "clash_ai_triage",
        {
            "clash_triage.read": Role.VIEWER,
            "clash_triage.execute": Role.EDITOR,
            "clash_triage.manage_prompts": Role.MANAGER,
        },
    )
