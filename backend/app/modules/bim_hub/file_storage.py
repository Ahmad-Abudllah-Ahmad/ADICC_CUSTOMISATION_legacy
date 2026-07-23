# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BIM Hub file-storage helper.

Thin wrapper around :mod:`app.core.storage` that owns the key layout
for BIM model blobs.  Lives in its own module so the refactor that
moves BIM file I/O off the local filesystem stays isolated from
``service.py`` / ``router.py`` - both of which are currently being
edited by another agent for the Element Groups feature.

Key layout
----------
::

    bim/{project_id}/{model_id}/geometry.glb   (preferred - 8.8x faster)
    bim/{project_id}/{model_id}/geometry.dae   (fallback for pre-v1.5 models)
    bim/{project_id}/{model_id}/original.{ext}

The storage backend is resolved via
:func:`app.core.storage.get_storage_backend`, so switching to S3 is
a single ``STORAGE_BACKEND=s3`` environment variable away.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import re
import uuid
from collections.abc import AsyncIterator
from typing import Final

from app.core.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)

_BIM_PREFIX: Final[str] = "bim"

# Geometry files the viewer can load (order = lookup priority).
# GLB is preferred: 2x smaller transfer, faster browser parsing.
# Node names are preserved via post-processing of the GLB JSON chunk
# after trimesh conversion (see ifc_processor._convert_dae_to_glb).
GEOMETRY_EXTENSIONS: Final[tuple[str, ...]] = (".glb", ".dae", ".gltf")

GEOMETRY_MEDIA_TYPES: Final[dict[str, str]] = {
    ".dae": "model/vnd.collada+xml",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
}


# ──────────────────────────────────────────────────────────────────────────
# Key helpers
# ──────────────────────────────────────────────────────────────────────────


def _stringify(value: uuid.UUID | str) -> str:
    return str(value)


def bim_model_prefix(project_id: uuid.UUID | str, model_id: uuid.UUID | str) -> str:
    """Return the storage prefix holding every blob for a given model."""
    return f"{_BIM_PREFIX}/{_stringify(project_id)}/{_stringify(model_id)}"


def geometry_key(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
) -> str:
    """Return the storage key for a geometry file with extension ``ext``.

    ``ext`` may be given with or without a leading dot. The extension is
    lower-cased so keys are always written/probed in a single canonical case;
    a converter on a case-sensitive filesystem (Linux) that emitted
    ``geometry.GLB`` is still located via the case-insensitive fallback in
    :func:`find_geometry_key`.
    """
    clean_ext = ext if ext.startswith(".") else f".{ext}"
    return f"{bim_model_prefix(project_id, model_id)}/geometry{clean_ext.lower()}"


def original_cad_key(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
) -> str:
    """Return the storage key for the ``original.{ext}`` CAD upload."""
    clean_ext = ext if ext.startswith(".") else f".{ext}"
    return f"{bim_model_prefix(project_id, model_id)}/original{clean_ext}"


# ──────────────────────────────────────────────────────────────────────────
# Operations
# ──────────────────────────────────────────────────────────────────────────


def _backend() -> StorageBackend:
    return get_storage_backend()


async def save_geometry(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
    content: bytes,
) -> str:
    """Persist a geometry blob for a model and return the storage key."""
    key = geometry_key(project_id, model_id, ext)
    await _backend().put(key, content)
    logger.info("Saved BIM geometry to key=%s (%d bytes)", key, len(content))
    return key


async def save_geometry_from_path(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
    src_path: pathlib.Path,
    *,
    size: int | None = None,
) -> str:
    """Persist a geometry blob from a file path (streaming).

    Use this instead of :func:`save_geometry` when the upload is a large
    DAE/GLB/glTF export - it avoids loading the whole mesh into memory
    (on the local backend ``put_stream`` is a single ``rename``).  ``size``
    is purely for the log line; it's read from the path if not provided.
    """
    key = geometry_key(project_id, model_id, ext)
    await _backend().put_stream(key, src_path)
    if size is None:
        try:
            size = src_path.stat().st_size
        except OSError:
            size = -1
    logger.info("Saved BIM geometry (streamed) to key=%s (%d bytes)", key, size)
    return key


async def save_original_cad(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
    content: bytes,
) -> str:
    """Persist an original CAD upload and return the storage key."""
    key = original_cad_key(project_id, model_id, ext)
    await _backend().put(key, content)
    logger.info("Saved original CAD to key=%s (%d bytes)", key, len(content))
    return key


async def save_original_cad_from_path(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
    src_path: pathlib.Path,
    *,
    size: int | None = None,
) -> str:
    """Persist an original CAD upload from a file path (streaming).

    Use this instead of :func:`save_original_cad` when the upload is
    multi-hundred-megabyte (RVT, IFC, PDF) - it avoids loading the file
    into memory.  ``size`` is purely for the log line; it's read from
    the path if not provided.
    """
    key = original_cad_key(project_id, model_id, ext)
    await _backend().put_stream(key, src_path)
    if size is None:
        try:
            size = src_path.stat().st_size
        except OSError:
            size = -1
    logger.info("Saved original CAD (streamed) to key=%s (%d bytes)", key, size)
    return key


async def find_geometry_key(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    prefer_ext: str | None = None,
) -> tuple[str, str] | None:
    """Return ``(key, ext)`` for the first geometry blob found, or ``None``.

    Geometry may have been uploaded as DAE / GLB / glTF.  We probe each
    candidate in priority order.

    When *prefer_ext* is set (e.g. ``".dae"``), that extension is tried
    first before falling back to the default priority order.  This lets
    the frontend force DAE when the GLB has scrambled node names.
    """
    backend = _backend()
    exts = list(GEOMETRY_EXTENSIONS)
    if prefer_ext and prefer_ext in exts:
        exts.remove(prefer_ext)
        exts.insert(0, prefer_ext)
    for ext in exts:
        key = geometry_key(project_id, model_id, ext)
        if await backend.exists(key):
            return key, ext

    # Case-insensitive fallback: a converter on a case-sensitive filesystem
    # (Linux) may have written ``geometry.GLB``/``geometry.Dae``. The exact
    # probes above are lower-case only, so list the model prefix once and match
    # ``geometry.<ext>`` ignoring case, returning the REAL stored key. This also
    # rescues models written before keys were canonicalised to lower-case.
    #
    # ``include_backcompat_roots=True`` so the listing spans the SAME data roots
    # the exact-case ``exists()`` probe above already covers (it resolves via
    # ``_existing_path_for`` which falls back across ``safe_data_roots()``).
    # Without it an uppercase ``geometry.GLB`` stranded under a back-compat root
    # - e.g. a standalone/Docker/macOS deployment whose blobs predate the
    # OE_DATA_DIR fix - would be ready-in-DB but 404 here.
    prefix = bim_model_prefix(project_id, model_id)
    try:
        entries = await backend.list_prefix(prefix, include_backcompat_roots=True)
    except NotImplementedError:
        entries = []
    except Exception:  # noqa: BLE001 - listing must never raise into the caller
        logger.exception("find_geometry_key: list_prefix failed for prefix=%s", prefix)
        entries = []
    for stored_key, _size in entries:
        name = stored_key.rsplit("/", 1)[-1].lower()
        for ext in exts:
            if name == f"geometry{ext}":
                logger.info(
                    "find_geometry_key: matched %s case-insensitively for model %s",
                    stored_key,
                    model_id,
                )
                return stored_key, ext
    return None


def open_geometry_stream(key: str) -> AsyncIterator[bytes]:
    """Return an async iterator streaming a geometry blob.

    Not ``async`` - the underlying ``open_stream`` is itself an async
    generator, so we just hand its iterator back to the caller.
    """
    return _backend().open_stream(key)


def presigned_geometry_url(key: str, *, expires_in: int = 3600) -> str | None:
    """Return a presigned URL for the blob (S3 only).

    ``None`` means the backend cannot presign - the caller should
    stream via :func:`open_geometry_stream` instead.
    """
    return _backend().url_for(key, expires_in=expires_in)


async def delete_model_blobs(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
) -> int:
    """Delete every blob belonging to a model.  Returns count removed."""
    prefix = bim_model_prefix(project_id, model_id)
    try:
        removed = await _backend().delete_prefix(prefix)
    except Exception as exc:  # noqa: BLE001 - blob cleanup must not block delete
        logger.warning("Failed to delete BIM blobs at prefix=%s: %s", prefix, exc)
        return 0
    if removed:
        logger.info("Removed %d BIM blob(s) at prefix=%s", removed, prefix)
    return removed


# ──────────────────────────────────────────────────────────────────────────
# Persistence-policy helpers (v2.6.29)
# ──────────────────────────────────────────────────────────────────────────


# Extensions of files we treat as "conversion artifacts" - these are kept
# forever so the /bim page can serve them instantly without re-conversion.
_ARTIFACT_EXTENSIONS: Final[tuple[str, ...]] = (
    ".glb",
    ".dae",
    ".gltf",
    ".json",
    ".parquet",
    ".png",
    ".jpg",
    ".pdf",
)


async def delete_original_cad(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
) -> bool:
    """Delete the raw uploaded ``original.{ext}`` blob.

    Returns ``True`` if a blob existed and was removed, ``False`` if no
    blob was present.  Errors are swallowed and logged - the storage
    cleanup must never block conversion success.

    Used by the post-conversion success path when
    ``settings.keep_original_cad`` is False (production default).
    """
    backend = _backend()
    key = original_cad_key(project_id, model_id, ext)
    try:
        if not await backend.exists(key):
            return False
        await backend.delete(key)
        logger.info("Deleted original CAD blob key=%s (storage policy)", key)
        return True
    except Exception as exc:  # noqa: BLE001 - never block conversion success
        logger.warning("Failed to delete original CAD blob key=%s: %s", key, exc)
        return False


async def has_original_cad(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    ext: str,
) -> bool:
    """Return True iff the raw upload is still on storage."""
    if not ext:
        return False
    backend = _backend()
    key = original_cad_key(project_id, model_id, ext)
    try:
        return await backend.exists(key)
    except Exception:  # noqa: BLE001 - probing the backend must never raise
        logger.exception("has_original_cad probe failed for key=%s", key)
        return False


async def compute_artifact_size_bytes(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
) -> int:
    """Return total bytes of conversion artifacts for a single model.

    For backends implementing ``list_prefix`` this is a single bulk sweep of
    the model prefix (excluding ``original.*``). For the local backend the
    sweep spans every platform-owned data root via
    ``include_backcompat_roots=True`` so a blob stranded under a pre-8.6.1
    default/back-compat root is still counted (otherwise the artifact size
    under-reports for those deployments). For S3 this is a ``list_objects_v2``
    sweep; for backends without ``list_prefix`` we fall back to counting the
    geometry-key candidates only, which keeps the call cheap for the common
    case (single GLB).
    """
    backend = _backend()
    prefix = bim_model_prefix(project_id, model_id)

    # Bulk path - one listing spans every (back-compat) data root.
    if list_prefix_supported():
        try:
            entries = await backend.list_prefix(prefix, include_backcompat_roots=True)
        except NotImplementedError:
            entries = None
        except Exception:  # noqa: BLE001 - sizing is best-effort, never fatal
            logger.exception("compute_artifact_size_bytes: list_prefix failed for prefix=%s", prefix)
            entries = []
        if entries is not None:
            total = 0
            for stored_key, size_bytes in entries:
                # Exclude raw uploads; everything else is treated as an artifact.
                if stored_key.rsplit("/", 1)[-1].lower().startswith("original."):
                    continue
                total += size_bytes
            return total

    # Fallback (community backends without list_prefix) - probe geometry keys.
    total = 0
    for ext in _ARTIFACT_EXTENSIONS:
        if ext not in GEOMETRY_EXTENSIONS:
            continue
        key = geometry_key(project_id, model_id, ext)
        try:
            if await backend.exists(key):
                total += await backend.size(key)
        except Exception:  # noqa: BLE001 - best-effort sizing
            continue
    return total


def project_bim_prefix(project_id: uuid.UUID | str) -> str:
    """Return the storage prefix holding every BIM model under a project."""
    return f"{_BIM_PREFIX}/{_stringify(project_id)}"


async def bulk_model_storage_summary(
    project_id: uuid.UUID | str,
) -> dict[str, dict[str, object]]:
    """Return per-model storage summary for every model under a project.

    Single storage round-trip via :meth:`StorageBackend.list_prefix`,
    then bucket the results by ``{project}/{model_id}`` segment in
    Python.  Each value is a dict with:

    * ``artifact_size_bytes`` - sum of bytes for everything that isn't
      the raw ``original.*`` upload
    * ``original_size_bytes`` - sum of bytes for ``original.*`` blobs
      (``None`` if no raw upload remains - matches the
      ``keep_original_cad=False`` production default semantics)
    * ``geometry_exts`` - set of geometry extensions present (``.glb`` /
      ``.dae`` / ``.gltf``) - empty set means "no geometry on disk"

    Replaces the per-model fan-out of
    ``compute_artifact_size_bytes`` + ``has_original_cad`` +
    ``find_geometry_key`` probes that the list endpoint used to issue
    via ``asyncio.gather`` (50-150 storage round-trips per page →
    a single one).

    Lookup pattern for callers:
        summary = await bulk_model_storage_summary(project_id)
        info = summary.get(str(model_id), {})
        size_bytes = info.get("artifact_size_bytes", 0)
        ...

    When ``list_prefix`` isn't implemented by the backend (community
    backends predating v4.6.1), an empty dict is returned and the
    caller MUST fall back to per-model probes - :func:`list_prefix_supported`
    surfaces that capability check.
    """
    backend = _backend()
    prefix = project_bim_prefix(project_id)
    try:
        # Span back-compat roots so a model whose artifacts live under a
        # pre-8.6.1 default root still reports its geometry/size here instead
        # of appearing artifact-less (ready-in-DB but empty/404 on serve).
        entries = await backend.list_prefix(prefix, include_backcompat_roots=True)
    except NotImplementedError:
        logger.debug(
            "Storage backend %s does not implement list_prefix; BIM list endpoint will fall back to per-model probes.",
            type(backend).__name__,
        )
        return {}

    summary: dict[str, dict[str, object]] = {}
    # Keys are of shape "bim/{project_id}/{model_id}/<filename>" - split
    # on '/' and group by the model_id segment.
    prefix_with_slash = prefix.rstrip("/") + "/"
    for key, size_bytes in entries:
        if not key.startswith(prefix_with_slash):
            continue
        remainder = key[len(prefix_with_slash) :]
        parts = remainder.split("/", 1)
        if len(parts) != 2:
            # Stray file directly under the project dir; not a model artifact.
            continue
        model_id, filename = parts
        if not model_id or not filename:
            continue
        bucket = summary.setdefault(
            model_id,
            {
                "artifact_size_bytes": 0,
                "original_size_bytes": 0,
                "has_original": False,
                "geometry_exts": set(),
            },
        )
        lower = filename.lower()
        if lower.startswith("original."):
            bucket["original_size_bytes"] = int(bucket["original_size_bytes"]) + size_bytes  # type: ignore[operator]
            bucket["has_original"] = True
            continue
        bucket["artifact_size_bytes"] = int(bucket["artifact_size_bytes"]) + size_bytes  # type: ignore[operator]
        # Detect geometry presence by extension match.
        for ext in GEOMETRY_EXTENSIONS:
            if lower == f"geometry{ext}":
                bucket["geometry_exts"].add(ext)  # type: ignore[union-attr]
                break
    return summary


def list_prefix_supported() -> bool:
    """Return True iff the configured backend implements ``list_prefix``.

    Used by the BIM list endpoint to pick between the bulk
    :func:`bulk_model_storage_summary` path and the per-model probe
    fallback (community backends that haven't overridden the new
    abstract base method).
    """
    backend = _backend()
    # Compare the bound method to the abstract base's default to detect
    # whether the subclass overrode list_prefix.  Both shipped backends
    # (LocalStorageBackend, S3StorageBackend) override it.
    from app.core.storage import StorageBackend

    base_impl = StorageBackend.list_prefix
    bound = type(backend).list_prefix
    return bound is not base_impl


def bim_root_label() -> str:
    """Return a short human-readable label for where BIM blobs live.

    The header chip on the BIM page surfaces this so users can see at a
    glance whether the instance is on local disk or pushing to S3.
    """
    backend = _backend()
    base_dir = getattr(backend, "base_dir", None)
    if base_dir is not None:
        # Trim to the conventional "data/bim/" suffix to keep the chip short.
        return "data/bim/"
    bucket = getattr(backend, "_bucket", None)
    if bucket:
        return f"s3://{bucket}/{_BIM_PREFIX}/"
    return f"{_BIM_PREFIX}/"


# ──────────────────────────────────────────────────────────────────────────
# Streaming tiles (v11.x - fast viewer)
# ──────────────────────────────────────────────────────────────────────────
#
# A model's monolithic ``geometry.glb`` is baked once into spatially-tiled,
# content-addressed sub-GLBs so the viewer can stream geometry progressively
# and cache tiles forever. Key layout::
#
#     bim/{project_id}/{model_id}/tiles/manifest.json
#     bim/{project_id}/{model_id}/tiles/{content_hash}.glb
#
# The manifest is the readiness marker (written last); its presence means the
# tileset is complete. Tiles are immutable because the URL is the content hash.

_TILES_SUBDIR: Final[str] = "tiles"

# Tile hashes are hex (sha256 prefix). This strips anything else so a hash
# taken straight from a URL path can never escape the model's tiles prefix.
_HEX_ONLY: Final[re.Pattern[str]] = re.compile(r"[^0-9a-f]")


def _safe_hash(content_hash: str) -> str:
    """Return a path-safe, hex-only form of a tile content hash."""
    return _HEX_ONLY.sub("", (content_hash or "").lower())[:64]


def tiles_prefix(project_id: uuid.UUID | str, model_id: uuid.UUID | str) -> str:
    """Return the storage prefix holding every streaming tile for a model."""
    return f"{bim_model_prefix(project_id, model_id)}/{_TILES_SUBDIR}"


def tiles_manifest_key(project_id: uuid.UUID | str, model_id: uuid.UUID | str) -> str:
    """Return the storage key for a model's tile manifest."""
    return f"{tiles_prefix(project_id, model_id)}/manifest.json"


def tile_key(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    content_hash: str,
) -> str:
    """Return the storage key for a single content-addressed tile GLB."""
    return f"{tiles_prefix(project_id, model_id)}/{_safe_hash(content_hash)}.glb"


async def save_tile(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    content_hash: str,
    content: bytes,
) -> str:
    """Persist one tile GLB and return its storage key."""
    key = tile_key(project_id, model_id, content_hash)
    await _backend().put(key, content)
    return key


async def save_tiles_manifest(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    content: bytes,
) -> str:
    """Persist the tile manifest (written last - marks the tileset complete)."""
    key = tiles_manifest_key(project_id, model_id)
    await _backend().put(key, content)
    logger.info("Saved BIM tile manifest key=%s (%d bytes)", key, len(content))
    return key


async def read_tiles_manifest(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
) -> bytes | None:
    """Return the raw manifest bytes, or ``None`` if the model has no tileset."""
    key = tiles_manifest_key(project_id, model_id)
    backend = _backend()
    try:
        if await backend.exists(key):
            return await backend.get(key)
    except Exception:  # noqa: BLE001 - a probe must never raise into the caller
        logger.exception("read_tiles_manifest failed key=%s", key)
    return None


async def read_tile(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
    content_hash: str,
) -> bytes | None:
    """Return one tile's GLB bytes, or ``None`` if it does not exist.

    Prefers a zero-copy local-disk read; falls back to the backend's
    ``get`` for remote/community backends.
    """
    key = tile_key(project_id, model_id, content_hash)
    backend = _backend()
    try:
        disk_path = backend.local_path(key)
        if disk_path is not None:
            if not disk_path.exists():
                return None
            return await asyncio.to_thread(disk_path.read_bytes)
        if await backend.exists(key):
            return await backend.get(key)
    except Exception:  # noqa: BLE001 - never raise a serve error into the caller
        logger.exception("read_tile failed key=%s", key)
    return None


async def delete_tiles(
    project_id: uuid.UUID | str,
    model_id: uuid.UUID | str,
) -> int:
    """Delete a model's whole tiles subtree (used before a re-bake)."""
    prefix = tiles_prefix(project_id, model_id)
    try:
        return await _backend().delete_prefix(prefix)
    except Exception as exc:  # noqa: BLE001 - cleanup must not block a re-bake
        logger.warning("Failed to delete BIM tiles at prefix=%s: %s", prefix, exc)
        return 0
