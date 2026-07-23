# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for the DIN SPEC 91350 BIM-LV container codec.

Pure round-trip / edge-case coverage - no DB, no network. Validates that
``write_container`` -> ``read_container`` preserves the LV positions, the
position-ordinal <-> element-GUID link table and the model reference, that
malformed input is rejected cleanly, and (when the platform's GAEB importer is
importable) that the embedded LV is a real GAEB DA XML the importer reads back.
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal

import pytest

from app.modules.bimlv.container import (
    LV_NAME,
    MANIFEST_NAME,
    BimLvContainerError,
    ContainerPosition,
    ModelReference,
    read_container,
    write_container,
)


def _sample_positions() -> list[ContainerPosition]:
    return [
        ContainerPosition(
            ordinal="01.01.001",
            description="Concrete C30/37 for foundation slab",
            unit="m3",
            quantity=Decimal("42.500"),
            unit_rate=Decimal("135.75"),
        ),
        ContainerPosition(
            ordinal="01.01.002",
            description="Reinforcement steel B500B",
            unit="kg",
            quantity=Decimal("3150.000"),
            unit_rate=Decimal("1.42"),
        ),
        # An unpriced line (unit_rate == 0): the writer omits <UP> so this
        # stays a strict DP 81 LV skeleton line.
        ContainerPosition(
            ordinal="02.03.010",
            description="Formwork to slab edges",
            unit="m2",
            quantity=Decimal("88.000"),
            unit_rate=Decimal("0"),
        ),
    ]


def _sample_mapping() -> dict[str, list[str]]:
    return {
        "01.01.001": ["1aB2cD3eF4gH5iJ6kL7mN"],
        "01.01.002": ["2xY3zA4bC5dE6fG7hI8jK", "9oP8qR7sT6uV5wX4yZ3aB"],
        "02.03.010": ["0kL9jM8nO7pQ6rS5tU4vW"],
    }


def _sample_model_ref() -> ModelReference:
    return ModelReference(
        filename="structural.ifc",
        model_id="7f3d9c1e-2b4a-4c6d-8e0f-1a2b3c4d5e6f",
        schema="IFC4",
        guid="1a2b3c4d5e6f7g8h9i0j1k",
        checksum="sha256:abcdef0123456789",
    )


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _repack(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return buf.getvalue()


# ── happy-path round trip ────────────────────────────────────────────────────


def test_output_is_a_zip_with_expected_members() -> None:
    data = write_container(_sample_positions(), _sample_mapping(), _sample_model_ref())
    assert data[:4] == b"PK\x03\x04"
    members = _members(data)
    assert MANIFEST_NAME in members
    assert LV_NAME in members
    assert "links/bimlv-links.xml" in members


def test_roundtrip_preserves_positions() -> None:
    data = write_container(_sample_positions(), _sample_mapping(), _sample_model_ref())
    parsed = read_container(data)

    assert [p.ordinal for p in parsed.positions] == ["01.01.001", "01.01.002", "02.03.010"]
    by_ordinal = {p.ordinal: p for p in parsed.positions}

    slab = by_ordinal["01.01.001"]
    assert slab.description == "Concrete C30/37 for foundation slab"
    assert slab.unit == "m3"
    assert slab.quantity == Decimal("42.500")
    assert slab.unit_rate == Decimal("135.75")

    # Unpriced line: rate comes back as an exact zero, quantity intact.
    formwork = by_ordinal["02.03.010"]
    assert formwork.unit_rate == Decimal("0")
    assert formwork.quantity == Decimal("88.000")


def test_roundtrip_preserves_decimal_precision_exactly() -> None:
    positions = [
        ContainerPosition(
            ordinal="7",
            description="Trailing zeros and sub-cent precision",
            unit="m",
            quantity=Decimal("1.005"),
            unit_rate=Decimal("12.500"),
        ),
    ]
    parsed = read_container(write_container(positions, {}, ModelReference()))
    got = parsed.positions[0]
    # Flat numeric ordinal must NOT be zero-padded by the codec.
    assert got.ordinal == "7"
    assert str(got.quantity) == "1.005"
    assert str(got.unit_rate) == "12.500"


def test_roundtrip_preserves_mapping() -> None:
    mapping = _sample_mapping()
    parsed = read_container(write_container(_sample_positions(), mapping, _sample_model_ref()))
    assert parsed.mapping == mapping


def test_roundtrip_preserves_model_reference() -> None:
    ref = _sample_model_ref()
    parsed = read_container(write_container(_sample_positions(), {}, ref))
    assert parsed.model_ref == ref


def test_multiple_guids_per_position_keep_order() -> None:
    mapping = {"01.01.002": ["guid-A", "guid-B", "guid-C"]}
    parsed = read_container(write_container(_sample_positions(), mapping, ModelReference()))
    assert parsed.mapping["01.01.002"] == ["guid-A", "guid-B", "guid-C"]


# ── mapping normalisation ────────────────────────────────────────────────────


def test_empty_mapping_roundtrips_to_empty() -> None:
    parsed = read_container(write_container(_sample_positions(), {}, ModelReference()))
    assert parsed.mapping == {}


def test_mapping_normalisation_drops_blanks_and_dedupes() -> None:
    mapping = {
        "01.01.001": ["g1", "g1", " g2 ", ""],  # dupes + blanks + padding
        "  ": ["gX"],  # blank ordinal -> dropped
        "02.03.010": [],  # empty guid list -> dropped
    }
    parsed = read_container(write_container(_sample_positions(), mapping, ModelReference()))
    assert parsed.mapping == {"01.01.001": ["g1", "g2"]}


# ── XML escaping ─────────────────────────────────────────────────────────────


def test_xml_special_characters_roundtrip() -> None:
    positions = [
        ContainerPosition(
            ordinal="01.02&03",
            description="Wall <C30/37> & \"waterproof\" 'grade' <tag>",
            unit="m2",
            quantity=Decimal("5"),
            unit_rate=Decimal("9.99"),
        ),
    ]
    mapping = {"01.02&03": ["guid<&>\"'"]}
    ref = ModelReference(filename='a&b "c" <d>.ifc', model_id="x&y")
    parsed = read_container(write_container(positions, mapping, ref))

    assert parsed.positions[0].ordinal == "01.02&03"
    assert parsed.positions[0].description == "Wall <C30/37> & \"waterproof\" 'grade' <tag>"
    assert parsed.mapping == {"01.02&03": ["guid<&>\"'"]}
    assert parsed.model_ref.filename == 'a&b "c" <d>.ifc'
    assert parsed.model_ref.model_id == "x&y"


# ── malformed / hostile input ────────────────────────────────────────────────


def test_empty_bytes_rejected() -> None:
    with pytest.raises(BimLvContainerError):
        read_container(b"")


def test_non_zip_rejected() -> None:
    with pytest.raises(BimLvContainerError):
        read_container(b"this is not a zip archive at all")


def test_container_without_lv_rejected() -> None:
    data = _repack({"something-else.xml": b"<x/>"})
    with pytest.raises(BimLvContainerError):
        read_container(data)


def test_malformed_lv_xml_rejected() -> None:
    data = _repack({LV_NAME: b"<GAEB><BoQ><not-closed"})
    with pytest.raises(BimLvContainerError):
        read_container(data)


def test_doctype_payload_rejected() -> None:
    # A DOCTYPE in any member must be refused before parsing (billion-laughs
    # guard). Keep a valid LV so the reader reaches the links member.
    good = _members(write_container(_sample_positions(), _sample_mapping(), ModelReference()))
    good["links/bimlv-links.xml"] = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE lolz [<!ENTITY lol "lol">]>\n'
        b'<BimLvLinks><Link ordinal="x"><Element guid="&lol;"/></Link></BimLvLinks>'
    )
    with pytest.raises(BimLvContainerError):
        read_container(_repack(good))


def test_unsafe_entry_path_rejected() -> None:
    data = _repack({LV_NAME: b"<GAEB/>", "../evil.xml": b"<x/>"})
    with pytest.raises(BimLvContainerError):
        read_container(data)


# ── LV-only container (best-effort manifest/links) ───────────────────────────


def test_lv_only_container_parses_with_warnings() -> None:
    lv_bytes = _members(write_container(_sample_positions(), _sample_mapping(), ModelReference()))[LV_NAME]
    parsed = read_container(_repack({LV_NAME: lv_bytes}))
    assert [p.ordinal for p in parsed.positions] == ["01.01.001", "01.01.002", "02.03.010"]
    assert parsed.mapping == {}
    assert parsed.model_ref == ModelReference()
    assert parsed.warnings  # missing manifest + links surfaced, not silent


def test_parsed_container_exposes_raw_lv_bytes() -> None:
    parsed = read_container(write_container(_sample_positions(), {}, ModelReference()))
    assert parsed.lv_gaeb_bytes.startswith(b"<?xml")
    assert b"<GAEB" in parsed.lv_gaeb_bytes


# ── interoperability with the platform GAEB importer (bonus) ─────────────────


@pytest.mark.asyncio
async def test_embedded_lv_is_importable_by_platform_gaeb_importer() -> None:
    """The embedded LV must be a real GAEB DA XML the platform importer reads."""
    try:
        from app.modules.boq.importers.gaeb_xml import GAEBXMLImporter
    except Exception:  # pragma: no cover - importer deps unavailable in this env
        pytest.skip("GAEB importer not importable in this environment")

    data = write_container(_sample_positions(), _sample_mapping(), _sample_model_ref())
    parsed = read_container(data)

    imported = await GAEBXMLImporter.parse(parsed.lv_gaeb_bytes)
    got = {p.ordinal: p for p in imported.positions}

    # Every LV position survives the standard GAEB import with its ordinal,
    # unit and quantity intact (proves the file is genuinely interoperable).
    for src in _sample_positions():
        assert src.ordinal in got, f"ordinal {src.ordinal} lost on GAEB import"
        assert got[src.ordinal].unit == src.unit
        assert Decimal(str(got[src.ordinal].quantity)) == src.quantity
