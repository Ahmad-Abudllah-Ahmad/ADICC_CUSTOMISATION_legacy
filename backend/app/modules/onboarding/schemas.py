# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request/response schemas for the onboarding provisioning API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProvisionRequest(BaseModel):
    """What the wizard wants provisioned in the background.

    The list is intentionally open to growth (vectorization, converter install)
    without a breaking change; today the two heavy first-run blockers are the
    regional cost base import and the sample project install.
    """

    region: str | None = Field(
        default=None,
        description="Regional cost base id to import, e.g. 'TR_TRY'. None to skip.",
    )
    demo_ids: list[str] = Field(
        default_factory=list,
        description="Sample project ids to install.",
    )


class JobState(BaseModel):
    """One background provisioning job's live state, safe to expose to its owner."""

    id: str
    kind: str
    arg: str | None = None
    state: str = Field(description="pending | started | success | failed | cancelled")
    pct: int = 0
    message: str | None = None
    error: str | None = None


class ProvisionResponse(BaseModel):
    """The jobs kicked off (or reused) by a provision call."""

    jobs: list[JobState] = Field(default_factory=list)


class StatusRequest(BaseModel):
    """Poll the state of previously provisioned jobs by their ids."""

    ids: list[str] = Field(
        default_factory=list,
        description="Job ids returned by /provision.",
    )


class StatusResponse(BaseModel):
    """Live state for the caller's provisioning jobs."""

    jobs: list[JobState] = Field(default_factory=list)
