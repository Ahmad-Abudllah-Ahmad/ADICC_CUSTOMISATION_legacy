# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DIN SPEC 91350 BIM-LV container codec (read + write).

A *BIM-LV container* bundles a bill of quantities (Leistungsverzeichnis, LV)
with the BIM/IFC model it was measured from, plus an explicit table that links
each LV position to the BIM elements that carry its quantity. DIN SPEC 91350
defines this bundle so an estimate and its model travel together and the
position <-> element traceability survives the hand-off between tools.

Honest note on the spec text
----------------------------
The paid DIN SPEC 91350 document is not reproduced here. This module implements
a clean, self-describing interpretation of the container's three published
building blocks - it does not claim byte-for-byte conformance with the DIN XSD:

    1. the GAEB LV (the priced/unpriced positions),
    2. a reference to the IFC/BIM model,
    3. a link table position-ordinal <-> IFC element GUID(s).

Container layout (a ZIP package)
--------------------------------
    bimlv-container.xml   - manifest: container version, spec id, generator,
                            the <ModelReference> (IFC/BIM model the LV was
                            measured from) and the <Parts> hrefs.
    lv/lv.gaeb.xml        - the LV as GAEB DA XML 3.3 (Leistungsverzeichnis,
                            DP 81 shape). Each Item carries its full OZ
                            (Ordnungszahl) in ``@RNoPart``, the unit in
                            ``<QU>``, the quantity in ``<Qty>`` and - when the
                            estimator has priced the line - the unit rate in
                            ``<UP>`` (a strict-unpriced DP 81 reader simply
                            ignores ``<UP>``). This file re-imports losslessly
                            through the platform's own ``GAEBXMLImporter``.
    links/bimlv-links.xml - the link table: one <Link ordinal="..."> per LV
                            position, holding one or more <Element guid="..."/>
                            children (the IFC GlobalId / BIM stable id).

Design mirrors the existing pure codecs (``boq.build_gaeb_xml``, the BCF-XML
codec and ``einvoice.cii``): a side-effect-free builder/parser over stdlib
``xml.etree`` + ``zipfile`` only, with every quantity/rate kept as ``Decimal``.
Untrusted XML is DOCTYPE-guarded before parsing (no external/internal entity
expansion), and the archive is walked with zip-bomb / path-traversal ceilings.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET  # noqa: N817 - input is DOCTYPE-guarded below

# ── Container constants ──────────────────────────────────────────────────────

CONTAINER_VERSION = "1.0"
SPEC_ID = "DIN SPEC 91350"
GENERATOR = "OpenConstructionERP"

MANIFEST_NAME = "bimlv-container.xml"
LV_NAME = "lv/lv.gaeb.xml"
LINKS_NAME = "links/bimlv-links.xml"

# DP 81 (Leistungsverzeichnis) envelope. The namespace follows the published
# GAEB DA XML 3.3 URI scheme so authoring tools recognise the LV file.
GAEB_NS = "http://www.gaeb.de/GAEB_DA_XML/DA81/3.3"
_GAEB_DP = "81"

# Safety ceilings for reading an untrusted archive (mirrors the BCF codec, sized
# down for an LV container which is never a multi-hundred-MB payload).
_MAX_ENTRIES = 4096
_MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MiB total
_MAX_SINGLE_ENTRY_BYTES = 64 * 1024 * 1024  # 64 MiB per member


class BimLvContainerError(ValueError):
    """Raised when a buffer cannot be read as a BIM-LV container.

    The message is user-safe (no stack traces, no internal paths) so a router
    can surface it directly as an HTTP 422 - same contract as the GAEB
    importer's ``ImporterParseError`` and the BCF codec's ``BCFParseError``.
    """


# ── Transport dataclasses ────────────────────────────────────────────────────


@dataclass(slots=True)
class ModelReference:
    """Reference to the IFC/BIM model the LV was measured from.

    All fields are optional so a container can be written before every detail
    is known; ``filename`` is the human-facing model file name and ``model_id``
    is the platform's stable model identifier. ``schema`` is the IFC schema
    (e.g. ``IFC4``), ``guid`` an optional model/project GlobalId and
    ``checksum`` an optional content hash for integrity checks.
    """

    filename: str = ""
    model_id: str = ""
    schema: str = ""
    guid: str = ""
    checksum: str = ""


@dataclass(slots=True)
class ContainerPosition:
    """One LV position as carried by the container's GAEB LV file."""

    ordinal: str
    description: str = ""
    unit: str = "pcs"
    quantity: Decimal = Decimal(0)
    unit_rate: Decimal = Decimal(0)


@dataclass(slots=True)
class ParsedContainer:
    """Result of :func:`read_container`.

    ``mapping`` is ordered ``{position_ordinal: [element_guid, ...]}``.
    ``lv_gaeb_bytes`` is the raw GAEB LV member so a caller can hand it
    straight to the platform's ``GAEBXMLImporter`` for the canonical,
    validated import path.
    """

    positions: list[ContainerPosition] = field(default_factory=list)
    mapping: dict[str, list[str]] = field(default_factory=dict)
    model_ref: ModelReference = field(default_factory=ModelReference)
    lv_gaeb_bytes: bytes = b""
    warnings: list[str] = field(default_factory=list)


# ── stdlib XML helpers ───────────────────────────────────────────────────────


def _local(tag: str) -> str:
    """Strip a ``{namespace}`` prefix from an ElementTree tag."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_child(parent: ET.Element, name: str) -> ET.Element | None:
    """Namespace-agnostic single-child lookup by local name."""
    for child in parent:
        if _local(child.tag) == name:
            return child
    return None


def _iter_local(parent: ET.Element, name: str) -> list[ET.Element]:
    """Collect every descendant whose local name matches ``name``."""
    return [el for el in parent.iter() if _local(el.tag) == name]


def _text_of(parent: ET.Element, name: str) -> str:
    child = _find_child(parent, name)
    return (child.text or "").strip() if child is not None else ""


def _safe_fromstring(raw: bytes, *, what: str) -> ET.Element:
    """Parse ``raw`` XML, rejecting DOCTYPE/entity payloads up-front.

    stdlib ``xml.etree`` (expat) does not fetch external entities, but a DTD
    with nested internal entities is the classic "billion laughs" amplifier.
    We therefore refuse any document carrying a ``<!DOCTYPE`` / ``<!ENTITY``
    declaration before handing the bytes to the parser - a pure-stdlib
    mitigation that keeps this module dependency-free.
    """
    head = raw[:4096].lstrip()
    lowered = head.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise BimLvContainerError(f"{what}: DOCTYPE / entity declarations are not allowed")
    try:
        return ET.fromstring(raw)  # noqa: S314 - DOCTYPE-guarded, no external entities
    except ET.ParseError as exc:
        raise BimLvContainerError(f"{what}: malformed XML ({exc})") from exc


def _to_decimal(raw: str) -> Decimal | None:
    """Parse a numeric field as an exact ``Decimal`` (``None`` when unusable)."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _coerce_decimal(value: object) -> Decimal:
    """Best-effort coercion of a caller-supplied amount to a finite Decimal."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal(0)
    if value is None or value == "":
        return Decimal(0)
    parsed = _to_decimal(str(value))
    return parsed if parsed is not None else Decimal(0)


def _fmt_num(value: Decimal) -> str:
    """Serialise a Decimal as fixed-point text (never scientific notation)."""
    return f"{value:f}"


def _norm_guids(guids: object) -> list[str]:
    """Normalise a position's GUID list: strip, drop blanks, dedupe, keep order."""
    if not isinstance(guids, (list, tuple, set)):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in guids:
        guid = str(raw).strip()
        if guid and guid not in seen:
            seen.add(guid)
            out.append(guid)
    return out


# ── Writer: GAEB LV ──────────────────────────────────────────────────────────


def _append_description(item: ET.Element, text: str) -> None:
    """Append a schema-shaped ``Description/CompleteText/DetailTxt/Text`` block.

    GAEB models long text as ``<p>`` paragraphs of ``<span>`` runs; a bare text
    child is not valid, so we always wrap. One paragraph per source line.
    """
    desc = ET.SubElement(item, "Description")
    complete = ET.SubElement(desc, "CompleteText")
    detail = ET.SubElement(complete, "DetailTxt")
    text_el = ET.SubElement(detail, "Text")
    for line in (text or "").split("\n"):
        para = ET.SubElement(text_el, "p")
        span = ET.SubElement(para, "span")
        span.text = line


def _build_lv_gaeb_xml(
    positions: list[ContainerPosition],
    *,
    project_name: str,
    currency: str,
) -> bytes:
    """Build the container's GAEB DA XML 3.3 LV (DP 81) member as bytes.

    Positions are emitted as a flat ``Itemlist`` whose ``Item/@RNoPart`` carries
    the full dotted OZ verbatim - a documented simplification for the
    link-focused container that still re-imports cleanly through the platform's
    namespace-agnostic ``GAEBXMLImporter`` (a single dotted ``RNoPart`` is read
    back as the whole OZ). ``<UP>`` is written only for priced lines so an
    unpriced LV stays a strict DP 81 skeleton.
    """
    gaeb = ET.Element("GAEB", xmlns=GAEB_NS)

    info = ET.SubElement(gaeb, "GAEBInfo")
    ET.SubElement(info, "Version").text = "3.3"
    ET.SubElement(info, "Date").text = datetime.now(UTC).date().isoformat()
    ET.SubElement(info, "ProgSystem").text = GENERATOR

    prj = ET.SubElement(gaeb, "PrjInfo")
    ET.SubElement(prj, "NamePrj").text = (project_name or "")[:60]
    if currency:
        ET.SubElement(prj, "Cur").text = currency

    award = ET.SubElement(gaeb, "Award")
    ET.SubElement(award, "DP").text = _GAEB_DP
    award_info = ET.SubElement(award, "AwardInfo")
    ET.SubElement(award_info, "Cur").text = currency

    boq = ET.SubElement(award, "BoQ", ID="oeBoQ")
    boq_info = ET.SubElement(boq, "BoQInfo")
    ET.SubElement(boq_info, "Name").text = (project_name or "LV")[:20]
    # No BoQBkdn (OZ-Maske) is emitted on purpose: this container carries the
    # FULL dotted OZ verbatim in a single ``Item/@RNoPart``. A mask would make a
    # standards-compliant reader zero-pad a flat numeric ordinal (``5`` ->
    # ``000000005``) and corrupt it; omitting it keeps every ordinal exact on a
    # re-import through the platform's own namespace-agnostic GAEB importer.

    body = ET.SubElement(boq, "BoQBody")
    itemlist = ET.SubElement(body, "Itemlist")
    for pos in positions:
        ordinal = (pos.ordinal or "").strip()
        item = ET.SubElement(itemlist, "Item", ID="oeItem", RNoPart=ordinal or "0")
        ET.SubElement(item, "Qty").text = _fmt_num(_coerce_decimal(pos.quantity))
        ET.SubElement(item, "QU").text = (pos.unit or "")[:20]
        rate = _coerce_decimal(pos.unit_rate)
        if rate != 0:
            ET.SubElement(item, "UP").text = _fmt_num(rate)
        _append_description(item, pos.description or ordinal)

    return _serialise(gaeb)


# ── Writer: manifest + links ─────────────────────────────────────────────────


def _build_manifest_xml(model_ref: ModelReference) -> bytes:
    """Build the container manifest (model reference + part hrefs)."""
    root = ET.Element("BimLvContainer", {"version": CONTAINER_VERSION, "spec": SPEC_ID})

    meta = ET.SubElement(root, "Info")
    ET.SubElement(meta, "Generator").text = GENERATOR
    ET.SubElement(meta, "Created").text = datetime.now(UTC).isoformat()

    model = ET.SubElement(root, "ModelReference")
    if model_ref.filename:
        model.set("filename", model_ref.filename)
    if model_ref.model_id:
        model.set("modelId", model_ref.model_id)
    if model_ref.schema:
        model.set("schema", model_ref.schema)
    if model_ref.guid:
        model.set("guid", model_ref.guid)
    if model_ref.checksum:
        model.set("checksum", model_ref.checksum)

    parts = ET.SubElement(root, "Parts")
    ET.SubElement(parts, "Lv", {"href": LV_NAME, "format": "GAEB DA XML 3.3"})
    ET.SubElement(parts, "Links", {"href": LINKS_NAME})

    return _serialise(root)


def _build_links_xml(mapping: dict[str, list[str]]) -> bytes:
    """Build the position-ordinal <-> element-GUID link table."""
    root = ET.Element("BimLvLinks", {"version": CONTAINER_VERSION, "spec": SPEC_ID})
    for ordinal, guids in mapping.items():
        key = str(ordinal).strip()
        norm = _norm_guids(guids)
        if not key or not norm:
            continue
        link = ET.SubElement(root, "Link", {"ordinal": key})
        for guid in norm:
            ET.SubElement(link, "Element", {"guid": guid})
    return _serialise(root)


def _serialise(root: ET.Element) -> bytes:
    """Serialise an element tree to a UTF-8 XML document with a declaration."""
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body).encode("utf-8")


# ── Public: write ────────────────────────────────────────────────────────────


def write_container(
    lv_positions: list[ContainerPosition],
    mapping: dict[str, list[str]],
    model_ref: ModelReference,
    *,
    project_name: str = "",
    currency: str = "",
) -> bytes:
    """Write a DIN SPEC 91350 BIM-LV container.

    Args:
        lv_positions: the LV positions (ordinal, description, unit, quantity,
            unit rate). Serialised to the GAEB LV member.
        mapping: ordered ``{position_ordinal: [element_guid, ...]}``. Blank
            ordinals and empty GUID lists are dropped; GUIDs are deduped per
            position while preserving order.
        model_ref: reference to the IFC/BIM model the LV was measured from.
        project_name: optional human-facing project name for the LV envelope.
        currency: optional ISO currency code for the LV envelope.

    Returns:
        The container as ZIP ``bytes``.
    """
    positions = list(lv_positions)
    manifest_xml = _build_manifest_xml(model_ref)
    lv_xml = _build_lv_gaeb_xml(positions, project_name=project_name, currency=currency)
    links_xml = _build_links_xml(dict(mapping))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Manifest first so a streaming reader hits the descriptor up-front.
        zf.writestr(MANIFEST_NAME, manifest_xml)
        zf.writestr(LV_NAME, lv_xml)
        zf.writestr(LINKS_NAME, links_xml)
    return buf.getvalue()


# ── Reader ───────────────────────────────────────────────────────────────────


def _safe_read_member(zf: zipfile.ZipFile, name: str, *, required: bool) -> bytes:
    """Read one archive member by exact name, enforcing the size ceiling.

    Returns ``b""`` when an optional member is absent; raises for a missing
    required member or an over-size entry.
    """
    try:
        info = zf.getinfo(name)
    except KeyError as exc:
        if required:
            raise BimLvContainerError(f"Container is missing the required '{name}' member") from exc
        return b""
    if info.file_size > _MAX_SINGLE_ENTRY_BYTES:
        raise BimLvContainerError(f"Container member '{name}' exceeds the size limit")
    try:
        return zf.read(name)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BimLvContainerError(f"Container member '{name}' is corrupt ({exc})") from exc


def _guard_archive(zf: zipfile.ZipFile) -> None:
    """Reject zip-bombs / path-traversal before reading any member."""
    infos = zf.infolist()
    if len(infos) > _MAX_ENTRIES:
        raise BimLvContainerError("Container has too many entries")
    total = 0
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
            raise BimLvContainerError(f"Container has an unsafe entry path: {name!r}")
        total += info.file_size
    if total > _MAX_UNCOMPRESSED_BYTES:
        raise BimLvContainerError("Container uncompressed size exceeds the safety ceiling")


def _parse_model_ref(manifest_xml: bytes) -> ModelReference:
    """Read the ``<ModelReference>`` out of the manifest member."""
    if not manifest_xml:
        return ModelReference()
    root = _safe_fromstring(manifest_xml, what="container manifest")
    node = _find_child(root, "ModelReference")
    if node is None:
        return ModelReference()
    return ModelReference(
        filename=(node.get("filename") or "").strip(),
        model_id=(node.get("modelId") or "").strip(),
        schema=(node.get("schema") or "").strip(),
        guid=(node.get("guid") or "").strip(),
        checksum=(node.get("checksum") or "").strip(),
    )


def _parse_links(links_xml: bytes) -> dict[str, list[str]]:
    """Read the ordered ``{ordinal: [guid, ...]}`` link table."""
    if not links_xml:
        return {}
    root = _safe_fromstring(links_xml, what="container links")
    mapping: dict[str, list[str]] = {}
    for link in _iter_local(root, "Link"):
        ordinal = (link.get("ordinal") or "").strip()
        if not ordinal:
            continue
        guids = [
            (el.get("guid") or "").strip() for el in _iter_local(link, "Element") if (el.get("guid") or "").strip()
        ]
        norm = _norm_guids(guids)
        if not norm:
            continue
        mapping.setdefault(ordinal, [])
        for guid in norm:
            if guid not in mapping[ordinal]:
                mapping[ordinal].append(guid)
    return mapping


def _item_description(item: ET.Element) -> str:
    """Extract the long-text description from a GAEB Item's Text block."""
    desc = _find_child(item, "Description")
    if desc is None:
        return ""
    container = _find_child(desc, "CompleteText") or desc
    detail = _find_child(container, "DetailTxt")
    text_node = _find_child(detail, "Text") if detail is not None else _find_child(container, "Text")
    if text_node is None:
        return ""
    lines: list[str] = []
    paragraphs = [c for c in text_node if _local(c.tag) == "p"]
    for para in paragraphs or [text_node]:
        parts = [span.text.strip() for span in para.iter() if _local(span.tag) == "span" and span.text]
        line = " ".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _parse_lv(lv_xml: bytes) -> list[ContainerPosition]:
    """Read the LV positions out of the container's GAEB member."""
    if not lv_xml:
        return []
    root = _safe_fromstring(lv_xml, what="container LV")
    positions: list[ContainerPosition] = []
    for item in _iter_local(root, "Item"):
        ordinal = (item.get("RNoPart") or "").strip()
        qty = _to_decimal(_text_of(item, "Qty")) or Decimal(0)
        rate = _to_decimal(_text_of(item, "UP")) or Decimal(0)
        positions.append(
            ContainerPosition(
                ordinal=ordinal,
                description=_item_description(item),
                unit=_text_of(item, "QU") or "pcs",
                quantity=qty,
                unit_rate=rate,
            ),
        )
    return positions


def read_container(data: bytes) -> ParsedContainer:
    """Read a DIN SPEC 91350 BIM-LV container.

    Args:
        data: the raw container (ZIP) bytes.

    Returns:
        A :class:`ParsedContainer` (positions + link table + model reference +
        the raw GAEB LV bytes).

    Raises:
        BimLvContainerError: the buffer is not a valid container (not a ZIP,
            corrupt, unsafe entry paths, or a malformed / missing LV member).
    """
    if not data:
        raise BimLvContainerError("Container upload is empty")

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BimLvContainerError(f"Not a valid BIM-LV container (not a ZIP archive): {exc}") from exc

    warnings: list[str] = []
    with zf:
        try:
            bad = zf.testzip()
        except (zipfile.BadZipFile, OSError) as exc:
            raise BimLvContainerError(f"Corrupt container archive: {exc}") from exc
        if bad is not None:
            raise BimLvContainerError(f"Corrupt container member: {bad}")

        _guard_archive(zf)

        # The GAEB LV is the one indispensable member - a container without it
        # is not a BIM-LV container. Manifest + links are read best-effort so a
        # minimal LV-only bundle still yields its positions.
        lv_xml = _safe_read_member(zf, LV_NAME, required=True)
        manifest_xml = _safe_read_member(zf, MANIFEST_NAME, required=False)
        links_xml = _safe_read_member(zf, LINKS_NAME, required=False)

    if not manifest_xml:
        warnings.append("Container has no manifest; model reference is unknown")
    if not links_xml:
        warnings.append("Container has no link table; no BIM element links present")

    model_ref = _parse_model_ref(manifest_xml)
    positions = _parse_lv(lv_xml)
    mapping = _parse_links(links_xml)

    return ParsedContainer(
        positions=positions,
        mapping=mapping,
        model_ref=model_ref,
        lv_gaeb_bytes=lv_xml,
        warnings=warnings,
    )
