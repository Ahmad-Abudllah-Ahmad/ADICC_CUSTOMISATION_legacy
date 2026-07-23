# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the AI accuracy scoreboard endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class AIFeedbackIn(BaseModel):
    """A correct / incorrect verdict on any AI output in the app.

    Generic counterpart to :class:`RecordOutcomeIn`: where that one scores a
    persisted agent *run*, this records a verdict on an AI surface that has no
    run row (the AI Estimator result, a match suggestion, an advisor answer).
    """

    # Which AI surface the verdict is about (short slug, e.g. "ai_estimator").
    surface: str = Field(min_length=1, max_length=40)
    # The verdict: did this AI output turn out correct?
    correct: bool
    # Optional project scope - verified against the caller's access on write.
    project_id: uuid.UUID | None = None
    # Opaque pointer to the specific output (run / session / message id, ...).
    ref: str | None = Field(default=None, max_length=200)
    # Optional short correction / context note.
    note: str | None = Field(default=None, max_length=2000)


class AIFeedbackOut(BaseModel):
    """Acknowledgement that a piece of AI feedback was recorded."""

    id: str
    surface: str
    correct: bool


class SurfaceFeedbackOut(BaseModel):
    """Verdict rollup for one AI surface (correct_rate is null when no verdicts)."""

    model_config = ConfigDict(from_attributes=True)

    surface: str
    total: int
    correct: int
    incorrect: int
    correct_rate: float | None


class AIFeedbackSummaryOut(BaseModel):
    """The caller's AI feedback verdicts rolled up overall and per surface."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    correct: int
    incorrect: int
    correct_rate: float | None
    by_surface: list[SurfaceFeedbackOut]


class RecordOutcomeIn(BaseModel):
    """Request body recording whether an agent run turned out correct."""

    correct: bool
    note: str | None = None


class OutcomeRecordedOut(BaseModel):
    """Acknowledgement that an outcome was recorded on a run."""

    run_id: str
    agent_name: str
    actual_outcome: bool


class CalibrationBinOut(BaseModel):
    """One reliability bucket over the confidence range."""

    model_config = ConfigDict(from_attributes=True)

    lower: float
    upper: float
    count: int
    mean_confidence: float
    observed_rate: float


class AccuracyScoreOut(BaseModel):
    """Aggregate accuracy and calibration summary for one agent."""

    model_config = ConfigDict(from_attributes=True)

    agent_name: str
    count: int
    brier_score: float
    mean_confidence: float
    observed_rate: float
    calibration_error: float
    bins: list[CalibrationBinOut]


class AccuracyScoreboardOut(BaseModel):
    """The accuracy scoreboard: one score per agent the caller has run."""

    scores: list[AccuracyScoreOut]


class SandboxSeedOut(BaseModel):
    """Result of seeding the demo sandbox with sample scored agent runs."""

    # How many runs this call created (0 when they already existed - the seed
    # is idempotent), the total sample-run count, and the distinct agent names.
    created: int
    total: int
    agents: list[str]
