# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Universal Element Reference (UER) resolver.

One helper resolves an inbound element link to the normalised bim_hub identity,
regardless of source format (IFC, Revit, DWG, DGN, point cloud, ...), and backfills
the denormalised display fields so a control record renders without loading the model.

Resolve order: ``bim_element_id`` (strong) -> ``(model_id, stable_id)`` ->
``(model_id, native_id)``. Any referenced model is checked to belong to the record's
project: a cross-project model/element reference raises 404 (IDOR defence - the same
"missing == denied" policy the rest of the platform uses), never revealing that
another tenant's id exists.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bim_hub.models import BIMElement, BIMModel
from app.modules.construction_control.schemas import ElementRefIn

# A 22-character, base64-ish IFC GlobalId; used only to opportunistically backfill
# the optional BCF crosswalk when an IFC element resolves and none was supplied.
_IFC_GLOBAL_ID_LEN = 22


def is_empty_ref(ref: ElementRefIn | None) -> bool:
    """True when the inbound link carries no resolvable or displayable content."""
    if ref is None:
        return True
    return not any(
        (
            ref.bim_element_id,
            ref.model_id,
            ref.stable_id,
            ref.native_id,
            ref.element_name,
            ref.element_type,
            ref.ifc_global_id,
            ref.bbox,
            ref.viewpoint,
        )
    )


async def _load_model_in_project(
    session: AsyncSession,
    model_id: uuid.UUID,
    project_id: uuid.UUID,
) -> BIMModel:
    """Load a BIM model and assert it belongs to ``project_id`` (else 404)."""
    model = await session.get(BIMModel, model_id)
    if model is None or model.project_id != project_id:
        # Same 404 for "no such model" and "model in another project" so the
        # response never distinguishes the two (IDOR defence).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced model not found in this project",
        )
    return model


async def resolve_element_ref(
    session: AsyncSession,
    project_id: uuid.UUID,
    ref: ElementRefIn,
) -> dict:
    """Resolve a UER and return the ``ElementRef`` column values to persist.

    The returned dict always carries the contract field set; ``bim_element_id`` /
    ``model_id`` / ``stable_id`` are filled as far as the link resolves, and the
    display fields (``element_name``, ``element_type``, ``source_format``,
    ``model_version``, ``bbox``) are backfilled from the resolved element/model when
    the caller did not supply them.
    """
    resolved_element: BIMElement | None = None
    resolved_model: BIMModel | None = None

    if ref.bim_element_id is not None:
        element = await session.get(BIMElement, ref.bim_element_id)
        if element is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Referenced model element not found",
            )
        # The element's model proves the project; reject cross-project elements.
        resolved_model = await _load_model_in_project(session, element.model_id, project_id)
        resolved_element = element
    elif ref.model_id is not None:
        resolved_model = await _load_model_in_project(session, ref.model_id, project_id)
        lookup_key = ref.stable_id or ref.native_id
        if lookup_key:
            # Normalised identity: stable_id is the per-format id; native_id falls
            # back to the same column because most converters store the native id
            # there when the two coincide.
            result = await session.execute(
                select(BIMElement)
                .where(BIMElement.model_id == resolved_model.id)
                .where(BIMElement.stable_id == lookup_key)
                .limit(1)
            )
            resolved_element = result.scalar_one_or_none()
    # else: a purely denormalised reference (model not yet ingested) - carry the
    # caller's display fields unchanged so the record still renders.

    def pick(provided, resolved):
        return provided if provided is not None else resolved

    source_format = pick(ref.source_format, resolved_model.model_format if resolved_model else None)
    stable_id = pick(ref.stable_id, resolved_element.stable_id if resolved_element else None)

    ifc_global_id = ref.ifc_global_id
    if (
        ifc_global_id is None
        and stable_id is not None
        and len(stable_id) == _IFC_GLOBAL_ID_LEN
        and (source_format or "").lower() in ("ifc", "ifc2x3", "ifc4")
    ):
        # An IFC element's stable_id IS its GlobalId; expose it as the BCF crosswalk.
        ifc_global_id = stable_id

    return {
        "bim_element_id": resolved_element.id if resolved_element else ref.bim_element_id,
        "model_id": resolved_model.id if resolved_model else ref.model_id,
        "stable_id": stable_id,
        "source_format": source_format,
        "ifc_global_id": ifc_global_id,
        "native_id": ref.native_id,
        "model_version": pick(ref.model_version, resolved_model.version if resolved_model else None),
        "element_name": pick(ref.element_name, resolved_element.name if resolved_element else None),
        "element_type": pick(ref.element_type, resolved_element.element_type if resolved_element else None),
        "bbox": pick(ref.bbox, resolved_element.bounding_box if resolved_element else None),
        "viewpoint": ref.viewpoint,
        "metadata_": ref.metadata or {},
    }
