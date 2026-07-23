# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Canonical assembly templates - platform-wide library seed.

This module ships 25 pre-built, canonical assembly templates that cover
the most common construction recipes (concrete walls, brick walls,
drywall partitions, slabs, roofs, finishes, MEP, structural columns,
beams, excavation). Templates are catalogue-agnostic: each component is
defined by a free-text ``cost_match_query`` that the apply endpoint
matches against the project's bound cost catalogue at runtime via the
``costs.matcher`` lexical/semantic search.

Schema of a single template dict::

    {
        "name": str,                  # canonical English name
        "name_translations": {        # DE / RU / ES at minimum
            "de": str, "ru": str, "es": str,
        },
        "category": str,              # concrete | masonry | drywall | ...
        "unit": str,                  # m, m2, m3, kg, pcs, lsum
        "components": [
            {
                "cost_match_query": str,  # free-text catalogue search query
                "factor": float,          # multiplier per unit of assembly
                "unit": str,              # component unit
                "role": str,              # material | labor | equipment | ...
                "description": str,       # human-readable component label
            },
            ...
        ],
        "classification": {
            "din276": str,            # DIN 276 KG code, e.g. "330"
            "masterformat": str,      # MasterFormat division, e.g. "03 30 00"
        },
        "tags": list[str],
    }

The seeder (``repository.seed_assembly_templates``) inserts these on
first call and upserts on subsequent calls keyed by ``name``.
"""

from __future__ import annotations

from typing import Any

# Canonical assembly templates. Order is meaningful only for
# deterministic seed reads in tests - the upsert is keyed by name.
ASSEMBLY_TEMPLATES: list[dict[str, Any]] = [
    # ── Concrete walls ──────────────────────────────────────────────────
    {
        "name": "Reinforced concrete wall C25/30 d=20cm",
        "name_translations": {
            "de": "Stahlbetonwand C25/30 d=20cm",
            "ru": "Железобетонная стена C25/30 d=20см",
            "es": "Muro de hormigón armado C25/30 d=20cm",
        },
        "category": "concrete",
        "unit": "m3",
        "components": [
            {
                "cost_match_query": "concrete C25/30 ready-mix",
                "factor": 1.0,
                "unit": "m3",
                "role": "material",
                "description": "Ready-mix concrete C25/30",
            },
            {
                "cost_match_query": "rebar reinforcement steel",
                "factor": 90.0,
                "unit": "kg",
                "role": "material",
                "description": "Rebar reinforcement",
            },
            {
                "cost_match_query": "wall formwork plywood",
                "factor": 10.0,
                "unit": "m2",
                "role": "material",
                "description": "Wall formwork",
            },
            {
                "cost_match_query": "concrete pouring labor",
                "factor": 2.5,
                "unit": "h",
                "role": "labor",
                "description": "Concrete placement labor",
            },
        ],
        "classification": {"din276": "331", "masterformat": "03 30 00"},
        "tags": ["concrete", "wall", "structural", "rc", "C25/30"],
    },
    {
        "name": "Reinforced concrete wall C30/37 d=24cm",
        "name_translations": {
            "de": "Stahlbetonwand C30/37 d=24cm",
            "ru": "Железобетонная стена C30/37 d=24см",
            "es": "Muro de hormigón armado C30/37 d=24cm",
        },
        "category": "concrete",
        "unit": "m3",
        "components": [
            {
                "cost_match_query": "concrete C30/37 ready-mix",
                "factor": 1.0,
                "unit": "m3",
                "role": "material",
                "description": "Ready-mix concrete C30/37",
            },
            {
                "cost_match_query": "rebar reinforcement steel",
                "factor": 110.0,
                "unit": "kg",
                "role": "material",
                "description": "Rebar reinforcement",
            },
            {
                "cost_match_query": "wall formwork plywood",
                "factor": 8.33,
                "unit": "m2",
                "role": "material",
                "description": "Wall formwork (both sides)",
            },
            {
                "cost_match_query": "concrete pouring labor",
                "factor": 2.8,
                "unit": "h",
                "role": "labor",
                "description": "Concrete placement labor",
            },
        ],
        "classification": {"din276": "331", "masterformat": "03 30 00"},
        "tags": ["concrete", "wall", "structural", "rc", "C30/37"],
    },
    # ── Brick / KS walls ────────────────────────────────────────────────
    {
        "name": "KSL sand-lime brick wall 11.5cm",
        "name_translations": {
            "de": "Kalksandstein-Wand KSL 11,5cm",
            "ru": "Стена из силикатного кирпича 11,5см",
            "es": "Muro de ladrillo silicocalcáreo 11,5cm",
        },
        "category": "masonry",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "sand lime brick KSL 11.5",
                "factor": 24.0,
                "unit": "pcs",
                "role": "material",
                "description": "KSL sand-lime brick",
            },
            {
                "cost_match_query": "mortar masonry M5",
                "factor": 0.012,
                "unit": "m3",
                "role": "material",
                "description": "Masonry mortar",
            },
            {
                "cost_match_query": "mason labor brick laying",
                "factor": 0.7,
                "unit": "h",
                "role": "labor",
                "description": "Mason labor",
            },
        ],
        "classification": {"din276": "331", "masterformat": "04 20 00"},
        "tags": ["masonry", "wall", "ksl", "brick"],
    },
    {
        "name": "KSL sand-lime brick wall 17.5cm",
        "name_translations": {
            "de": "Kalksandstein-Wand KSL 17,5cm",
            "ru": "Стена из силикатного кирпича 17,5см",
            "es": "Muro de ladrillo silicocalcáreo 17,5cm",
        },
        "category": "masonry",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "sand lime brick KSL 17.5",
                "factor": 36.0,
                "unit": "pcs",
                "role": "material",
                "description": "KSL sand-lime brick",
            },
            {
                "cost_match_query": "mortar masonry M5",
                "factor": 0.018,
                "unit": "m3",
                "role": "material",
                "description": "Masonry mortar",
            },
            {
                "cost_match_query": "mason labor brick laying",
                "factor": 0.95,
                "unit": "h",
                "role": "labor",
                "description": "Mason labor",
            },
        ],
        "classification": {"din276": "331", "masterformat": "04 20 00"},
        "tags": ["masonry", "wall", "ksl", "brick"],
    },
    # ── Drywall partitions ──────────────────────────────────────────────
    {
        "name": "Drywall partition W111 single-stud single-board",
        "name_translations": {
            "de": "Trockenbau-Trennwand W111 einfach-beplankt",
            "ru": "Перегородка из гипсокартона W111 однослойная",
            "es": "Tabique de cartón-yeso W111 una hoja",
        },
        "category": "drywall",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "gypsum plasterboard 12.5mm",
                "factor": 2.05,
                "unit": "m2",
                "role": "material",
                "description": "Plasterboard 12.5 mm",
            },
            {
                "cost_match_query": "metal stud CW 75",
                "factor": 2.8,
                "unit": "m",
                "role": "material",
                "description": "CW metal stud",
            },
            {
                "cost_match_query": "mineral wool insulation 60mm",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "Mineral wool fill",
            },
            {
                "cost_match_query": "drywall installer labor",
                "factor": 0.45,
                "unit": "h",
                "role": "labor",
                "description": "Drywall installer",
            },
        ],
        "classification": {"din276": "332", "masterformat": "09 21 16"},
        "tags": ["drywall", "partition", "w111", "interior"],
    },
    {
        "name": "Drywall partition W112 single-stud double-board",
        "name_translations": {
            "de": "Trockenbau-Trennwand W112 doppelt-beplankt",
            "ru": "Перегородка из гипсокартона W112 двухслойная",
            "es": "Tabique de cartón-yeso W112 doble hoja",
        },
        "category": "drywall",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "gypsum plasterboard 12.5mm",
                "factor": 4.1,
                "unit": "m2",
                "role": "material",
                "description": "Plasterboard 12.5 mm (2 layers)",
            },
            {
                "cost_match_query": "metal stud CW 75",
                "factor": 2.8,
                "unit": "m",
                "role": "material",
                "description": "CW metal stud",
            },
            {
                "cost_match_query": "mineral wool insulation 60mm",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "Mineral wool fill",
            },
            {
                "cost_match_query": "drywall installer labor",
                "factor": 0.65,
                "unit": "h",
                "role": "labor",
                "description": "Drywall installer",
            },
        ],
        "classification": {"din276": "332", "masterformat": "09 21 16"},
        "tags": ["drywall", "partition", "w112", "interior"],
    },
    # ── Concrete slabs ──────────────────────────────────────────────────
    {
        "name": "In-situ concrete slab d=20cm",
        "name_translations": {
            "de": "Stahlbeton-Geschossdecke d=20cm",
            "ru": "Монолитная железобетонная плита перекрытия d=20см",
            "es": "Losa de hormigón armado in-situ d=20cm",
        },
        "category": "concrete",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "concrete C25/30 ready-mix",
                "factor": 0.2,
                "unit": "m3",
                "role": "material",
                "description": "Ready-mix concrete C25/30",
            },
            {
                "cost_match_query": "rebar reinforcement steel",
                "factor": 18.0,
                "unit": "kg",
                "role": "material",
                "description": "Rebar reinforcement",
            },
            {
                "cost_match_query": "slab formwork",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "Slab formwork",
            },
            {
                "cost_match_query": "concrete pouring labor",
                "factor": 0.6,
                "unit": "h",
                "role": "labor",
                "description": "Concrete placement labor",
            },
        ],
        "classification": {"din276": "351", "masterformat": "03 30 00"},
        "tags": ["concrete", "slab", "structural", "floor"],
    },
    {
        "name": "In-situ concrete slab d=25cm",
        "name_translations": {
            "de": "Stahlbeton-Geschossdecke d=25cm",
            "ru": "Монолитная железобетонная плита перекрытия d=25см",
            "es": "Losa de hormigón armado in-situ d=25cm",
        },
        "category": "concrete",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "concrete C30/37 ready-mix",
                "factor": 0.25,
                "unit": "m3",
                "role": "material",
                "description": "Ready-mix concrete C30/37",
            },
            {
                "cost_match_query": "rebar reinforcement steel",
                "factor": 28.0,
                "unit": "kg",
                "role": "material",
                "description": "Rebar reinforcement",
            },
            {
                "cost_match_query": "slab formwork",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "Slab formwork",
            },
            {
                "cost_match_query": "concrete pouring labor",
                "factor": 0.75,
                "unit": "h",
                "role": "labor",
                "description": "Concrete placement labor",
            },
        ],
        "classification": {"din276": "351", "masterformat": "03 30 00"},
        "tags": ["concrete", "slab", "structural", "floor"],
    },
    # ── Roof / Insulation ───────────────────────────────────────────────
    {
        "name": "Flat roof bitumen 2-layer with insulation",
        "name_translations": {
            "de": "Flachdach bituminöse zweilagige Abdichtung mit Dämmung",
            "ru": "Плоская кровля битумная двухслойная с утеплителем",
            "es": "Cubierta plana asfáltica 2 capas con aislamiento",
        },
        "category": "roofing",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "bitumen membrane SBS modified",
                "factor": 2.1,
                "unit": "m2",
                "role": "material",
                "description": "SBS bitumen membrane (2 layers)",
            },
            {
                "cost_match_query": "EPS roof insulation 120mm",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "EPS rigid insulation 120 mm",
            },
            {
                "cost_match_query": "vapor barrier polyethylene",
                "factor": 1.05,
                "unit": "m2",
                "role": "material",
                "description": "Vapour barrier",
            },
            {
                "cost_match_query": "roofer labor flat roof",
                "factor": 0.55,
                "unit": "h",
                "role": "labor",
                "description": "Roofer labor",
            },
        ],
        "classification": {"din276": "363", "masterformat": "07 50 00"},
        "tags": ["roof", "bitumen", "insulation", "flat"],
    },
    {
        "name": "ETICS facade insulation EPS 160mm",
        "name_translations": {
            "de": "WDVS-Fassadendämmung EPS 160mm",
            "ru": "Фасадная теплоизоляция СФТК EPS 160мм",
            "es": "SATE aislamiento fachada EPS 160mm",
        },
        "category": "insulation",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "EPS facade insulation 160mm",
                "factor": 1.0,
                "unit": "m2",
                "role": "material",
                "description": "EPS facade panel 160 mm",
            },
            {
                "cost_match_query": "facade adhesive mortar",
                "factor": 5.5,
                "unit": "kg",
                "role": "material",
                "description": "Adhesive mortar",
            },
            {
                "cost_match_query": "fiberglass reinforcement mesh",
                "factor": 1.1,
                "unit": "m2",
                "role": "material",
                "description": "Reinforcement mesh",
            },
            {
                "cost_match_query": "facade plasterer labor",
                "factor": 0.8,
                "unit": "h",
                "role": "labor",
                "description": "Plasterer labor",
            },
        ],
        "classification": {"din276": "335", "masterformat": "07 24 00"},
        "tags": ["insulation", "facade", "etics", "eps"],
    },
    # ── Doors ──────────────────────────────────────────────────────────
    {
        "name": "Interior wood door 90x210cm",
        "name_translations": {
            "de": "Innentür Holz 90x210cm",
            "ru": "Дверь межкомнатная деревянная 90x210см",
            "es": "Puerta interior de madera 90x210cm",
        },
        "category": "finishing",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "interior wood door leaf",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Interior wood door leaf",
            },
            {
                "cost_match_query": "door frame wood",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Wood door frame",
            },
            {
                "cost_match_query": "door hardware lockset hinges",
                "factor": 1.0,
                "unit": "set",
                "role": "material",
                "description": "Lockset and hinges",
            },
            {
                "cost_match_query": "carpenter labor door installation",
                "factor": 1.5,
                "unit": "h",
                "role": "labor",
                "description": "Carpenter labor",
            },
        ],
        "classification": {"din276": "344", "masterformat": "08 14 00"},
        "tags": ["door", "interior", "wood"],
    },
    {
        "name": "Exterior steel door 100x210cm",
        "name_translations": {
            "de": "Außentür Stahl 100x210cm",
            "ru": "Дверь входная стальная 100x210см",
            "es": "Puerta exterior de acero 100x210cm",
        },
        "category": "finishing",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "exterior steel door insulated",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Insulated steel door leaf",
            },
            {
                "cost_match_query": "door frame steel",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Steel door frame",
            },
            {
                "cost_match_query": "security lockset multi-point",
                "factor": 1.0,
                "unit": "set",
                "role": "material",
                "description": "Multi-point security lockset",
            },
            {
                "cost_match_query": "carpenter labor door installation",
                "factor": 2.5,
                "unit": "h",
                "role": "labor",
                "description": "Installer labor",
            },
        ],
        "classification": {"din276": "334", "masterformat": "08 11 13"},
        "tags": ["door", "exterior", "steel", "security"],
    },
    # ── Windows ────────────────────────────────────────────────────────
    {
        "name": "uPVC window double-glazed 120x140cm",
        "name_translations": {
            "de": "Kunststoff-Fenster 2-fach verglast 120x140cm",
            "ru": "Окно ПВХ двухкамерное 120x140см",
            "es": "Ventana PVC doble acristalamiento 120x140cm",
        },
        "category": "finishing",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "uPVC window double-glazed",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "uPVC window with double glazing",
            },
            {
                "cost_match_query": "window sill aluminum",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Aluminum sill",
            },
            {
                "cost_match_query": "expanding foam sealant",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Sealant and foam",
            },
            {
                "cost_match_query": "window installer labor",
                "factor": 2.0,
                "unit": "h",
                "role": "labor",
                "description": "Window installer",
            },
        ],
        "classification": {"din276": "334", "masterformat": "08 53 13"},
        "tags": ["window", "upvc", "double-glazed"],
    },
    {
        "name": "Aluminum window triple-glazed 120x140cm",
        "name_translations": {
            "de": "Aluminium-Fenster 3-fach verglast 120x140cm",
            "ru": "Окно алюминиевое трехкамерное 120x140см",
            "es": "Ventana aluminio triple acristalamiento 120x140cm",
        },
        "category": "finishing",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "aluminum window triple-glazed thermal-break",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Aluminum window with triple glazing",
            },
            {
                "cost_match_query": "window sill aluminum",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Aluminum sill",
            },
            {
                "cost_match_query": "expanding foam sealant",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Sealant and foam",
            },
            {
                "cost_match_query": "window installer labor",
                "factor": 2.5,
                "unit": "h",
                "role": "labor",
                "description": "Window installer",
            },
        ],
        "classification": {"din276": "334", "masterformat": "08 51 13"},
        "tags": ["window", "aluminum", "triple-glazed", "thermal-break"],
    },
    # ── Floor finishes ──────────────────────────────────────────────────
    {
        "name": "Ceramic tile floor finish",
        "name_translations": {
            "de": "Bodenfliesen Keramik",
            "ru": "Пол керамическая плитка",
            "es": "Pavimento de baldosa cerámica",
        },
        "category": "finishing",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "ceramic floor tile",
                "factor": 1.05,
                "unit": "m2",
                "role": "material",
                "description": "Ceramic floor tile",
            },
            {
                "cost_match_query": "tile adhesive",
                "factor": 5.0,
                "unit": "kg",
                "role": "material",
                "description": "Tile adhesive",
            },
            {
                "cost_match_query": "tile grout",
                "factor": 0.5,
                "unit": "kg",
                "role": "material",
                "description": "Grout",
            },
            {
                "cost_match_query": "tile layer labor",
                "factor": 0.6,
                "unit": "h",
                "role": "labor",
                "description": "Tile layer labor",
            },
        ],
        "classification": {"din276": "352", "masterformat": "09 30 13"},
        "tags": ["floor", "finish", "tile", "ceramic"],
    },
    {
        "name": "Vinyl LVT floor finish",
        "name_translations": {
            "de": "Vinyl-Bodenbelag LVT",
            "ru": "Пол кварц-винил LVT",
            "es": "Pavimento vinílico LVT",
        },
        "category": "finishing",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "vinyl LVT plank flooring",
                "factor": 1.05,
                "unit": "m2",
                "role": "material",
                "description": "LVT plank flooring",
            },
            {
                "cost_match_query": "vinyl floor adhesive",
                "factor": 0.35,
                "unit": "kg",
                "role": "material",
                "description": "Vinyl adhesive",
            },
            {
                "cost_match_query": "flooring installer labor",
                "factor": 0.3,
                "unit": "h",
                "role": "labor",
                "description": "Flooring installer",
            },
        ],
        "classification": {"din276": "352", "masterformat": "09 65 19"},
        "tags": ["floor", "finish", "vinyl", "lvt"],
    },
    {
        "name": "Engineered parquet floor finish",
        "name_translations": {
            "de": "Mehrschicht-Parkett",
            "ru": "Паркетная доска инженерная",
            "es": "Parquet multicapa",
        },
        "category": "finishing",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "engineered parquet oak",
                "factor": 1.05,
                "unit": "m2",
                "role": "material",
                "description": "Engineered oak parquet",
            },
            {
                "cost_match_query": "parquet underlay foam",
                "factor": 1.05,
                "unit": "m2",
                "role": "material",
                "description": "Foam underlay",
            },
            {
                "cost_match_query": "flooring installer labor",
                "factor": 0.45,
                "unit": "h",
                "role": "labor",
                "description": "Flooring installer",
            },
        ],
        "classification": {"din276": "352", "masterformat": "09 64 29"},
        "tags": ["floor", "finish", "parquet", "wood"],
    },
    # ── MEP ─────────────────────────────────────────────────────────────
    {
        "name": "Copper pipe DN20 installed",
        "name_translations": {
            "de": "Kupferrohr DN20 verlegt",
            "ru": "Труба медная DN20 монтаж",
            "es": "Tubería de cobre DN20 instalada",
        },
        "category": "mep",
        "unit": "m",
        "components": [
            {
                "cost_match_query": "copper pipe DN20 22mm",
                "factor": 1.05,
                "unit": "m",
                "role": "material",
                "description": "Copper pipe DN20",
            },
            {
                "cost_match_query": "copper fittings DN20",
                "factor": 0.4,
                "unit": "pcs",
                "role": "material",
                "description": "Fittings (avg)",
            },
            {
                "cost_match_query": "pipe insulation 22mm",
                "factor": 1.0,
                "unit": "m",
                "role": "material",
                "description": "Pipe insulation",
            },
            {
                "cost_match_query": "plumber labor pipe installation",
                "factor": 0.35,
                "unit": "h",
                "role": "labor",
                "description": "Plumber labor",
            },
        ],
        "classification": {"din276": "411", "masterformat": "22 11 13"},
        "tags": ["mep", "plumbing", "copper", "pipe"],
    },
    {
        "name": "Sanitary WC complete with cistern",
        "name_translations": {
            "de": "WC-Becken komplett mit Spülkasten",
            "ru": "Унитаз с бачком в сборе",
            "es": "Inodoro completo con cisterna",
        },
        "category": "mep",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "WC ceramic bowl",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Ceramic WC bowl",
            },
            {
                "cost_match_query": "concealed cistern WC",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Concealed cistern",
            },
            {
                "cost_match_query": "WC seat soft-close",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Soft-close seat",
            },
            {
                "cost_match_query": "plumber labor sanitary fixture",
                "factor": 2.5,
                "unit": "h",
                "role": "labor",
                "description": "Plumber labor",
            },
        ],
        "classification": {"din276": "414", "masterformat": "22 41 13"},
        "tags": ["mep", "sanitary", "wc"],
    },
    {
        "name": "Wall-mounted radiator type 22 600x1000mm",
        "name_translations": {
            "de": "Wand-Heizkörper Typ 22 600x1000mm",
            "ru": "Радиатор настенный тип 22 600x1000мм",
            "es": "Radiador mural tipo 22 600x1000mm",
        },
        "category": "mep",
        "unit": "pcs",
        "components": [
            {
                "cost_match_query": "panel radiator type 22 600x1000",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Type-22 panel radiator",
            },
            {
                "cost_match_query": "radiator valve thermostatic",
                "factor": 1.0,
                "unit": "pcs",
                "role": "material",
                "description": "Thermostatic valve",
            },
            {
                "cost_match_query": "radiator wall bracket",
                "factor": 1.0,
                "unit": "set",
                "role": "material",
                "description": "Wall bracket set",
            },
            {
                "cost_match_query": "heating installer labor",
                "factor": 1.5,
                "unit": "h",
                "role": "labor",
                "description": "Heating installer",
            },
        ],
        "classification": {"din276": "421", "masterformat": "23 82 39"},
        "tags": ["mep", "heating", "radiator"],
    },
    # ── Structural ──────────────────────────────────────────────────────
    {
        "name": "Reinforced concrete column 30x30cm",
        "name_translations": {
            "de": "Stahlbetonstütze 30x30cm",
            "ru": "Колонна железобетонная 30x30см",
            "es": "Pilar de hormigón armado 30x30cm",
        },
        "category": "concrete",
        "unit": "m",
        "components": [
            {
                "cost_match_query": "concrete C30/37 ready-mix",
                "factor": 0.09,
                "unit": "m3",
                "role": "material",
                "description": "Ready-mix concrete C30/37",
            },
            {
                "cost_match_query": "rebar reinforcement steel",
                "factor": 18.0,
                "unit": "kg",
                "role": "material",
                "description": "Rebar reinforcement",
            },
            {
                "cost_match_query": "column formwork",
                "factor": 1.2,
                "unit": "m2",
                "role": "material",
                "description": "Column formwork",
            },
            {
                "cost_match_query": "concrete pouring labor",
                "factor": 0.6,
                "unit": "h",
                "role": "labor",
                "description": "Concrete placement labor",
            },
        ],
        "classification": {"din276": "341", "masterformat": "03 30 00"},
        "tags": ["concrete", "column", "structural", "rc"],
    },
    {
        "name": "Steel beam HEB200",
        "name_translations": {
            "de": "Stahlträger HEB200",
            "ru": "Стальная балка HEB200",
            "es": "Viga de acero HEB200",
        },
        "category": "steel",
        "unit": "m",
        "components": [
            {
                "cost_match_query": "steel beam HEB200 S235",
                "factor": 61.3,
                "unit": "kg",
                "role": "material",
                "description": "Hot-rolled steel beam HEB200 (S235)",
            },
            {
                "cost_match_query": "anti-corrosion primer steel",
                "factor": 0.85,
                "unit": "m2",
                "role": "material",
                "description": "Anti-corrosion primer",
            },
            {
                "cost_match_query": "steel erector labor structural",
                "factor": 0.6,
                "unit": "h",
                "role": "labor",
                "description": "Steel erector labor",
            },
            {
                "cost_match_query": "mobile crane operation",
                "factor": 0.15,
                "unit": "h",
                "role": "equipment",
                "description": "Mobile crane",
            },
        ],
        "classification": {"din276": "341", "masterformat": "05 12 00"},
        "tags": ["steel", "beam", "heb200", "structural"],
    },
    # ── Excavation ──────────────────────────────────────────────────────
    {
        "name": "Open cut excavation up to 2m depth",
        "name_translations": {
            "de": "Erdaushub offen bis 2m Tiefe",
            "ru": "Открытая разработка грунта до 2м глубины",
            "es": "Excavación a cielo abierto hasta 2m de profundidad",
        },
        "category": "earthwork",
        "unit": "m3",
        "components": [
            {
                "cost_match_query": "excavator operation hourly",
                "factor": 0.05,
                "unit": "h",
                "role": "equipment",
                "description": "Excavator",
            },
            {
                "cost_match_query": "earthwork laborer",
                "factor": 0.1,
                "unit": "h",
                "role": "labor",
                "description": "Earthwork laborer",
            },
            {
                "cost_match_query": "soil disposal transport",
                "factor": 1.0,
                "unit": "m3",
                "role": "subcontractor",
                "description": "Soil disposal and transport",
            },
        ],
        "classification": {"din276": "311", "masterformat": "31 23 16"},
        "tags": ["earthwork", "excavation", "sitework"],
    },
    {
        "name": "Cement screed floor d=5cm",
        "name_translations": {
            "de": "Zementestrich d=5cm",
            "ru": "Цементная стяжка d=5см",
            "es": "Solera de cemento d=5cm",
        },
        "category": "concrete",
        "unit": "m2",
        "components": [
            {
                "cost_match_query": "cement screed CT-C25-F4",
                "factor": 0.05,
                "unit": "m3",
                "role": "material",
                "description": "Cement screed mix",
            },
            {
                "cost_match_query": "edge insulation strip screed",
                "factor": 0.5,
                "unit": "m",
                "role": "material",
                "description": "Edge insulation strip",
            },
            {
                "cost_match_query": "screed installer labor",
                "factor": 0.3,
                "unit": "h",
                "role": "labor",
                "description": "Screed installer",
            },
        ],
        "classification": {"din276": "352", "masterformat": "03 53 00"},
        "tags": ["concrete", "screed", "floor", "subfloor"],
    },
    {
        "name": "Backfill with compaction",
        "name_translations": {
            "de": "Wiederverfüllung mit Verdichtung",
            "ru": "Обратная засыпка с уплотнением",
            "es": "Relleno con compactación",
        },
        "category": "earthwork",
        "unit": "m3",
        "components": [
            {
                "cost_match_query": "gravel fill material",
                "factor": 1.15,
                "unit": "m3",
                "role": "material",
                "description": "Gravel fill",
            },
            {
                "cost_match_query": "compactor plate vibratory",
                "factor": 0.1,
                "unit": "h",
                "role": "equipment",
                "description": "Vibratory plate compactor",
            },
            {
                "cost_match_query": "earthwork laborer",
                "factor": 0.2,
                "unit": "h",
                "role": "labor",
                "description": "Earthwork laborer",
            },
        ],
        "classification": {"din276": "312", "masterformat": "31 23 23"},
        "tags": ["earthwork", "backfill", "compaction", "sitework"],
    },
]


def get_seed_templates() -> list[dict[str, Any]]:
    """Return a deep copy of the canonical templates list.

    Returns a fresh copy each call so the seeder can mutate / enrich
    rows without polluting the module-level constant.
    """
    import copy

    return copy.deepcopy(ASSEMBLY_TEMPLATES)
