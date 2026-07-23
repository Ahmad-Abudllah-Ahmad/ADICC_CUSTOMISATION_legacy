# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure chunk-math helpers for resumable uploads.

Everything here is stateless and DB-free so the assembly / integrity math
and the idempotency + missing-chunk logic can be unit-tested with plain
namespaces (no session, no storage). The service layer wires these to the
ORM and the filesystem; this module never touches either.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class ChunkValidationError(ValueError):
    """Raised when a chunk index or size violates the session contract."""


def compute_total_chunks(total_size: int, chunk_size: int) -> int:
    """Return how many chunks a file of ``total_size`` splits into.

    Args:
        total_size: Total file size in bytes (must be > 0).
        chunk_size: Fixed chunk size in bytes (must be > 0).

    Returns:
        The chunk count, ``ceil(total_size / chunk_size)``.

    Raises:
        ChunkValidationError: If either argument is not positive.
    """
    if total_size <= 0:
        raise ChunkValidationError("total_size must be positive")
    if chunk_size <= 0:
        raise ChunkValidationError("chunk_size must be positive")
    return math.ceil(total_size / chunk_size)


def expected_chunk_size(
    chunk_index: int,
    *,
    total_size: int,
    chunk_size: int,
    total_chunks: int,
) -> int:
    """Return the exact byte length chunk ``chunk_index`` must have.

    Every chunk except the final one is exactly ``chunk_size`` bytes. The
    last chunk carries the remainder (which equals ``chunk_size`` only when
    the file divides evenly).

    Raises:
        ChunkValidationError: If ``chunk_index`` is outside
            ``[0, total_chunks)``.
    """
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise ChunkValidationError(f"chunk_index {chunk_index} out of range [0, {total_chunks})")
    if chunk_index < total_chunks - 1:
        return chunk_size
    remainder = total_size - chunk_size * (total_chunks - 1)
    # remainder is always in (0, chunk_size] for a well-formed session.
    return remainder


def validate_chunk(
    chunk_index: int,
    chunk_length: int,
    *,
    total_size: int,
    chunk_size: int,
    total_chunks: int,
) -> None:
    """Validate an incoming chunk's index and byte length.

    Rejects out-of-range indices and any chunk whose length does not match
    the size the session contract demands for that index. An empty chunk is
    always rejected.

    Raises:
        ChunkValidationError: On any violation.
    """
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise ChunkValidationError(f"chunk_index {chunk_index} out of range [0, {total_chunks})")
    if chunk_length <= 0:
        raise ChunkValidationError("chunk body is empty")
    want = expected_chunk_size(
        chunk_index,
        total_size=total_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
    )
    if chunk_length != want:
        raise ChunkValidationError(f"chunk {chunk_index} has {chunk_length} bytes, expected {want}")


def normalize_received(received: object) -> set[int]:
    """Coerce a stored ``received_chunks`` value into a set of ints.

    The column is a JSON list but legacy / partial writes might hand us a
    ``None`` or stray non-int entries; this keeps the set semantics robust.
    """
    if not received:
        return set()
    out: set[int] = set()
    for item in received:  # type: ignore[union-attr]
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return out


def missing_chunks(received: object, total_chunks: int) -> list[int]:
    """Return the sorted list of indices in ``range(total_chunks)`` not yet received."""
    have = normalize_received(received)
    return [i for i in range(total_chunks) if i not in have]


def is_complete(received: object, total_chunks: int) -> bool:
    """True when every index in ``range(total_chunks)`` has been received."""
    have = normalize_received(received)
    return all(i in have for i in range(total_chunks))


def add_chunk_index(received: object, chunk_index: int) -> tuple[list[int], bool]:
    """Idempotently add ``chunk_index`` to the received set.

    Returns:
        A tuple ``(new_sorted_list, was_duplicate)``. ``was_duplicate`` is
        True when ``chunk_index`` was already present, so the caller can
        treat the chunk write as a no-op replay.
    """
    have = normalize_received(received)
    duplicate = chunk_index in have
    have.add(chunk_index)
    return sorted(have), duplicate


@dataclass(frozen=True)
class IntegrityCheck:
    """Outcome of the final assemble-time integrity verification."""

    ok: bool
    reason: str | None = None


def verify_assembled(
    *,
    assembled_size: int,
    expected_size: int,
    computed_sha256: str | None,
    expected_sha256: str | None,
) -> IntegrityCheck:
    """Verify the assembled file's size and (optional) SHA-256.

    The size check is mandatory. The SHA-256 check runs only when the
    client supplied a hash at session creation; comparison is
    case-insensitive. Returns a structured result rather than raising so
    the service can map it to the right HTTP error.
    """
    if assembled_size != expected_size:
        return IntegrityCheck(
            ok=False,
            reason=(f"assembled size {assembled_size} != declared total_size {expected_size}"),
        )
    if expected_sha256 is not None:
        if computed_sha256 is None:
            return IntegrityCheck(ok=False, reason="missing computed checksum")
        if computed_sha256.lower() != expected_sha256.lower():
            return IntegrityCheck(ok=False, reason="sha256 mismatch")
    return IntegrityCheck(ok=True)
