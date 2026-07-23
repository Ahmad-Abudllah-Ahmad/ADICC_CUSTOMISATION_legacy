# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ Excel/CSV round-trip diff (GitHub #360).

Pure, dependency-free decision layer for a faithful export -> edit ->
re-import cycle. Given the rows parsed out of a previously exported (and
possibly hand-edited) spreadsheet, plus the set of position ids that
currently live in the *target* BOQ, it decides for every row whether it

* UPDATES an existing position in place (its id column still holds an id
  that belongs to this BOQ),
* CREATES a new position (the id column is blank - a row the user added),
* or carries a foreign / unknown / duplicate id, which is treated as a
  *new* row and flagged (never allowed to mutate a position outside this
  BOQ).

It also reports which of the BOQ's current positions were absent from the
sheet, so the route can (opt-in) delete them and can always tell the user
how many *would* be deleted.

The module is kept free of SQLAlchemy / FastAPI / Pydantic so it unit-tests
against plain data. The route layer feeds it a scoped id set (built solely
from ``list_all_for_boq(boq_id)``) which is the structural guarantee that a
cross-BOQ id can never be honoured as an update: only ids present in that
set are ever emitted as an ``update``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

# Header label written into the dedicated identity column of every export,
# plus the set of header spellings the importer recognises as that column.
# Keep the label stable - a downstream export/import must agree on it.
ID_COLUMN_HEADER = "Position ID"
ID_COLUMN_ALIASES: frozenset[str] = frozenset(
    {
        "position id",
        "position_id",
        "position-id",
        "id",
        "pos id",
        "pos. id",
        "uuid",
    }
)


def normalise_id(raw: Any) -> str | None:
    """Canonicalise an id cell to a comparable token, or ``None`` if blank.

    Strips whitespace and lowercases so a copy-pasted / re-cased id still
    matches. Returns ``None`` for a blank / empty cell (a brand-new row).

    Deliberately does NOT validate UUID shape: a non-empty but
    unrecognisable value is returned as-is (lowered) so the differ can flag
    it and treat it as a new row. It will not be present in the current-BOQ
    id set, so it can never update anything.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return text.lower()


@dataclass(slots=True, frozen=True)
class RoundTripRow:
    """One parsed spreadsheet row as seen by the differ.

    ``position_id`` is the RAW id-column value (may be blank, re-cased,
    malformed, or from another BOQ). ``row_index`` is the 1-based sheet row
    used only for user-facing messages. ``payload`` is the already-parsed
    field dict the route hands to the service; the differ never inspects it.
    """

    row_index: int
    position_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RoundTripAction:
    """A resolved create/update decision for one sheet row."""

    kind: Literal["create", "update"]
    row: RoundTripRow
    # Target position id for ``kind == "update"`` (a normalised token that
    # equals ``str(uuid)``); ``None`` for ``kind == "create"``.
    position_id: str | None = None


@dataclass(slots=True)
class RoundTripPlan:
    """Full resolved plan for one re-import."""

    updates: list[RoundTripAction] = field(default_factory=list)
    creates: list[RoundTripAction] = field(default_factory=list)
    # Actionable deletes - populated only when ``delete_missing=True``.
    deletes: list[str] = field(default_factory=list)
    # Every current-BOQ id absent from the sheet, ALWAYS populated so the
    # route can report "N would be deleted" even with the flag off.
    would_delete: list[str] = field(default_factory=list)
    # Per-row advisories (unknown id -> new, duplicate id -> new, ...).
    problems: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        """Headline counts for the import summary."""
        return {
            "updated": len(self.updates),
            "created": len(self.creates),
            "deleted": len(self.deletes),
            "would_delete": len(self.would_delete),
            "problems": len(self.problems),
        }


def diff_import_rows(
    rows: Iterable[RoundTripRow],
    current_position_ids: Iterable[str],
    *,
    delete_missing: bool = False,
) -> RoundTripPlan:
    """Resolve one re-import into create / update / delete actions.

    Args:
        rows: The parsed spreadsheet rows. Order is preserved but matching is
            purely by id, so reordering the sheet never changes the outcome.
        current_position_ids: ``str(id)`` of every position that currently
            belongs to the TARGET BOQ, and only that BOQ. This scoping is the
            guarantee that a foreign id can never update another BOQ.
        delete_missing: When ``True``, current positions not referenced by any
            row are queued for deletion; otherwise they are only reported via
            ``would_delete``.

    Returns:
        A :class:`RoundTripPlan`. Guarantees:

        * a row becomes an UPDATE only when its normalised id is present in
          ``current_position_ids``;
        * each current id is the update target of at most ONE row (any later
          duplicate is flagged and demoted to a create);
        * ``updates`` and ``creates`` together cover every input row exactly
          once.
    """
    current: set[str] = set()
    for cid in current_position_ids:
        token = normalise_id(cid)
        if token is not None:
            current.add(token)

    plan = RoundTripPlan()
    consumed: set[str] = set()

    for row in rows:
        token = normalise_id(row.position_id)
        if token is None:
            # Blank id -> a row the user added in Excel. Plain create.
            plan.creates.append(RoundTripAction(kind="create", row=row))
            continue
        if token not in current:
            # An id that does not belong to THIS BOQ: a stale paste, an id
            # from another BOQ / project, or garbage. NEVER update across the
            # boundary - import as a new row and flag it.
            plan.creates.append(RoundTripAction(kind="create", row=row))
            plan.problems.append(
                {
                    "row": row.row_index,
                    "position_id": str(row.position_id),
                    "severity": "warning",
                    "issue": "unknown_id",
                    "message": (
                        "Row carries an id that is not in this BOQ; imported as "
                        "a NEW position (an id from another BOQ can never "
                        "overwrite one here)."
                    ),
                }
            )
            continue
        if token in consumed:
            # A second row claims an id already matched above. Updating twice
            # would be silent last-write-wins; demote the duplicate to a new
            # row and flag it.
            plan.creates.append(RoundTripAction(kind="create", row=row))
            plan.problems.append(
                {
                    "row": row.row_index,
                    "position_id": str(row.position_id),
                    "severity": "warning",
                    "issue": "duplicate_id",
                    "message": (
                        "The same position id appears on more than one row; the "
                        "first updates in place, this one is imported as a NEW "
                        "position."
                    ),
                }
            )
            continue
        consumed.add(token)
        plan.updates.append(RoundTripAction(kind="update", row=row, position_id=token))

    # Deterministic order so reporting / tests are stable.
    missing = sorted(token for token in current if token not in consumed)
    plan.would_delete = missing
    if delete_missing:
        plan.deletes = list(missing)

    return plan
