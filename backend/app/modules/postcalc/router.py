# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Post-calculation API routes.

Mounted at ``/api/v1/postcalc``. One read-only endpoint that reconciles a
project's estimate against its site actuals into a planned-vs-actual productivity
report:

    GET /projects/{project_id}/productivity?format=json|markdown

``format=json`` (default) returns the full structured report; ``format=markdown``
returns the same numbers as an auditable Markdown document. Optional ``tolerance``
(the on-plan band, default 0.05) and ``min_confidence`` (the installed-coverage
floor for a feedback factor, default 0.10) tune the analysis. Reads need viewer
access to the project, and access is verified first so a caller can never read the
productivity of a project they cannot see.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.postcalc.service import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_TOLERANCE,
    PostCalcService,
)

router = APIRouter()

_READ = Depends(RequirePermission("postcalc.read"))

_MARKDOWN_FORMATS = frozenset({"markdown", "md"})


@router.get(
    "/projects/{project_id}/productivity",
    response_model=None,
    dependencies=[_READ],
)
async def get_productivity(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    fmt: str = Query(default="json", alias="format", description="json (default) or markdown"),
    tolerance: float | None = Query(default=None, ge=0, le=1, description="On-plan band, e.g. 0.05 for 5%"),
    min_confidence: float | None = Query(
        default=None,
        ge=0,
        le=1,
        description="Installed-coverage floor for a feedback factor, e.g. 0.10",
    ),
) -> Response | dict:
    """Planned-vs-actual labour productivity for a project, as JSON or Markdown."""
    await verify_project_access(project_id, user_id, session)

    tol = Decimal(str(tolerance)) if tolerance is not None else DEFAULT_TOLERANCE
    conf = Decimal(str(min_confidence)) if min_confidence is not None else DEFAULT_MIN_CONFIDENCE
    service = PostCalcService(session)

    if fmt.strip().lower() in _MARKDOWN_FORMATS:
        body = await service.render_markdown(project_id, tolerance=tol, min_confidence=conf)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'inline; filename="postcalc-{project_id}.md"'},
        )

    report = await service.generate(project_id, tolerance=tol, min_confidence=conf)
    return report.to_dict()
