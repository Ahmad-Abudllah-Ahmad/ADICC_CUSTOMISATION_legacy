# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Variations module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_variations_permissions() -> None:
    """Register permissions for the variations module."""
    permission_registry.register_module_permissions(
        "variations",
        {
            "variations.read": Role.VIEWER,
            "variations.create": Role.EDITOR,
            "variations.update": Role.EDITOR,
            "variations.delete": Role.MANAGER,
            "variations.submit_request": Role.EDITOR,
            "variations.approve_request": Role.MANAGER,
            # R7 audit: tunable in service.HIGH_VALUE_APPROVAL_THRESHOLD -
            # this permission gates approvals whose cost impact exceeds the
            # threshold (default 100_000). Admin-only by default so a
            # rubber-stamp manager cannot wave through a large change.
            "variations.approve_high_value": Role.ADMIN,
            "variations.convert_to_vo": Role.MANAGER,
            "variations.complete_vo": Role.EDITOR,
            "variations.sign_daywork": Role.EDITOR,
            "variations.decide_claim": Role.MANAGER,
            "variations.close_final_account": Role.MANAGER,
        },
    )
