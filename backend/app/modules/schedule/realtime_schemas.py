# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic request/response schemas for schedule real-time collaboration (T3.4).

Deliberately NOT named ``schemas.py``: this file carries no money fields (a
guarded activity patch and a revision token only), and keeping the name distinct
sidesteps the money-Decimal guard that scans ``schemas.py`` files. Dependency
free (pydantic + stdlib) so it imports cleanly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GuardedActivityUpdate(BaseModel):
    """An optimistic-concurrency guarded patch of a single activity.

    ``base_revision`` is the revision the client last read. ``None`` is the
    documented force / first-write escape hatch (the client did not track a
    base) and applies unconditionally at ``server + 1``. ``fields`` is the patch
    body; the service validates every key against an editable-field allowlist
    and rejects unknown keys with 422, so ``extra`` here stays permissive only
    at the envelope level.
    """

    model_config = ConfigDict(extra="forbid")

    base_revision: int | None = Field(default=None, ge=0)
    fields: dict[str, Any] = Field(default_factory=dict)


class GuardedUpdateResponse(BaseModel):
    """Result of an applied (or no-op) guarded update.

    ``activity`` is the serialised current activity; ``revision`` is its
    revision after the call (bumped on APPLY, unchanged on NOOP).
    """

    activity: dict[str, Any]
    revision: int


class RevisionConflict(BaseModel):
    """Body of the 409 returned when the client's base revision is stale.

    Carries the authoritative current revision plus the full current activity
    state so the client can rebase its edit without a second round-trip.
    """

    detail: str = "Activity was modified by another user"
    current_revision: int
    current_state: dict[str, Any]


class ActivityRevisionResponse(BaseModel):
    """The current optimistic-concurrency revision of an activity."""

    activity_id: UUID
    revision: int


class PresenceUser(BaseModel):
    """One connected co-editor in a schedule presence room."""

    user_id: str
    user_name: str


class SchedulePresenceResponse(BaseModel):
    """A REST snapshot of who is currently connected to a schedule room."""

    schedule_id: UUID
    users: list[PresenceUser] = Field(default_factory=list)
