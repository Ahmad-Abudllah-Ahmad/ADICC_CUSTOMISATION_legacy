# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""HSE Advanced module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_hse_advanced_permissions() -> None:
    """Register permissions for the hse_advanced module."""
    permission_registry.register_module_permissions(
        "hse_advanced",
        {
            "hse_advanced.read": Role.VIEWER,
            "hse_advanced.create": Role.EDITOR,
            "hse_advanced.update": Role.EDITOR,
            "hse_advanced.delete": Role.MANAGER,
            "hse_advanced.approve_jsa": Role.MANAGER,
            "hse_advanced.approve_permit": Role.MANAGER,
            # Closure of safety records is a compliance-bearing action
            # (RIDDOR §10, OSHA 29 CFR 1904, ISO 45001 §10.2) - gate to
            # manager-or-above so a line editor can't silently sign off
            # a permit, audit, CAPA or incident investigation.
            "hse_advanced.close_permit": Role.MANAGER,
            "hse_advanced.conduct_audit": Role.MANAGER,
            "hse_advanced.close_capa": Role.MANAGER,
            "hse_advanced.close_investigation": Role.MANAGER,
            "hse_advanced.escalate_capa": Role.MANAGER,
            "hse_advanced.issue_ppe": Role.EDITOR,
            "hse_advanced.jsa_template.read": Role.VIEWER,
            "hse_advanced.jsa_template.write": Role.MANAGER,
            "hse_advanced.jsa_template.delete": Role.MANAGER,
            "hse_advanced.activate_permit": Role.EDITOR,
            "hse_advanced.update_prereqs": Role.EDITOR,
            "hse_advanced.verify_effectiveness": Role.MANAGER,
        },
    )
