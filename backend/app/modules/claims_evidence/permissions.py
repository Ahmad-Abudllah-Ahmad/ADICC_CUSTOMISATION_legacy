# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Claims evidence-pack permission definitions."""

from app.core.permissions import Role, permission_registry


def register_claims_evidence_permissions() -> None:
    """Register the read permission for the claims evidence-pack module."""
    permission_registry.register_module_permissions(
        "claims_evidence",
        {
            "claims_evidence.read": Role.VIEWER,
        },
    )
