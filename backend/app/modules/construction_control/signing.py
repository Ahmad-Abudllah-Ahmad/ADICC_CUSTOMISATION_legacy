# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Non-repudiation helpers for construction-control attestations.

The as-built legal-record attestation (Pillar 3) and the gate release (Pillar 5) each
capture an e-signature: a SHA-256 digest over a canonical snapshot of the record at the
moment of signing, plus the signer and their IP. The digest is computed over a stable,
sorted JSON serialisation so the same snapshot always hashes identically regardless of
key insertion order - mirroring the QMS signature pattern.
"""

import hashlib
import json
from typing import Any


def canonical_snapshot(snapshot: dict[str, Any]) -> str:
    """Serialise a snapshot to canonical JSON (sorted keys, compact separators)."""
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)


def snapshot_sha256(snapshot: dict[str, Any]) -> str:
    """SHA-256 hex digest over the canonical snapshot. Deterministic for equal snapshots."""
    return hashlib.sha256(canonical_snapshot(snapshot).encode("utf-8")).hexdigest()
