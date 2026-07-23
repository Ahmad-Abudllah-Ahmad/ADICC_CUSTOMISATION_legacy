# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Schemas for the resource-aware leveling *preview* (T3.1).

The preview is the headline differentiator: it honours all four PDM link types
(SS/FF/SF, not just FS), supports splittable activities, reports single-activity
self-overloads explicitly, and - crucially - returns the honest finish-date
impact computed from a copy of the network, before anything is committed. The
arithmetic lives in the pure :mod:`app.modules.resources.resource_engine`.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LevelPreviewRequest(BaseModel):
    """Inputs for a resource-leveling preview."""

    model_config = ConfigDict(extra="forbid")

    # ``{resource_code: max_concurrent_units}``; resources absent are unconstrained.
    resource_limits: dict[str, float] = Field(default_factory=dict)
    # Activity ids that may be split into multiple day-runs to fit a ceiling.
    splittable: list[UUID] = Field(default_factory=list)


class LevelPreviewShift(BaseModel):
    """One activity whose early start moved under leveling."""

    activity_id: UUID
    base_es: int
    new_es: int
    delta: int


class LevelPreviewSegmentRun(BaseModel):
    """One placed day-run of a split activity (work-day indices)."""

    start: int
    finish: int


class LevelPreviewSegment(BaseModel):
    """A splittable activity placed across multiple day-runs."""

    activity_id: UUID
    runs: list[LevelPreviewSegmentRun] = Field(default_factory=list)


class LevelPreviewUnresolvable(BaseModel):
    """A single-activity self-overload leveling cannot clear by shifting."""

    activity_id: UUID
    resource: str
    required: float
    limit: float


class LevelPreviewResponse(BaseModel):
    """Read-only leveling preview with the honest finish-date impact."""

    schedule_id: UUID
    num_shifted: int
    finish_delta_days: int
    base_finish_workday: int
    leveled_finish_workday: int
    shifts: list[LevelPreviewShift] = Field(default_factory=list)
    segments: list[LevelPreviewSegment] = Field(default_factory=list)
    unresolvable: list[LevelPreviewUnresolvable] = Field(default_factory=list)
    peak_before: dict[str, float] = Field(default_factory=dict)
    peak_after: dict[str, float] = Field(default_factory=dict)


class LevelApplyResponse(BaseModel):
    """Result of committing a leveling run to the schedule.

    Runs the same pure leveling arithmetic as the preview, then persists each
    shifted activity's ``start_date`` / ``end_date`` (moved by the activity's
    leveling delta in calendar days, preserving its span). ``num_applied`` counts
    rows actually written; ``num_skipped`` counts shifted activities whose stored
    dates could not be parsed and so were left untouched.
    """

    schedule_id: UUID
    num_shifted: int
    num_applied: int
    num_skipped: int
    finish_delta_days: int
    base_finish_workday: int
    leveled_finish_workday: int
