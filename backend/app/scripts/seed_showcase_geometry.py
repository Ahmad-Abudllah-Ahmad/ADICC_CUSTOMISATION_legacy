# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Restore bundled 3D geometry for the showcase BIM models.

The localized 7-project showcase snapshot (``showcase_snapshot.json.gz``)
ships *database rows* only - it has no mesh blobs.  On a lightweight
self-hosted install that means the 14 showcase BIM models exist in the
model list but the 3D viewer has nothing to render, so the geometry
endpoint returns ``404 geometry_missing`` (issue #168).

To make the showcase render out-of-the-box, the two distinct hero meshes
(an architectural IFC export and a structural RVT export - every showcase
project reuses one of the two) are shipped gzip-compressed next to this
module under ``showcase_geometry/`` (~3.4 MB total).  This seeder
decompresses them once and writes a ``geometry.glb`` blob for each of the
14 models via the normal :mod:`file_storage` layer, so the existing
``GET /bim_hub/models/{id}/geometry/`` endpoint serves them unchanged.

Idempotent: a model that already has a geometry blob on storage (real
upload, prior seed, or a re-converted model) is left untouched.
"""

from __future__ import annotations

import gzip
import json
import logging
import pathlib
from typing import Any

logger = logging.getLogger(__name__)

_BUNDLE_DIR = pathlib.Path(__file__).resolve().parent / "showcase_geometry"
_MANIFEST = _BUNDLE_DIR / "manifest.json"


def _load_manifest() -> list[dict[str, str]]:
    """Return the model→glb manifest, or an empty list if the bundle is absent."""
    if not _MANIFEST.is_file():
        return []
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Showcase geometry manifest unreadable at %s", _MANIFEST)
        return []
    models = data.get("models") if isinstance(data, dict) else None
    return models if isinstance(models, list) else []


def _read_glb(name: str, _cache: dict[str, bytes]) -> bytes | None:
    """Decompress and cache a bundled ``{name}.glb.gz`` blob."""
    if name in _cache:
        return _cache[name]
    path = _BUNDLE_DIR / f"{name}.glb.gz"
    if not path.is_file():
        logger.warning("Showcase geometry blob missing: %s", path)
        return None
    try:
        content = gzip.decompress(path.read_bytes())
    except (OSError, gzip.BadGzipFile):
        logger.warning("Showcase geometry blob corrupt: %s", path)
        return None
    _cache[name] = content
    return content


async def seed_showcase_geometry() -> dict[str, Any]:
    """Write a ``geometry.glb`` blob for each showcase model that lacks one.

    Returns a small summary dict ``{restored, skipped, missing, total}``.
    Never raises - geometry seeding must never block application startup.
    """
    manifest = _load_manifest()
    if not manifest:
        return {"status": "no_bundle", "restored": 0, "skipped": 0, "total": 0}

    # Local imports: keep this script importable without pulling the BIM
    # storage stack at module-load time (e.g. for tooling / tests).
    from app.modules.bim_hub.file_storage import find_geometry_key, save_geometry

    cache: dict[str, bytes] = {}
    restored = skipped = missing = 0

    for entry in manifest:
        model_id = entry.get("model_id")
        project_id = entry.get("project_id")
        glb_name = entry.get("glb")
        if not (model_id and project_id and glb_name):
            continue
        try:
            existing = await find_geometry_key(project_id, model_id)
            if existing is not None:
                skipped += 1
                continue
            content = _read_glb(glb_name, cache)
            if content is None:
                missing += 1
                continue
            await save_geometry(project_id, model_id, ".glb", content)
            restored += 1
        except Exception:  # noqa: BLE001 - per-model failure must not abort the seed
            logger.debug("Showcase geometry restore failed for %s", model_id, exc_info=True)
            missing += 1

    return {
        "status": "ok",
        "restored": restored,
        "skipped": skipped,
        "missing": missing,
        "total": len(manifest),
    }
