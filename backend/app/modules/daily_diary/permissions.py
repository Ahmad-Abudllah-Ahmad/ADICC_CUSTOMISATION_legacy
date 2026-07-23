# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Daily Site Diary module permission definitions.

Internal ref: ddc-lineage:a17f93c4-diary-01
"""

from app.core.permissions import Role, permission_registry


def register_daily_diary_permissions() -> None:
    """Register all RBAC permissions for the daily_diary module."""
    permission_registry.register_module_permissions(
        "daily_diary",
        {
            "daily_diary.read": Role.VIEWER,
            "daily_diary.create": Role.EDITOR,
            "daily_diary.update": Role.EDITOR,
            "daily_diary.delete": Role.MANAGER,
            "daily_diary.close": Role.EDITOR,
            "daily_diary.sign": Role.MANAGER,
            # R7: unlock breaks the signed-immutable invariant; it MUST
            # require manager-or-above. The unlock writes an audit row
            # (revision_history) so the broken signature stays traceable.
            "daily_diary.unlock": Role.MANAGER,
            "daily_diary.archive": Role.MANAGER,
            "daily_diary.upload_photo": Role.EDITOR,
            "daily_diary.attach_drone": Role.EDITOR,
            "daily_diary.attach_reality_capture": Role.EDITOR,
            "daily_diary.fetch_weather": Role.EDITOR,
            "daily_diary.export_scl_bundle": Role.MANAGER,
        },
    )
