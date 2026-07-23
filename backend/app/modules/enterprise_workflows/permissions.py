# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Enterprise Workflows module permission definitions.

Permissions:

* ``enterprise_workflows.read``     - list / get workflows and requests
                                      (VIEWER tier).
* ``enterprise_workflows.manage``   - create / update / delete workflow
                                      definitions (MANAGER tier: defining
                                      an approval chain is an admin-style
                                      configuration action, not routine
                                      editing).
* ``enterprise_workflows.submit``   - submit an entity for approval
                                      (EDITOR tier).
* ``enterprise_workflows.decide``   - approve / reject a pending request
                                      (EDITOR tier; the per-step role /
                                      assignee gate in the service narrows
                                      this further at decision time).
* ``enterprise_workflows.cancel``   - withdraw a pending request (EDITOR
                                      tier; the service additionally
                                      restricts this to the original
                                      requester or an admin).
"""

from app.core.permissions import Role, permission_registry


def register_enterprise_workflows_permissions() -> None:
    """Register permissions for the enterprise_workflows module."""
    permission_registry.register_module_permissions(
        "enterprise_workflows",
        {
            "enterprise_workflows.read": Role.VIEWER,
            "enterprise_workflows.manage": Role.MANAGER,
            "enterprise_workflows.submit": Role.EDITOR,
            "enterprise_workflows.decide": Role.EDITOR,
            "enterprise_workflows.cancel": Role.EDITOR,
        },
    )
