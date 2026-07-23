# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Partner-pack project scoping helper.

When a pack is active, the workspace presents a single-client view: only
projects tagged ``metadata_["partner_pack"] == <slug>`` are shown, everywhere
projects are listed (the /projects page, the dashboard cards, the per-project
summary). Activation tags the pack's demo projects and any project created while
the pack is active; deactivation untags them so the normal listing returns.

This module is the single source of truth for "which pack scopes the workspace
right now", so every listing site applies the exact same rule. Every helper is
fail-soft: a partner-pack lookup error returns "no active pack", leaving the
caller's normal (un-scoped) query intact.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# JSONB key under Project.metadata_ that carries the owning pack's slug.
PACK_TAG_KEY = "partner_pack"


def active_pack_slug() -> str | None:
    """Return the active pack's slug, or ``None`` when none is active.

    Honours both an in-app applied pack and an ``OE_PARTNER_PACK`` env pin (it
    delegates to :func:`get_active_pack`). Never raises.
    """
    try:
        from app.core.partner_pack.discovery import get_active_pack

        pack = get_active_pack()
        return pack.slug if pack else None
    except Exception:  # noqa: BLE001 - scoping must never break a listing
        logger.debug("active_pack_slug lookup failed; treating as no active pack", exc_info=True)
        return None


def scope_project_query(stmt: Any, project_model: Any) -> Any:
    """Add the active-pack filter to a ``select(Project)`` statement, if any.

    Returns the statement unchanged when no pack is active. The filter matches
    ``project_model.metadata_["partner_pack"].as_string() == <slug>`` (the same
    PostgreSQL ``->>`` accessor used across the codebase for JSON-key lookups).
    """
    slug = active_pack_slug()
    if not slug:
        return stmt
    return stmt.where(project_model.metadata_[PACK_TAG_KEY].as_string() == slug)
