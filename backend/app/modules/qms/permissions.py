# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""QMS module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_qms_permissions() -> None:
    """Register permissions for the QMS module."""
    permission_registry.register_module_permissions(
        "qms",
        {
            "qms.itp.read": Role.VIEWER,
            "qms.itp.write": Role.EDITOR,
            "qms.inspection.read": Role.VIEWER,
            "qms.inspection.write": Role.EDITOR,
            "qms.inspection.sign": Role.EDITOR,
            # Item 12: releasing a passed hold point unblocks downstream work
            # and must not be a routine editor action - gate it to MANAGER+,
            # matching the other gate-keeping QMS calls (escalate, audit).
            "qms.inspection.release_hold": Role.MANAGER,
            "qms.ncr.read": Role.VIEWER,
            "qms.ncr.write": Role.EDITOR,
            "qms.ncr.escalate": Role.MANAGER,
            "qms.punch.read": Role.VIEWER,
            "qms.punch.write": Role.EDITOR,
            "qms.audit.read": Role.VIEWER,
            "qms.audit.write": Role.MANAGER,
            "qms.calibration.read": Role.VIEWER,
            "qms.calibration.write": Role.EDITOR,
            # R7: tenant-wide (project_id=None) calibrations bypass per-project
            # ownership gates and are visible to every reader in the tenant.
            # An editor must not be able to create one - promoting them is a
            # manager-level call (matches `qms.template.write`, which is also
            # tenant-scoped and gated to MANAGER+).
            "qms.calibration.tenant_write": Role.MANAGER,
            "qms.calibration.delete": Role.MANAGER,
            "qms.template.read": Role.VIEWER,
            "qms.template.write": Role.MANAGER,
            "qms.template.delete": Role.MANAGER,
            "qms.report.read": Role.VIEWER,
        },
    )
