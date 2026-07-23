# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Reporting module permission definitions.

Registered at module startup via ``app.modules.reporting.on_startup``.
Without this, every ``RequirePermission("reporting.*")`` gate in
``router.py`` resolves against an *unregistered* permission, which the
RBAC engine treats as "unknown → deny" for every non-admin role - i.e.
KPI snapshot creation, template authoring, scheduling, run-now, report
generation and deletion would silently 403 for editors/managers and
only work for admins.

Role mapping mirrors the platform-wide sibling convention
(projects / finance / boq): create+update = EDITOR, read = VIEWER,
delete = MANAGER.

Internal id: ddc-lineage:a17f93c4-reporting-01
"""

from app.core.permissions import Role, permission_registry


def register_reporting_permissions() -> None:
    """Register permissions for the reporting module.

    R7 audit (2026-05-24) added ``reporting.distribute`` for the
    schedule + recipient-list endpoints. Distribution is elevated to
    MANAGER because a scheduled template can email arbitrary recipients
    on a cron - a compromised EDITOR account could otherwise turn the
    platform into a spam/phishing relay tied to legitimate project
    data.
    """
    permission_registry.register_module_permissions(
        "reporting",
        {
            "reporting.create": Role.EDITOR,
            "reporting.read": Role.VIEWER,
            "reporting.update": Role.EDITOR,
            "reporting.delete": Role.MANAGER,
            # Scheduling + recipient mgmt = MANAGER (can fan out PDFs to
            # arbitrary email addresses on a cron, so blast radius >>
            # plain BOQ editing).
            "reporting.distribute": Role.MANAGER,
        },
    )
