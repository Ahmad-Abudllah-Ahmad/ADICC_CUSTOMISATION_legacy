# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Vision-first Recognize: rooms from plan-read when AI key exists."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.takeoff.service import TakeoffService


@pytest.mark.asyncio
async def test_try_vision_recognize_rooms_maps_polygons() -> None:
    svc = TakeoffService(MagicMock())
    svc._resolve_plan_read_provider = AsyncMock(
        return_value=("openai", "sk-test", None, "gpt-4o")
    )
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    plan_json = {
        "scale": None,
        "rooms": [
            {
                "name": "Kitchen",
                "polygon": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
                "confidence": 0.88,
            },
            {
                "name": "Office",
                "polygon": [[0.5, 0.1], [0.8, 0.1], [0.8, 0.35], [0.5, 0.35]],
                "confidence": 0.81,
            },
        ],
        "symbols": [],
    }
    with (
        patch("app.modules.takeoff.plan_read.rasterize_page", return_value=(fake_png, "image/png", 150, 612.0, 792.0)),
        patch("app.modules.ai.ai_client.call_ai", new_callable=AsyncMock) as call_ai,
        patch("app.modules.ai.ai_client.extract_json", return_value=plan_json),
    ):
        call_ai.return_value = ('{"rooms":[]}', 100)
        out = await svc._try_vision_recognize_rooms(
            user_id="11111111-1111-1111-1111-111111111111",
            content=b"%PDF-1.4",
            page=1,
            scale_pixels_per_unit=50.0,
        )
    assert out is not None
    assert out["source"] == "vision_recognize"
    assert len(out["candidates"]) == 2
    labels = {c["label"] for c in out["candidates"]}
    assert labels == {"Kitchen", "Office"}
    for c in out["candidates"]:
        assert c["type"] == "area"
        assert len(c["points"]) >= 3
        assert c["value"] is not None and c["value"] > 0


@pytest.mark.asyncio
async def test_try_vision_recognize_rooms_no_key_falls_back() -> None:
    from fastapi import HTTPException

    svc = TakeoffService(MagicMock())
    svc._resolve_plan_read_provider = AsyncMock(
        side_effect=HTTPException(status_code=400, detail="No AI provider configured")
    )
    out = await svc._try_vision_recognize_rooms(
        user_id="11111111-1111-1111-1111-111111111111",
        content=b"%PDF-1.4",
        page=1,
        scale_pixels_per_unit=None,
    )
    assert out is None


@pytest.mark.asyncio
async def test_try_vision_recognize_rooms_skips_without_user() -> None:
    svc = TakeoffService(MagicMock())
    out = await svc._try_vision_recognize_rooms(
        user_id=None,
        content=b"%PDF-1.4",
        page=1,
        scale_pixels_per_unit=None,
    )
    assert out is None
