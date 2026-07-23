# Formwork Management Module — Design Specification

Status: Draft 1
Author: OpenConstructionERP Core Team
Last updated: 2026-05-24
Contact: info@datadrivenconstruction.io
Implementation target: single 4-to-6-week development wave

---

## 1. Executive Summary

Formwork (Schalung / coffrage / encofrado / опалубка) is the **single most expensive
re-usable line item** on most concrete-heavy projects, yet it is the line item
**most poorly tracked** by general-purpose ERP and PMIS tools. A 240 m² wall-panel set
from a major supplier rents at roughly EUR 4–7 per m² per day; one mid-rise residential
project routinely runs EUR 200k–800k in formwork rental over a 9-month shell phase,
with a further 5–15 % surcharge silently absorbed at end-of-job for damage, missing
ties, and idle days that nobody attributed to a pour. Existing GC software treats
formwork either as bulk equipment (loses the panel-level accountability) or as a
material line on the BOQ (loses the rental clock and the condition history).

This module gives OpenConstructionERP a **first-class formwork lifecycle** —
catalogue, unit, accessory, order, assignment-to-pour, inspection, movement —
that fits a small contractor running 50 panels on one floor *and* a Doka-class
rental yard issuing 10 000 panels across 30 projects. It is vendor-neutral by
design: Doka, Peri, Ulma, Meva, Hünnebeck, RMD Kwikform, Faresin, Efco, and any
in-house steel/timber system register as `FormworkSystem` rows; no manufacturer
is privileged. Mobile-first field UX (PWA, scan + tap, offline queue) is a
core requirement, not an afterthought — the foreman, not the office, is the
primary writer of state changes.

---

## 2. Domain Primer (for non-construction readers)

**Formwork** is the temporary mould into which fresh concrete is poured. Once
the concrete has cured (typically 12 h to 7 days depending on element and mix),
the formwork is stripped, cleaned, and re-used on the next pour. A typical
concrete-shell project will cycle the same panels 20–80 times over its life.

Major **categories** the module must represent natively:

| Category               | Example use                                | Daily-rate driver       |
| ---------------------- | ------------------------------------------ | ----------------------- |
| Wall (Wand)            | Basement walls, shaft walls, retaining     | m² of formed surface    |
| Slab (Decke)           | Suspended floors, transfer slabs           | m² of formed surface    |
| Column (Stütze)        | Rectangular / round columns                | Lin. m of column height |
| Climbing (Klettern)    | Cores / shafts cast lift-by-lift           | Per climbing unit       |
| Self-climbing / ACS    | Tall cores cast without a crane lift       | Per ACS bracket         |
| Table (Tisch)          | Large pre-assembled slab decks, flown      | Per table assembly      |
| Modular framed         | Standard panel grid (Framax, Maximo, etc.) | m² of panel face        |
| Beam / heavy duty      | Transfer beams, post-tensioned beams       | Lin. m of beam soffit   |
| Shoring / falsework    | Vertical load support under slabs          | Per prop / per tower    |
| Single-face / blindside | Slurry walls, against existing structure  | m² of formed face       |

**Accessories** are the small parts that make formwork work: ties (DW15 /
DW20 / SK series), wing nuts, water-stop ties, cones, anchors, climbing
brackets, push-pull props, tripods, walers, soldiers, corner units, infill
timbers, magnets, chamfer strips, form release oil. Some accessories are
**re-usable** (ties, props), some are **consumed per pour** (cones, sleeves,
release oil). The module must distinguish: re-usable accessories track like
panels; consumables track as inventory drawdown against the project's BOQ.

A formwork **pour cycle** is the smallest unit of useful work the module
models: *deliver → set → align → close → pour → cure → strip → clean → move
or return*. Rental clocks run from delivery to return, not from set to
strip — so leaving panels idle on a slab for 11 days because the rebar crew
was late is a real and frequently un-attributed cost.

**Engineering input** typically comes from the formwork supplier's own CAD
tool (Doka Tipos 8, Peri CAD, Ulma 3D-Form). Output is a per-pour drawing
plus a list of panels and accessories. OpenConstructionERP will not embed
those tools; it ingests their output as a CSV/Excel/JSON parts list and
optionally the IFC of the formwork assembly through the existing DDC
cad2data pipeline.

---

## 3. Entity Model

All models live in `backend/app/modules/formwork/models.py` and follow
existing OCERP conventions (UUID PK via `GUID()`, `oe_formwork_*` table
prefix, `metadata_` JSON column for extension, server defaults on money
and currency, `created_at` / `updated_at` from `Base`).

### 3.1 Catalogue layer (tenant-shared, seedable)

```python
class FormworkSystem(Base):
    """Vendor-neutral catalogue of formwork systems.

    Examples: Doka Framax Xlife, Peri Maximo MX, Ulma Orma, Meva Mammut XT.
    Seeded from data/seeds/formwork_systems.csv; community modules may
    register additional rows at startup via rule_registry-style hooks.
    """
    __tablename__ = "oe_formwork_system"

    code: str                       # "doka.framax_xlife"  (vendor-neutral key)
    manufacturer: str               # "Doka" / "Peri" / "in_house"
    model_name: str                 # "Framax Xlife"
    category: str                   # wall|slab|column|climbing|table|...
    typical_panel_face_m2: Decimal  # nominal panel size for rate maths
    description_i18n: dict          # {"en": "...", "de": "...", ...}
    spec_sheet_url: str | None
    manufacturer_part_prefix: str | None  # for barcode parsing


class FormworkUnit(Base):
    """A specific physical instance — one panel, one prop, one bracket.

    `code` is unique per tenant; `barcode` (free text) is what the foreman
    scans. Multiple units can share the same system+sku — only `code` is
    PK-unique.
    """
    __tablename__ = "oe_formwork_unit"

    code: str                       # internal asset tag, unique
    barcode: str | None             # what the QR/barcode reader returns
    system_id: UUID -> FormworkSystem
    sku: str                        # manufacturer SKU within the system
    nominal_size: str               # "2.70 x 0.90 m" — free text label
    nominal_face_m2: Decimal        # m² of formed surface for one unit
    weight_kg: Decimal | None
    ownership: str                  # owned | rented_in | sub_owned
    supplier_contact_id: UUID | None -> Contact   # contacts module
    purchase_value: Decimal | None
    currency: str                   # "" default — service layer fills
    condition: str                  # new|good|fair|repair|scrap
    surface_treatment: str | None   # phenolic|board|sandblasted|...
    surface_remaining_pours: int | None  # est. pours until reskin needed
    home_yard_location: str | None
    current_location_type: str      # yard|in_transit|project|repair|lost
    current_location_id: UUID | None  # project_id or yard_id depending on type
    last_seen_at: datetime | None
    metadata_: dict


class FormworkAccessory(Base):
    """Re-usable accessories tracked at *aggregate* count, not per-serial.

    Ties, wing nuts, props, tripods. Consumables (cones, sleeves, release
    oil) are *not* tracked here — they belong on the BOQ as material.
    The kind=`consumable` row type exists only for very high-value
    consumables a yard manager wants to count (e.g. magnetic chamfer).
    """
    __tablename__ = "oe_formwork_accessory"

    code: str
    system_id: UUID | None -> FormworkSystem  # null = system-agnostic
    accessory_type: str             # tie|prop|tripod|waler|soldier|...
    kind: str                       # reusable | consumable_tracked
    nominal_size: str               # "DW15 x 1.00 m"
    unit_weight_kg: Decimal | None
    total_owned: int                # aggregate count owned
    total_in_yard: int              # currently in yard (denormalised cache)
    total_deployed: int             # currently on projects (denormalised)
    total_lost: int                 # written-off in rolling 12 mo
    metadata_: dict


class FormworkAccessoryAllocation(Base):
    """Audit row: who pulled which accessories for which assignment."""
    __tablename__ = "oe_formwork_accessory_allocation"

    accessory_id: UUID
    assignment_id: UUID -> FormworkAssignment
    quantity_out: int
    quantity_returned: int
    quantity_damaged: int
    quantity_lost: int
    out_at: datetime
    returned_at: datetime | None
```

### 3.2 Commercial layer

```python
class FormworkOrder(Base):
    """Rental contract or purchase order with an external supplier.

    Mirrors `oe_procurement_purchase_order` shape so a planned formwork
    order can be promoted to a real PO without re-keying. Owned units
    are *not* represented here — they live in FormworkUnit directly.
    """
    __tablename__ = "oe_formwork_order"

    order_no: str                   # human reference; unique per tenant
    order_type: str                 # rental | purchase
    supplier_contact_id: UUID -> Contact
    project_id: UUID | None         # null = central yard order
    currency: str
    daily_rate_basis: str           # per_m2 | per_unit | per_lump_sum
    delivery_planned_for: date
    delivery_actual_at: datetime | None
    return_planned_for: date | None
    return_actual_at: datetime | None
    status: str                     # draft|confirmed|delivered|partial_return|closed|cancelled
    total_value_estimate: Decimal
    notes: str
    procurement_po_id: UUID | None -> PurchaseOrder   # promoted link
    metadata_: dict


class FormworkOrderLine(Base):
    __tablename__ = "oe_formwork_order_line"

    order_id: UUID
    system_id: UUID -> FormworkSystem
    sku: str
    description: str
    quantity_ordered: Decimal
    quantity_delivered: Decimal
    quantity_returned: Decimal
    unit: str                       # ea | m2 | m
    daily_rate: Decimal
    minimum_rental_days: int        # contractual floor
    notes: str
```

### 3.3 Operational layer

```python
class FormworkAssignment(Base):
    """A *use of formwork on a specific pour*. Closest analogue to an
    EquipmentRental row but pour-scoped, not project-scoped.

    The same unit can appear in many sequential assignments — that is
    exactly the re-use cycle the module exists to measure. A unit may
    NOT appear in two open (status=in_use) assignments simultaneously.
    """
    __tablename__ = "oe_formwork_assignment"

    project_id: UUID -> Project
    pour_id: UUID | None            # FK to upcoming oe_concrete_pour table
    bim_zone_ref: str | None        # canonical-format zone or element id
    level: str | None               # "level_03" — copy from BIM zone
    section: str | None             # free text: "core_A"
    cast_type: str                  # wall|slab|column|beam|foundation|other
    formed_area_m2: Decimal | None  # planning value
    planned_set_at: datetime
    planned_strip_at: datetime
    actual_set_at: datetime | None
    actual_strip_at: datetime | None
    status: str                     # planned|delivered|set|cast|stripped|cleaned|returned
    pour_cycle_number: int          # 1 = first re-use, 2 = second, ...
    foreman_user_id: UUID | None
    notes: str


class FormworkAssignmentUnit(Base):
    """Join: which specific unit IDs are part of this assignment."""
    __tablename__ = "oe_formwork_assignment_unit"

    assignment_id: UUID
    unit_id: UUID
    role: str                       # primary|filler|corner|infill
    condition_in: str               # snapshot at set
    condition_out: str | None       # snapshot at strip
    moved_to_assignment_id: UUID | None  # for re-use cycle traceability
```

### 3.4 Quality & movement layer

```python
class FormworkInspection(Base):
    """Pre-use and post-use checks. Photos in `documents` module."""
    __tablename__ = "oe_formwork_inspection"

    unit_id: UUID | None            # null = batch inspection of assignment
    assignment_id: UUID | None
    inspection_type: str            # pre_use|post_use|periodic|return
    inspected_at: datetime
    inspector_user_id: UUID
    result: str                     # pass|pass_with_notes|fail|scrap
    damage_severity: str | None     # cosmetic|minor|major|destructive
    repair_cost_estimate: Decimal | None
    currency: str
    photo_document_ids: list[UUID]  # FK to documents module
    notes: str
    chargeback_to: str | None       # subcontractor_id | own_loss


class FormworkMovement(Base):
    """Every physical move generates one row. Source of truth for location."""
    __tablename__ = "oe_formwork_movement"

    movement_type: str              # delivery|transfer|return|loss|scrap|repair_out|repair_in
    from_location_type: str         # yard|project|in_transit|supplier
    from_location_id: UUID | None
    to_location_type: str
    to_location_id: UUID | None
    moved_at: datetime
    initiated_by_user_id: UUID
    transport_reference: str | None # truck plate, delivery note number
    notes: str
    unit_ids: list[UUID]            # JSON: which units in this consignment
    accessory_lines: list[dict]     # [{accessory_id, qty}]
```

Twelve tables total. Numeric money: `Numeric(18, 4)` with `server_default="0"`,
currency `String(3)` with `server_default=""` (service layer fills from tenant
preference — see `feedback_no_orjson_default` and the v3 EUR-default audit).
All money fields are serialised as strings in API responses to avoid the
float-money trap currently flagged across modules in `MONEY_FLOAT_REMAINING.md`.

---

## 4. API Surface

All endpoints mount at `/api/v1/formwork/`. Responses use the existing
`{data: ..., meta: ...}` envelope where the module already returns lists.

### 4.1 Catalogue

```
GET    /systems                          List systems (?manufacturer=, ?category=)
POST   /systems                          Create system               [admin]
PATCH  /systems/{id}                     Update system               [admin]
POST   /systems/{id}/seed-units          Bulk-add units from CSV     [manager]

GET    /units                            List units (?status=, ?project_id=, ?system_id=, ?q=)
POST   /units                            Create unit                 [manager]
GET    /units/{id}                       Get one + last 20 movements
PATCH  /units/{id}                       Update unit                 [manager]
DELETE /units/{id}                       Soft-delete (status=scrap)  [manager]
POST   /units/lookup                     Body: {barcode|code}        [editor]
POST   /units/bulk-status                Bulk update {ids, new_status}[editor]

GET    /accessories                      List accessories
POST   /accessories                      Create                      [manager]
PATCH  /accessories/{id}                 Update                      [manager]
POST   /accessories/{id}/reconcile       Body: {counted_in_yard}     [yard_manager]
```

### 4.2 Commercial

```
GET    /orders                           List orders (?status=, ?project_id=)
POST   /orders                           Create rental/purchase      [manager]
GET    /orders/{id}                      Detail + lines + linked PO
PATCH  /orders/{id}                      Update header               [manager]
POST   /orders/{id}/confirm              draft -> confirmed          [manager]
POST   /orders/{id}/promote-to-po        Promote to procurement PO   [manager]
POST   /orders/{id}/close                Finalize + freeze billing   [manager]
POST   /orders/{id}/lines                Add line                    [manager]
PATCH  /orders/{id}/lines/{line_id}      Update line                 [manager]
DELETE /orders/{id}/lines/{line_id}      Remove line                 [manager]
```

### 4.3 Assignments (the operational core)

```
GET    /assignments                      List (?project_id=, ?status=, ?level=)
POST   /assignments                      Create planned assignment   [editor]
GET    /assignments/{id}                 Detail + units + inspections
PATCH  /assignments/{id}                 Update header               [editor]
POST   /assignments/{id}/units           Add unit IDs                [editor]
DELETE /assignments/{id}/units/{unit_id} Remove unit                 [editor]
POST   /assignments/{id}/accessories     Add accessory lines         [editor]
POST   /assignments/{id}/transition      Body: {to_status}           [editor]
                                         planned->delivered->set->cast->
                                         stripped->cleaned->returned
                                         FSM-validated, same engine as
                                         schedule_advanced / variations
POST   /assignments/{id}/reuse           Clone for next pour cycle   [editor]
                                         Body: {new_pour_id, units_kept[]}
                                         Returns new assignment with
                                         pour_cycle_number incremented.
```

### 4.4 Field operations (mobile-optimised)

```
POST   /field/scan                       Body: {barcode}             [site_worker]
                                         Returns minimal unit + current
                                         assignment + valid next actions.
                                         <100 ms p95 target.
POST   /field/quick-action               Body: {unit_ids[], action}  [site_worker]
                                         action in {mark_delivered,
                                         mark_set, mark_stripped,
                                         flag_damage}.
                                         Idempotent via client-supplied
                                         action_id (sync-queue safe).
POST   /field/photo-upload               multipart                   [site_worker]
                                         Returns document_id to attach
                                         to inspection/damage record.
POST   /field/inspection                 Body: {unit_id|assignment_id,
                                                result, damage_severity?,
                                                notes, photo_document_ids[]}
                                                                     [site_worker]
GET    /field/my-assignments             What's on my project today  [site_worker]
GET    /field/sync                       ?since=ts — bulk pull for
                                         offline cache priming       [site_worker]
```

### 4.5 Movements & analytics

```
GET    /movements                        List (?unit_id=, ?type=, ?since=)
POST   /movements                        Record a movement           [yard_manager]
POST   /movements/return                 Return-to-yard consignment  [yard_manager]
                                         Auto-creates post_use inspections.

GET    /inspections                      List (?unit_id=, ?result=)
POST   /inspections                      Create                      [editor]
PATCH  /inspections/{id}                 Update                      [editor]

GET    /dashboard/project/{project_id}   Per-project rollup:
                                         - rental cost burn-down vs budget
                                         - units on site by category
                                         - upcoming returns / overruns
                                         - damage incidents this week
GET    /dashboard/yard                   Yard-wide:
                                         - utilisation per system
                                         - top idle units (>14 d on project)
                                         - shrinkage / loss YTD
                                         - reskin queue
GET    /reports/reuse-cycle              CSV/Excel: per unit, pour-cycle history
GET    /reports/idle-days                CSV/Excel: units idle on projects
GET    /reports/damage-chargebacks       CSV/Excel: by subcontractor
```

### 4.6 Representative request/response shapes

```jsonc
// POST /api/v1/formwork/field/scan
// Request
{"barcode": "DOKA-FX-271-0090-A0007421"}

// Response
{
  "unit": {
    "id": "8b3f...",
    "code": "FW-0007421",
    "system": {"code": "doka.framax_xlife", "name_i18n_key": "fw.sys.doka.framax_xlife"},
    "nominal_size": "2.70 x 0.90 m",
    "condition": "good",
    "current_location_type": "project",
    "current_location_id": "proj-...",
    "current_assignment_id": "asgn-..."
  },
  "current_assignment": {
    "id": "asgn-...",
    "level": "level_03",
    "section": "core_A",
    "cast_type": "wall",
    "status": "set",
    "pour_cycle_number": 4
  },
  "valid_next_actions": ["mark_stripped", "flag_damage"]
}
```

```jsonc
// POST /api/v1/formwork/assignments/{id}/transition
// Request
{"to_status": "stripped", "occurred_at": "2026-05-24T14:12:00Z"}

// Response (200) — same shape as schedule_advanced FSM transitions
{
  "id": "asgn-...",
  "status": "stripped",
  "actual_strip_at": "2026-05-24T14:12:00Z",
  "events_published": ["formwork.assignment.stripped"]
}
```

---

## 5. Frontend Pages

Frontend lives at `frontend/src/features/formwork/`. Routes registered through
the existing `app/router` module config. All strings via `useTranslation('formwork')`.

### 5.1 Routes

```
/formwork                              Inventory (units list)
/formwork/units/:id                    Unit detail (movements + assignments timeline)
/formwork/systems                      Catalogue admin
/formwork/orders                       Rental orders list
/formwork/orders/:id                   Order detail
/formwork/planning                     Pour-cycle planning calendar
/formwork/assignments/:id              Assignment detail (units, inspections)
/formwork/yard                         Yard manager dashboard
/formwork/reports                      Reports launcher
/formwork/field                        Mobile field UI (PWA shell)
/formwork/field/scan                   Camera scanner full-screen
```

### 5.2 Inventory page (desktop) — ASCII wireframe

```
+----------------------------------------------------------------------------------------+
|  Formwork - Inventory                  [+ New unit]  [Import CSV]   [Bulk status...]   |
+----------------------------------------------------------------------------------------+
| Filters: System [Doka Framax v]  Status [Any v]  Project [Any v]   Search [.........]  |
+----------------------------------------------------------------------------------------+
| [ ] | Code        | System            | Size         | Condition | Location  | Last seen |
+----------------------------------------------------------------------------------------+
| [ ] | FW-0007421 | Doka Framax Xlife | 2.70x0.90 m  |  Good     | Sky Tower | 2 h ago   |
| [ ] | FW-0007422 | Doka Framax Xlife | 2.70x0.90 m  |  Fair *   | Sky Tower | 2 h ago   |
| [ ] | FW-0007430 | Peri Maximo MX    | 2.70x2.40 m  |  Good     | Yard A    | 6 d ago   |
| [ ] | FW-0007441 | Ulma Orma         | 3.00x1.00 m  |  Repair   | Repair Bay| 1 d ago   |
| [ ] | FW-0008012 | Doka Framax Xlife | 1.35x0.90 m  |  Good     | In transit| 4 h ago   |
+----------------------------------------------------------------------------------------+
| Showing 1-50 of 1 247                                       < Prev   Page 1 of 25   > |
+----------------------------------------------------------------------------------------+
|  Selected: 0 units      [Move...]  [Inspect...]  [Scrap...]   [Print labels]           |
+----------------------------------------------------------------------------------------+

* asterisk = surface_remaining_pours <= 3 (reskin warning)
```

Key behaviours:
- AG Grid (same shared component as BOQ); column visibility persisted per user.
- Row click opens drawer with movements + assignment history (no full nav).
- Filters preserved in URL (deep-linkable).
- Bulk selection enables status change, move, scrap, print-labels.
- Reskin warning surfaces inline (asterisk + tooltip) before the unit goes
  out — yard managers told us this is their #1 ask.

### 5.3 Planning calendar (desktop) — ASCII wireframe

```
+-------------------------------------------------------------------------------+
|  Sky Tower — Formwork planning                  [Week | 2 weeks | Month]      |
+-------------------------------------------------------------------------------+
|                Mon 25  Tue 26  Wed 27  Thu 28  Fri 29  Sat 30  Sun 31         |
| Level 3 ----------------------------------------------------------------------|
|  Core A   [== set ====[ cast ][ cure  ][ strip ]                             ]|
|           120 m2  Doka Framax  cycle #4                                       |
|  Wall N1  [        deliv ][ set ][ cast ][ cure  ][ strip ]                  |
|           80 m2  Peri Maximo  cycle #2                                        |
| Level 4 ----------------------------------------------------------------------|
|  Core A         [   reuse of L3 set  ][ cast ][ cure ][ strip ]              |
|                                                                               |
| Idle alerts: 12 panels on Level 2 stripped 5 d ago, not moved (cost: EUR 410) |
+-------------------------------------------------------------------------------+
```

Bars are draggable; dragging recomputes daily-rate impact in the right rail
sidebar and warns when re-use chains break (e.g. shifting Level 4 set earlier
than Level 3 strip).

### 5.4 Field worker mobile view — ASCII wireframe

```
+---------------------------+
| Sky Tower - Today         |
| (synced 12:04, 0 queued)  |
+---------------------------+
|                           |
|   +-------------------+   |
|   |       SCAN        |   |
|   |   (camera icon)   |   |
|   +-------------------+   |
|                           |
| My assignments today      |
|---------------------------|
| L3 / Core A    [ Set    ] |
|   42 panels  cycle #4     |
| L3 / Wall N1   [ Cast   ] |
|   28 panels  cycle #2     |
| L2 / Wall S2   [ Strip  ] |
|   31 panels  cycle #3     |
|                           |
| Damage flags (mine)       |
|---------------------------|
| FW-0007422  Fair  2 d ago |
|                           |
|         [ Sync now ]      |
+---------------------------+
```

After scan:

```
+---------------------------+
| FW-0007421  Doka Framax   |
| 2.70 x 0.90 m   Good      |
+---------------------------+
| On: L3 / Core A           |
| Status: SET   cycle #4    |
+---------------------------+
|                           |
|   [  Mark STRIPPED     ]  |
|   [  Flag DAMAGE       ]  |
|   [  Move to other pour]  |
|   [  History           ]  |
+---------------------------+
|  Back to today            |
+---------------------------+
```

Implementation notes:
- PWA already configured at app root; this view registers a dedicated service
  worker route for `/formwork/field/*` that caches the last `/field/sync`
  payload in IndexedDB.
- Quick-action POSTs are wrapped in the existing `sync_queue` hook (used by
  `daily_diary` and `fieldreports`). Each action gets a client UUID so a
  replay after offline window is idempotent server-side.
- Camera scanning via `@zxing/browser` (already a dep in `bim_hub` for QR
  scanning the markup tokens). Manual entry fallback always visible.
- One-handed thumb zone: primary actions in the bottom 40 % of the screen.

---

## 6. Integration Points

| Module                     | Direction | Event / call                                       | Purpose                                              |
| -------------------------- | --------- | -------------------------------------------------- | ---------------------------------------------------- |
| `oe_projects`              | depends   | FK + project lifecycle subscription                | Assignments require a project; project archive cascades to assignments. |
| `oe_users`                 | depends   | Role/user lookup                                   | Foreman / yard manager / project manager identity.   |
| `oe_contacts`              | consumes  | Contact lookup (supplier)                          | Order supplier and chargeback target.                |
| `oe_documents`             | consumes  | Document IDs for photos                            | Inspection and damage report attachments.            |
| `oe_costs`                 | consumes  | Daily rate lookup; rolls up to project EAC         | Cost-of-formwork shows on EAC and project P&L.       |
| `oe_procurement`           | bidirectional | Emits `formwork.order.confirmed` -> procurement event handler creates PO; consumes `procurement.po.cancelled` to mark FormworkOrder cancelled. | Auto-PO from rental order; reverse cancellation propagates. |
| `oe_bim_hub` / `oe_cad`    | consumes  | Canonical-format zone / element IDs                | Assignments may reference a BIM zone (level + section) without coupling to IFC parser. NO IfcOpenShell. |
| `oe_clash`                 | emits     | `formwork.assignment.set` carries level + zone     | Clash module flags formwork that geometrically conflicts with rebar / MEP. |
| `oe_schedule_advanced`     | emits     | `formwork.assignment.transition`                   | Schedule tasks tagged "concrete pour L3 core A" can auto-link assignments and surface idle-days on the Gantt. |
| `oe_hse_advanced`          | emits/consumes | Failed inspection emits HSE-relevant incident if severity >= major; HSE inspection covering "shoring / falsework" can short-circuit to formwork inspection list. | Falsework collapse is the single highest-severity event on a concrete project — HSE must see it. |
| `oe_daily_diary`           | emits     | `formwork.assignment.transition` auto-creates diary entry stub | The diary entry the PM has to write every evening becomes one click instead of remembering 8 events. |
| `oe_eac` / `oe_full_evm`   | consumes  | Daily accrual stream                               | Earned-value tracking includes formwork burn vs forecast. |
| `oe_carbon`                | consumes  | Re-use cycle count -> embodied carbon amortisation | A panel re-used 60× has dramatically lower embodied carbon per pour than a panel re-used 4×. |
| `oe_dashboard`             | consumes  | New widget kind: `formwork.utilisation`            | Joins the existing dashboard widget catalogue.       |
| `oe_validation` (core)     | consumes  | Validation rules: `formwork.assignment_open_for_too_long`, `formwork.unit_in_two_open_assignments`, `formwork.return_pending_after_project_close`. | First-class citizen of OCERP's validation framework. |

Event names follow the `module.entity.verb` convention already in use by
`tendering.package.awarded`, `procurement.po.cancelled`, and the schedule FSM.

---

## 7. RBAC + Permissions Matrix

Permissions registered in `permissions.py` and consumed by `RequirePermission`
in the router. The site-worker role is a new addition to the existing role
hierarchy — implemented as a **role alias** in `ROLE_ALIASES` so the four
canonical roles (`admin`, `manager`, `editor`, `viewer`) stay intact, and
`site_worker` resolves to `editor` with **project-scoped record filters**
applied in the repository layer (same pattern used by `subcontractors`).

```python
permission_registry.register_module_permissions("formwork", {
    "formwork.system.read":              Role.VIEWER,
    "formwork.system.manage":            Role.ADMIN,
    "formwork.unit.read":                Role.VIEWER,
    "formwork.unit.create":              Role.MANAGER,
    "formwork.unit.update":              Role.MANAGER,
    "formwork.unit.scrap":               Role.MANAGER,
    "formwork.unit.bulk_status":         Role.EDITOR,
    "formwork.accessory.read":           Role.VIEWER,
    "formwork.accessory.manage":         Role.MANAGER,
    "formwork.accessory.reconcile":      Role.MANAGER,    # yard_manager alias -> MANAGER
    "formwork.order.read":               Role.VIEWER,
    "formwork.order.create":             Role.MANAGER,
    "formwork.order.confirm":            Role.MANAGER,
    "formwork.order.promote_to_po":      Role.MANAGER,
    "formwork.order.close":              Role.MANAGER,
    "formwork.assignment.read":          Role.VIEWER,
    "formwork.assignment.create":        Role.EDITOR,
    "formwork.assignment.update":        Role.EDITOR,
    "formwork.assignment.transition":    Role.EDITOR,
    "formwork.assignment.reuse":         Role.EDITOR,
    "formwork.inspection.create":        Role.EDITOR,
    "formwork.inspection.approve":       Role.MANAGER,
    "formwork.movement.read":            Role.VIEWER,
    "formwork.movement.create":          Role.EDITOR,
    "formwork.field.scan":               Role.VIEWER,     # site_worker alias -> EDITOR
    "formwork.field.quick_action":       Role.EDITOR,
    "formwork.dashboard.project":        Role.VIEWER,
    "formwork.dashboard.yard":           Role.MANAGER,
    "formwork.report.export":            Role.VIEWER,
})

# In ROLE_ALIASES (core/permissions.py)
ROLE_ALIASES["site_worker"] = Role.EDITOR
ROLE_ALIASES["yard_manager"] = Role.MANAGER
ROLE_ALIASES["formwork_engineer"] = Role.EDITOR
ROLE_ALIASES["project_manager"] = Role.MANAGER
```

Effective matrix (rows = permission, columns = role; `Y` = allowed,
`Y(p)` = project-scoped, `-` = denied):

| Permission                       | site_worker | yard_manager | project_manager | admin |
| -------------------------------- | :---------: | :----------: | :-------------: | :---: |
| formwork.system.read             |     Y       |      Y       |       Y         |   Y   |
| formwork.system.manage           |     -       |      -       |       -         |   Y   |
| formwork.unit.read               |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.unit.create             |     -       |      Y       |       Y         |   Y   |
| formwork.unit.scrap              |     -       |      Y       |       Y         |   Y   |
| formwork.unit.bulk_status        |     -       |      Y       |       Y         |   Y   |
| formwork.accessory.reconcile     |     -       |      Y       |       Y         |   Y   |
| formwork.order.create            |     -       |      Y       |       Y         |   Y   |
| formwork.order.promote_to_po     |     -       |      -       |       Y         |   Y   |
| formwork.assignment.create       |     -       |      -       |       Y         |   Y   |
| formwork.assignment.update       |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.assignment.transition   |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.assignment.reuse        |     -       |      -       |       Y         |   Y   |
| formwork.inspection.create       |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.inspection.approve      |     -       |      Y       |       Y         |   Y   |
| formwork.movement.create         |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.field.scan              |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.field.quick_action      |     Y(p)    |      Y       |       Y         |   Y   |
| formwork.dashboard.yard          |     -       |      Y       |       Y         |   Y   |
| formwork.report.export           |     Y(p)    |      Y       |       Y         |   Y   |

Project-scoped filtering enforced in `repository.py` using the existing
`verify_project_access` dependency (same mechanism as `daily_diary` and
`fieldreports`). Site workers attempting cross-project reads receive 404 (not
403) per the IDOR-hardening pattern established in v4.6.1 R7.

---

## 8. MVP (2 weeks) vs Full (6 weeks)

### MVP — 2-week single wave

Goal: a contractor with one project and 100–500 panels can replace
their spreadsheet. Doka's mobile-portal users would see this as an
"inventory + check-in" tool, not yet as a rental-billing engine.

| In scope                                             | Out of scope                                                   |
| ---------------------------------------------------- | -------------------------------------------------------------- |
| `FormworkSystem`, `FormworkUnit`, `FormworkAccessory` (no `Allocation` audit) | `FormworkOrder` / commercial layer                          |
| `FormworkAssignment` with simple status (open / closed), no FSM | Full FSM (planned -> delivered -> set -> ... -> returned) |
| `FormworkInspection` with photo (single)             | Periodic-inspection scheduling                                 |
| `FormworkMovement` (delivery / return / transfer)    | `FormworkAccessoryAllocation` audit                            |
| Field PWA: scan, quick mark-set / mark-stripped, flag-damage, offline sync | Calendar planning view, drag-to-replan                |
| Desktop inventory page (AG Grid)                     | Yard dashboard, reports CSV/XLSX                               |
| Seed: Doka Framax, Peri Maximo, Ulma Orma catalogues (~120 SKUs) | RMD Kwikform, Faresin, Hünnebeck seeds                |
| RBAC with site_worker / yard_manager aliases         | Procurement promote-to-PO                                      |
| 3 validation rules: open-too-long, double-booking, unreturned-at-project-close | BIM zone linking from canonical format            |
| ~30 backend tests, ~10 frontend tests                | Carbon module integration                                       |
| Alembic migration `formwork_init`                    | Dashboard widget                                                |

Estimated effort: 2 backend engineers + 1 frontend, 10 working days.

### Full module — 6-week deliverable

Adds (on top of MVP):
- Commercial layer (`FormworkOrder` + lines, promote-to-PO, rental clock).
- Full FSM with FSM-engine integration and event publication.
- Re-use cycle traceability (`moved_to_assignment_id` chain + report).
- Planning calendar (drag-to-replan with rate impact).
- Yard dashboard, project dashboard, dashboard widget.
- BIM zone linking via canonical-format references; clash module hook.
- HSE inspection cross-link for shoring / falsework.
- Carbon amortisation per re-use cycle.
- Daily diary auto-stub on status transition.
- 8 additional seeded catalogues (Meva, Hünnebeck, RMD, Faresin, Efco, generic-steel, generic-timber, in-house).
- Reports: re-use cycle, idle days, damage chargebacks (CSV + XLSX).
- ~120 backend tests, ~40 frontend tests, ~6 Playwright field scenarios.
- Mobile UX polish: one-hand mode, vibration on scan, bulk-scan-then-act.

Estimated effort: 3 backend + 2 frontend + 0.5 product, 6 calendar weeks (30 working days).

---

## 9. Open Questions for the Product Owner

1. **Scanning hardware.** Do we target device-camera-only (zxing, free, slower in
   poor light), or also support Bluetooth/USB barcode guns and Zebra hand-held
   PDAs that Doka's yards already deploy? Hardware support pushes timeline +1
   week and brings native-app pressure.
2. **Tenant model for the catalogue.** Is the `FormworkSystem` table shared
   across all tenants (one Doka seed for everyone) or per-tenant (each
   customer can edit their own copy)? Affects seed-loader strategy and how
   community-contributed system seeds are distributed.
3. **Rental-billing depth.** Do we need full accrual accounting (post a daily
   journal entry per unit per day to `oe_finance`), or is end-of-month
   summary roll-up to `oe_costs` enough? Full accrual = +2 weeks and a
   finance-module review.
4. **Owned vs rented separation.** Is "owned-by-customer" a real use case
   (large GCs increasingly own a stake), or are we 100 % rental-yard
   centric? Owned-flow needs depreciation, periodic inspection scheduling,
   and a yard-internal cost-rate alongside the supplier daily rate.
5. **Integration with manufacturer CAD output.** Doka's Tipos exports an
   XML parts list; Peri's PeriCloud exposes a project-data API. Do we ship
   parsers in this module, or land them as separate community modules later
   (preferred per the modules-as-plugins philosophy)? If in-module: scope
   creep risk + per-vendor format drift maintenance burden.

---

## 10. Reference Comparison

Doka **MyDoka** customer portal:
- Per-project rental list, downloadable delivery / return notes.
- Outstanding-items list pulled from yard ERP.
- E-signed delivery receipts (HTML + PDF).
- No re-use cycle metrics; no on-site condition reports; no offline mobile.
- Built around the supplier's own ERP back-end; closed to third-party inventory.

Peri **PeriCloud**:
- 3D pour planner browser viewer.
- Parts list export to CSV / Excel.
- Project-level cost forecast that compares planned vs actual rental days.
- Limited mobile (web-responsive, not offline-first).
- Vendor-locked: only Peri systems load into the planner.

Ulma **Construct** software, RMD Kwikform **TrakFast**, Meva **MevaPlan**:
- Vary in maturity. Common pattern: a planning tool + a yard ERP + a customer
  portal. All vendor-locked; none of them expose the inventory through an open
  API that a general contractor's PMIS could consume.

OpenConstructionERP **Formwork module** target differentiation:
- Vendor-neutral catalogue (every major manufacturer + in-house systems coexist).
- Offline-first mobile worker UX (PWA + sync queue, not a portal).
- Re-use cycle is a first-class metric (none of the above expose it cleanly).
- Open REST API + event bus, integrates with the same project a customer uses
  for BOQ / schedule / HSE / EAC — no silo.
- AGPL community edition with optional commercial; open data export
  (CSV / XLSX / JSON) at every screen.

The module's strategic claim: a customer of Doka, Peri, *or* Ulma can run this
module on top of their existing rental contracts and unify what today lives in
three vendor portals plus an Excel sheet on the foreman's desktop.

---

## Appendix A — File Layout (target)

```
backend/app/modules/formwork/
  manifest.py
  models.py
  schemas.py
  router.py
  service.py
  repository.py
  permissions.py
  events.py            # subscribes to procurement.po.cancelled
  validators.py        # 3 MVP rules, more in full scope
  seed.py              # FormworkSystem seeds
  migrations/
    versions/3130_formwork_init.py
  tests/

frontend/src/features/formwork/
  routes.tsx
  pages/
    InventoryPage.tsx
    UnitDetailPage.tsx
    SystemsAdminPage.tsx
    OrdersPage.tsx / OrderDetailPage.tsx
    PlanningCalendarPage.tsx
    AssignmentDetailPage.tsx
    YardDashboardPage.tsx
    ReportsPage.tsx
  field/
    FieldHomePage.tsx
    ScannerPage.tsx
    UnitActionsPage.tsx
    syncQueue.ts       # IndexedDB-backed offline queue
    serviceWorker.ts
  components/
    UnitGrid.tsx
    AssignmentTimeline.tsx
    PourCycleBar.tsx
    ReskinWarningBadge.tsx
  hooks/
    useUnits.ts
    useAssignments.ts
    useFieldScan.ts
  i18n/
    en.json  de.json  ru.json  fr.json  es.json  it.json  pl.json

data/seeds/
  formwork_systems.csv
  formwork_accessories.csv

docs/modules/
  FORMWORK_MODULE_DESIGN.md      <-- this file
```

## Appendix B — Risks

- **Scope creep into rental-yard ERP.** Doka and Peri's full yard ERPs took
  decades to mature. We commit to the *general contractor* and *small rental
  yard* persona only; we do not chase full warehouse-management features
  (bin slotting, asset-photo training pipelines, automated reorder points).
- **Tipos / PeriCloud integration drift.** Per Q5, we lean on
  community-module pattern to absorb format churn outside the core.
- **Mobile reliability.** Offline-first is hard; the daily-diary module's
  sync queue is the proven internal reference and must be re-used, not
  re-implemented.
- **Multi-currency rental.** A Swiss tenant ordering panels from a German
  yard runs CHF site / EUR contract; the existing currency-discipline
  (string serialisation, server-default `""`, service layer fills from
  tenant preference) carries forward unchanged.
