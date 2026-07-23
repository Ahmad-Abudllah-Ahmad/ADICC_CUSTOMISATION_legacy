# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Vector matcher - wraps the existing ``match_service`` ranker.

The match-elements service calls this when the user clicks "Run vector
match" on a group. The underlying ranker handles translation cascade,
LanceDB embedding lookup, classification boosts and unit boosts.

The ``use_reranker`` knob is OFF here - that's the LLM tier, gated to
Phase A.5+ behind an explicit toggle so we don't burn tokens on bulk
runs.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.match_service import match_envelope
from app.core.match_service.envelope import ElementEnvelope, MatchCandidate


class VectorMatcher:
    name = "vector"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rank(
        self,
        *,
        envelope: ElementEnvelope,
        project_id: uuid.UUID,
        catalogue_id: uuid.UUID | None = None,  # noqa: ARG002 - reserved
        top_k: int = 10,
    ) -> list[MatchCandidate]:
        response = await match_envelope(
            envelope,
            project_id=project_id,
            top_k=top_k,
            use_reranker=False,
            db=self.session,
        )
        return list(response.candidates)
