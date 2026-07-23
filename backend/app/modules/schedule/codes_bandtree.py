# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure band-tree builder for the grouped activity grid (T2.3).

Dependency-free (stdlib only) so it imports and unit-tests on the local runner.
Takes per-combination counts from the database and collapses them into a
pre-ordered, banded tree whose band counts always sum to the total (an
unassigned activity falls into a ``(none)`` band).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

NONE_KEY = "__none__"


def group_key(value: Any) -> str | None:
    """Stringify a group-level column value into a stable band key.

    ``None`` (unassigned) stays ``None`` so it lands in the ``(none)`` band. The
    same function feeds both the PHASE 1 band keys and the PHASE 2 row paths, so
    a row always nests under its own band. A numeric UDF column comes back as a
    ``Decimal``; render it without the storage padding (``Decimal('5.0000')`` ->
    ``"5"``, ``Decimal('5.5000')`` -> ``"5.5"``) and never let the ``Decimal(..)``
    repr leak into a band label.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def build_band_tree(
    count_rows: list[tuple[tuple[str | None, ...], int]],
    n_levels: int,
    meta: dict[tuple[int, str], dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Collapse per-combination counts into a pre-ordered banded tree.

    Args:
        count_rows: ``[(level_keys, count), ...]`` where ``level_keys`` is a
            tuple of one key per group level (a string, or ``None`` for an
            unassigned / ``(none)`` band).
        n_levels: number of group levels.
        meta: optional ``{(level_index, key): {"label": .., "color": ..}}`` for
            display; a key with no meta uses the key itself as the label.

    Returns:
        ``(bands, total)`` - ``bands`` is the depth-first list of band dicts
        (``key`` / ``label`` / ``color`` / ``depth`` / ``count`` / ``path``),
        ``total`` is the sum of every leaf count (band counts always sum to it).
    """
    meta = meta or {}
    root: dict[str, Any] = {"count": 0, "children": {}}
    for level_keys, count in count_rows:
        root["count"] += count
        node = root
        for depth in range(n_levels):
            key = level_keys[depth] if depth < len(level_keys) else None
            child = node["children"].get(key)
            if child is None:
                child = {"count": 0, "children": {}}
                node["children"][key] = child
            child["count"] += count
            node = child

    def _label(depth: int, key: str | None) -> str:
        if key is None:
            return "(none)"
        return meta.get((depth, key), {}).get("label", key)

    def _color(depth: int, key: str | None) -> str:
        if key is None:
            return ""
        return meta.get((depth, key), {}).get("color", "")

    bands: list[dict[str, Any]] = []

    def _walk(node: dict[str, Any], depth: int, path: list[str]) -> None:
        items = sorted(
            node["children"].items(),
            key=lambda kv: (kv[0] is None, _label(depth, kv[0]).lower(), str(kv[0])),
        )
        for key, child in items:
            disp_key = NONE_KEY if key is None else str(key)
            new_path = [*path, disp_key]
            bands.append(
                {
                    "key": disp_key,
                    "label": _label(depth, key),
                    "color": _color(depth, key),
                    "depth": depth,
                    "count": child["count"],
                    "path": new_path,
                }
            )
            _walk(child, depth + 1, new_path)

    _walk(root, 0, [])
    return bands, root["count"]
