# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BIM scorecard service - async orchestration around the pure scorecard.

Loads a model's elements and its persisted validation history, then delegates
to the pure, DB-free builders in :mod:`app.modules.validation.bim_scorecard`:

* :func:`build_bim_scorecard` turns the currently-loaded elements into a
  composite maturity scorecard (facet sub-scores + overall grade + element
  drill-down).
* :func:`assemble_score_trend` turns the existing ``ValidationReport`` rows for
  the model into a version-over-version score series.

This service adds NO new storage. The trend is read straight from the reports
that ``BIMValidationService.validate_bim_model`` already persists per run, so a
scorecard read is side-effect free (it never writes a report).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bim_hub.repository import BIMElementRepository, BIMModelRepository
from app.modules.validation.bim_scorecard import (
    assemble_score_trend,
    build_bim_scorecard,
)
from app.modules.validation.repository import ValidationReportRepository

# Match the per-model element load ceiling used by BIMValidationService.
_ELEMENT_LOAD_LIMIT = 1_000_000
# Cap the number of historical reports pulled for the trend series.
_TREND_HISTORY_LIMIT = 200

BIM_MODEL_TARGET_TYPE = "bim_model"


class BIMScorecardService:
    """Build a maturity scorecard + score trend for a BIM model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.model_repo = BIMModelRepository(session)
        self.element_repo = BIMElementRepository(session)
        self.report_repo = ValidationReportRepository(session)

    async def get_scorecard(
        self,
        model_id: uuid.UUID,
        *,
        expected_disciplines: list[str] | None = None,
        rule_ids: list[str] | None = None,
        include_trend: bool = True,
    ) -> dict[str, Any]:
        """Compute the composite scorecard (and, by default, the score trend).

        Args:
            model_id: Target BIM model UUID.
            expected_disciplines: Optional override of the expected discipline
                set for the coverage facet.
            rule_ids: Optional subset of universal rule ids for the property
                completeness facet.
            include_trend: When True, also assemble the version trend from the
                model's persisted report history.

        Returns:
            A JSON-serialisable dict with ``model``, ``scorecard`` and (when
            requested) ``trend`` keys.

        Raises:
            ValueError: If the referenced BIM model does not exist.
        """
        model = await self.model_repo.get(model_id)
        if model is None:
            msg = f"BIM model {model_id} not found"
            raise ValueError(msg)

        elements, total = await self.element_repo.list_for_model(
            model_id,
            offset=0,
            limit=_ELEMENT_LOAD_LIMIT,
        )

        scorecard = build_bim_scorecard(
            elements,
            expected_disciplines=expected_disciplines,
            rule_ids=rule_ids,
            model_id=str(model_id),
            model_name=model.name,
        )

        payload: dict[str, Any] = {
            "model": {
                "id": str(model_id),
                "name": model.name,
                "project_id": str(model.project_id),
                "version": model.version,
                "element_count": total,
            },
            "scorecard": scorecard.to_dict(),
        }
        if include_trend:
            trend = await self._build_trend(model_id)
            payload["trend"] = trend.to_dict()
        return payload

    async def get_trend(self, model_id: uuid.UUID) -> dict[str, Any]:
        """Return only the version-over-version score trend for a model.

        Raises:
            ValueError: If the referenced BIM model does not exist.
        """
        model = await self.model_repo.get(model_id)
        if model is None:
            msg = f"BIM model {model_id} not found"
            raise ValueError(msg)
        trend = await self._build_trend(model_id)
        return {
            "model": {
                "id": str(model_id),
                "name": model.name,
                "project_id": str(model.project_id),
            },
            "trend": trend.to_dict(),
        }

    async def _build_trend(self, model_id: uuid.UUID) -> Any:
        """Assemble the score trend from the model's persisted reports."""
        reports = await self.report_repo.list_for_target(
            BIM_MODEL_TARGET_TYPE,
            str(model_id),
            limit=_TREND_HISTORY_LIMIT,
        )
        return assemble_score_trend(
            reports,
            target_type=BIM_MODEL_TARGET_TYPE,
            target_id=str(model_id),
        )
