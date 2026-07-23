# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Shared construction-vocabulary layer for catalog and cost search.

Estimators type the word they know; a price book or catalog stores the word its
author chose, often in another language or as a trade acronym. This module is the
single source of the platform's search vocabulary, loaded by both the resource
catalog search (:mod:`app.modules.catalog.repository`) and the Cost Explorer text
search (:mod:`app.modules.cost_explorer.search`), so the two never drift apart:

* :data:`SYNONYM_GROUPS` - groups of interchangeable terms. Typing any member of a
  group can search for the others. Each group spans the trades and materials
  estimators search for most, across English, German, French, Spanish, Italian
  and Russian, plus the common US/UK spelling pairs.
* :data:`CORE_TERMS` - the English / US-UK spellings inside those groups: the only
  ones a plain substring (``ILIKE '%term%'``) search may safely OR together,
  because a short cross-language token (``porte`` for a door) would otherwise hide
  inside an unrelated English word (``supported``). The multilingual spellings
  stay available to the word-boundary-aware Cost Explorer search.
* :data:`ABBREVIATIONS` - a deterministic trade abbreviation / acronym map
  (``rc`` -> ``reinforced concrete``, ``cmu``, ``dpc``, ``dpm``, ``mep``,
  ``hvac`` ...). A short code expands to its spelled-out phrase at query time, so
  a two- or three-letter search stops dead-ending on zero results.
* :func:`fold` - normalise a string for accent- and case-insensitive comparison.
* :func:`expand_query` - the catalog-facing whole-query expansion (English core
  plus abbreviation phrases), each returned term matched as a substring.

Kept deliberately conservative: only genuinely interchangeable words share a
group. Related-but-distinct materials (a brick is not a block, a door is not a
window) are never merged, so expansion widens recall without dragging in the
wrong resource. Pure and stdlib-only (``re`` + ``unicodedata``), so it imports and
unit-tests on any interpreter, independent of the FastAPI dependency graph.
"""

from __future__ import annotations

import re
import unicodedata


def fold(text: str) -> str:
    """Normalise a string for accent-insensitive, case-insensitive comparison.

    Decomposes accented Latin letters and drops the combining marks (so ``Béton``
    folds to ``beton`` and ``hormigón`` to ``hormigon``), collapses runs of
    whitespace to single spaces, trims, and lowercases. Non-Latin scripts such as
    Cyrillic carry no combining marks here and survive unchanged, so a Russian
    query still matches a Russian row.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


# Groups of interchangeable construction terms. Typing any member searches for
# every member. Accented spellings are listed as authored; the folded
# (accent-stripped) form is added by the consumer via :func:`fold`, so a base that
# stored either spelling is still reached.
SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"concrete", "beton", "béton", "hormigón", "calcestruzzo", "бетон"}),
    frozenset({"cement", "opc", "portland cement", "zement", "ciment", "cemento", "цемент"}),
    frozenset(
        {
            "rebar",
            "reinforcement",
            "reinforcing",
            "reinforcing bar",
            "reinforcing steel",
            "reinforcement steel",
            "bewehrung",
            "betonstahl",
            "armature",
            "armadura",
            "armatura",
            "арматура",
        }
    ),
    frozenset({"steel", "stahl", "acier", "acero", "acciaio", "сталь"}),
    frozenset({"formwork", "shuttering", "schalung", "coffrage", "encofrado", "cassaforma", "опалубка"}),
    frozenset({"brick", "brickwork", "ziegel", "brique", "ladrillo", "mattone", "кирпич"}),
    frozenset({"block", "blockwork", "hohlblock", "bloc", "bloque", "blocco", "блок"}),
    frozenset(
        {
            "plaster",
            "plastering",
            "render",
            "rendering",
            "putz",
            "enduit",
            "enlucido",
            "revoco",
            "intonaco",
            "штукатурка",
        }
    ),
    frozenset(
        {
            "paint",
            "painting",
            "emulsion",
            "anstrich",
            "peinture",
            "pintura",
            "pittura",
            "vernice",
            "краска",
        }
    ),
    frozenset(
        {
            "insulation",
            "insulating",
            "dämmung",
            "dammung",
            "isolation",
            "aislamiento",
            "isolamento",
            "изоляция",
            "утеплитель",
        }
    ),
    frozenset(
        {
            "excavation",
            "excavate",
            "earthwork",
            "earthworks",
            "aushub",
            "erdarbeiten",
            "terrassement",
            "excavación",
            "excavacion",
            "scavo",
            "земляные",
            "выемка",
        }
    ),
    frozenset(
        {
            "waterproofing",
            "waterproof",
            "tanking",
            "abdichtung",
            "étanchéité",
            "etancheite",
            "impermeabilización",
            "impermeabilizacion",
            "impermeabilizzazione",
            "гидроизоляция",
        }
    ),
    frozenset(
        {"scaffold", "scaffolding", "gerüst", "geruest", "échafaudage", "echafaudage", "andamio", "ponteggio", "леса"}
    ),
    frozenset({"timber", "lumber", "wood", "holz", "bois", "madera", "legno", "древесина", "дерево"}),
    frozenset(
        {
            "tile",
            "tiles",
            "tiling",
            "fliese",
            "carrelage",
            "baldosa",
            "azulejo",
            "piastrella",
            "плитка",
        }
    ),
    frozenset({"door", "doors", "tür", "porte", "puerta", "porta", "дверь"}),
    frozenset({"window", "windows", "fenster", "fenêtre", "fenetre", "ventana", "finestra", "окно"}),
    frozenset(
        {
            "roof",
            "roofing",
            "dach",
            "toiture",
            "tejado",
            "cubierta",
            "tetto",
            "copertura",
            "крыша",
            "кровля",
        }
    ),
    frozenset(
        {
            "labour",
            "labor",
            "manpower",
            "workman",
            "arbeit",
            "lohn",
            "main d oeuvre",
            "mano de obra",
            "manodopera",
            "труд",
        }
    ),
    frozenset(
        {
            "plant",
            "equipment",
            "machinery",
            "geräte",
            "geraete",
            "maschinen",
            "maquinaria",
            "attrezzatura",
            "оборудование",
        }
    ),
    frozenset({"pipe", "piping", "rohr", "tuyau", "tube", "tubo", "труба"}),
    frozenset({"sand", "sable", "arena", "sabbia", "песок"}),
    frozenset(
        {
            "aggregate",
            "gravel",
            "ballast",
            "kies",
            "schotter",
            "gravier",
            "grava",
            "árido",
            "arido",
            "ghiaia",
            "щебень",
            "гравий",
        }
    ),
    frozenset({"glass", "glazing", "glas", "verre", "vidrio", "vetro", "стекло"}),
    frozenset({"mortar", "mörtel", "moertel", "mortier", "mortero", "malta", "раствор"}),
    frozenset({"asphalt", "tarmac", "blacktop", "asphalte", "asfalto", "асфальт"}),
    frozenset({"waterstop", "waterbar"}),
    # US / UK spelling pairs that appear verbatim in resource and work names.
    frozenset({"fibre", "fiber"}),
    frozenset({"aluminium", "aluminum"}),
    frozenset({"colour", "color"}),
    frozenset({"mould", "mold"}),
    frozenset({"galvanised", "galvanized"}),
)


# The English / US-UK terms of every group above: the spellings a mostly-English
# resource catalog actually stores, and the only ones safe to OR into its plain
# substring (``ILIKE '%term%'``) search. The international spellings stay in
# :data:`SYNONYM_GROUPS` for the word-boundary-aware Cost Explorer search, which
# can use them without a short foreign token hiding inside an unrelated English
# word.
CORE_TERMS: frozenset[str] = frozenset(
    {
        "aggregate",
        "aluminium",
        "aluminum",
        "asphalt",
        "ballast",
        "blacktop",
        "block",
        "blockwork",
        "brick",
        "brickwork",
        "cement",
        "color",
        "colour",
        "concrete",
        "door",
        "doors",
        "earthwork",
        "earthworks",
        "emulsion",
        "equipment",
        "excavate",
        "excavation",
        "fiber",
        "fibre",
        "formwork",
        "galvanised",
        "galvanized",
        "glass",
        "glazing",
        "gravel",
        "insulating",
        "insulation",
        "labor",
        "labour",
        "lumber",
        "machinery",
        "manpower",
        "mold",
        "mortar",
        "mould",
        "opc",
        "paint",
        "painting",
        "pipe",
        "piping",
        "plant",
        "plaster",
        "plastering",
        "portland cement",
        "rebar",
        "reinforcement",
        "reinforcement steel",
        "reinforcing",
        "reinforcing bar",
        "reinforcing steel",
        "render",
        "rendering",
        "roof",
        "roofing",
        "sand",
        "scaffold",
        "scaffolding",
        "shuttering",
        "steel",
        "tanking",
        "tarmac",
        "tile",
        "tiles",
        "tiling",
        "timber",
        "waterbar",
        "waterproof",
        "waterproofing",
        "waterstop",
        "window",
        "windows",
        "wood",
        "workman",
    }
)


# Deterministic trade abbreviation / acronym map: a folded short code -> the
# spelled-out phrase(s) it stands for. Expanded at query time (never auto-applied
# to stored data), so a two- or three-letter search like "rc", "cmu" or "mep"
# also searches for its full phrase instead of dead-ending on zero results.
# Mono-directional by design: a code expands to its phrase, not the other way
# round, so a long descriptive query is never rewritten into a poison-prone
# two-letter token.
ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "rc": ("reinforced concrete",),
    "rcc": ("reinforced cement concrete",),
    "pcc": ("plain cement concrete",),
    "cmu": ("concrete masonry unit", "concrete block"),
    "dpc": ("damp proof course",),
    "dpm": ("damp proof membrane",),
    "mep": ("mechanical electrical plumbing",),
    "hvac": ("heating ventilation air conditioning",),
}


# Folded core spellings, for the substring-safety test in :func:`expand_query`.
_CORE_FOLDED: frozenset[str] = frozenset(fold(term) for term in CORE_TERMS)

# Folded term -> the English core of the group it belongs to (built once at
# import). Every term of a group, English or international, maps to the same
# English core, so a foreign query still reaches the English resource names the
# catalog stores while the substring search only ever ORs safe English spellings.
_CORE_INDEX: dict[str, frozenset[str]] = {}
for _group in SYNONYM_GROUPS:
    _core = frozenset(term for term in _group if fold(term) in _CORE_FOLDED)
    for _term in _group:
        _CORE_INDEX.setdefault(fold(_term), _core)


def expand_query(q: str, limit: int = 8) -> list[str]:
    """Return the search term plus interchangeable trade synonyms and abbreviations.

    The original query is always first (so an exact / substring hit ranks
    itself); expansions follow. Matching is whole-query and case/accent
    insensitive: the trimmed, folded query is looked up as a whole, so a short
    precise word like "plant" expands while a long descriptive phrase does not
    accidentally match a short synonym term.

    The catalog search that calls this matches every returned term as a substring
    (``ILIKE '%term%'``), so expansion is limited to the English / US-UK core of
    the matched concept plus any abbreviation phrase - both safe as substrings -
    and never the short cross-language spellings (those are reserved for the
    word-boundary-aware Cost Explorer search). Deduped by folded spelling and
    capped so the OR-expansion stays bounded.
    """
    original = q.strip()
    if not original:
        return []
    folded = fold(original)
    terms: list[str] = [original]
    core = _CORE_INDEX.get(folded)
    if core:
        terms.extend(term for term in sorted(core) if fold(term) != folded)
    terms.extend(ABBREVIATIONS.get(folded, ()))
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = fold(term)
        if key not in seen:
            seen.add(key)
            out.append(term)
        if len(out) >= limit:
            break
    return out
