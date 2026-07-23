"""Command-line entry for the OpenConstructionERP module SDK.

``oe-sdk`` wraps the platform's own server-side scaffolder
(``app.scripts.scaffold_module``). It does not generate code itself and it runs
nothing from the new module. Scaffolding is a template copy with placeholder
substitution performed by the platform core, so the CLI stays a thin, auditable
front end over a trusted generator.

Commands:

    oe-sdk new <oe_name> [author]     scaffold a new module (alias: scaffold)
    oe-sdk info                       show the SDK version and core import status

Examples:

    oe-sdk new oe_site_log
    oe-sdk new oe_site_log "Your Name"
    oe-sdk info
"""

from __future__ import annotations

import argparse
import sys

from oe_sdk import __version__

_CORE_MISSING_HINT = (
    "oe-sdk: the platform core (app.scripts.scaffold_module) is not importable "
    "in this environment.\n"
    "The scaffolder ships with the OpenConstructionERP backend and copies the "
    "template from the repository checkout.\n"
    "Install the backend into this environment and run oe-sdk from the "
    "repository, for local work:\n"
    "    pip install -e ./backend       (from the repository root)\n"
)


def _cmd_new(name: str, author: str | None) -> int:
    """Delegate to the platform scaffolder, preserving its output."""
    try:
        from app.scripts import scaffold_module
    except ModuleNotFoundError as exc:
        sys.stderr.write(_CORE_MISSING_HINT)
        sys.stderr.write(f"Import error: {exc}\n")
        return 2
    argv = [name] + ([author] if author else [])
    return scaffold_module.main(argv)


def _cmd_info() -> int:
    """Print the SDK version and whether the platform core is importable."""
    sys.stdout.write(f"oe-sdk {__version__}\n")
    try:
        import app  # noqa: F401

        core = "importable"
    except ModuleNotFoundError:
        core = "NOT importable (install the openconstructionerp backend)"
    sys.stdout.write(f"platform core (app): {core}\n")
    sys.stdout.write(
        "import surface: ModuleManifest, module_manifest, event_bus, on, publish, "
        "publish_detached, hooks, ValidationRule, register_rule, rule_registry, "
        "Role, register_permissions, permission_registry, Base, GUID, SessionDep, "
        "CurrentUserId, RequirePermission, verify_project_access\n"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``oe-sdk`` command."""
    parser = argparse.ArgumentParser(
        prog="oe-sdk",
        description="Build modules for OpenConstructionERP.",
    )
    parser.add_argument("--version", action="version", version=f"oe-sdk {__version__}")
    sub = parser.add_subparsers(dest="command")

    new = sub.add_parser("new", aliases=["scaffold"], help="Scaffold a new module from the template")
    new.add_argument(
        "name",
        help="Module name in snake_case with an oe_ prefix, e.g. oe_site_log",
    )
    new.add_argument("author", nargs="?", default=None, help="Optional author name for the manifest")

    sub.add_parser("info", help="Show the SDK version and whether the platform core is importable")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``oe-sdk`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("new", "scaffold"):
        return _cmd_new(args.name, args.author)
    if args.command == "info":
        return _cmd_info()
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
