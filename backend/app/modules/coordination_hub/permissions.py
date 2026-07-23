# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Coordination Hub module permission definitions.

The hub is a read-only aggregator; everything it surfaces is already
gated by the underlying module's own permissions (``clash.read``,
``bcf.read``, …). A single coarse ``coordination.read`` keeps the gate
simple while still letting an org disable hub access for plain VIEWERs
who shouldn't see the cross-module rollup. Defaults to VIEWER so any
authenticated project member sees the dashboard.
"""

from app.core.permissions import Role, permission_registry


def register_coordination_hub_permissions() -> None:
    """Register RBAC permissions for the coordination hub module."""
    permission_registry.register_module_permissions(
        "coordination",
        {
            "coordination.read": Role.VIEWER,
            # Editing thresholds is a project-configuration action - gate
            # behind EDITOR so plain VIEWERs cannot raise/lower their own
            # alarm bar. Admins & Managers satisfy this implicitly.
            "coordination.write": Role.EDITOR,
        },
    )
