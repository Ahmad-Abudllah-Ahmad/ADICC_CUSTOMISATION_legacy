# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Matcher protocol - uniform interface for vector / lexical / LLM."""

from __future__ import annotations

import uuid
from typing import Literal, Protocol

from app.core.match_service.envelope import ElementEnvelope, MatchCandidate

MatcherName = Literal["vector", "lexical", "llm"]


class Matcher(Protocol):
    """Protocol every matcher implements."""

    name: MatcherName

    async def rank(
        self,
        *,
        envelope: ElementEnvelope,
        project_id: uuid.UUID,
        catalogue_id: uuid.UUID | None,
        top_k: int = 10,
    ) -> list[MatchCandidate]:
        """Return top-k CWICR candidates ranked by this matcher's score."""
        ...
