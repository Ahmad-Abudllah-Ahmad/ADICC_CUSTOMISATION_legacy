"""Module manifest, re-exported from the platform core, plus a thin builder.

Every module ships a ``manifest.py`` that exposes a value named ``manifest`` of
type ``ModuleManifest``. The loader discovers it and derives the package
directory from ``name`` by removing the ``oe_`` prefix. See
``app.core.module_loader`` for the dataclass and the loader contract.
"""

from __future__ import annotations

from app.core.module_loader import ModuleManifest

__all__ = ["ModuleManifest", "module_manifest"]


def module_manifest(
    name: str,
    version: str,
    display_name: str,
    *,
    description: str = "",
    author: str = "",
    category: str = "community",
    depends: list[str] | None = None,
    optional_depends: list[str] | None = None,
    display_name_i18n: dict[str, str] | None = None,
    auto_install: bool = False,
    enabled: bool = True,
) -> ModuleManifest:
    """Build a ``ModuleManifest`` with community-friendly defaults.

    This is a thin pass-through to ``ModuleManifest`` with two conveniences for
    third-party authors: ``category`` defaults to ``"community"`` (the core
    dataclass defaults to ``"core"``, which only core modules should use), and
    the list and dict fields accept ``None`` instead of requiring an explicit
    empty collection. Field names and meanings match ``ModuleManifest`` exactly.

    Use ``ModuleManifest`` directly if you want the raw dataclass; this helper
    only exists so a community manifest reads in one short call:

        from oe_sdk import module_manifest

        manifest = module_manifest(
            "oe_site_log",
            "0.1.0",
            "Site Log",
            description="Per-project site log of daily entries.",
            depends=["oe_projects"],
        )
    """
    return ModuleManifest(
        name=name,
        version=version,
        display_name=display_name,
        description=description,
        author=author,
        category=category,
        depends=depends or [],
        optional_depends=optional_depends or [],
        display_name_i18n=display_name_i18n or {},
        auto_install=auto_install,
        enabled=enabled,
    )
