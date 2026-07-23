# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Portfolio module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_portfolio_permissions() -> None:
    """Register permissions for the Portfolio module.

    The portfolio tree is a navigation / rollup overlay and grants no project
    access on its own - reads are still intersected with ``accessible_project_ids``
    and per-project writes go through ``verify_project_access``. ``portfolio.read``
    is a VIEWER-level RBAC gate; managing the tree is an EDITOR action.
    """
    permission_registry.register_module_permissions(
        "portfolio",
        {
            "portfolio.read": Role.VIEWER,
            "portfolio.manage": Role.EDITOR,
        },
    )
