# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Bid Management module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bid_management_permissions() -> None:
    """Register permissions for the bid_management module."""
    permission_registry.register_module_permissions(
        "bid_management",
        {
            "bid_management.read": Role.VIEWER,
            "bid_management.create": Role.EDITOR,
            "bid_management.update": Role.EDITOR,
            "bid_management.delete": Role.MANAGER,
            "bid_management.publish": Role.MANAGER,
            "bid_management.open_bids": Role.MANAGER,
            "bid_management.disqualify_bidder": Role.MANAGER,
            "bid_management.compute_leveling": Role.EDITOR,
            "bid_management.award": Role.MANAGER,
            "bid_management.cancel": Role.MANAGER,
            # Subcontractor performance scorecards feed the long-term
            # bidder rating in the subcontractors module - a viewer or
            # estimator must not be able to plant retaliatory scores.
            "bid_management.record_scorecard": Role.MANAGER,
        },
    )
