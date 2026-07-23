# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure portfolio-tree pruning (T3.3).

Dependency-free (stdlib only) so it imports and unit-tests on the local runner.
Given the flat node + membership rows and the caller's accessible project set,
it builds the nested, access-pruned tree:

* ``accessible is None`` => admin: every node is visible.
* otherwise a node is visible iff its subtree contains at least one accessible
  project; a node whose every project (across its whole subtree) is
  inaccessible is omitted entirely - so a user never even sees the *label* of a
  node that holds only projects they cannot reach.

Visibility is monotonic up the tree (any ancestor of a visible membership is
itself visible), so pruning never orphans a visible node. The tree never widens
access: ``project_ids`` on each returned node lists only the accessible direct
memberships.
"""

from __future__ import annotations

from typing import Any


def _sort_key(node: dict[str, Any]) -> tuple[int, str]:
    return (node.get("sort_order", 0) or 0, str(node.get("name", "")))


def build_visible_tree(
    nodes: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    accessible: set[str] | None,
) -> list[dict[str, Any]]:
    """Build the access-pruned nested portfolio tree.

    Args:
        nodes: flat node rows, each ``{id, parent_id, node_type, name, code,
            sort_order}`` with string ids (``parent_id`` may be ``None``).
        memberships: ``{node_id, project_id}`` rows with string ids.
        accessible: the caller's accessible project-id set, or ``None`` for an
            admin (everything visible).

    Returns:
        A list of root node dicts, each with a ``children`` list and a
        ``project_ids`` list of its accessible direct memberships.
    """
    by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in nodes}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for n in nodes:
        parent = n.get("parent_id")
        # An orphan (parent deleted -> SET NULL left a dangling ref) is a root.
        if parent is not None and parent not in by_id:
            parent = None
        children.setdefault(parent, []).append(n)

    direct: dict[str, list[str]] = {}
    for m in memberships:
        pid = m["project_id"]
        if accessible is None or pid in accessible:
            direct.setdefault(m["node_id"], []).append(pid)

    visible: dict[str, bool] = {}

    def visit(node_id: str, seen: set[str]) -> bool:
        if node_id in seen:  # cycle guard (DB is acyclic, but stay safe)
            return False
        seen.add(node_id)
        child_visible = False
        for child in children.get(node_id, []):
            if visit(child["id"], seen):
                child_visible = True
        is_visible = (accessible is None) or bool(direct.get(node_id)) or child_visible
        visible[node_id] = is_visible
        return is_visible

    roots = sorted(children.get(None, []), key=_sort_key)
    for root in roots:
        visit(root["id"], set())

    def build(node_id: str) -> dict[str, Any]:
        node = by_id[node_id]
        kids = [build(c["id"]) for c in sorted(children.get(node_id, []), key=_sort_key) if visible.get(c["id"])]
        return {
            "id": node_id,
            "parent_id": node.get("parent_id") if node.get("parent_id") in by_id else None,
            "node_type": node.get("node_type"),
            "name": node.get("name"),
            "code": node.get("code", ""),
            "sort_order": node.get("sort_order", 0) or 0,
            "project_ids": sorted(direct.get(node_id, [])),
            "children": kids,
        }

    return [build(r["id"]) for r in roots if visible.get(r["id"])]
