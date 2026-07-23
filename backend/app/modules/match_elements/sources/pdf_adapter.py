# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""PDF source adapter - extracted PDF line items to /match-elements.

Implements MAPPING_PROCESS.md §4.1.x - the "PDF" source. A tender PDF
(printed bill of quantities, priced schedule, specification table) is
parsed once at session-creation time by
:mod:`app.modules.match_elements.pdf_import`, and the extracted line
items are persisted into ``MatchSession.metadata_["pdf_rows"]``.

This adapter is then a thin reader over those rows - no PDF parsing on
the match hot path. It is intentionally a near-twin of
:class:`app.modules.match_elements.sources.boq_adapter.BoqAdapter`
because a parsed PDF line and a parsed Excel BoQ row carry the same
fields (``description`` + optional ``qty`` / ``unit`` / ``code`` /
``category``); keeping the two readers symmetric means the downstream
group / match / apply pipeline does not branch on source type. The only
behavioural differences from the BoQ adapter are the storage key
(``pdf_rows`` vs ``boq_rows``), the default category label (``"PDF"``),
and the element-id namespace (``pdf:<n>``).

Storage shape
-------------
``MatchSession.metadata_["pdf_rows"]`` is a list of dicts. Required:
``description``. Recognised optional keys mirror the BoQ adapter:

    description / name / text   -> element name + dense query
    qty / quantity              -> numeric quantity
    unit / uom                  -> canonical CWICR unit (-> quantity dim)
    code / rate_code            -> exact-match shortcut
    category / section / page   -> group-by dimension
    source_lang                 -> query-language hint

When the adapter is constructed without a ``match_session`` reference
(unit-test or smoke probe), it returns empty results from every method
rather than crashing - the loose contract mirrors the Text / BoQ
adapters' "no session -> empty list" fallback.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.match_elements.models import MatchSession
from app.modules.match_elements.sources.base import SourceElement

# Reuse the BoQ adapter's unit -> canonical quantity-dimension mapping and
# numeric coercion so a PDF line priced in "m³" rolls up the same way an
# Excel BoQ row does. Single source of truth for the unit table.
from app.modules.match_elements.sources.boq_adapter import (
    _quantities_for,
    _to_float,
)

_GROUP_BY_KEY_ORDER = (
    "category",
    "section",
    "page",
    "ifc_class",
    "description",
    "unit",
    "source_lang",
)


class PdfAdapter:
    """Reads pre-parsed PDF line items from ``MatchSession.metadata_``."""

    source_name: str = "pdf"

    def __init__(
        self,
        session: AsyncSession,
        match_session: MatchSession | None = None,
    ) -> None:
        self.session = session
        self.match_session = match_session

    def _rows(self) -> list[dict[str, Any]]:
        """Return the raw PDF rows from session metadata.

        Empty list when no session is bound or ``pdf_rows`` is missing.
        Non-dict entries are filtered out so a malformed metadata blob
        does not crash the matcher.
        """
        if self.match_session is None:
            return []
        meta = self.match_session.metadata_ or {}
        raw_rows = meta.get("pdf_rows") or []
        if not isinstance(raw_rows, list):
            return []
        return [r for r in raw_rows if isinstance(r, dict)]

    async def list_attribute_keys(
        self,
        project_id: uuid.UUID,  # noqa: ARG002 - pdf adapter is session-scoped
        bim_model_id: uuid.UUID | None = None,  # noqa: ARG002
    ) -> list[str]:
        """Return the union of dict keys across all PDF rows.

        Filters out quantity columns (qty/quantity) since those drive
        ``quantities``, not the chip-bar group-by.
        """
        keys: set[str] = {"category", "description", "unit"}
        for row in self._rows():
            keys.update(k for k in row if isinstance(k, str))
        for q in ("qty", "quantity", "Qty", "Quantity"):
            keys.discard(q)
        ordered = [k for k in _GROUP_BY_KEY_ORDER if k in keys]
        ordered.extend(sorted(k for k in keys if k not in _GROUP_BY_KEY_ORDER))
        return ordered

    async def list_categories(
        self,
        project_id: uuid.UUID,  # noqa: ARG002
        bim_model_id: uuid.UUID | None = None,  # noqa: ARG002
    ) -> list[tuple[str, int]]:
        """Group rows by ``category`` (or ``section``) - fallback "PDF"."""
        counter: Counter[str] = Counter()
        for row in self._rows():
            cat = str(row.get("category") or row.get("section") or "PDF") or "PDF"
            counter[cat] += 1
        return counter.most_common()

    async def iter_elements(
        self,
        *,
        project_id: uuid.UUID,  # noqa: ARG002
        bim_model_id: uuid.UUID | None = None,  # noqa: ARG002
        filters: dict[str, list[Any]] | None = None,
        excluded_categories: list[str] | None = None,
        use_net_quantities: bool = True,  # noqa: ARG002 - PDF has no openings
    ) -> list[SourceElement]:
        """Convert each parsed PDF row to a :class:`SourceElement`."""
        excluded = {str(c) for c in (excluded_categories or []) if c}
        norm_filters: dict[str, set[str]] = {}
        if filters:
            for fkey, fvals in filters.items():
                if fvals:
                    norm_filters[fkey] = {str(v) for v in fvals}

        out: list[SourceElement] = []
        for idx, row in enumerate(self._rows()):
            cat = str(row.get("category") or row.get("section") or "PDF") or "PDF"
            if cat in excluded:
                continue

            description = str(row.get("description") or row.get("name") or row.get("text") or "").strip()
            unit = str(row.get("unit") or row.get("uom") or "").strip()
            qty = _to_float(row.get("qty") or row.get("quantity") or row.get("Qty") or row.get("Quantity"))

            attrs: dict[str, Any] = dict(row)
            attrs.setdefault("category", cat)
            attrs.setdefault("description", description)
            attrs.setdefault("unit", unit)
            # ``ifc_class`` is kept only when the row carries a real IFC
            # class name. A printed PDF almost never does; the synthetic
            # "PDF" / category label is NOT an IFC class and promoting it
            # would poison the Qdrant ``ifc_class`` hard filter and zero
            # out every CWICR candidate (see the same guard in BoqAdapter
            # and the ``match_elements_three_filter_bugs`` memory).
            row_ifc = attrs.get("ifc_class")
            if not (isinstance(row_ifc, str) and row_ifc.startswith("Ifc")):
                attrs.pop("ifc_class", None)

            # Exact-code shortcut - when the PDF row carried a recognisable
            # position code, forward it so the ranker can fetch the rate
            # directly from parquet instead of fanning out to Qdrant.
            code = row.get("code") or row.get("rate_code")
            if code:
                attrs["exact_code"] = str(code).strip()

            if norm_filters:
                skip = False
                for fkey, fvals in norm_filters.items():
                    actual = attrs.get(fkey)
                    if actual is None or str(actual) not in fvals:
                        skip = True
                        break
                if skip:
                    continue

            quantities = _quantities_for(unit, qty)

            row_id = row.get("id") or row.get("row_id") or row.get("ordinal") or f"pdf:{idx}"
            ref = str(self.match_session.id) if self.match_session is not None else None

            out.append(
                SourceElement(
                    id=str(row_id),
                    category=cat,
                    name=description[:200] or None,
                    attributes=attrs,
                    quantities=quantities,
                    raw_ref=ref,
                )
            )
        return out


__all__ = ["PdfAdapter"]
