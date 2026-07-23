"""Custom hatchling build hook for OpenConstructionERP backend.

Solves a long-standing fresh-install paper-cut: the wheel target uses
``[tool.hatch.build.targets.wheel.force-include]`` to bundle the pre-built
Vite frontend (``../frontend/dist`` → ``app/_frontend_dist``). On a cold
clone the ``frontend/dist`` directory does not exist yet, and hatchling
1.27+ walks the force-include map BEFORE running the editable target's
overrides, so ``pip install -e ./backend`` aborts with::

    FileNotFoundError: Forced include not found:
       .../frontend/dist
    error: metadata-generation-failed

This hook runs early in every build (wheel and editable) and creates an
empty ``frontend/dist`` directory with a single ``.placeholder`` file so
the force-include path always resolves. The placeholder is never bundled
into the editable install (the editable target has ``only-include =
["app"]``) and is silently overwritten by a real ``npm run build`` when
the operator builds a production wheel.

This removes the documented workaround
``mkdir frontend/dist && touch frontend/dist/.placeholder`` from the
install runbook — the user runs ``pip install -e ./backend`` directly.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class EnsureFrontendDistHook(BuildHookInterface):
    """Create ``frontend/dist/.placeholder`` if the dir doesn't exist."""

    PLUGIN_NAME = "ensure-frontend-dist"

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        """Create the placeholder before hatchling resolves force-include paths."""
        # ``self.root`` is the directory containing pyproject.toml (backend/).
        # The frontend lives one level up at ../frontend/dist.
        backend_root = Path(self.root)
        dist_dir = backend_root.parent / "frontend" / "dist"
        try:
            dist_dir.mkdir(parents=True, exist_ok=True)
            placeholder = dist_dir / ".placeholder"
            if not placeholder.exists():
                placeholder.write_text(
                    "Placeholder created by backend/hatch_build.py so editable\n"
                    "installs work on a cold clone. Overwritten by `npm run build`.\n",
                    encoding="utf-8",
                )
        except OSError:
            # Best-effort: never block a build because we couldn't write the
            # placeholder. The original FileNotFoundError will surface
            # downstream with the same diagnostic the operator would have
            # seen before this hook existed.
            pass
