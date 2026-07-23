# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Matchers - vector + lexical for Phase A; LLM rerank planned.

Each matcher implements :class:`Matcher` and returns a ranked list of
:class:`MatchCandidate` for a given :class:`ElementEnvelope`. The
match-elements service runs one or more matchers per group on demand
and caches per-method results in the group's ``methods`` JSON column.
"""

from app.modules.match_elements.matchers.base import Matcher, MatcherName

__all__ = ["Matcher", "MatcherName"]
