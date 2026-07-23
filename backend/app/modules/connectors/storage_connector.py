# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure framework for inbound document / storage connectors (roadmap item #26).

This module is deliberately **dependency-free**: it imports nothing from the
ORM, the DB engine, FastAPI or the rest of the app -- only the Python standard
library. That keeps the connector core a set of *pure*, IO-free functions and
dataclasses that can be unit-tested in isolation (and on Python 3.11 locally,
where importing a service module would otherwise pull in ``app.database`` and
require a live PostgreSQL cluster).

What it does
------------
Heterogeneous storage sources (a watched folder, an object store, a cloud
drive, an email-attachment drop) each describe their files with their own key
names and shapes. This framework:

* normalizes one raw listing entry into a canonical :class:`IncomingDocument`
  descriptor via :func:`normalize_entry` (alias mapping + coercion), and
* computes an idempotent :class:`SyncPlan` via :func:`compute_sync_plan`
  that partitions the incoming documents into *new*, *duplicate-content* and
  *already-known* buckets given what the system already stores.

The real filesystem / network adapters (which perform actual IO) subclass the
abstract :class:`StorageAdapter` later and are built by the integrator; the
only adapter here is :class:`InMemoryAdapter`, an IO-free stand-in used for
tests and as a reference implementation.

Determinism
-----------
No function reads the wall clock or uses randomness. Every input is passed
explicitly and ordering is fully specified, so results are reproducible:
re-running a sync after recording the previously-created ids and hashes yields
an empty ``to_create`` bucket (idempotency).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "IncomingDocument",
    "ALIAS_MAP",
    "normalize_entry",
    "hash_bytes",
    "is_within_base",
    "StorageAdapter",
    "InMemoryAdapter",
    "SyncPlan",
    "compute_sync_plan",
]


# ---------------------------------------------------------------------------
# Path containment
# ---------------------------------------------------------------------------


def is_within_base(base: Path, candidate: Path) -> bool:
    """Whether ``candidate`` is ``base`` itself or sits below it.

    Pure comparison of two paths: it does **no** IO and resolves nothing, so
    the caller is responsible for passing already-canonicalized (symlink-free)
    paths when it wants the check to be about real locations. Used to confine a
    watched-folder root to an allowlisted base directory so a source can never
    be pointed at, say, ``/etc`` or escape the base via ``..``.
    """
    return candidate == base or base in candidate.parents


# ---------------------------------------------------------------------------
# Alias mapping
# ---------------------------------------------------------------------------
#
# Map a *canonical* field name to the set of raw key spellings a source might
# use for it. Lookup is case-insensitive (raw keys are lower-cased first), and
# within a canonical field the first alias that is present in the raw entry
# wins (aliases are tried in the listed order).

ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "name": ("name", "filename", "title", "file_name"),
    "external_id": ("external_id", "id", "key", "path", "object_key"),
    "content_hash": (
        "content_hash",
        "hash",
        "etag",
        "checksum",
        "md5",
        "sha256",
    ),
    "size_bytes": ("size_bytes", "size", "bytes", "content_length"),
    "content_type": ("content_type", "mime", "mime_type", "type"),
    "modified_at": ("modified_at", "modified", "last_modified", "updated_at"),
    "folder": ("folder", "prefix", "directory"),
}

#: Every raw key that maps to *some* canonical field (used to decide which raw
#: keys are "known" and which spill into ``metadata``).
_ALIASED_KEYS: frozenset[str] = frozenset(alias for aliases in ALIAS_MAP.values() for alias in aliases)


# ---------------------------------------------------------------------------
# Canonical document descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncomingDocument:
    """A single inbound file, normalized to canonical fields.

    Frozen and hashable so descriptors can live in sets / be used as dict
    keys. ``metadata`` is a plain ``dict`` (so it is *not* part of equality /
    hashing -- two descriptors with the same canonical fields but different
    extra metadata compare equal and hash equal, which is what the sync plan
    wants).
    """

    external_id: str
    name: str
    content_hash: str
    size_bytes: int
    content_type: str
    source: str
    modified_at: str = ""
    folder: str = ""
    metadata: dict = field(default_factory=dict, compare=False, hash=False)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _as_text(value: object) -> str:
    """Coerce ``value`` to a stripped string; ``None`` -> ``""``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_int(value: object) -> int:
    """Best-effort coercion to a non-negative-ish int; bad / missing -> 0.

    Accepts ``int``, ``float`` and numeric strings (with surrounding
    whitespace). Booleans and anything non-numeric collapse to ``0`` so a
    junk ``size`` never crashes the pipeline.
    """
    if value is None:
        return 0
    # ``bool`` is a subclass of ``int``; a flag is not a size.
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # NaN / inf are not valid sizes.
        if value != value or value in (float("inf"), float("-inf")):
            return 0
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            try:
                f = float(text)
            except ValueError:
                return 0
            if f != f or f in (float("inf"), float("-inf")):
                return 0
            return int(f)
    return 0


def _normalize_hash(value: object) -> str:
    """Lower-case + strip a content hash; drop a surrounding ``"..."``.

    Object stores often quote ETags (``"d41d8cd9..."``) and may prefix a
    weak-validator marker (``W/"..."``). Normalize those away and lower-case
    the hex so equal bytes always produce an equal key. A missing hash stays
    ``""`` (never treated as a duplicate of another empty hash).
    """
    text = _as_text(value)
    if not text:
        return ""
    # Strip a weak-ETag prefix, then surrounding double quotes.
    if text[:2] in ("W/", "w/"):
        text = text[2:].strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text.lower()


def _lookup(raw_lower: Mapping[str, object], canonical: str) -> object:
    """Return the first present aliased value for ``canonical``, else ``None``."""
    for alias in ALIAS_MAP[canonical]:
        if alias in raw_lower:
            return raw_lower[alias]
    return None


def normalize_entry(raw: Mapping[str, object], *, source: str) -> IncomingDocument:
    """Normalize one raw listing entry into an :class:`IncomingDocument`.

    * Alias keys are mapped to canonical fields (case-insensitive on the key).
    * ``size_bytes`` is coerced to ``int`` (bad / missing -> ``0``).
    * ``content_hash`` is lower-cased / de-quoted; a missing hash stays ``""``.
    * ``external_id`` falls back to ``"<folder>/<name>"`` (or just ``name``)
      when no id-like key is present.
    * Any raw key that is *not* a recognised alias is preserved verbatim under
      ``metadata`` (original key spelling kept).
    """
    # Case-insensitive view of the raw keys. On a duplicate-after-lower-casing
    # collision (e.g. both ``Name`` and ``name``), last one wins -- which is
    # deterministic for a given input mapping order.
    raw_lower: dict[str, object] = {}
    casing: dict[str, str] = {}
    for key, value in raw.items():
        lk = key.lower() if isinstance(key, str) else str(key).lower()
        raw_lower[lk] = value
        casing[lk] = key if isinstance(key, str) else str(key)

    name = _as_text(_lookup(raw_lower, "name"))
    folder = _as_text(_lookup(raw_lower, "folder"))

    external_id = _as_text(_lookup(raw_lower, "external_id"))
    if not external_id:
        external_id = f"{folder}/{name}" if folder else name

    content_hash = _normalize_hash(_lookup(raw_lower, "content_hash"))
    size_bytes = _as_int(_lookup(raw_lower, "size_bytes"))
    content_type = _as_text(_lookup(raw_lower, "content_type"))
    modified_at = _as_text(_lookup(raw_lower, "modified_at"))

    # Unknown keys -> metadata, using the original key spelling.
    metadata: dict = {}
    for lk, value in raw_lower.items():
        if lk not in _ALIASED_KEYS:
            metadata[casing[lk]] = value

    return IncomingDocument(
        external_id=external_id,
        name=name,
        content_hash=content_hash,
        size_bytes=size_bytes,
        content_type=content_type,
        source=_as_text(source),
        modified_at=modified_at,
        folder=folder,
        metadata=metadata,
    )


def hash_bytes(data: bytes) -> str:
    """Return the lower-case SHA-256 hex digest of ``data``.

    A small helper so a real adapter can hash file *content* (after reading
    it) and feed the result straight into ``content_hash``; kept here so the
    hashing convention lives next to the normalizer and stays pure.
    """
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class StorageAdapter(ABC):
    """Abstract source of inbound documents.

    Concrete adapters (watched folder, object store, cloud drive, ...) own the
    IO and yield already-normalized :class:`IncomingDocument` instances from
    :meth:`list_documents`. They should set ``source_name`` to a short, stable
    identifier for the source so descriptors carry their provenance.
    """

    #: Short, stable identifier for this source (e.g. ``"watched-folder"``).
    source_name: str = ""

    @abstractmethod
    def list_documents(self) -> Iterable[IncomingDocument]:
        """Yield the current set of documents visible at this source."""
        raise NotImplementedError


class InMemoryAdapter(StorageAdapter):
    """IO-free adapter over a fixed list of raw entries.

    Stands in for real watched-folder / cloud-storage adapters in tests and as
    a reference implementation: it simply normalizes each supplied raw entry
    through :func:`normalize_entry`, tagging every descriptor with ``source``.
    """

    def __init__(self, entries: Sequence[Mapping[str, object]], *, source: str) -> None:
        self._entries: tuple[Mapping[str, object], ...] = tuple(entries)
        self.source_name = source

    def list_documents(self) -> Iterable[IncomingDocument]:
        for entry in self._entries:
            yield normalize_entry(entry, source=self.source_name)


# ---------------------------------------------------------------------------
# Sync plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncPlan:
    """The deterministic outcome of reconciling a listing with known state.

    Every incoming document lands in exactly one bucket. Within each bucket
    input order is preserved.
    """

    to_create: tuple[IncomingDocument, ...] = ()
    duplicate_content: tuple[IncomingDocument, ...] = ()
    already_known: tuple[IncomingDocument, ...] = ()

    @property
    def created_count(self) -> int:
        return len(self.to_create)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_content)

    @property
    def known_count(self) -> int:
        return len(self.already_known)

    @property
    def total_count(self) -> int:
        return self.created_count + self.duplicate_count + self.known_count

    @property
    def is_empty(self) -> bool:
        """True when nothing needs creating (no new content this run)."""
        return self.created_count == 0


def compute_sync_plan(
    incoming: Iterable[IncomingDocument],
    *,
    known_external_ids: Set[str],
    known_content_hashes: Set[str],
) -> SyncPlan:
    """Partition ``incoming`` into create / duplicate / already-known buckets.

    Rules, applied per document in input order:

    * If its ``external_id`` is already in ``known_external_ids`` (or was seen
      earlier in *this* run) -> ``already_known``.
    * Else if its ``content_hash`` is non-empty and is in
      ``known_content_hashes`` (or matches the hash of an earlier
      to-be-created document this run) -> ``duplicate_content`` (the same
      bytes arriving under a new id / name; do not re-create).
    * Else -> ``to_create``.

    An empty ``content_hash`` is never treated as duplicate content, so files
    whose hash is unknown are always created rather than silently merged.

    The function does not mutate its arguments. Feeding the same listing again
    after adding the just-created ids and hashes to the known sets yields an
    empty ``to_create`` bucket (idempotency).
    """
    create: list[IncomingDocument] = []
    duplicate: list[IncomingDocument] = []
    known: list[IncomingDocument] = []

    # Local copies so we never mutate the caller's sets, and so within-run
    # collisions (a second entry with an id/hash first seen this run) resolve
    # against what we have already decided to create.
    seen_ids: set[str] = set(known_external_ids)
    seen_hashes: set[str] = set(known_content_hashes)

    for doc in incoming:
        ext_id = doc.external_id
        if ext_id in seen_ids:
            known.append(doc)
            continue

        chash = doc.content_hash
        if chash and chash in seen_hashes:
            duplicate.append(doc)
            # An external_id seen only here still counts as known going
            # forward so a later exact-id repeat is classified consistently.
            seen_ids.add(ext_id)
            continue

        create.append(doc)
        seen_ids.add(ext_id)
        if chash:
            seen_hashes.add(chash)

    return SyncPlan(
        to_create=tuple(create),
        duplicate_content=tuple(duplicate),
        already_known=tuple(known),
    )
