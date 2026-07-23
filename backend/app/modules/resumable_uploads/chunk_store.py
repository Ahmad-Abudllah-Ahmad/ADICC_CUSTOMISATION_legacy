# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Filesystem chunk store for resumable uploads.

Chunks for an in-flight session land under a per-session temp directory.
Assembly streams the parts in index order into a single temp file and
computes the SHA-256 incrementally, so the whole payload is never held in
memory. The assembled file is then handed to the document service.

The temp root sits under the same per-user data directory the rest of the
local storage uses (``OE_CLI_DATA_DIR`` / ``DATA_DIR`` / ``~/.openestimator``)
so it inherits the platform's safe-root containment and is cleaned up by
the GC sweep.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Bytes streamed per read during assembly. 1 MiB balances syscall count
# against memory; it is independent of the upload chunk size.
_ASSEMBLY_READ_SIZE: int = 1024 * 1024


def _resumable_base_dir() -> Path:
    """Return the root temp directory for resumable chunk storage.

    Mirrors ``app.core.storage._default_local_base_dir`` preference order
    so an install under a read-only location still has a writable scratch
    area, then falls back to ``~/.openestimator/resumable``.
    """
    override = os.environ.get("OE_CLI_DATA_DIR") or os.environ.get("DATA_DIR")
    if override:
        return Path(override) / "resumable"
    return Path.home() / ".openestimator" / "resumable"


def session_dir(session_id: uuid.UUID | str) -> Path:
    """Return (and create) the per-session chunk directory."""
    path = _resumable_base_dir() / str(session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def chunk_path(session_id: uuid.UUID | str, chunk_index: int) -> Path:
    """Return the on-disk path for one chunk of a session."""
    return session_dir(session_id) / f"{chunk_index:08d}.part"


def write_chunk(session_id: uuid.UUID | str, chunk_index: int, data: bytes) -> None:
    """Persist a single chunk to disk.

    The write is atomic-ish: data is written to a temp name then renamed
    into place so a crash mid-write never leaves a partial chunk that a
    later assembly would trust. Re-writing an existing chunk is harmless
    (the rename overwrites).
    """
    target = chunk_path(session_id, chunk_index)
    tmp = target.with_suffix(".part.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def has_chunk(session_id: uuid.UUID | str, chunk_index: int) -> bool:
    """True when the chunk file already exists on disk."""
    return chunk_path(session_id, chunk_index).is_file()


def assemble(
    session_id: uuid.UUID | str,
    total_chunks: int,
    dest_path: Path,
) -> tuple[int, str]:
    """Concatenate chunks ``0..total_chunks-1`` into ``dest_path``.

    Streams each chunk through a fixed-size buffer and updates a running
    SHA-256 so neither the individual chunks nor the assembled file are
    ever fully resident in memory.

    Args:
        session_id: The upload session whose chunks to assemble.
        total_chunks: Number of chunks expected (all must be present).
        dest_path: Where to write the assembled file.

    Returns:
        A tuple ``(assembled_size_bytes, sha256_hex)``.

    Raises:
        FileNotFoundError: If any expected chunk is missing on disk.
    """
    hasher = hashlib.sha256()
    written = 0
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with dest_path.open("wb") as out:
        for index in range(total_chunks):
            part = chunk_path(session_id, index)
            if not part.is_file():
                raise FileNotFoundError(f"missing chunk {index} for session {session_id}")
            with part.open("rb") as src:
                while True:
                    buf = src.read(_ASSEMBLY_READ_SIZE)
                    if not buf:
                        break
                    out.write(buf)
                    hasher.update(buf)
                    written += len(buf)
    return written, hasher.hexdigest()


def cleanup(session_id: uuid.UUID | str) -> None:
    """Remove the per-session chunk directory and all its parts.

    Never raises - cleanup is best-effort so a stale lock or a file the
    GC already removed can't surface an error to the caller.
    """
    path = _resumable_base_dir() / str(session_id)
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Failed to clean resumable session dir %s: %s", path, exc)
