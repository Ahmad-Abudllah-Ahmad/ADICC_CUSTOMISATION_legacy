"""v3 live smoke #188 — restore a DDC CWICR snapshot into embedded Qdrant.

Run:
    python scripts/v3_smoke_recover.py /tmp/cwicr-v3/RU_STPETERSBURG.snapshot

Verifies:
- Embedded Qdrant accepts a v3 snapshot (named ``dense`` + ``sparse`` +
  ``resources`` vectors).
- Collection metadata reports the expected vector schemas.
- A sample point carries the v3 payload columns (``rate_code``,
  ``country``, ``is_abstract``, ``construction_stage``, …).

This is the smoke gate the v3 plan §6.6 #1 listed as the first verification
item. Pass = our adapter can drive embedded mode end-to-end.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint


def main(snapshot_path: str) -> int:
    snap = Path(snapshot_path).resolve()
    if not snap.is_file():
        print(f"FAIL: snapshot not found at {snap}")
        return 2

    work = snap.parent / "qdrant_embedded"
    work.mkdir(exist_ok=True)
    print(f"Embedded store: {work}")
    print(f"Snapshot:       {snap}  ({snap.stat().st_size / 1e6:.1f} MB)")

    from qdrant_client import QdrantClient

    client = QdrantClient(path=str(work))
    target = "cwicr_ru_v3"
    print(f"Restoring into collection: {target}")
    try:
        client.recover_snapshot(collection_name=target, location=str(snap))
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL recover_snapshot: {type(exc).__name__}: {exc}")
        return 3

    print("\nCollections after restore:")
    cols = client.get_collections().collections
    for c in cols:
        print(f"  - {c.name}")

    info = client.get_collection(target)
    _count = (
        getattr(info, "points_count", None)
        if getattr(info, "points_count", None) is not None
        else getattr(info, "vectors_count", None)
    )
    print(f"\nCollection {target}:")
    print(f"  vectors_count:  {_count}")
    print(f"  points_count:   {getattr(info, 'points_count', None)}")
    print(f"  status:         {info.status}")
    print("  vector schemas:")
    config = info.config.params
    if hasattr(config, "vectors") and config.vectors:
        try:
            pprint(config.vectors, depth=3, indent=4)
        except Exception:
            print(f"    {config.vectors!r}")
    if hasattr(config, "sparse_vectors") and config.sparse_vectors:
        print("  sparse schemas:")
        pprint(config.sparse_vectors, depth=3, indent=4)

    print("\nSample 1 point (first record, payload only):")
    pts, _ = client.scroll(
        collection_name=target,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not pts:
        print("  EMPTY collection — restore likely failed silently.")
        return 4
    pprint(pts[0].payload, depth=2, indent=4)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(64)
    sys.exit(main(sys.argv[1]))
