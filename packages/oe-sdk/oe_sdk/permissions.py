"""RBAC primitives, re-exported from the platform core, plus a helper.

Roles are hierarchical: ``admin`` > ``manager`` > ``editor`` > ``viewer`` (plus
the field-worker personas). A module registers its own permissions, each mapped
to the minimum role that may use it. Register them from your module's
``on_startup()`` hook, because ``permissions.py`` is not auto-imported by the
loader (unlike ``validators.py`` or ``events.py``). See ``app.core.permissions``.
"""

from __future__ import annotations

from app.core.permissions import PermissionRegistry, Role, permission_registry

__all__ = ["Role", "permission_registry", "register_permissions", "PermissionRegistry"]


def register_permissions(module_name: str, permissions: dict[str, Role]) -> None:
    """Register a module's permission-to-minimum-role map.

    Thin convenience over
    ``permission_registry.register_module_permissions(module_name, permissions)``:

        from oe_sdk import Role, register_permissions

        def register_site_log_permissions() -> None:
            register_permissions(
                "site_log",
                {
                    "site_log.read": Role.VIEWER,
                    "site_log.write": Role.EDITOR,
                },
            )

    Permission keys follow the ``{module}.{action}`` pattern. Call this from your
    module's ``on_startup()`` so the permissions exist before any request is
    gated on them with ``RequirePermission``.
    """
    permission_registry.register_module_permissions(module_name, permissions)
