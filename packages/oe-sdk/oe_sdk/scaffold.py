"""Programmatic wrapper over the platform's server-side module scaffolder.

The generator itself lives in the platform core at
``app.scripts.scaffold_module``. This wrapper delegates to it and adds nothing
of its own, so scaffolding stays a trusted, in-repo template copy rather than
arbitrary code generation. The platform core (the ``app`` package) must be
importable from a repository checkout, because the generator resolves the
template directory relative to the installed ``app`` package.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["scaffold"]


def scaffold(name: str, *, author: str = "Module Author") -> Path:
    """Scaffold a new module by delegating to the platform core generator.

    Wraps ``app.scripts.scaffold_module.scaffold``. The generator validates
    ``name`` against ``^oe_[a-z][a-z0-9_]*$``, copies
    ``modules/oe-module-template`` into ``backend/app/modules/<short>/`` (the
    ``oe_`` prefix is stripped for the directory name) and substitutes the
    ``{{module_name}}``, ``{{module_short}}``, ``{{display_name}}`` and
    ``{{author}}`` placeholders in every file and in the test filename. It
    refuses to overwrite an existing module.

    Args:
        name: Module name in snake_case with an ``oe_`` prefix, e.g.
            ``oe_site_log``.
        author: Optional author name written into the generated manifest.

    Returns:
        The path to the created module directory.

    Raises:
        ModuleNotFoundError: The platform core is not importable in this
            environment. Install the backend (``pip install -e ./backend`` from
            the repository root) and run from the repository checkout.
        SystemExit: The generator rejected the name, found an existing target
            directory, or could not locate the template. Its message explains
            which.
    """
    from app.scripts.scaffold_module import scaffold as _scaffold

    return _scaffold(name, author=author)
