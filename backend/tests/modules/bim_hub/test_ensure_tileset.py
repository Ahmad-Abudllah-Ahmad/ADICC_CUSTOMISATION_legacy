# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Service-level tests for ``BIMHubService.ensure_tileset``.

Exercises the bake orchestration end to end against the real storage backend
and DB session (no HTTP / auth - that is the endpoint's job): a model's
monolithic GLB is baked into tiles, the manifest + tiles land in storage, a
second call reuses the cache without re-baking, and a re-converted model
(changed source fingerprint) transparently re-bakes.
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio

trimesh = pytest.importorskip("trimesh")

from app.database import async_session_factory
from app.modules.bim_hub import file_storage as bim_file_storage
from app.modules.bim_hub.models import BIMModel
from app.modules.bim_hub.service import BIMHubService


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _schema_ready():
    """Ensure just the ``oe_bim_model`` table exists for this module.

    ``ensure_tileset`` only reads a model row (for its project id) and then
    does storage I/O, so a single table is all we need. We create it directly
    on the engine rather than entering the full app lifespan - the lifespan
    imports modules that use Python 3.12 ``type`` aliases, which fail to parse
    under a 3.11 local test interpreter (CI runs 3.12).
    """
    from app.database import engine
    from app.modules.bim_hub.models import BIMElement, BIMModel

    async with engine.begin() as conn:
        await conn.run_sync(BIMModel.__table__.create, checkfirst=True)
        await conn.run_sync(BIMElement.__table__.create, checkfirst=True)
    yield


def _grid_glb(nx: int, ny: int, nz: int) -> bytes:
    """Build a GLB of ``nx*ny*nz`` unit boxes, each its own named node."""
    scene = trimesh.Scene()
    k = 0
    for x in range(nx):
        for y in range(ny):
            for z in range(nz):
                box = trimesh.creation.box(extents=(0.8, 0.8, 0.8))
                box.apply_translation((x * 1.0, y * 1.0, z * 1.0))
                name = f"elem_{k:04d}"
                scene.add_geometry(box, node_name=name, geom_name=name)
                k += 1
    return bytes(scene.export(file_type="glb"))


async def _insert_model(project_id: uuid.UUID, model_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        session.add(
            BIMModel(
                id=model_id,
                project_id=project_id,
                name=f"tiler-test-{model_id}",
                model_format="ifc",
                status="ready",
                element_count=0,
            )
        )
        await session.commit()


async def _cleanup(project_id: uuid.UUID, model_id: uuid.UUID) -> None:
    await bim_file_storage.delete_model_blobs(project_id, model_id)
    async with async_session_factory() as session:
        obj = await session.get(BIMModel, model_id)
        if obj is not None:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_ensure_tileset_bakes_persists_caches_and_reheals() -> None:
    project_id = uuid.uuid4()
    model_id = uuid.uuid4()
    await _insert_model(project_id, model_id)
    await bim_file_storage.save_geometry(project_id, model_id, ".glb", _grid_glb(16, 16, 2))

    try:
        async with async_session_factory() as session:
            manifest = await BIMHubService(session).ensure_tileset(model_id)

        assert manifest is not None
        assert manifest["tiles"]
        assert manifest["tile_count"] == len(manifest["tiles"])
        assert "source_fingerprint" in manifest
        assert manifest["model_id"] == str(model_id)

        # Tiles + manifest are actually persisted to storage.
        first_hash = manifest["tiles"][0]["hash"]
        tile_blob = await bim_file_storage.read_tile(project_id, model_id, first_hash)
        assert tile_blob is not None and tile_blob[:4] == b"glTF"
        raw = await bim_file_storage.read_tiles_manifest(project_id, model_id)
        assert raw is not None
        assert json.loads(raw)["tile_count"] == manifest["tile_count"]

        # Second call reuses the cache: identical hashes, no re-bake.
        async with async_session_factory() as session:
            cached = await BIMHubService(session).ensure_tileset(model_id)
        assert cached is not None
        assert [t["hash"] for t in cached["tiles"]] == [t["hash"] for t in manifest["tiles"]]

        # Re-convert the model (new geometry) -> fingerprint changes -> re-bake.
        await bim_file_storage.save_geometry(project_id, model_id, ".glb", _grid_glb(16, 16, 3))
        async with async_session_factory() as session:
            rebaked = await BIMHubService(session).ensure_tileset(model_id)
        assert rebaked is not None
        assert rebaked["source_fingerprint"] != manifest["source_fingerprint"]
        assert rebaked["mesh_count"] != manifest["mesh_count"]
    finally:
        await _cleanup(project_id, model_id)


@pytest.mark.asyncio
async def test_ensure_tileset_returns_none_and_marks_skipped_for_small_model() -> None:
    project_id = uuid.uuid4()
    model_id = uuid.uuid4()
    await _insert_model(project_id, model_id)
    # 72 boxes: below the tiler's MIN_NODES_TO_TILE, so it declines to tile.
    await bim_file_storage.save_geometry(project_id, model_id, ".glb", _grid_glb(6, 6, 2))

    try:
        async with async_session_factory() as session:
            manifest = await BIMHubService(session).ensure_tileset(model_id)
        assert manifest is None

        # A sentinel is stored so we don't re-attempt the bake on every open.
        raw = await bim_file_storage.read_tiles_manifest(project_id, model_id)
        assert raw is not None
        assert json.loads(raw).get("skipped") is True
    finally:
        await _cleanup(project_id, model_id)


@pytest.mark.asyncio
async def test_ensure_tileset_none_when_no_geometry() -> None:
    project_id = uuid.uuid4()
    model_id = uuid.uuid4()
    await _insert_model(project_id, model_id)  # no geometry blob written
    try:
        async with async_session_factory() as session:
            manifest = await BIMHubService(session).ensure_tileset(model_id)
        assert manifest is None
    finally:
        await _cleanup(project_id, model_id)
