# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Document-level per-page scale calibration (issue #334).

Calibration for a PDF takeoff used to live only in the browser (localStorage)
plus a weak per-measurement ``scale_pixels_per_unit`` echo, so a reload where a
stale local default won - or a non-geometry edit that re-stamped the live view
scale - silently dropped a real calibration. It is now persisted once at the
document level in the ``page_scales`` JSON column, which the viewer restores on
load as the authoritative source.

These tests pin the backend half: the service writes the calibration verbatim
and returns the refreshed row (or ``None`` for a missing document), and the
update schema stores a normal payload while guarding against an abusive one.

Hermetic: the SQLAlchemy session and repository are mocked, so the suite runs
without a database (mirrors test_takeoff_measurement_document_identity).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError


def _make_service() -> object:
    """A TakeoffService over a mocked session (no DB)."""
    from app.modules.takeoff.service import TakeoffService

    return TakeoffService(AsyncMock())


@pytest.mark.asyncio
async def test_set_document_page_scales_persists_and_returns_refreshed() -> None:
    """The calibration is written verbatim via ``update_fields`` and the
    refreshed row is returned so the caller echoes the stored value."""
    service = _make_service()
    doc_id = uuid.uuid4()
    scales = {
        "defaultScale": {"pixelsPerUnit": 100, "unitLabel": "m"},
        "byPage": {"1": {"pixelsPerUnit": 144, "unitLabel": "m"}},
    }
    before = type("Doc", (), {"id": doc_id, "page_scales": None})()
    after = type("Doc", (), {"id": doc_id, "page_scales": scales})()
    get_mock = AsyncMock(side_effect=[before, after])
    update_mock = AsyncMock()
    with (
        patch.object(service.repo, "get_by_id", new=get_mock),  # type: ignore[attr-defined]
        patch.object(service.repo, "update_fields", new=update_mock),  # type: ignore[attr-defined]
    ):
        result = await service.set_document_page_scales(str(doc_id), scales)  # type: ignore[attr-defined]

    assert result is after
    update_mock.assert_awaited_once()
    _, kwargs = update_mock.await_args
    assert kwargs["page_scales"] == scales


@pytest.mark.asyncio
async def test_set_document_page_scales_missing_document_returns_none() -> None:
    """A missing document is a no-op returning ``None`` (the router 404s)."""
    service = _make_service()
    update_mock = AsyncMock()
    with (
        patch.object(service.repo, "get_by_id", new=AsyncMock(return_value=None)),  # type: ignore[attr-defined]
        patch.object(service.repo, "update_fields", new=update_mock),  # type: ignore[attr-defined]
    ):
        result = await service.set_document_page_scales(str(uuid.uuid4()), {})  # type: ignore[attr-defined]

    assert result is None
    update_mock.assert_not_awaited()


def test_document_page_scales_update_accepts_normal_payload() -> None:
    """A well-formed PageScales payload round-trips verbatim."""
    from app.modules.takeoff.schemas import DocumentPageScalesUpdate

    payload = DocumentPageScalesUpdate(
        page_scales={
            "defaultScale": {"pixelsPerUnit": 100, "unitLabel": "m"},
            "byPage": {"3": {"pixelsPerUnit": 25, "unitLabel": "m"}},
        }
    )
    assert payload.page_scales["byPage"]["3"]["pixelsPerUnit"] == 25


def test_document_page_scales_update_rejects_oversized_bypage() -> None:
    """An abusive per-page map (> 5000 sheets) is rejected."""
    from app.modules.takeoff.schemas import DocumentPageScalesUpdate

    big = {str(i): {"pixelsPerUnit": 100, "unitLabel": "m"} for i in range(5001)}
    with pytest.raises(ValidationError):
        DocumentPageScalesUpdate(page_scales={"byPage": big})
