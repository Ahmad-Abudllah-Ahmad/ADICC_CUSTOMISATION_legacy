# US Resource-Based Cost Database: Methodology and Integration Guide

**Written for:** OCERP developers and the people wiring data into the platform  
**Revised:** 2026-05-15  
**See also:** `docs/US_COST_DATABASE_PILOT.md` for the pilot batch  
**See also:** `docs/validation_report.md` for the pilot validation results  
**Looking for the API import path?** The CSV, Excel, and JSON bulk-upload guides live in [`docs/cost-database-import.md`](cost-database-import.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [How We Built the Pilot: Process Walkthrough](#2-how-we-built-the-pilot-process-walkthrough)
3. [OCERP Cost Database Architecture](#3-ocerp-cost-database-architecture)
4. [CostItem Schema Reference](#4-costitem-schema-reference)
5. [The Resource-Based Costing Method](#5-the-resource-based-costing-method)
6. [How to Determine What Cost Items Are Needed](#6-how-to-determine-what-cost-items-are-needed)
7. [External Cost Data Sources](#7-external-cost-data-sources)
8. [Source-to-Schema Mapping Reference](#8-source-to-schema-mapping-reference)
9. [Classification Systems](#9-classification-systems)
10. [Step-by-Step: Building a New Regional Database](#10-step-by-step-building-a-new-regional-database)
11. [Validation and Quality Assurance](#11-validation-and-quality-assurance)
12. [Importing Data into OCERP](#12-importing-data-into-ocerp)

---

## 1. Overview

The OCERP cost database keeps its entries as **resource-based cost items**. Every item stands for one unit of construction work, for example "Bulk excavation, common earth, machine", and its total rate is **broken down into labor, material, and equipment parts**. Splitting the rate this way gives us several things at once:

- **Transparent costing:** estimators can see *why* a rate ended up where it did instead of just reading a final number.
- **Regional adaptation:** swap in different labor wages or material prices for another market and you do not have to rebuild the item from the ground up.
- **Cross-validation:** line up the calculated rate against actual bid prices and any errors stand out.
- **Sensitivity analysis:** model what happens to cost when wages move, material prices swing, or a different machine is chosen.

This document walks through:

- How we assembled the USA_TENNESSEE pilot out of real government and market data.
- The architecture and schema behind the OCERP cost database.
- A way to decide which cost items a given project type actually requires.
- Where to find, pull, and map data from each of the major US cost sources.
- A repeatable procedure for standing up a brand new regional database.

---

## 2. How We Built the Pilot: Process Walkthrough

We produced the pilot batch of 12 sitework cost items for Nashville, TN, by following the steps below.

### Phase 1: Identify Required Items (Scope Definition)

We took the TCG Brentwood Sitework project scope as our starting point and pulled out 12 items spread across four categories:

| Category | Items | MasterFormat Division |
|----------|-------|----------------------|
| Demolition | 4 (house, garage, concrete, asphalt) | 02, Existing Conditions |
| Excavation and Grading | 4 (bulk, trench, grading, fill) | 31, Earthwork |
| Stormwater | 2 (French drain, infiltration pit) | 33, Utilities |
| Utilities | 2 (water, sewer service lines) | 33, Utilities |

Every item received a readable code (such as `DEM-HSE-01` or `EXC-BLK-01`) plus a unit of measure that matches how the trade conventionally measures that kind of work.

### Phase 2: Source Research

Three free government sources supplied the underlying numbers:

| Source | What It Provided | How We Used It |
|--------|-----------------|----------------|
| **USACE EP 1110-1-8** (Region 3 Southeast, 2022 ed.) | Equipment hourly rates (ownership plus operating) | Machine cost components across every cost item |
| **BLS OEWS** (May 2024, Nashville MSA #34980) | Mean hourly wages by occupation (SOC codes) | Labor cost components |
| **TDOT Average Bid Prices** (2024) | Real bid prices for validation | Sanity check of our calculated rates against the market |

Material rates were put together from local Nashville market estimates (national home-improvement retailers and regional suppliers).

### Phase 3: Component Decomposition

For each cost item we worked out:

1. **The crew and equipment involved.** House demolition, for instance, needs 1 excavator operator plus 2 laborers plus a hydraulic excavator fitted with a grapple.
2. **Productivity rates,** meaning how many hours of each resource go into one unit of work (about 0.06 equipment-hrs/SF for house demolition).
3. **Material quantities,** such as 0.003 dumpster rentals per SF and 0.015 tons of debris per SF.

We then calculated each component cost as `quantity x unit_rate` and set the total rate equal to `sum(component_costs)`.

**Example, DEM-HSE-01 (House Demolition):**

```
rate = sum(components.cost) = $10.33/SF

Component breakdown:
  Labor:     0.12 hrs/SF x $22.45/hr  = $2.69  (Construction Laborers, BLS 47-2061)
  Equipment: 0.06 hrs/SF x $73.58/hr  = $4.41  (Excavator 30T, USACE EXC-30T)
  Material:  0.003 EA/SF x $650/EA    = $1.95  (Dumpster 30-yd)
  Material:  0.015 ton/SF x $85/ton   = $1.28  (Debris disposal)
```

### Phase 4: Validation

We validated in two ways:

1. **Component math:** `abs(rate - sum(components.cost)) < 0.01` holds for all 12 items.
2. **TDOT cross-comparison:** our rates set against TDOT bid prices. Where the scope lines up (French drain at +6.4% variance), our rates land within plus or minus 10%. Where the scope genuinely differs (a residential service line against a highway sewer at -86%), the gap is expected and we document it.

The pilot left behind these files:

```
data/
├── usace_equipment_rates.json   # 14 equipment types from USACE
├── bls_labor_wages.json         # 8 occupations from BLS
├── material_rates.json           # 14 material costs
├── tdot_bid_prices.json          # 14 TDOT bid items for validation
└── us_tn_sitework_costs.json    # 12 CostItems with 78 components
```

---

## 3. OCERP Cost Database Architecture

### 3.1 Module Structure

```
backend/app/modules/costs/
├── models.py           # CostItem ORM model (oe_costs_item table)
├── schemas.py          # Pydantic request/response schemas
├── repository.py      # Database queries (search, bulk ops, category tree)
├── service.py         # Business logic layer
├── router.py           # FastAPI routes (REST API)
├── matcher.py          # CWICR text/semantic matcher
├── vector_adapter.py   # Vector search adapter (LanceDB embedded or Qdrant)
├── permissions.py      # Role-based access control
├── events.py           # Event bus integration
├── translations/       # 16-locale localization JSON files
└── manifest.py         # Module registration
```

### 3.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rate storage | `String(50)` | Protects SQLite float precision; parsed to float on read. PostgreSQL is the production DB and SQLite is the zero-config dev fallback |
| Currency fallback | 3-tier chain | Explicit, then region map, then `"EUR"` default. Covers legacy CWICR rows that left currency empty |
| Component type | Free-form JSON list | Allows `labor`, `material`, `equipment`, `subcontractor`, `operator`, `electricity`, `other` |
| Classification | Free-form dict | Holds DIN 276, MasterFormat, UniFormat, NRM, and any other standard at the same time |
| Uniqueness | `(code, region)` | The same code is fine in different regions. Bulk import does not upsert; duplicates are quietly skipped |
| Region format | `COUNTRYCODE_CITY` | Uppercase, underscore-delimited: `USA_TENNESSEE`, `DE_BERLIN`, `GB_LONDON` |
| Search pagination | Keyset cursor | O(1) page fetches; total count cached for 60 min |
| Lite mode | `?lite=true` | Drops the 31KB `components` array for list views; `components_count` still flags "has breakdown" |

### 3.3 API Endpoints Summary

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/costs/` | Search/filter cost items | Public |
| GET | `/costs/autocomplete/` | Fast text autocomplete | Public |
| GET | `/costs/{id}` | Get single item by UUID | Public |
| POST | `/costs/` | Create single item | Editor+ |
| PATCH | `/costs/{id}` | Update item | Editor+ |
| DELETE | `/costs/{id}` | Delete item | Manager+ |
| POST | `/costs/bulk/` | Bulk import JSON array | Editor+ |
| POST | `/costs/import/file/` | Import from Excel/CSV | Editor+ |
| DELETE | `/costs/actions/clear-region/{region}` | Wipe all items in a region | Admin |
| GET | `/costs/regions/` | List distinct regions | Public |
| GET | `/costs/regions/stats/` | Region row counts | Public |
| POST | `/costs/match/` | CWICR text matcher | Public |
| POST | `/costs/match-from-position/` | Match from BOQ position | Public |

### 3.4 Catalog Module (`backend/app/modules/catalog/`)

Once cost items are loaded, the resources inside their component arrays can be pulled out into the **Resource Catalog**, where they become reusable in assemblies and the BOQ editor.

```
backend/app/modules/catalog/
├── models.py           # CatalogResource ORM model (oe_catalog_resource table)
├── schemas.py          # Pydantic request/response schemas
├── repository.py       # Database queries (search, stats, bulk ops)
├── service.py          # Business logic including extraction from cost items
├── router.py           # FastAPI routes (REST API)
├── permissions.py      # Role-based access control (catalog.extract requires Manager+)
└── manifest.py         # Module registration (depends on oe_costs)
```

**The core idea:** the Resource Catalog holds **leaf resources**, the individual materials, equipment items, labor rates, and operators that get extracted out of the `components` arrays of cost items. Assemblies can then reference those resources and they can be applied straight onto BOQ positions.

**The extraction flow runs like this:**
1. Import cost items, each with its `components[]` array, into `oe_costs_item`.
2. Run `CatalogResourceService.import_region_from_costs(region)` or call `POST /catalog/extract/`.
3. Components are grouped by `(code, type)`, averages are computed, and the results are written into `oe_catalog_resource`.
4. The extracted resources show up in the catalog UI under their region tab (for example `USA_TENNESSEE`).

> **Note:** The "My Catalog" tab on `/catalog` only lists `region='CUSTOM'` resources. Extracted regional resources land on their own region tab instead.

---

## 4. CostItem Schema Reference

### 4.1 Database Model (`oe_costs_item`)

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | PK | auto | |
| `code` | `String(100)` | NO | - | Unique per region. E.g. `"DEM-HSE-01"` or `"03.330.10"` |
| `description` | `Text` | NO | - | Primary human-readable description |
| `descriptions` | `JSON` | NO | `{}` | Localized: `{"en": "House demolition", "de": "Haushaltabbruch"}` |
| `unit` | `String(20)` | NO | - | Measurement unit: `SF`, `CY`, `LF`, `EA`, `hr`, `m`, `m2`, `m3`, `kg`, `pcs` |
| `rate` | `String(50)` | NO | - | Unit rate stored as a string for SQLite compatibility |
| `currency` | `String(10)` | NO | `""` | ISO 4217 code. Resolved from region if left empty |
| `source` | `String(50)` | NO | `"cwicr"` | Data provenance: `cwicr`, `rsmeans`, `manual`, `file_import`, `custom` |
| `classification` | `JSON` | NO | `{}` | Multi-standard: `{"masterformat": "03 30 00", "din276": "330"}` |
| `components` | `JSON` | NO | `[]` | Resource breakdown: `[{type, name, quantity, unit_rate, cost, unit}]` |
| `tags` | `JSON` | NO | `[]` | Searchable: `["demolition", "sitework", "nashville"]` |
| `region` | `String(50)` | YES | `None` | E.g. `USA_TENNESSEE`, `DE_BERLIN` |
| `is_active` | `Boolean` | NO | `True` | Soft-delete |
| `metadata_` | `JSON` | NO | `{}` | Column name `metadata`; arbitrary key-value store |

**Unique constraint:** `uq_costs_code_region` covers `(code, region)`

### 4.2 Component Schema

Every entry in the `components` array has this shape:

```json
{
  "type": "labor",              // "labor" | "material" | "equipment" | "subcontractor" | "other"
  "name": "Construction Laborers (SOC 47-2061)",  // Descriptive name
  "quantity": 0.12,             // Quantity per parent unit
  "unit_rate": 22.45,           // Rate per component unit
  "cost": 2.69,                 // quantity x unit_rate (MUST sum to parent rate)
  "unit": "hr",                 // Component unit (hr, SF, CY, EA, ton, etc.)
  "code": "LAB-2061"            // Required for catalog extraction; optional otherwise. Auto-generated by the import script if missing
}
```

**The rule to enforce:**

```python
assert abs(rate - sum(c["cost"] for c in components)) < 0.01
```

The parent `rate` has to match the sum of all component `cost` values to within $0.01. The import script enforces this, and you should run the check before any bulk import.

### 4.3 Classification Dict

The `classification` field carries one or more classification standard codes:

```json
{
  "division": "02",
  "section": "4100",
  "category": "Selective Demolition",
  "masterformat": "02 41 00",
  "uniformat": "G2020"
}
```

For the 4-level CWICR tree, OCERP uses `collection`, then `department`, then `section`, then `subsection`. Standard classification codes go under their own keys such as `masterformat`, `din276`, or `nrm`.

### 4.4 Metadata Dict

The `metadata_` field is a free-form bag for extension data:

```json
{
  "labor_hours": 0.12,
  "equipment_hours": 0.06,
  "data_sources": ["USACE EP 1110-1-8", "BLS OEWS May 2024"],
  "validation_status": "pilot",
  "tdot_comparison": {
    "tdot_item": "203-01",
    "tdot_rate_2024": 21.42,
    "variance_pct": -41.9
  }
}
```

---

## 5. The Resource-Based Costing Method

### 5.1 What Is Resource-Based Costing?

Resource-based costing takes a unit rate apart into the resources that make it up:

```
total_rate = Σ(labor_costs) + Σ(equipment_costs) + Σ(material_costs)
           = Σ(quantity_i x unit_rate_i) for each component i
```

This is a different approach from **unit-price estimating**, which carries one rate per unit of work with no breakdown, and from **parametric estimating**, where the rate comes from building characteristics like $/SF.

### 5.2 Why Resource-Based?

| Advantage | Explanation |
|-----------|-------------|
| **Transparency** | Estimators see *why* a rate is $10.33/SF, not just the bottom line |
| **Regional adaptation** | Swap Nashville labor wages for Denver wages and the rates update on their own |
| **Time adjustment** | Move equipment rates from the USACE 2022 edition to 2026 and costs follow |
| **Cross-validation** | Compare calculated rates against TDOT or commercial cost-database bid prices |
| **Sensitivity analysis** | Model the impact of wage changes, material price volatility, or equipment choice |
| **Audit trail** | Each component points back to its source (a BLS SOC code, a USACE equipment code, a market rate) |

### 5.3 Productivity Rates

The make-or-break input is the **productivity rate**, the number of hours of each resource needed per unit of work. Common sources for productivity rates:

| Source | Type | Best For |
|--------|------|----------|
| Commercial unit-cost database | Published manhours/unit | General building |
| Commercial estimator handbook | Published manhours/unit | Residential/light commercial |
| Commercial heavy-civil database | Published manhours/unit | Heavy civil/industrial |
| USACE EP 1110-1-8 | Equipment hours/unit (derived) | Government work |
| DOT standard specifications | Implicit in bid items | Highway/infrastructure |
| Historic project data | Your own records | Project-specific |
| Crew analysis | Engineering judgment | Custom assemblies |

### 5.4 Component Decomposition Template

Run each cost item through this template:

```
1. Define the scope of work (what's included/excluded)
2. Identify the crew composition:
   - Which trades? -> BLS SOC codes -> labor hourly rate
   - How many workers per crew? -> labor hours per unit
3. Identify the equipment:
   - Which machines? -> USACE/FEMA equipment code -> equipment hourly rate
   - How many hours per unit? -> equipment hours per unit
4. Identify the materials:
   - What materials? -> material code -> material unit price
   - What quantity per unit? -> material quantity per parent unit
5. Add incidentals:
   - Dumpster rentals, water, marking paint, silt fence, etc.
6. Compute:
   component_cost = quantity x unit_rate
   total_rate = round(sum(component_costs), 2)
7. Validate:
   abs(total_rate - sum(component_costs)) < 0.01
8. Cross-check against bid prices
```

### 5.5 Example: French Drain (SW-FRN-01)

**Scope:** Trench excavation, geotextile wrap, #57 stone fill, 4" perforated PVC pipe, backfill, and compaction. Priced per linear foot.

**Crew and equipment:**
- Operating Engineer (excavator operator, SOC 47-2073): 0.08 hr/LF x $25.58/hr
- Pipelayer (pipe installation, SOC 47-2151): 0.10 hr/LF x $22.77/hr
- Construction Laborer (backfill/compaction, SOC 47-2061): 0.10 hr/LF x $22.45/hr
- Excavator 20-ton: 0.08 hr/LF x $60.94/hr
- Vibratory Roller 5.2-ton: 0.04 hr/LF x $30.73/hr

**Materials going in:**
- 4" PVC perforated pipe: 1.05 LF/LF x $3.50/LF (5% waste allowance)
- #57 stone: 0.08 CY/LF x $45.00/CY
- Geotextile fabric: 6.0 SF/LF x $0.85/SF
- Sand bedding: 0.03 CY/LF x $35.00/CY
- PVC fittings: 1.00 LF/LF x $1.88/LF

**Rolled-up result:**
```
rate = $28.00/LF = 2.05 + 2.28 + 2.25 + 4.88 + 1.23 + 3.68 + 3.60 + 5.10 + 1.05 + 1.88
```

**Validation:** The TDOT 2024 average bid price for Filter Cloth Underdrain (Item 710-04) is $26.31/LF. That puts our variance at +6.4%.

---

## 6. How to Determine What Cost Items Are Needed

### 6.1 Scope-Driven Approach

**Begin from the project scope of work, not from whatever data sources happen to be on hand.**

1. **Identify the project type.** Sitework, building, highway, utility? Each maps onto a particular set of CSI MasterFormat divisions.

2. **List the work items from the scope.**
   - Sitework: demolition, earthwork, stormwater, utilities.
   - Building: foundations, structure, envelope, MEP, finishes.
   - Highway: earthwork, paving, drainage, traffic, landscaping.

3. **Map each work item to a cost item code,** drawing on the project specification or the estimator's work breakdown structure.

4. **Validate coverage.** For every MasterFormat division in the project, confirm the cost database covers 80% or more of the estimated value.

### 6.2 MasterFormat Division Coverage for Sitework

| Division | Name | Key Items |
|----------|------|-----------|
| 02 | Existing Conditions | Demolition, site assessment, hazardous material survey |
| 31 | Earthwork | Excavation, fill, grading, compaction, dewatering |
| 32 | Exterior Improvements | Paving, landscaping, fencing, irrigation |
| 33 | Utilities | Water, sewer, storm drain, gas, electric, communications |
| 34 | Transportation | Roadways, bridges, rail, signage |

### 6.3 Project-Type Templates

When you spin up a new regional database, start from a project-type template:

**Sitework (Residential Subdivision, 20 items):**
```
02 41 00 - Demolition (4): house, garage, concrete, asphalt removal
31 23 00 - Excavation (4): bulk, trench, grading, fill
33 46 00 - Stormwater (2): French drain, infiltration pit
33 11 00 - Water utility (1): water service line
33 30 00 - Sewer utility (1): sewer service line
31 25 00 - Erosion control (4): silt fence, construction entrance, stabilization, mulch
32 12 00 - Paving (2): asphalt base, asphalt surface
32 31 00 - Fencing (2): chain-link fence, temporary construction fence
```

**Heavy Highway (30 or more items):**
- Division 31 items for cut, fill, and haul.
- TDOT or CALTRANS standard bid items for paving, drainage, and striping.
- Additional items for utility relocation.

### 6.4 Coverage Analysis Method

Once a region's cost database is built, check coverage across four angles:

1. **By division.** Does the database hold items for every MasterFormat division that applies?
2. **By value.** Do the top 20 items by estimated project value all have cost entries?
3. **By bid item.** Can 80% or more of the project's bid items be mapped onto cost entries?
4. **By source.** Are all components (labor, material, equipment) drawn from current data?

### 6.5 Prioritization When Starting a New Region

When building a region from scratch:

1. **Lay down the labor, equipment, and material rate tables first.** These are the building blocks for everything else.
2. **Build the highest-value items first.** Excavation, concrete, and pipe work tend to make up 60 to 70% of sitework value.
3. **Validate each batch against local bid prices** (TDOT, CALTRANS, and so on).
4. **Add detail in waves.** A first batch can carry simplified components; later batches fill in variants, alternates, and finer detail.

---

## 7. External Cost Data Sources

We group the sources into three tiers: **Government Free** (authoritative, no cost), **Commercial Subscription** (comprehensive, paid), and **Industry Free/Low-Cost** (partial, accessible).

### 7.1 Government Free Sources

#### 7.1.1 USACE EP 1110-1-8: Equipment Ownership and Operating Rates

| Attribute | Value |
|-----------|-------|
| **What** | Hourly equipment rates (ownership plus operating) by machine type, size, condition |
| **Regions** | 12 US regions (Northeast through Pacific) |
| **Update** | Sporadic (current edition 2022) |
| **Access** | Free PDF download |
| **URL** | https://www.usace.army.mil/Missions/Cost-Engineering/EP1110-1-8/ |

**Our use:** Equipment cost components in every cost item. We parsed the 2022 Region 3 (Southeast) data and stored it in `data/usace_equipment_rates.json`.

**Limitations:** The data dates from 2011 with 2022 rate adjustments. It does not carry operator labor, which comes from a separate BLS wage. The rates are machine-only.

**Better alternative:** the FEMA Schedule of Equipment Rates (annual updates, around 530 items, national scope):
- URL: https://www.fema.gov/sites/default/files/documents/fema_pa_schedule-equipment-rates_2025.pdf
- Also on data.gov as dataset FEMA-0359

#### 7.1.2 BLS OEWS: Occupational Employment and Wage Statistics

| Attribute | Value |
|-----------|-------|
| **What** | Mean/median hourly and annual wages by SOC occupation code, by metro area |
| **Regions** | National, state, 400+ metro areas |
| **Update** | Annual (May data, released about 18 months later) |
| **Access** | Free API (v2.2) plus downloadable CSV/XLSX |
| **URL** | https://www.bls.gov/oes/tables.htm |
| **API** | https://www.bls.gov/bls/api_features.htm |

**Our use:** Labor cost components. Nashville MSA (34980) May 2024 data is stored in `data/bls_labor_wages.json`.

**The construction SOC codes that matter most:**

| SOC Code | Occupation | Typical Use |
|----------|-----------|-------------|
| 47-2061 | Construction Laborers | Ground crew, cleanup, manual labor |
| 47-2073 | Operating Engineers | Equipment operators |
| 47-2151 | Pipelayers | Pipe installation |
| 47-2051 | Cement Masons | Concrete work |
| 47-2031 | Carpenters | Formwork, woodwork |
| 47-2111 | Electricians | Electrical utility work |
| 47-2152 | Plumbers | Water/sewer connections |
| 37-3013 | Tree Trimmers | Clearing, site prep |
| 47-2211 | Ironworkers | Structural steel, rebar |

**Limitations:** These are mean wages, not prevailing (Davis-Bacon) wages. On federally funded projects, use Davis-Bacon determinations instead.

#### 7.1.3 Davis-Bacon Wage Determinations

| Attribute | Value |
|-----------|-------|
| **What** | Legally binding prevailing wage rates by county, by construction type |
| **Regions** | County-level for all US states and territories |
| **Update** | Annual general determinations plus modifications |
| **Access** | Free on SAM.gov |
| **URL** | https://sam.gov (Wage Determinations tab) |

**When to use:** Davis-Bacon rates are **mandatory** on federally funded construction over $2,000. They usually run 25 to 40% higher than BLS mean wages because they reflect union and collective bargaining rates.

**How to extract:** There is no bulk API. Determinations are individual HTML pages on SAM.gov. A scraper has to enumerate WD numbers by state plus construction type (Building, Heavy, Highway, Residential).

#### 7.1.4 State DOT Bid Prices

| Attribute | Value |
|-----------|-------|
| **What** | Average unit bid prices from awarded contracts |
| **Regions** | State-wide (some states publish district-level too) |
| **Update** | Annual or quarterly |
| **Access** | Free from state DOT websites |
| **Best states** | TN, CA, FL, WI, TX, NY (via a third-party DOT data portal) |

**Our use:** Cross-validation of our calculated rates against real market prices. The TDOT 2024 data lives in `data/tdot_bid_prices.json`.

**Where each state DOT publishes:**

| State | URL | Format |
|-------|-----|--------|
| Tennessee | https://www.tn.gov/tdot/.../transportation-construction-price-information.html | Excel/PDF |
| California | https://sv08data.dot.ca.gov/ | Interactive web DB |
| Florida | https://www.fdot.gov/fpo/fpc/reports/historicalitemaveragecost | Power BI |
| Wisconsin | https://wisconsindot.gov/.../average-unit-price.pdf | PDF |
| Texas | https://www.txdot.gov/.../average-low-bid-prices.html | Excel |
| New York | Via a third-party DOT data portal | Web platform |

**Key insight:** DOT bid prices are the **gold standard for sitework and civil unit costs** because they track actual market conditions. They are, however, composite rates that bundle labor plus material plus equipment plus overhead plus profit into one figure, not resource-decomposed. Use them for **validation**, not as component sources.

### 7.2 Commercial Subscription Sources

#### 7.2.1 Commercial Unit-Cost Databases

| Attribute | Value |
|-----------|-------|
| **What** | Large commercial unit-cost line-item databases (tens of thousands of items) with labor/material/equipment breakdowns, crew compositions, daily outputs, and city cost indexes |
| **Regions** | National average plus hundreds of city adjustment factors |
| **Update** | Typically quarterly |
| **Format** | Online, print, API (enterprise) |
| **Access** | Paid subscription; imported into OCERP as XLSX/CSV |

**Why they matter:** a comprehensive commercial unit-cost database lines up almost perfectly with OCERP's `components` field (labor plus material plus equipment breakdown, crew compositions). MasterFormat line numbering maps straight onto `classification.masterformat`.

**How the fields line up:**

```
source line number   -> code (e.g., "US-033053.40-3950")
source description    -> description
source unit           -> unit
source bare cost      -> rate
source city index     -> metadata.city_cost_index
source crew details   -> components (labor, material, equipment)
source CSI division    -> classification.masterformat
```

**Limitation:** commercial cost data is copyrighted and *cannot be redistributed freely*. For OCERP it can ship as a premium data connector that users subscribe to separately, or serve as a reference and benchmarking source during development.

#### 7.2.2 Commercial Estimator Handbooks

| Attribute | Value |
|-----------|-------|
| **What** | Mid-size unit-cost references (several thousand items) with manhours, crew sizes, labor/material/total costs |
| **Regions** | National with area modification factors |
| **Update** | Annual editions |
| **Format** | PDF, print, cloud, API (licensing available) |
| **Access** | Low-cost book or subscription; imported as XLSX/CSV |

**Why they matter:** an affordable commercial estimator handbook is a good fit for residential and light commercial work, often with API access for integration, and it maps directly onto OCERP components.

#### 7.2.3 Published Construction Cost Indexes

| Attribute | Value |
|-----------|-------|
| **What** | Construction cost escalation indexes (building and general construction) plus material prices across a set of cities |
| **Regions** | Around 20 US cities plus national average |
| **Update** | Monthly |
| **Access** | Paid subscription; index values imported as XLSX/CSV |

**Why they matter:** published cost indexes are not unit cost databases, but they are essential for **time-adjusting historical costs** into current dollars. The building and general construction indexes are the most widely cited construction inflation measures. The multi-city material price data (concrete, steel, lumber) can populate individual `CostItem` entries with `source: "enr_materials"`.

#### 7.2.4 Commercial Heavy-Civil / Industrial Databases

| Attribute | Value |
|-----------|-------|
| **What** | Very large line-item databases (100,000+ items across hundreds of phases). Heavy civil/industrial focus. Manhours, materials, equipment, subcontractor pricing |
| **Regions** | 100+ North American labor markets; some international coverage |
| **Access** | Paid subscription; imported as XLSX/CSV |

**Why they matter:** a commercial heavy-civil database is the best source for heavy civil and industrial process-plant estimating. Its per-labor-market rates are more granular than BLS OEWS, and the phase structure lines up with sitework scope.

### 7.3 Industry Free / Low-Cost Sources

#### 7.3.1 Building Valuation Datasets

| Attribute | Value |
|-----------|-------|
| **What** | $/SF construction costs by occupancy group and construction type |
| **Regions** | National with regional modifiers |
| **Update** | Semi-annual |
| **Access** | Published by code / membership bodies; imported as XLSX/CSV |

**Use case:** Conceptual and square-foot estimating only. Not suited to detailed estimating, but handy for order-of-magnitude validation.

#### 7.3.2 Replacement-Cost Valuation Databases

| Attribute | Value |
|-----------|-------|
| **What** | Square-foot and unit-in-place replacement costs for insurance and tax assessment |
| **Regions** | US and Canada with local multipliers |
| **Access** | Paid subscription; imported as XLSX/CSV |

**Use case:** Building valuation rather than sitework. The segregated cost breakdowns could populate OCERP `components` for building-level items.

---

## 8. Source-to-Schema Mapping Reference

### 8.1 Universal Mapping Template

Every external source resolves to the same OCERP `CostItemCreate` schema. Here is the universal mapping:

```
source item identifier     -> code
source item description    -> description
source unit                 -> unit
source rate/price           -> rate
source geographic region    -> region (transformed to COUNTRYCODE_CITY)
source currency             -> currency (ISO 4217)
source classification       -> classification (transformed to standard keys)
source labor/equip/material -> components (resource-based decomposition)
source metadata             -> metadata (provenance, effective dates, source URLs)
source tags                 -> tags
source identifier           -> source field ("usace", "bls_oews", "rsmeans", etc.)
```

### 8.2 Per-Source Mapping Details

#### USACE / FEMA Equipment Rates -> CostItem

```json
{
  "code": "USACE-EXC-30T",
  "description": "Hydraulic Excavator, Crawler, 30-ton class (CAT 326F, 0.69 CY)",
  "unit": "hr",
  "rate": 73.58,
  "currency": "USD",
  "source": "usace_ep1110",
  "region": "USA_SOUTHEAST",
  "classification": {"masterformat": "01 54 00", "equipment_type": "excavator"},
  "components": [
    {"type": "equipment", "name": "Ownership cost (depreciation + FCCM)", "quantity": 1, "unit_rate": 20.77, "cost": 20.77, "unit": "hr"},
    {"type": "equipment", "name": "Operating cost (fuel, tires, repairs)", "quantity": 1, "unit_rate": 52.81, "cost": 52.81, "unit": "hr"},
    {"type": "labor", "name": "Operator (Operating Engineer, SOC 47-2073)", "quantity": 1, "unit_rate": 25.58, "cost": 25.58, "unit": "hr"}
  ],
  "tags": ["equipment", "excavator", "heavy-civil", "usace"],
  "metadata": {
    "ownership_rate": 20.77,
    "operating_rate": 52.81,
    "condition": "average",
    "effective_date": "2022-12-01",
    "usace_region": "3"
  }
}
```

**Note:** the USACE rate is machine-only at $73.58/hr. Operator labor ($25.58/hr from BLS) is layered in as a separate component, which brings the fully burdened rate to $99.16/hr.

#### BLS OEWS Labor Rates -> CostItem

```json
{
  "code": "BLS-47-2061",
  "description": "Construction Laborers, Nashville-Davidson-Murfreesboro-Franklin, TN MSA",
  "unit": "hr",
  "rate": 22.45,
  "currency": "USD",
  "source": "bls_oews",
  "region": "USA_TENNESSEE",
  "classification": {"soc": "47-2061", "masterformat": "01 54 00"},
  "components": [],
  "tags": ["labor", "general", "construction", "nashville"],
  "metadata": {
    "soc_code": "47-2061",
    "msa_code": "34980",
    "mean_hourly_wage": 22.45,
    "median_hourly_wage": 18.96,
    "effective_date": "2024-05",
    "data_type": "mean"
  }
}
```

#### TDOT Bid Prices -> CostItem (Validation Only)

Bid prices are **composite rates** (labor plus material plus equipment plus overhead plus profit). Do not break them into components unless you have the breakdown from another source. Store them instead as **reference items** with `source: "tdot_bid"` and lean on them for cross-validation:

```json
{
  "code": "TDOT-710-04",
  "description": "Filter Cloth Underdrain (With Pipe) [French Drain]",
  "unit": "LF",
  "rate": 26.31,
  "currency": "USD",
  "source": "tdot_bid",
  "region": "USA_TENNESSEE",
  "classification": {"tdot_item": "710-04", "masterformat": "33 46 00"},
  "components": [],
  "tags": ["validation", "french_drain", "stormwater", "tdot"],
  "metadata": {
    "tdot_item_no": "710-04",
    "year": 2024,
    "is_composite": true,
    "includes_overhead_profit": true
  }
}
```

#### Commercial Cost Database -> CostItem (Conceptual Mapping)

```json
{
  "code": "RSM-312313.10-0400",
  "description": "Excavation, trench, common earth, 0-4 ft deep, machine",
  "unit": "CY",
  "rate": 18.50,
  "currency": "USD",
  "source": "rsmeans",
  "region": "USA_USD",
  "classification": {"masterformat": "31 23 13.10", "uniformat": "G10"},
  "components": [
    {"type": "labor", "name": "Crew C-1 (1 laborer)", "quantity": 0.35, "unit_rate": 22.45, "cost": 7.86, "unit": "hr"},
    {"type": "equipment", "name": "Hydraulic excavator 3/4 CY", "quantity": 0.35, "unit_rate": 25.49, "cost": 8.92, "unit": "hr"},
    {"type": "material", "name": "No material", "quantity": 0, "unit_rate": 0, "cost": 0, "unit": "CY"}
  ],
  "tags": ["excavation", "trench", "earthwork", "rsmeans"],
  "metadata": {"city_cost_index": 1.0, "rsmeans_line": "312313.10-0400"}
}
```

### 8.3 Common Source Tags

Apply these `source` field values consistently:

| Source Tag | Description |
|-----------|-------------|
| `usace_ep1110` | USACE EP 1110-1-8 equipment rates |
| `fema_equipment` | FEMA Schedule of Equipment Rates |
| `bls_oews` | BLS Occupational Employment and Wage Statistics |
| `davis_bacon` | Davis-Bacon prevailing wage determinations |
| `tdot_bid` | Tennessee DOT average bid prices |
| `caltrans_bid` | California DOT contract cost data |
| `fdot_bid` | Florida DOT historical item average cost |
| `dot_bid` | Generic state DOT bid prices |
| `rsmeans` | Commercial unit-cost database import |
| `craftsman_nce` | Commercial estimator handbook |
| `enr_index` | Published construction cost index / material prices |
| `marshall_swift` | Replacement-cost valuation data |
| `richardson` | Commercial heavy-civil cost database |
| `icc_bvd` | Building valuation dataset |
| `cwicr` | DDC CWICR database (legacy) |
| `manual` | Manually compiled from multiple sources |
| `file_import` | Imported from a user-uploaded spreadsheet |
| `custom` | User-created custom items |

---

## 9. Classification Systems

### 9.1 MasterFormat (CSI)

This is the primary classification standard for US construction cost data: 50 divisions (00 to 49), each carrying hierarchical section numbers.

**The sitework divisions OCERP leans on:**

| Division | Name | Typical Items |
|----------|------|---------------|
| 01 | General Requirements | Project management, temporary facilities |
| 02 | Existing Conditions | Demolition, site assessment, environmental remediation |
| 31 | Earthwork | Excavation, fill, grading, compaction, dewatering |
| 32 | Exterior Improvements | Paving, landscaping, fencing, irrigation |
| 33 | Utilities | Water, sewer, storm drain, gas, electric, communications |
| 34 | Transportation | Roadways, bridges, rail, signage, markings |

**In the `classification` dict this reads as:**

```json
{"masterformat": "31 23 13"}
```

### 9.2 UniFormat (CSI)

An assembly-level classification aimed at early-stage estimating, built from letter-based elements with numeric subdivisions.

**The sitework elements you will use:**

| Element | Name |
|---------|------|
| G10 | Site Preparation |
| G20 | Site Improvements |
| G30 | Site Civil/Mechanical Utilities |
| G40 | Site Electrical Utilities |

**In the `classification` dict this reads as:**

```json
{"uniformat": "G30"}
```

### 9.3 Using Both Together

OCERP's `classification` dict can hold several standards at once:

```json
{
  "division": "02",
  "section": "4100",
  "category": "Selective Demolition",
  "masterformat": "02 41 00",
  "uniformat": "G10"
}
```

The CWICR import relies on `collection`, `department`, `section`, and `subsection` for its 4-level tree. US items can carry `masterformat` and `uniformat` right alongside the CWICR keys.

---

## 10. Step-by-Step: Building a New Regional Database

### 10.1 Define Scope

1. Pick the region (for example `USA_COLORADO`, `USA_SEATTLE`, `CA_TORONTO`).
2. Decide the project type (sitework, building, highway, utility).
3. List the MasterFormat divisions to cover.
4. Estimate the item count (12 to 30 makes a reasonable pilot).

### 10.2 Gather Source Data

| Data Need | Primary Source | Alternative | Format |
|-----------|---------------|-------------|--------|
| Equipment rates | FEMA Schedule (free, current) | USACE EP 1110-1-8 | PDF -> JSON |
| Labor wages | BLS OEWS (free API) | Davis-Bacon (county-level) | CSV/XLSX -> JSON |
| Material prices | Local supplier quotes | Home-improvement retailer websites | Manual -> JSON |
| Bid prices (validation) | State DOT website | Third-party DOT data portal | Excel/PDF -> JSON |
| Productivity rates | Commercial cost database (paid) | Commercial estimator handbook (paid) | API/book -> JSON |

### 10.3 Create Reference Data Files

Mirror the pilot structure and create these under `data/`:

```python
data/
├── {region}_equipment_rates.json    # Hourly equipment rates
├── {region}_labor_wages.json         # Hourly wages by occupation
├── {region}_material_rates.json       # Material prices
├── {region}_bid_prices.json           # Validation bid prices
└── {region}_cost_items.json          # Final CostItem array (import this)
```

### 10.4 Build Cost Items

For each cost item:

1. **Identify the crew composition** (trades, count, hours).
2. **Identify the equipment** (types, hours).
3. **Identify the materials** (quantities, units).
4. **Look up unit rates** from your reference data.
5. **Calculate each component cost** as quantity x unit_rate.
6. **Sum the component costs** to get the total rate.
7. **Validate** that the rate rounds to 2 decimal places.
8. **Cross-check** against bid prices (plus or minus 30% tolerance on a first pass).

### 10.5 Validation Checklist

Work through this list before you import:

- [ ] Each item satisfies `rate == sum(components.cost)` to within $0.01
- [ ] Each item carries a `region` (for example `USA_TENNESSEE`)
- [ ] Each item carries a `currency` (for example `USD`), or it will resolve from the region
- [ ] Each item carries a `source` (for example `manual`)
- [ ] Each component `type` is one of `labor`, `material`, `equipment`, `subcontractor`, `other`
- [ ] Every component `quantity` and `unit_rate` is a positive number
- [ ] Every component `cost` equals round(`quantity` x `unit_rate`, 2)
- [ ] There are no duplicate `(code, region)` pairs
- [ ] Classification codes line up with the standard you intend (MasterFormat, and so on)
- [ ] Tags are lowercase and on-topic
- [ ] Rates sit in the right unit (SF, CY, LF, EA, not SY, CF, and the like)

### 10.6 Add Region to Currency Map

In `backend/app/modules/costs/schemas.py` and `router.py`, add the new region to `_REGION_CURRENCY_FALLBACK`:

```python
"USA_TENNESSEE": "USD",
"USA_COLORADO": "USD",
```

### 10.7 Import

```bash
# Import using the recommended script
python scripts/import_tennessee_costs.py \
  --email you@example.com \
  --password "your-password" \
  --port 8000 \
  --data-dir /tmp/tn_import/tn_import_package/data
```

Or call the bulk API directly:

```bash
curl -X POST http://localhost:8000/api/v1/costs/bulk/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @data/usa_colorado_cost_items.json
```

---

## 11. Validation and Quality Assurance

### 11.1 Component Math Validation

**The check:** `abs(rate - sum(component_costs)) < 0.01`

```python
for item in cost_items:
    total = item["rate"]
    calculated = sum(c["cost"] for c in item["components"])
    assert abs(total - calculated) < 0.01, f"{item['code']}: {total} != {calculated}"
```

### 11.2 Bid Price Cross-Validation

Set the calculated rates against local DOT bid prices:

```python
variance_pct = (our_rate - tdot_rate) / tdot_rate * 100
```

**How to read the variance:**

| Variance | Assessment |
|----------|------------|
| plus or minus 5% | Excellent match |
| plus or minus 10% | Good match |
| plus or minus 15 to 20% | Acceptable for a first pass |
| plus or minus 20 to 30% | Needs investigation (scope differences likely) |
| over plus or minus 30% | Investigate; could be scope, productivity, or source data |

**What usually drives the variance:**
- Our rates are **direct cost only**; DOT prices fold in 15 to 25% overhead and profit.
- DOT items often pull in more scope (traffic control, erosion control, mobilization).
- Scale differences, such as residential sitework against highway heavy civil.
- Davis-Bacon (prevailing) wages against BLS (mean) wages.

### 11.3 Reasonableness Checks

| Check | Method |
|-------|--------|
| Labor hours per unit | Compare to published commercial manhour tables |
| Equipment hours per unit | Compare to USACE productivity guides |
| Material quantities per unit | Verify against construction takeoff standards |
| Total rate per SF/CY/LF | Compare to similar items in other regions (CWICR for EUR, a commercial database for USD) |
| Component cost percentages | For sitework, labor is usually 30 to 50%, material 30 to 50%, equipment 10 to 30% |

### 11.4 Continuity Checks

As you add items to a region that already has data:

- [ ] There are no `(code, region)` duplicates
- [ ] Units stay consistent within a category (all demolition items in SF, or all in CY, never mixed)
- [ ] Rate ordering is logical (house demolition costs more per SF than garage demolition)
- [ ] New items do not clash with CWICR or imported items (search by code and description)

---

## 12. Importing Data into OCERP

### 12.1 Bulk JSON Import

This is the main route for importing curated cost items:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/users/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/costs/bulk/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @data/us_tn_sitework_costs.json
```

**Behavior:** it creates all items and skips any where `(code, region)` already exists (no upsert). It returns the list of created items.

### 12.2 File Import (Excel/CSV)

For quick imports straight from spreadsheets:

```bash
curl -X POST http://localhost:8000/api/v1/costs/import/file/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/cost_items.xlsx"
```

**Columns the parser recognises automatically:** `code`, `description`, `unit`, `rate`/`price`, `currency`, `classification`/`din 276`/`masterformat`

**Limitations:** file import does not handle `components` arrays. For resource-based items, go through the bulk JSON import.

### 12.3 Python Import Script

The recommended script is `scripts/import_tennessee_costs.py`, which:

1. Authenticates through the regular user login (`POST /users/auth/login/`).
2. Loads every JSON data file from a directory.
3. Auto-generates component `code` fields where they are missing (required for catalog extraction).
4. Validates `rate == sum(components.cost)` for each item.
5. Calls `POST /costs/bulk/`.
6. Verifies the items by searching the API.

> **Note:** `scripts/import_cost_database.py` is the legacy script that uses demo auth on port 8082. It is deprecated for production use.

### 12.4 CWICR Catalog Import

For large CWICR regional catalogs (55K+ items per region):

```bash
# List available catalogs
curl -s http://localhost:8000/api/v1/costs/catalogues/ | python3 -m json.tool

# Load a catalog
curl -X POST http://localhost:8000/api/v1/costs/load-cwicr/DE_BERLIN \
  -H "Authorization: Bearer $TOKEN"
```

This downloads parquet data from GitHub, deduplicates it, extracts components, and bulk-inserts. The source is set to `"cwicr"`.

### 12.5 Clearing a Region

To wipe all items for a region before re-importing:

```bash
curl -X DELETE http://localhost:8000/api/v1/costs/actions/clear-region/USA_TENNESSEE \
  -H "Authorization: Bearer $TOKEN"
```

**This cannot be undone.** Use it with care.

### 12.6 Catalog Resource Extraction

After importing cost items with `components[]` arrays, pull their individual resources into the catalog so they can be reused in assemblies and the BOQ editor.

**Why bother extracting:**
- Components without a `code` field are **silently skipped** during extraction.
- Extracted resources become searchable in the catalog UI.
- They can be picked directly when building assemblies or adding resources to BOQ positions.
- Each resource reports avg/min/max rates and a usage count across all cost items in the region.

**With the standalone script:**

```bash
cd backend
python -m app.scripts.extract_tennessee_catalog
```

**Using the API** (requires the `catalog.extract` permission, i.e. a Manager or Admin role):

```bash
curl -X POST http://localhost:8000/api/v1/catalog/extract/ \
  -H "Authorization: Bearer $TOKEN"
```

**Confirm the extraction worked:**

```bash
# List regions with catalog resources
curl -s http://localhost:8000/api/v1/catalog/regions/ \
  -H "Authorization: Bearer $TOKEN" | jq .

# Search Tennessee catalog resources
curl -s "http://localhost:8000/api/v1/catalog/?region=USA_TENNESSEE&limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq '.total'
```

**The component `code` requirement:**

The extraction service groups components by their `code` field. A component with no `code` gets skipped:

```python
code = comp.get("code", "")
if not code:
    continue  # silently skipped
```

The import script (`scripts/import_tennessee_costs.py`) auto-generates codes in the form `TN-{TYPE}-{slug}` when they are missing.

---

## Appendix A: Source Comparison Matrix

| Source | Type | Data Provided | Geo | Update | Access | Cost | Best For |
|--------|------|--------------|-----|--------|--------|------|-----------|
| FEMA Equipment Rates | Gov Free | Equipment rates/hr | National | Annual | PDF | $0 | **Equipment rates (primary)** |
| BLS OEWS | Gov Free | Labor wages | National/state/metro | Annual | API/CSV | $0 | **Labor wages (primary)** |
| Davis-Bacon | Gov Free | Prevailing wages | County | Annual | HTML/PDF | $0 | **Federal project wages** |
| State DOT Bid Prices | Gov Free | Unit bid prices | State | Annual | Excel/web | $0 | **Validation benchmark** |
| Building valuation dataset | Member Free | $/SF by occupancy | National | Semi-annual | PDF | Membership* | Conceptual estimates |
| Commercial unit-cost database | Commercial | Tens of thousands of unit costs | Hundreds of cities | Quarterly | Online/API | Paid | Comprehensive estimating |
| Commercial estimator handbook | Commercial | Several thousand unit costs | National | Annual | Book/API | Paid | Affordable estimating |
| Published cost indexes | Commercial | Cost indexes plus materials | ~20 cities | Monthly | Web | Paid | Escalation/trending |
| Market-intelligence service | Commercial | Project leads | US/Canada | Continuous | Web | Paid | Market intelligence |
| Replacement-cost valuation | Commercial | $/SF replacement | US/Canada | Quarterly | Online | Paid | Building valuation |
| Commercial heavy-civil database | Commercial | 100K+ items | 100+ markets | Quarterly | Online | Paid | Heavy civil/industrial |

\* The building valuation dataset requires membership

## Appendix B: Region Naming Convention

OCERP accepts several region key formats. The legacy CWICR catalogues follow two conventions.

### Currency-based regions (broad markets)

CWICR uses these for national and regional price databases:

```
USA_USD           # United States (broad market, USD currency)
UK_GBP            # United Kingdom (broad market, GBP currency)
DE___DDC_CWICR    # Germany (CWICR internal identifier)
```

### Location-based regions (specific metros/states)

These cover custom or city-specific data:

```
USA_TENNESSEE     # Tennessee (state-level)
USA_COLORADO      # Colorado (state-level)
USA_SEATTLE       # Seattle metro
USA_CHICAGO       # Chicago metro
CA_TORONTO        # Toronto, Canada
DE_BERLIN         # Berlin, Germany
FR_PARIS          # Paris, France
PT_SAOPAULO       # São Paulo, Brazil
```

### Custom region guidelines

When you create new custom regions:

1. **Prefer `COUNTRYCODE_STATE`** for state-wide data: `USA_TENNESSEE`, `USA_COLORADO`.
2. **Prefer `COUNTRYCODE_CITY`** for metro-specific data: `USA_SEATTLE`, `USA_CHICAGO`.
3. **Avoid currency codes** in custom regions unless you are deliberately building a broad national market.
4. **Keep it uppercase** and use underscores: `USA_TENNESSEE`, not `usa_tennessee` or `USA-Tennessee`.
5. **Stay consistent** within a region set. Do not mix `USA_NASHVILLE` and `USA_TENNESSEE` for the same data.

## Appendix C: Recommended Data Strategy for US Sitework

### Immediate (Free, Already Implemented)

1. **FEMA Equipment Rates** for equipment cost items (replaces USACE, more current).
2. **BLS OEWS** for labor wage items (API-accessible, annual updates).
3. **State DOT bid prices** for validation items (start with TDOT, add others as needed).
4. **Local material quotes** for manual market estimates.

### Near-Term (Free, Moderate Effort)

5. **Davis-Bacon wage determinations** for prevailing wage items (requires a SAM.gov scraper).
6. **Additional state DOT data** for CA (Caltrans), FL (FDOT), TX (TxDOT), WI.

### Medium-Term (Paid, High Value)

7. **A commercial estimator handbook (API)** for general building costs.
8. **A published cost-index subscription** for cost indexes and material prices for escalation.

### Long-Term (Paid, Enterprise)

9. **A comprehensive commercial unit-cost database** for the deepest item coverage.
10. **A commercial heavy-civil database** for deep heavy-civil data.

## Appendix D: File Structure Reference

```
OCERP/
├── data/
│   ├── usace_equipment_rates.json    # Equipment rates (Sec 7.1.1)
│   ├── bls_labor_wages.json          # Labor wages (Sec 7.1.2)
│   ├── material_rates.json            # Material prices (Sec 7.1.4 context)
│   ├── tdot_bid_prices.json           # Validation prices (Sec 7.1.4)
│   ├── us_tn_sitework_costs.json          # Final CostItem array, sitework (Sec 4)
│   └── us_tn_concrete_utilities_costs.json # Final CostItem array, concrete & utilities
├── scripts/
│   ├── import_tennessee_costs.py          # Recommended import script (Sec 12.3)
│   └── import_cost_database.py            # Legacy demo-auth script (deprecated)
├── docs/
│   ├── US_COST_DATABASE_PILOT.md          # Pilot handoff document
│   ├── US_COST_DATABASE_METHODOLOGY.md    # This document
│   ├── validation_report.md               # TDOT cross-validation results
│   └── cost-database-import.md            # CSV/Excel import guide
├── backend/app/modules/costs/
│   ├── models.py                          # CostItem ORM model (Sec 4.1)
│   ├── schemas.py                         # Pydantic schemas (Sec 4.2)
│   ├── router.py                          # REST API endpoints (Sec 3.3)
│   ├── repository.py                      # Database queries (Sec 3.2)
│   └── service.py                         # Business logic layer
└── backend/app/modules/catalog/
    ├── models.py                          # CatalogResource ORM model
    ├── service.py                         # Extraction logic (Sec 3.4, Sec 12.6)
    ├── router.py                          # Catalog REST API
    └── repository.py                      # Catalog data access
```
