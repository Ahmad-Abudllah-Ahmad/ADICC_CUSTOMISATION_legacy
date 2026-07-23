# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resumable Uploads business logic.

The service owns the session lifecycle: create, accept-chunk (idempotent),
report status, complete (assemble + integrity + hand-off to the document
store), abort, and a GC sweep for stale sessions. All chunk math lives in
:mod:`app.modules.resumable_uploads.chunking` so it can be unit-tested
without a DB; this layer wires that math to the ORM and the filesystem.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.modules.resumable_uploads import chunk_store
from app.modules.resumable_uploads.chunking import (
    ChunkValidationError,
    add_chunk_index,
    compute_total_chunks,
    is_complete,
    missing_chunks,
    validate_chunk,
    verify_assembled,
)
from app.modules.resumable_uploads.models import ResumableUploadSession
from app.modules.resumable_uploads.repository import ResumableUploadRepository
from app.modules.resumable_uploads.schemas import (
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNK_SIZE,
    MAX_TOTAL_CHUNKS,
    MAX_TOTAL_SIZE,
    MIN_CHUNK_SIZE,
)

logger = logging.getLogger(__name__)

# How long an in-flight session lives before the GC sweep may reap it. A
# day is generous enough for a human to resume across a laptop sleep yet
# short enough that abandoned scratch chunks do not accumulate.
SESSION_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


class ResumableUploadService:
    """Session lifecycle for chunked, resumable uploads."""

    def __init__(self, session: object) -> None:
        # ``session`` is an AsyncSession in production; tests pass a stub.
        self.session = session
        self.repo = ResumableUploadRepository(session)  # type: ignore[arg-type]

    # ── Create ──────────────────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        project_id: uuid.UUID,
        filename: str,
        total_size: int,
        chunk_size: int | None,
        category: str,
        sha256: str | None,
        user_id: str,
    ) -> ResumableUploadSession:
        """Open a new upload session and return the persisted row.

        Bounds are re-asserted here (the schema validates them too) so the
        service is safe to call directly from tests and future internal
        callers without a request layer. ``chunk_size`` defaults to
        :data:`DEFAULT_CHUNK_SIZE` and is clamped into the allowed range.
        """
        from app.modules.documents.service import _sanitize_filename

        if total_size <= 0 or total_size > MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"total_size must be in (0, {MAX_TOTAL_SIZE}] bytes",
            )

        size = chunk_size or DEFAULT_CHUNK_SIZE
        if size < MIN_CHUNK_SIZE or size > MAX_CHUNK_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"chunk_size must be in [{MIN_CHUNK_SIZE}, {MAX_CHUNK_SIZE}] bytes",
            )

        total_chunks = compute_total_chunks(total_size, size)
        if total_chunks > MAX_TOTAL_CHUNKS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"chunk_size {size} yields {total_chunks} chunks (max {MAX_TOTAL_CHUNKS}); use a larger chunk_size"
                ),
            )

        safe_name = _sanitize_filename(filename)
        record = ResumableUploadSession(
            project_id=project_id,
            filename=safe_name,
            category=category or "other",
            total_size=total_size,
            chunk_size=size,
            total_chunks=total_chunks,
            received_chunks=[],
            sha256=(sha256.lower() if sha256 else None),
            status="in_progress",
            created_by=str(user_id or ""),
            expires_at=_now() + SESSION_TTL,
        )
        return await self.repo.add(record)

    # ── Lookup ──────────────────────────────────────────────────────────────

    async def get_session(self, session_id: uuid.UUID) -> ResumableUploadSession:
        """Return a session row or raise 404.

        404 (never 403) for a missing OR cross-tenant session keeps the
        surface symmetric with the rest of the platform's IDOR contract;
        the caller verifies ``project_id`` access after this returns.
        """
        record = await self.repo.get_by_id(session_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload session not found",
            )
        return record

    # ── Accept a chunk (idempotent) ─────────────────────────────────────────

    async def accept_chunk(
        self,
        record: ResumableUploadSession,
        chunk_index: int,
        data: bytes,
    ) -> tuple[ResumableUploadSession, bool]:
        """Store one chunk; re-uploading an already-received chunk is a no-op.

        Returns ``(record, was_duplicate)``. Validation rejects an
        out-of-range index or a chunk whose byte length does not match the
        size the session contract demands for that index.
        """
        if record.status not in ("in_progress",):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"session is '{record.status}', not accepting chunks",
            )

        try:
            validate_chunk(
                chunk_index,
                len(data),
                total_size=record.total_size,
                chunk_size=record.chunk_size,
                total_chunks=record.total_chunks,
            )
        except ChunkValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        new_received, duplicate = add_chunk_index(record.received_chunks, chunk_index)
        if duplicate:
            # Idempotent replay: the chunk is already on disk and already
            # tracked. Do not rewrite or error; just acknowledge.
            return record, True

        chunk_store.write_chunk(record.id, chunk_index, data)
        # Reassign (not in-place mutate) so SQLAlchemy detects the change.
        record.received_chunks = new_received
        await self.repo.save(record)
        return record, False

    # ── Status ──────────────────────────────────────────────────────────────

    def missing(self, record: ResumableUploadSession) -> list[int]:
        """Return the chunk indices still missing for ``record``."""
        return missing_chunks(record.received_chunks, record.total_chunks)

    # ── Complete (assemble + integrity + hand-off) ──────────────────────────

    async def complete_session(
        self,
        record: ResumableUploadSession,
        *,
        document_service: object,
        user_id: str,
    ) -> ResumableUploadSession:
        """Assemble the chunks and hand the file to the document store.

        Steps:
            1. Require every chunk to be present (else 409 with the missing
               list so the client can resume).
            2. Stream-assemble into a temp file, computing SHA-256.
            3. Verify assembled size (always) and SHA-256 (when the client
               supplied one). A mismatch fails the session and rejects.
            4. Wrap the assembled file in an ``UploadFile`` and call the
               EXISTING ``DocumentService.upload_document`` so it flows
               through the same magic-byte gate, storage, events, version
               chain, and conversion pipeline as a single-shot upload.
            5. Record the resulting document id + storage key and clean up
               the scratch chunks.
        """
        if record.status == "complete" and record.document_id is not None:
            # Idempotent completion replay - the file is already stored.
            return record
        if record.status not in ("in_progress",):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"session is '{record.status}', cannot complete",
            )

        if not is_complete(record.received_chunks, record.total_chunks):
            missing = missing_chunks(record.received_chunks, record.total_chunks)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "upload incomplete",
                    "missing_chunks": missing,
                },
            )

        record.status = "assembling"
        await self.repo.save(record)

        tmp_fd, tmp_name = tempfile.mkstemp(prefix="oe_assembled_", suffix=".bin")
        # Close the low-level fd; chunk_store.assemble reopens by path.
        os.close(tmp_fd)
        assembled_path = Path(tmp_name)
        try:
            assembled_size, computed_sha = chunk_store.assemble(
                record.id,
                record.total_chunks,
                assembled_path,
            )

            check = verify_assembled(
                assembled_size=assembled_size,
                expected_size=record.total_size,
                computed_sha256=computed_sha,
                expected_sha256=record.sha256,
            )
            if not check.ok:
                record.status = "failed"
                await self.repo.save(record)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"integrity check failed: {check.reason}",
                )

            # Hand off to the existing document pipeline. Reading the
            # assembled file into an UploadFile matches the single-shot
            # path, which itself does ``await file.read()`` of the whole
            # body; we do not fork the conversion path.
            with assembled_path.open("rb") as fh:
                buffer = io.BytesIO(fh.read())
            upload = UploadFile(filename=record.filename, file=buffer)
            document = await document_service.upload_document(  # type: ignore[attr-defined]
                record.project_id,
                upload,
                record.category,
                user_id,
            )

            record.status = "complete"
            record.document_id = document.id
            record.storage_key = str(getattr(document, "file_path", "") or "")
            await self.repo.save(record)
        finally:
            assembled_path.unlink(missing_ok=True)
            # Drop the scratch chunks regardless of success - on failure the
            # client must re-create the session; on success they are no
            # longer needed.
            chunk_store.cleanup(record.id)

        return record

    # ── Abort ───────────────────────────────────────────────────────────────

    async def abort_session(self, record: ResumableUploadSession) -> None:
        """Delete a session row and its scratch chunks."""
        chunk_store.cleanup(record.id)
        await self.repo.remove(record)

    # ── GC ──────────────────────────────────────────────────────────────────

    async def gc_expired(self, *, terminal_retention: timedelta = timedelta(days=7)) -> int:
        """Reap stale in-flight sessions and prune old terminal rows.

        In-flight sessions past their ``expires_at`` are flipped to
        ``expired`` and their scratch chunks removed. Terminal rows older
        than ``terminal_retention`` are hard-deleted. Returns the number of
        in-flight sessions expired in this sweep.
        """
        now = _now()
        expired = await self.repo.list_expired(now=now)
        for record in expired:
            chunk_store.cleanup(record.id)
            record.status = "expired"
        if expired:
            await self.repo.save(expired[0])
        await self.repo.delete_terminal_before(cutoff=now - terminal_retention)
        return len(expired)
