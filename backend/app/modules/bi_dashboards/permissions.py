# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""BI Dashboards permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bi_dashboards_permissions() -> None:
    """Register permissions for the BI Dashboards module."""
    permission_registry.register_module_permissions(
        "bi_dashboards",
        {
            # KPI library - broadly readable, only admins curate
            "bi.kpi.read": Role.VIEWER,
            "bi.kpi.compute": Role.VIEWER,
            # Dashboards - viewers can read shared/role/global dashboards,
            # editors can manage their own personal dashboards
            "bi.dashboard.read": Role.VIEWER,
            "bi.dashboard.write": Role.EDITOR,
            "bi.dashboard.share": Role.MANAGER,
            "bi.dashboard.delete": Role.EDITOR,
            # Reports - typical author/run pattern
            "bi.report.read": Role.VIEWER,
            "bi.report.write": Role.EDITOR,
            "bi.report.run": Role.VIEWER,
            "bi.report.schedule": Role.MANAGER,
            # Alerts - manager+ create, viewer reads, admin can mute global
            "bi.alert.read": Role.VIEWER,
            "bi.alert.write": Role.MANAGER,
            # System-KPI admin (curate the catalog, edit formula bindings)
            "bi.admin": Role.ADMIN,
            # Saved filters are personal scope by default - editors can write
            "bi.filter.read": Role.VIEWER,
            "bi.filter.write": Role.EDITOR,
        },
    )
