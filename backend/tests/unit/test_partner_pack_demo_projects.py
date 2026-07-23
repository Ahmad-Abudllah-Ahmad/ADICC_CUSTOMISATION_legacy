# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Integrity tests for the partner-pack flagship country projects.

Each active partner pack ships one fully worked-out demo project authored as
a standalone ``DemoTemplate`` under ``app/core/demo_packs/``. These templates
are merged into ``DEMO_TEMPLATES``, surfaced in ``DEMO_CATALOG``, and mapped
to their pack via ``PACK_DEMO_PROJECT`` so an active pack auto-installs its
country project on first boot.

This module asserts the wiring stays consistent:
1. Every discovered partner pack slug has a demo-project mapping.
2. Every mapped demo_id resolves to a loaded ``DemoTemplate``.
3. Every pack demo project appears in the marketplace catalog with the
   required keys and a derived ISO-2 country.
4. Each pack template is substantial and structurally valid (sections with
   items, allowed units, positive quantities/rates).
"""

from __future__ import annotations

import pytest

from app.core.demo_packs import PACK_TEMPLATES
from app.core.demo_projects import (
    DEMO_CATALOG,
    DEMO_TEMPLATES,
    PACK_DEMO_PROJECT,
)

# Units accepted by the BOQ position model / demo installer.
# Includes locale-authentic codes the flagship country demos use on purpose:
# Brazil "vb" (verba / lump sum), "un" (unidade), "mes" (month); India "MT"
# (metric tonne), "rm" (running metre); Canada "suite". The China GB/T
# 50500-2013 demo uses the standard Chinese measurement words: "项" (xiang,
# lump-sum work item, like "lsum"), "台" (tai, a machine/equipment set), "樘"
# (tang, a door/window leaf), "组" (zu, a group/set), "套" (tao, a set/system),
# "根" (gen, a long single piece such as a pile or rod).
_ALLOWED_UNITS = {
    "m2",
    "m3",
    "m",
    "t",
    "kg",
    "pcs",
    "lsum",
    "hour",
    "day",
    "month",
    "each",
    "ha",
    "l",
    "MT",
    "rm",
    "un",
    "vb",
    "mes",
    "suite",
    "项",
    "台",
    "樘",
    "组",
    "套",
    "根",
}

_CATALOG_BY_ID = {c["demo_id"]: c for c in DEMO_CATALOG}
_TEMPLATE_IDS = {t.demo_id for t in PACK_TEMPLATES}


def test_all_pack_slugs_have_a_demo_project() -> None:
    """Every installed partner pack maps to a flagship demo project."""
    from app.core.partner_pack.discovery import discover_packs

    slugs = {p.slug for p in discover_packs()}
    missing = sorted(slugs - set(PACK_DEMO_PROJECT))
    assert not missing, f"partner packs without a demo project mapping: {missing}"


def test_mapped_demo_ids_resolve_to_templates() -> None:
    """Each PACK_DEMO_PROJECT target is a real, loaded DemoTemplate."""
    for slug, demo_id in PACK_DEMO_PROJECT.items():
        assert demo_id in DEMO_TEMPLATES, f"{slug} -> {demo_id} not in DEMO_TEMPLATES"


def test_every_pack_resolves_to_exactly_two_demos() -> None:
    """Every discovered pack installs exactly two distinct, real demo projects.

    Some packs (the cross-region modular / renewables packs, and the small
    single-country ones) have no second demo that shares the flagship's country,
    so they pin an explicit ``demo_template_ids`` pair on the manifest. Whether a
    pack relies on the flagship + country-fill default or on an explicit list,
    the one-click installer must always land two in-market projects. This guards
    against the regression where ``aus`` / ``modular-prefab`` / ``renewables-epc``
    seeded only a single demo.
    """
    from app.core.partner_pack.discovery import discover_packs
    from app.core.partner_pack.full_install import _demo_install_list

    for pack in discover_packs():
        install_ids = _demo_install_list(pack.slug, 2)
        assert len(install_ids) == 2, f"{pack.slug} resolved {len(install_ids)} demo(s): {install_ids}"
        assert len(set(install_ids)) == 2, f"{pack.slug} resolved duplicate demos: {install_ids}"
        for demo_id in install_ids:
            assert demo_id in DEMO_TEMPLATES, f"{pack.slug} -> {demo_id} not in DEMO_TEMPLATES"


def test_explicit_demo_template_ids_resolve_to_templates() -> None:
    """Any pack that pins ``demo_template_ids`` references real templates."""
    from app.core.partner_pack.discovery import discover_packs

    for pack in discover_packs():
        for demo_id in pack.demo_template_ids:
            assert demo_id in DEMO_TEMPLATES, f"{pack.slug} demo_template_ids -> {demo_id} not in DEMO_TEMPLATES"


def test_pack_demos_present_in_catalog() -> None:
    """Each pack demo project has a marketplace catalog row with ISO-2 country."""
    required = {"demo_id", "name", "description", "country", "currency", "type", "sections", "positions"}
    for demo_id in PACK_DEMO_PROJECT.values():
        assert demo_id in _CATALOG_BY_ID, f"{demo_id} missing from DEMO_CATALOG"
        row = _CATALOG_BY_ID[demo_id]
        assert required <= set(row), f"{demo_id} catalog row missing keys: {required - set(row)}"
        assert len(row["country"]) == 2, f"{demo_id} country is not ISO-2: {row['country']!r}"
        assert row["positions"] > 0 and row["sections"] > 0


def test_pack_demos_have_a_populated_budget() -> None:
    """Each pack catalog row shows a real budget figure, not an empty cell.

    Pack templates carry no pre-formatted ``budget`` string in
    ``project_metadata`` (unlike the hand-authored built-in rows), so the
    catalog derives it from the priced section items. Regression guard for the
    bug where all pack rows rendered an empty budget on the dashboard demo card.
    """
    for demo_id in PACK_DEMO_PROJECT.values():
        row = _CATALOG_BY_ID[demo_id]
        budget = str(row.get("budget", ""))
        assert budget.strip(), f"{demo_id} catalog budget is empty"
        # Derived labels carry the currency code or a known symbol plus a
        # magnitude suffix (K/M) or a plain figure.
        assert any(ch.isdigit() for ch in budget), f"{demo_id} budget has no figure: {budget!r}"


@pytest.mark.parametrize("template", PACK_TEMPLATES, ids=lambda t: t.demo_id)
def test_pack_template_is_substantial_and_valid(template) -> None:  # noqa: ANN001
    """A flagship country project is large and structurally sound."""
    assert template.sections, f"{template.demo_id} has no sections"
    positions = sum(len(section[3]) for section in template.sections)
    assert positions >= 80, f"{template.demo_id} only has {positions} positions (expected >= 80)"
    assert template.currency and len(template.currency) == 3, f"{template.demo_id} bad currency"

    for section in template.sections:
        _ordinal, _title, _classification, items = section
        assert items, f"{template.demo_id} section {_ordinal} has no items"
        for item in items:
            ordinal, desc, unit, qty, rate, _cls = item
            assert unit in _ALLOWED_UNITS, f"{template.demo_id} {ordinal}: bad unit {unit!r}"
            assert qty > 0, f"{template.demo_id} {ordinal}: non-positive qty {qty}"
            assert rate >= 0, f"{template.demo_id} {ordinal}: negative rate {rate}"
            assert desc.strip(), f"{template.demo_id} {ordinal}: empty description"
