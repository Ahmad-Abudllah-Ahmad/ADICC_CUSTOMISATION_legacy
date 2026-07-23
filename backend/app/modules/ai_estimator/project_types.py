# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project-type taxonomy and per-type questionnaires for intake v2.

Curated, deterministic data (no ML), the same pattern as :mod:`taxonomy`. Ten
project types, each carrying:

* detection synonyms in EN / RU / DE so a free-text request can be matched to a
  type offline (substring match, the same technique as ``classify_trade``);
* a parameter questionnaire where every parameter is justified by the quantity
  it unlocks (a parameter that unlocks nothing is cut, enforced by a test);
* a curated work-package checklist where every package declares its foreman
  stages, candidate vector probes (in the catalogue's keyword-salad vocabulary),
  the quantity formula it uses, its trade bucket and its unit.

User-facing labels go through i18n (``aiest.ptype.<key>`` / ``aiest.param.<key>``
/ ``aiest.pkg.<key>``); this file carries English defaults plus the detection
synonyms. The intake API returns i18n keys, not hardcoded English prose, for
the question prompts and the "why we ask" justifications.

Foreman stages (the universal build sequence) are:
    demo -> structure -> rough -> close -> finish -> commission
Each maps onto one of the 12 OmniClass construction stages the catalogue
carries on its enriched collection (``construction_stage`` payload) so the
existing search plan's stage hard/soft filter can fire.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Foreman stage order + OmniClass mapping ──────────────────────────────────

# The universal build sequence. The composer emits one element-group per
# (package x stage) cell that has work, ordered by this sequence so the board
# reads top-to-bottom in build order.
FOREMAN_STAGES: tuple[str, ...] = (
    "demo",
    "structure",
    "rough",
    "close",
    "finish",
    "commission",
)

# Foreman stage -> OmniClass construction stage (the catalogue's
# ``construction_stage`` payload value), so ``build_search_plan`` can pin /
# boost the stage hard filter when the bound collection carries it. The MEP
# rough work lands on 09_MEP; structural alterations on 06_Superstructure.
FOREMAN_STAGE_TO_OMNICLASS: dict[str, str] = {
    "demo": "02_Demolition",
    "structure": "06_Superstructure",
    "rough": "09_MEP",
    "close": "07_Envelope",
    "finish": "10_Finishes",
    "commission": "12_Equipment",
}


# ── Dataclasses (the registry shape from the design) ─────────────────────────


@dataclass(frozen=True)
class ProjectParam:
    """One questionnaire parameter, justified by the quantity it unlocks.

    Attributes:
        key: Stable parameter key (e.g. ``"floor_area_m2"``).
        kind: One of ``number`` / ``choice`` / ``bool`` / ``length``.
        unit: Measurement unit suffix for number/length kinds, else None.
        required: Whether the parameter must be resolved before the sheet.
        choices: Allowed values for ``choice`` kinds, else None.
        unlocks: The ``qty_formula`` ids this parameter feeds; every entry must
            resolve to a real formula (asserted by a test). Drives the
            "why we ask" tooltip and lets the FSM skip a question whose answer
            is already known from the free text.
        round_group: Which clarification round (1, 2 or 3) this question lands
            in. Round 1 unlocks the most quantity; round 3 is nice-to-have.
        default: A sensible default applied when the param is still missing
            after the round cap, or None.
    """

    key: str
    kind: str
    unit: str | None
    required: bool
    unlocks: tuple[str, ...]
    round_group: int
    choices: tuple[str, ...] | None = None
    default: object | None = None


@dataclass(frozen=True)
class WorkPackage:
    """One curated work package (expands into package x stage element groups).

    Attributes:
        key: Stable package key (e.g. ``"wall_tiling"``).
        trade: One of :data:`taxonomy.TRADE_KEYWORDS` keys.
        default_on: In the curated checklist by default.
        stages: Ordered foreman stages this package spans.
        probes: Candidate vector phrasings in the catalogue's keyword-salad
            vocabulary (NOT natural sentences); the composer keeps the
            best-scoring one as the group description.
        qty_formula: The formula id from :mod:`quantities` (must resolve).
        unit: Measurement unit (m2 / m / m3 / pcs / lsum).
    """

    key: str
    trade: str
    default_on: bool
    stages: tuple[str, ...]
    probes: tuple[str, ...]
    qty_formula: str
    unit: str


@dataclass(frozen=True)
class ProjectType:
    """A curated project type: detection synonyms, params, packages."""

    key: str
    synonyms_en: tuple[str, ...]
    synonyms_ru: tuple[str, ...]
    synonyms_de: tuple[str, ...]
    params: tuple[ProjectParam, ...]
    packages: tuple[WorkPackage, ...]
    default_unit_system: str = "metric"


# ── Reusable parameter builders (keep the registry terse + consistent) ───────


def _area(key: str, round_group: int, unlocks: tuple[str, ...], *, required: bool = True) -> ProjectParam:
    return ProjectParam(key, "number", "m2", required, unlocks, round_group)


def _length(key: str, round_group: int, unlocks: tuple[str, ...], default: float | None = None) -> ProjectParam:
    return ProjectParam(key, "length", "m", False, unlocks, round_group, default=default)


def _count(key: str, round_group: int, unlocks: tuple[str, ...]) -> ProjectParam:
    return ProjectParam(key, "number", "pcs", False, unlocks, round_group)


def _bool(key: str, round_group: int, unlocks: tuple[str, ...], default: bool | None = None) -> ProjectParam:
    return ProjectParam(key, "bool", None, False, unlocks, round_group, default=default)


def _choice(
    key: str,
    round_group: int,
    choices: tuple[str, ...],
    unlocks: tuple[str, ...],
    *,
    required: bool = False,
) -> ProjectParam:
    return ProjectParam(key, "choice", None, required, unlocks, round_group, choices=choices)


_FINISH_LEVELS = ("economy", "standard", "premium")


# ── Reusable work packages (the residential / fit-out core) ──────────────────


def _pkg_demo_strip() -> WorkPackage:
    return WorkPackage(
        key="demo_strip",
        trade="demolition",
        default_on=True,
        stages=("demo",),
        probes=(
            "Demolition strip out interiors removal",
            "Repair and construction works demolition interiors",
        ),
        qty_formula="floor_area",
        unit="m2",
    )


def _pkg_debris() -> WorkPackage:
    return WorkPackage(
        key="debris_removal",
        trade="demolition",
        default_on=True,
        stages=("demo",),
        probes=(
            "Debris removal disposal construction waste",
            "Earthwork removal disposal volume",
        ),
        qty_formula="debris",
        unit="m3",
    )


def _pkg_screed() -> WorkPackage:
    return WorkPackage(
        key="floor_screed",
        trade="finishes",
        default_on=True,
        stages=("rough",),
        probes=(
            "Cement screed floor leveling",
            "Floors screed construction work area",
        ),
        qty_formula="floor_area",
        unit="m2",
    )


def _pkg_plaster() -> WorkPackage:
    return WorkPackage(
        key="wall_plaster",
        trade="finishes",
        default_on=True,
        stages=("close",),
        probes=(
            "Stucco work plaster walls interiors",
            "Render plastering finishing works",
        ),
        qty_formula="wall_full",
        unit="m2",
    )


def _pkg_wall_tiling() -> WorkPackage:
    return WorkPackage(
        key="wall_tiling",
        trade="finishes",
        default_on=True,
        stages=("demo", "finish"),
        probes=(
            "Ceramic tiling wall interior finishes",
            "Ceramic wall covering cladding interiors",
            "Tile finishing works wall",
        ),
        qty_formula="wall_net",
        unit="m2",
    )


def _pkg_floor_tiling() -> WorkPackage:
    return WorkPackage(
        key="floor_tiling",
        trade="finishes",
        default_on=True,
        stages=("finish",),
        probes=(
            "Ceramic tiling floor interior finishes",
            "Floors tile finishing works area",
        ),
        qty_formula="floor_area",
        unit="m2",
    )


def _pkg_painting_walls() -> WorkPackage:
    return WorkPackage(
        key="painting_walls",
        trade="finishes",
        default_on=True,
        stages=("finish",),
        probes=(
            "Painting work walls interiors",
            "Paint finishes interior two coats",
        ),
        qty_formula="wall_full",
        unit="m2",
    )


def _pkg_painting_ceiling() -> WorkPackage:
    return WorkPackage(
        key="painting_ceiling",
        trade="finishes",
        default_on=True,
        stages=("finish",),
        probes=(
            "Painting work ceiling interiors",
            "Paint finishes ceiling two coats",
        ),
        qty_formula="ceiling",
        unit="m2",
    )


def _pkg_plumbing_rough() -> WorkPackage:
    return WorkPackage(
        key="plumbing_first_fix",
        trade="mep_plumbing",
        default_on=False,
        stages=("rough",),
        probes=(
            "Internal sanitary and technical work water supply pipe",
            "Plumbing pipe drainage services",
        ),
        qty_formula="fixtures",
        unit="pcs",
    )


def _pkg_sanitary() -> WorkPackage:
    return WorkPackage(
        key="sanitary_install",
        trade="mep_plumbing",
        default_on=False,
        stages=("finish",),
        probes=(
            "Internal sanitary and technical work fixture install",
            "Sanitary ware installation equipment installation",
        ),
        qty_formula="fixtures",
        unit="pcs",
    )


def _pkg_electrical() -> WorkPackage:
    return WorkPackage(
        key="electrical_points",
        trade="mep_electrical",
        default_on=False,
        stages=("rough", "finish"),
        probes=(
            "Electrical installations wiring cable",
            "Electrical wire conduit services",
        ),
        qty_formula="points",
        unit="pcs",
    )


def _pkg_ventilation() -> WorkPackage:
    return WorkPackage(
        key="ventilation",
        trade="mep_mechanical",
        default_on=False,
        stages=("rough",),
        probes=(
            "Ventilation and air conditioning duct",
            "Air duct galvanized sheet steel installation",
        ),
        qty_formula="floor_area",
        unit="m2",
    )


def _pkg_waterproofing() -> WorkPackage:
    return WorkPackage(
        key="waterproofing",
        trade="envelope",
        default_on=True,
        stages=("close",),
        probes=(
            "Waterproofing tanking membrane wet area",
            "Insulation waterproofing finishing works",
        ),
        qty_formula="wall_full",
        unit="m2",
    )


def _pkg_commission() -> WorkPackage:
    return WorkPackage(
        key="commissioning",
        trade="other",
        default_on=True,
        stages=("commission",),
        probes=(
            "Commissioning testing balancing",
            "Commissioning works equipment",
        ),
        qty_formula="lump",
        unit="lsum",
    )


# ── The ten project types ────────────────────────────────────────────────────


def _kitchen_reno() -> ProjectType:
    return ProjectType(
        key="kitchen_reno",
        synonyms_en=("kitchen", "kitchen renovation", "kitchen refurb", "kitchen remodel"),
        synonyms_ru=("кухня", "ремонт кухни", "кухню", "кухни"),
        synonyms_de=("kueche", "küche", "kuechenumbau", "küchenumbau"),
        params=(
            _area("floor_area_m2", 1, ("floor_area", "ceiling", "wall_net")),
            ProjectParam("ceiling_height_m", "length", "m", False, ("wall_net",), 1, default=2.7),
            _length("perimeter_m", 2, ("wall_net",)),
            _choice("finish_level", 1, _FINISH_LEVELS, ("wall_net",), required=True),
            _bool("demolition", 1, ("floor_area", "debris"), default=True),
            _bool("wet_zone_tiling", 2, ("wall_net",), default=True),
            _bool("replace_plumbing", 2, ("fixtures",)),
            _bool("replace_electrical", 2, ("points",)),
            _length("cabinets_lm", 3, ("fixtures",)),
        ),
        packages=(
            _pkg_demo_strip(),
            _pkg_debris(),
            _pkg_screed(),
            _pkg_plaster(),
            _pkg_wall_tiling(),
            _pkg_floor_tiling(),
            _pkg_painting_walls(),
            _pkg_painting_ceiling(),
            _pkg_plumbing_rough(),
            _pkg_sanitary(),
            _pkg_electrical(),
            _pkg_ventilation(),
            _pkg_commission(),
        ),
    )


def _bathroom_reno() -> ProjectType:
    return ProjectType(
        key="bathroom_reno",
        synonyms_en=("bathroom", "bathroom renovation", "bathroom refurb", "wet room", "ensuite"),
        synonyms_ru=("санузел", "ванная", "ремонт ванной", "ванную", "санузла"),
        synonyms_de=("bad", "badezimmer", "badsanierung", "nasszelle"),
        params=(
            _area("floor_area_m2", 1, ("floor_area", "ceiling", "wall_full")),
            ProjectParam("ceiling_height_m", "length", "m", False, ("wall_full",), 1, default=2.7),
            _choice("finish_level", 1, _FINISH_LEVELS, ("wall_full",), required=True),
            _bool("demolition", 1, ("floor_area", "debris"), default=True),
            _bool("full_tiling", 1, ("wall_full",), default=True),
            _bool("waterproofing", 2, ("wall_full",), default=True),
            _count("fixtures_count", 2, ("fixtures",)),
            _bool("heated_floor", 3, ("floor_area",)),
            _bool("ventilation", 3, ("floor_area",)),
        ),
        packages=(
            _pkg_demo_strip(),
            _pkg_debris(),
            _pkg_screed(),
            _pkg_waterproofing(),
            _pkg_plaster(),
            _pkg_wall_tiling(),
            _pkg_floor_tiling(),
            _pkg_plumbing_rough(),
            _pkg_sanitary(),
            _pkg_electrical(),
            _pkg_ventilation(),
            _pkg_commission(),
        ),
    )


def _apartment_reno() -> ProjectType:
    return ProjectType(
        key="apartment_reno",
        synonyms_en=("apartment", "apartment renovation", "flat renovation", "flat refurb"),
        synonyms_ru=("квартира", "ремонт квартиры", "квартиру", "квартиры"),
        synonyms_de=("wohnung", "wohnungssanierung", "wohnungsrenovierung"),
        params=(
            _area("floor_area_m2", 1, ("floor_area", "ceiling", "wall_full")),
            _count("room_count", 1, ("fixtures",)),
            ProjectParam("ceiling_height_m", "length", "m", False, ("wall_full", "partition"), 1, default=2.7),
            _choice("finish_level", 1, _FINISH_LEVELS, ("wall_full",), required=True),
            _bool("demolition", 1, ("floor_area", "debris"), default=True),
            _count("wet_rooms_count", 1, ("fixtures",)),
            _bool("reconfigure_partitions", 2, ("partition",)),
            _length("partition_lm", 2, ("partition",)),
            _count("replace_windows", 2, ("wall_full",)),
            _count("replace_doors", 2, ("wall_full",)),
            _bool("rewire", 2, ("points",)),
            _bool("replumb", 2, ("fixtures",)),
            _choice("hvac", 3, ("none", "radiators", "underfloor", "split"), ("floor_area",)),
            _choice("flooring_type", 3, ("tile", "laminate", "parquet", "vinyl"), ("floor_area",)),
        ),
        packages=(
            _pkg_demo_strip(),
            _pkg_debris(),
            WorkPackage(
                key="partition_new",
                trade="masonry",
                default_on=False,
                stages=("structure",),
                probes=(
                    "Brick and block structures wall partition",
                    "Wooden structures wall interior partitions",
                ),
                qty_formula="partition",
                unit="m2",
            ),
            _pkg_screed(),
            _pkg_plaster(),
            _pkg_floor_tiling(),
            _pkg_painting_walls(),
            _pkg_painting_ceiling(),
            _pkg_plumbing_rough(),
            _pkg_sanitary(),
            _pkg_electrical(),
            _pkg_ventilation(),
            _pkg_commission(),
        ),
    )


def _house_new() -> ProjectType:
    return ProjectType(
        key="house_new",
        synonyms_en=("house", "new house", "house build", "single-family house", "new build"),
        synonyms_ru=("дом", "новый дом", "строительство дома", "коттедж"),
        synonyms_de=("einfamilienhaus", "neubau", "haus", "hausbau"),
        params=(
            _area("gross_floor_area_m2", 1, ("floor_area", "ceiling")),
            _count("storeys", 1, ("wall_full",)),
            _area("footprint_m2", 1, ("earthworks",), required=False),
            _choice(
                "wall_construction", 1, ("masonry", "timber_frame", "concrete", "sip"), ("wall_full",), required=True
            ),
            _choice("roof_type", 1, ("pitched", "flat"), ("slope",), required=True),
            _choice("foundation_type", 2, ("strip", "raft", "piles"), ("earthworks",)),
            _bool("basement", 2, ("earthworks",)),
            ProjectParam("ceiling_height_m", "length", "m", False, ("wall_full",), 2, default=2.7),
            _choice("finish_level", 2, _FINISH_LEVELS, ("wall_full",)),
            _bool("garage", 3, ("floor_area",)),
            _choice("mep_scope", 3, ("basic", "full"), ("points", "fixtures")),
            _area("site_area_m2", 3, ("site_area",), required=False),
            ProjectParam("roof_area_m2", "number", "m2", False, ("slope",), 1),
            ProjectParam("pitch_deg", "number", None, False, ("slope",), 2),
        ),
        packages=(
            WorkPackage(
                key="excavation",
                trade="earthworks",
                default_on=True,
                stages=("demo",),
                probes=(
                    "Earthwork excavation foundation trench",
                    "Tunnel excavation earthwork volume",
                ),
                qty_formula="earthworks",
                unit="m3",
            ),
            WorkPackage(
                key="foundation",
                trade="foundations",
                default_on=True,
                stages=("structure",),
                probes=(
                    "Reinforced concrete foundation footing slab",
                    "Concrete foundations construction work volume",
                ),
                qty_formula="floor_area",
                unit="m2",
            ),
            WorkPackage(
                key="superstructure_walls",
                trade="masonry",
                default_on=True,
                stages=("structure",),
                probes=(
                    "Brick and block structures wall external",
                    "Masonry brick walls envelope shell",
                ),
                qty_formula="wall_full",
                unit="m2",
            ),
            WorkPackage(
                key="roof_structure",
                trade="envelope",
                default_on=True,
                stages=("close",),
                probes=(
                    "Wooden structures roof rafters timber",
                    "Roof covering envelope construction work",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            _pkg_screed(),
            _pkg_plaster(),
            _pkg_painting_walls(),
            _pkg_plumbing_rough(),
            _pkg_electrical(),
            _pkg_ventilation(),
            _pkg_commission(),
        ),
    )


def _roof() -> ProjectType:
    return ProjectType(
        key="roof",
        synonyms_en=("roof", "roofing", "roof works", "roof repair", "re-roof"),
        synonyms_ru=("кровля", "крыша", "ремонт кровли", "кровлю"),
        synonyms_de=("dach", "dachsanierung", "dacharbeiten", "umdeckung"),
        params=(
            _area("roof_area_m2", 1, ("slope",)),
            _choice("roof_type", 1, ("pitched", "flat"), ("slope",), required=True),
            ProjectParam("pitch_deg", "number", None, False, ("slope",), 2),
            _choice("covering", 1, ("tile", "metal", "membrane", "shingle"), ("slope",), required=True),
            _bool("insulation", 2, ("slope",)),
            _bool("structure_replacement", 2, ("slope",)),
            _length("gutters_lm", 3, ("fencing",)),
            _count("skylights_count", 3, ("slope",)),
            _bool("demolition_existing", 1, ("slope", "debris"), default=True),
        ),
        packages=(
            WorkPackage(
                key="roof_strip",
                trade="demolition",
                default_on=True,
                stages=("demo",),
                probes=(
                    "Roof covering demolition strip removal",
                    "Repair and construction works roof demolition",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            WorkPackage(
                key="roof_structure",
                trade="envelope",
                default_on=False,
                stages=("structure",),
                probes=(
                    "Wooden structures roof rafters timber",
                    "Roof sheathing structure construction work",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            WorkPackage(
                key="roof_insulation",
                trade="envelope",
                default_on=False,
                stages=("close",),
                probes=(
                    "Insulation roof thermal finishing works",
                    "Insulation waterproofing roof envelope",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            WorkPackage(
                key="roof_covering",
                trade="envelope",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Roof covering tile metal envelope finishes",
                    "Roofing covering construction work area",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            WorkPackage(
                key="gutters",
                trade="envelope",
                default_on=False,
                stages=("finish",),
                probes=(
                    "Gutters downpipe rainwater linear",
                    "Sheet metal gutters envelope installation",
                ),
                qty_formula="fencing",
                unit="m",
            ),
            _pkg_commission(),
        ),
    )


def _facade() -> ProjectType:
    return ProjectType(
        key="facade",
        synonyms_en=("facade", "facade renovation", "external wall", "rendering", "cladding works"),
        synonyms_ru=("фасад", "отделка фасада", "фасадные работы", "фасада"),
        synonyms_de=("fassade", "fassadensanierung", "wdvs", "putzfassade"),
        params=(
            _area("facade_area_m2", 1, ("facade_net", "facade_gross")),
            _choice(
                "system",
                1,
                ("render_etics", "ventilated", "cladding", "paint_only"),
                ("facade_net",),
                required=True,
            ),
            ProjectParam("insulation_thickness_mm", "number", "mm", False, ("facade_net",), 2),
            _area("openings_area_m2", 1, ("facade_net",), required=False),
            _bool("scaffolding", 1, ("facade_gross",), default=True),
            _choice("substrate_prep", 2, ("none", "repair", "full_strip"), ("facade_net",)),
            _count("storeys", 2, ("facade_gross",)),
            _bool("plinth_treatment", 3, ("facade_net",)),
            _count("color_coats", 3, ("facade_net",)),
        ),
        packages=(
            WorkPackage(
                key="scaffolding",
                trade="sitework",
                default_on=True,
                stages=("demo",),
                probes=(
                    "Scaffolding facade external works",
                    "Scaffold erection construction work area",
                ),
                qty_formula="facade_gross",
                unit="m2",
            ),
            WorkPackage(
                key="facade_prep",
                trade="envelope",
                default_on=True,
                stages=("close",),
                probes=(
                    "Facade substrate preparation repair render",
                    "Stucco work facade preparation walls",
                ),
                qty_formula="facade_net",
                unit="m2",
            ),
            WorkPackage(
                key="facade_system",
                trade="envelope",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Exterior facade cladding ventilated curtain wall",
                    "Facade render ETICS insulation envelope finishes",
                ),
                qty_formula="facade_net",
                unit="m2",
            ),
            WorkPackage(
                key="facade_paint",
                trade="finishes",
                default_on=False,
                stages=("finish",),
                probes=(
                    "Painting work facade external coats",
                    "Paint finishes facade exterior",
                ),
                qty_formula="facade_net",
                unit="m2",
            ),
            _pkg_commission(),
        ),
    )


def _extension() -> ProjectType:
    return ProjectType(
        key="extension",
        synonyms_en=("extension", "building extension", "house extension", "annex"),
        synonyms_ru=("пристройка", "расширение", "пристройку"),
        synonyms_de=("anbau", "erweiterung", "hauserweiterung"),
        params=(
            _area("extension_floor_area_m2", 1, ("floor_area", "earthworks")),
            _count("storeys", 1, ("wall_full",)),
            _choice(
                "wall_construction", 1, ("masonry", "timber_frame", "concrete", "sip"), ("wall_full",), required=True
            ),
            _choice("roof_type", 1, ("pitched", "flat"), ("slope",), required=True),
            _choice("foundation_type", 2, ("strip", "raft", "piles"), ("earthworks",)),
            _bool("connect_to_existing", 1, ("floor_area",), default=True),
            ProjectParam("ceiling_height_m", "length", "m", False, ("wall_full",), 2, default=2.7),
            _choice("finish_level", 2, _FINISH_LEVELS, ("wall_full",)),
            _choice("mep_extension", 3, ("none", "basic", "full"), ("points", "fixtures")),
            ProjectParam("excavation_depth_m", "number", "m", False, ("earthworks",), 3),
            ProjectParam("roof_area_m2", "number", "m2", False, ("slope",), 1),
            ProjectParam("pitch_deg", "number", None, False, ("slope",), 2),
        ),
        packages=(
            WorkPackage(
                key="excavation",
                trade="earthworks",
                default_on=True,
                stages=("demo",),
                probes=(
                    "Earthwork excavation foundation trench",
                    "Earthwork excavation volume construction work",
                ),
                qty_formula="earthworks",
                unit="m3",
            ),
            WorkPackage(
                key="foundation",
                trade="foundations",
                default_on=True,
                stages=("structure",),
                probes=(
                    "Reinforced concrete foundation footing slab",
                    "Concrete foundations construction work",
                ),
                qty_formula="floor_area",
                unit="m2",
            ),
            WorkPackage(
                key="superstructure_walls",
                trade="masonry",
                default_on=True,
                stages=("structure",),
                probes=(
                    "Brick and block structures wall external",
                    "Masonry brick walls envelope shell",
                ),
                qty_formula="wall_full",
                unit="m2",
            ),
            WorkPackage(
                key="connection_making_good",
                trade="masonry",
                default_on=False,
                stages=("structure",),
                probes=(
                    "Breakthrough making good masonry opening",
                    "Repair and construction works wall opening",
                ),
                qty_formula="lump",
                unit="lsum",
            ),
            WorkPackage(
                key="roof_covering",
                trade="envelope",
                default_on=True,
                stages=("close",),
                probes=(
                    "Roof covering envelope construction work",
                    "Roofing covering area finishes",
                ),
                qty_formula="slope",
                unit="m2",
            ),
            _pkg_plaster(),
            _pkg_painting_walls(),
            _pkg_electrical(),
            _pkg_commission(),
        ),
    )


def _commercial_fitout() -> ProjectType:
    return ProjectType(
        key="commercial_fitout",
        synonyms_en=("fit-out", "fitout", "office fit-out", "office refurb", "tenant fit-out"),
        synonyms_ru=("офис", "ремонт офиса", "офиса", "отделка офиса"),
        synonyms_de=("ausbau", "mieterausbau", "bueroausbau", "büroausbau"),
        params=(
            _area("floor_area_m2", 1, ("floor_area", "ceiling")),
            _choice("category", 1, ("shell_and_core", "cat_a", "cat_b"), ("floor_area",), required=True),
            _choice("ceiling_type", 1, ("suspended", "exposed", "mf"), ("ceiling",), required=True),
            _length("partition_lm", 1, ("partition",)),
            _bool("raised_floor", 2, ("floor_area",)),
            _choice("hvac_scope", 2, ("none", "vav", "fcu", "vrf"), ("floor_area",)),
            _choice("small_power_density", 2, ("low", "medium", "high"), ("points",)),
            _choice("lighting", 2, ("led_panel", "track", "feature"), ("points",)),
            _bool("sprinklers", 3, ("floor_area",)),
            _count("data_outlets_count", 3, ("points",)),
            _choice("finishes_level", 2, _FINISH_LEVELS, ("floor_area",)),
            ProjectParam("ceiling_height_m", "length", "m", False, ("partition",), 2, default=2.7),
        ),
        packages=(
            _pkg_demo_strip(),
            WorkPackage(
                key="partition_new",
                trade="masonry",
                default_on=True,
                stages=("structure",),
                probes=(
                    "Wooden structures wall interior partitions",
                    "Drywall partition stud finishing works",
                ),
                qty_formula="partition",
                unit="m2",
            ),
            WorkPackage(
                key="ceiling_suspended",
                trade="finishes",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Suspended ceiling grid finishing works",
                    "Ceiling tile suspended finishes area",
                ),
                qty_formula="ceiling",
                unit="m2",
            ),
            _pkg_screed(),
            WorkPackage(
                key="flooring_finish",
                trade="finishes",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Floors carpet vinyl finishing works",
                    "Floor covering finishes area",
                ),
                qty_formula="floor_area",
                unit="m2",
            ),
            _pkg_painting_walls(),
            _pkg_electrical(),
            WorkPackage(
                key="hvac_fitout",
                trade="mep_mechanical",
                default_on=False,
                stages=("rough",),
                probes=(
                    "Ventilation and air conditioning duct",
                    "Air conditioning FCU VRF installation",
                ),
                qty_formula="floor_area",
                unit="m2",
            ),
            _pkg_commission(),
        ),
    )


def _landscaping() -> ProjectType:
    return ProjectType(
        key="landscaping",
        synonyms_en=("landscaping", "external works", "garden", "hard landscaping", "soft landscaping"),
        synonyms_ru=("благоустройство", "озеленение", "ландшафт", "благоустройства"),
        synonyms_de=("garten", "aussenanlagen", "außenanlagen", "gartenbau"),
        params=(
            _area("site_area_m2", 1, ("site_area",)),
            _area("paving_area_m2", 1, ("paving",)),
            _choice("paving_type", 1, ("block", "asphalt", "gravel", "concrete"), ("paving",), required=True),
            _area("planting_area_m2", 1, ("planting",), required=False),
            _area("turf_area_m2", 2, ("planting",), required=False),
            _length("fencing_lm", 1, ("fencing",)),
            _length("retaining_wall_lm", 2, ("fencing",)),
            _bool("drainage", 2, ("paving",)),
            _bool("lighting", 3, ("paving",)),
            _bool("irrigation", 3, ("planting",)),
            ProjectParam("earthworks_volume_m3", "number", "m3", False, ("earthworks",), 3),
        ),
        packages=(
            WorkPackage(
                key="site_clearance",
                trade="earthworks",
                default_on=True,
                stages=("demo",),
                probes=(
                    "Earthwork site clearance grading",
                    "Earthwork excavation site preparation",
                ),
                qty_formula="earthworks",
                unit="m3",
            ),
            WorkPackage(
                key="paving",
                trade="sitework",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Paving block asphalt external works",
                    "Sitework paving construction work area",
                ),
                qty_formula="paving",
                unit="m2",
            ),
            WorkPackage(
                key="fencing",
                trade="sitework",
                default_on=True,
                stages=("finish",),
                probes=(
                    "Fencing external works linear",
                    "Sitework fencing construction work",
                ),
                qty_formula="fencing",
                unit="m",
            ),
            WorkPackage(
                key="planting",
                trade="sitework",
                default_on=False,
                stages=("finish",),
                probes=(
                    "Planting turf landscaping external works",
                    "Sitework planting soft landscaping area",
                ),
                qty_formula="planting",
                unit="m2",
            ),
            WorkPackage(
                key="drainage",
                trade="mep_plumbing",
                default_on=False,
                stages=("rough",),
                probes=(
                    "Drainage external works pipe",
                    "Internal sanitary and technical work drainage",
                ),
                qty_formula="paving",
                unit="m2",
            ),
            _pkg_commission(),
        ),
    )


def _mep_retrofit() -> ProjectType:
    return ProjectType(
        key="mep_retrofit",
        synonyms_en=("mep", "mep retrofit", "services upgrade", "m&e", "building services"),
        synonyms_ru=("инженерные сети", "замена коммуникаций", "коммуникации", "инженерка"),
        synonyms_de=("haustechnik", "tga", "tga-sanierung", "gebaeudetechnik", "gebäudetechnik"),
        params=(
            _area("floor_area_m2", 1, ("floor_area", "points")),
            _choice(
                "disciplines",
                1,
                ("electrical", "plumbing", "heating", "ventilation", "cooling"),
                ("points", "fixtures", "floor_area"),
                required=True,
            ),
            _choice("building_type", 1, ("residential", "office", "retail"), ("points",), required=True),
            _choice("heating_system", 2, ("radiators", "underfloor", "air"), ("fixtures",)),
            _choice("points_density", 2, ("low", "medium", "high"), ("points",)),
            _count("riser_count", 2, ("fixtures",)),
            _bool("plant_replacement", 1, ("fixtures",)),
            _choice("ceiling_access", 3, ("suspended", "surface"), ("floor_area",)),
            _bool("commissioning", 3, ("floor_area",), default=True),
        ),
        packages=(
            _pkg_demo_strip(),
            WorkPackage(
                key="electrical_distribution",
                trade="mep_electrical",
                default_on=True,
                stages=("rough", "finish"),
                probes=(
                    "Electrical installations wiring cable distribution",
                    "Electrical wire conduit switchgear services",
                ),
                qty_formula="points",
                unit="pcs",
            ),
            WorkPackage(
                key="plumbing_services",
                trade="mep_plumbing",
                default_on=False,
                stages=("rough", "finish"),
                probes=(
                    "Internal sanitary and technical work water supply pipe",
                    "Plumbing pipe drainage services",
                ),
                qty_formula="fixtures",
                unit="pcs",
            ),
            WorkPackage(
                key="heating_install",
                trade="mep_mechanical",
                default_on=False,
                stages=("rough", "finish"),
                probes=(
                    "Heating radiator panel installation",
                    "Internal sanitary and technical work heating pipe",
                ),
                qty_formula="fixtures",
                unit="pcs",
            ),
            _pkg_ventilation(),
            WorkPackage(
                key="plant_replacement",
                trade="mep_mechanical",
                default_on=False,
                stages=("rough",),
                probes=(
                    "Boiler AHU plant equipment installation",
                    "Major equipment installation commissioning",
                ),
                qty_formula="lump",
                unit="lsum",
            ),
            _pkg_commission(),
        ),
    )


# ── The registry ─────────────────────────────────────────────────────────────

_TYPES: tuple[ProjectType, ...] = (
    _kitchen_reno(),
    _bathroom_reno(),
    _apartment_reno(),
    _house_new(),
    _roof(),
    _facade(),
    _extension(),
    _commercial_fitout(),
    _landscaping(),
    _mep_retrofit(),
)

PROJECT_TYPES: dict[str, ProjectType] = {pt.key: pt for pt in _TYPES}

# Stable display order for the type tiles (residential / fit-out first, the
# usual free-text requests, then the larger build types).
PROJECT_TYPE_ORDER: tuple[str, ...] = tuple(pt.key for pt in _TYPES)

# English default labels (UI translates via ``aiest.ptype.<key>``).
PROJECT_TYPE_LABELS: dict[str, str] = {
    "kitchen_reno": "Kitchen renovation",
    "bathroom_reno": "Bathroom renovation",
    "apartment_reno": "Apartment renovation",
    "house_new": "New house (single-family)",
    "roof": "Roof works",
    "facade": "Facade / external wall",
    "extension": "Building extension",
    "commercial_fitout": "Commercial fit-out",
    "landscaping": "Landscaping / external works",
    "mep_retrofit": "MEP retrofit",
}


def get_project_type(key: str) -> ProjectType | None:
    """Return the project type for ``key`` or None."""
    return PROJECT_TYPES.get(key)


def detect_project_type(text: str) -> tuple[str | None, int]:
    """Deterministically detect a project type from free text (offline path).

    Substring-matches the normalised text against every type's EN / RU / DE
    synonyms (the same technique as ``classify_trade``), counting how many
    distinct types matched. Returns ``(key_or_None, match_count)``:

    * exactly one type matched -> ``(that_key, 1)`` (the offline path selects it
      with a null confidence: deterministic, not probabilistic);
    * zero or several matched -> ``(None, count)`` so the caller shows the type
      tiles for a manual pick.

    Args:
        text: The raw free-text request.

    Returns:
        ``(detected_key_or_None, number_of_distinct_types_that_matched)``.
    """
    haystack = (text or "").lower()
    if not haystack.strip():
        return None, 0
    matched: list[tuple[int, str]] = []
    for pt in _TYPES:
        best = _best_synonym_len(haystack, pt)
        if best > 0:
            matched.append((best, pt.key))
    if not matched:
        return None, 0
    if len(matched) == 1:
        return matched[0][1], 1
    # Several matched: if a single type matched on a strictly longer (more
    # specific) synonym than every other, prefer it - "ремонт ванной" should
    # win over a bare "дом" substring that never appears. Otherwise ambiguous.
    matched.sort(reverse=True)
    if matched[0][0] > matched[1][0]:
        return matched[0][1], len(matched)
    return None, len(matched)


def _best_synonym_len(haystack: str, pt: ProjectType) -> int:
    """Length of the longest synonym of ``pt`` present in ``haystack`` (0 none)."""
    best = 0
    for syn in (*pt.synonyms_en, *pt.synonyms_ru, *pt.synonyms_de):
        s = syn.lower().strip()
        if s and s in haystack and len(s) > best:
            best = len(s)
    return best


def params_for_round(pt: ProjectType, round_idx: int) -> tuple[ProjectParam, ...]:
    """Return the parameters whose ``round_group`` equals ``round_idx`` (1..3)."""
    return tuple(p for p in pt.params if p.round_group == round_idx)


def default_packages(pt: ProjectType) -> tuple[WorkPackage, ...]:
    """Return the packages marked ``default_on`` for the curated checklist."""
    return tuple(p for p in pt.packages if p.default_on)


def package_by_key(pt: ProjectType, key: str) -> WorkPackage | None:
    """Return the work package ``key`` within ``pt`` or None."""
    for pkg in pt.packages:
        if pkg.key == key:
            return pkg
    return None


# ── Stage-dependency DAG (the foreman precedence logic, section 4.2) ─────────
#
# The universal stage order (:data:`FOREMAN_STAGES`) already gives the global
# top-to-bottom build sequence the board reads in. On top of that the foreman
# logic encodes specific PACKAGE-PAIR precedence: a successor package whose work
# physically depends on a prerequisite package being done first. These rules are
# ADVISORY (founder decision 4: "AI proposes, human confirms") - they never
# block the board, they only surface a yellow note when the selected package set
# violates a dependency (e.g. tiling scheduled with no plaster substrate, or a
# wall finished before its first-fix services are roughed in).
#
# Each entry is ``successor_package_key -> (prerequisite_package_key, ...)``.
# The keys are the curated ``WorkPackage.key`` values across the residential /
# fit-out types where the build sequence matters most; a package not listed has
# no advisory prerequisite. The examples carried verbatim from the design:
#
#   * demo.remove_tiling (demo_strip) precedes finish.wall_tiling.
#   * rough.plumbing_first_fix precedes finish.fixtures (sanitary_install) and
#     close.plaster on the same wall.
#   * rough.screed (floor_screed) precedes finish.floor_tiling.
#   * rough.electrical_first_fix (electrical_points) precedes close.plaster.
#   * close.plaster (wall_plaster) precedes finish.painting and finish.wall_tiling.
STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    # A wall cannot be plastered until first-fix services are roughed in and old
    # finishes stripped.
    "wall_plaster": ("demo_strip", "electrical_points", "plumbing_first_fix"),
    # Wet-area tanking goes on after the substrate is stripped, before tiling.
    "waterproofing": ("demo_strip",),
    # Tiling needs the wall stripped and (where present) plastered/tanked first.
    "wall_tiling": ("demo_strip", "wall_plaster", "waterproofing"),
    # Floor tiling lands on the cured screed.
    "floor_tiling": ("floor_screed",),
    # A finished floor finish lands on the screed too.
    "flooring_finish": ("floor_screed",),
    # Painting is the last wet trade: plaster substrate must be in.
    "painting_walls": ("wall_plaster",),
    "painting_ceiling": ("wall_plaster",),
    # Sanitary ware is set after its first-fix pipework.
    "sanitary_install": ("plumbing_first_fix",),
    # Superstructure walls rise off the foundation; the roof closes onto walls.
    "superstructure_walls": ("foundation",),
    "roof_structure": ("superstructure_walls",),
    "roof_covering": ("roof_structure", "roof_strip"),
    "roof_insulation": ("roof_strip",),
    # A facade system goes on after the substrate prep.
    "facade_system": ("facade_prep",),
    "facade_paint": ("facade_system", "facade_prep"),
    # Foundations follow excavation.
    "foundation": ("excavation",),
}


def dependency_warnings(pt: ProjectType, selected_keys: set[str]) -> list[dict[str, str]]:
    """Return advisory foreman-sequence warnings for a selected package set.

    For every selected package that declares prerequisites in
    :data:`STAGE_DEPENDENCIES`, emit one advisory note per prerequisite that is
    NOT in the selected set. The note names the successor, the missing
    prerequisite and the foreman stages involved, so the UI can render a yellow
    "tiling is scheduled before its plaster substrate" hint.

    These are never blocking (founder decision 4). A prerequisite that exists in
    the type but was deselected, or one that the type does not carry at all, both
    surface the same honest "no <prereq> scheduled before <successor>" advisory -
    the human decides whether that is intentional (e.g. tiling onto an existing
    sound substrate with no new plaster).

    Args:
        pt: The resolved project type (used to map keys to their foreman stages
            and skip prerequisites the type does not even offer).
        selected_keys: The package keys currently selected on the board.

    Returns:
        A list of ``{successor, prerequisite, successor_stage,
        prerequisite_stage, code}`` dicts, ordered by the successor's first
        foreman stage so the warnings read in build order. ``code`` is a stable
        i18n key (``aiest.dep.missing_prereq``) the UI can translate.
    """
    offered = {pkg.key for pkg in pt.packages}
    by_key = {pkg.key: pkg for pkg in pt.packages}
    warnings: list[dict[str, str]] = []
    for succ in selected_keys:
        prereqs = STAGE_DEPENDENCIES.get(succ)
        if not prereqs:
            continue
        succ_pkg = by_key.get(succ)
        succ_stage = succ_pkg.stages[-1] if succ_pkg and succ_pkg.stages else ""
        for prereq in prereqs:
            # Only warn about a prerequisite this type actually offers (so a
            # kitchen never warns about a missing roof); skip when it is also
            # selected (the sequence is satisfied).
            if prereq not in offered or prereq in selected_keys:
                continue
            prereq_pkg = by_key.get(prereq)
            prereq_stage = prereq_pkg.stages[0] if prereq_pkg and prereq_pkg.stages else ""
            warnings.append(
                {
                    "code": "aiest.dep.missing_prereq",
                    "successor": succ,
                    "prerequisite": prereq,
                    "successor_stage": succ_stage,
                    "prerequisite_stage": prereq_stage,
                }
            )
    warnings.sort(key=lambda w: _FOREMAN_INDEX.get(w["successor_stage"], len(FOREMAN_STAGES)))
    return warnings


# Stage -> index lookup for ordering warnings in build sequence (built once).
_FOREMAN_INDEX: dict[str, int] = {stage: i for i, stage in enumerate(FOREMAN_STAGES)}
