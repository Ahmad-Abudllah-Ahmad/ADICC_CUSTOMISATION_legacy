# RFC 35 — EAC v2 platform implementation

**Status:** draft → ready for review
**Date:** 2026-04-25
**Author:** Claude Opus + Artem
**Related:**
- `OCE_EAC_Implementation_Spec_v2_International.md` (1748 lines, six sections: engine, aliases, block editor, Excel import, classifier composition, 4D)
- RFC 34 — OCE_TECH_SPEC_GLOBAL integration plan
- ADR 002 — No IfcOpenShell, DDC canonical format is single source of truth

## 1. Why this RFC exists, and how it relates to RFC 34

RFC 34 mapped the global tech spec onto six waves (W0 foundation → W5 AI Copilot). Two of those waves — **W3 Validation+Classification** and **W4 QTO** — were sketched at the level of "we need an EAC schema" and "we need extraction rules."

The new EAC v2 spec is the **deep implementation specification** for those two waves and adds two pieces RFC 34 did not cover:

1. **One engine, four output modes** — the spec explicitly forbids creating parallel engines for QTO, validation, clash, issue. RFC 34's separate W3 / W4 narrative is replaced by **one EAC v2 engine + four adapters**.
2. **A new 4D module** built on the EAC selector layer — not present in RFC 34 at all.
3. **A visual block editor** (UX), **Excel import**, **classifier compositions**, and **parameter aliases** — none of these were in RFC 34.

This RFC therefore:
- Replaces RFC 34 §7 (Wave 3) and §8 (Wave 4) with the deep plan in §5–§10 below.
- Adds a new wave (4D) handled in §10.
- Inherits RFC 34's locked decisions L1–L10 and adds L11–L15 specific to EAC v2.
- Inherits RFC 34's 10 verification gates.
- Reuses ADR 002 — no new BIM parser; the EAC engine reads canonical Parquet through DuckDB.

## 2. Gap audit (verified against current code, 2026-04-25)

Audited via parallel Explore agent across `backend/app/modules/{validation,compliance_ai,bim_requirements,bim_hub,catalog,boq,schedule,dashboards}` and `backend/app/core/validation/`.

| Spec section | Existing surface | Coverage | Critical gaps |
|---|---|---|---|
| §1 EAC engine | `core/validation/engine.py` (`ValidationRule` ABC, `RuleRegistry`), `validation/service.py`, `compliance_ai/` skeleton | **30 %** | No `EacRule`/`EacRuleset`/`EacRun` ORM. No constraint-operator vocabulary. No `aggregate`/`clash` output modes. No formula/safe-eval. Rules are static Python classes, not a declarative `definition_json`. |
| §2 Parameter aliases | — | **0 %** | Greenfield. Zero references to "alias" / "synonym" in backend. |
| §3 Block editor + IDS round-trip | `bim_requirements/parsers/ids_parser.py`, `ids_exporter.py` (read-only IDS); no block UI | **15 %** | IDS parser exists (good); block UI greenfield; IDS↔EAC mapping greenfield; no live counter, no test panel, no template gallery. |
| §4 Excel import | `bim_requirements/parsers/excel_parser.py` (BIM requirement extract), `boq/cad_import.py` (DDC pipeline) | **20 %** | No EAC DSL Excel format. No round-trip. No column-mapping wizard. No partial-import. |
| §5 Classifier composition | `cad/classification_mapper.py` (Revit→DIN276/NRM/MasterFormat lookup tables), `catalog/models.py` (CatalogResource) | **35 %** | No `EacClassifier` / `EacClassifierComposition` / `EacMappingRule` tables. No CWICR-as-classifier (it's raw CSV). No parametric items, no intermediate items, no conflict resolver. Built-in classifiers (Uniformat, Uniclass, OmniClass, NRM2/3, ÖNORM) absent. |
| §6 4D module | `schedule/models.py` (Schedule, Activity, Relationship, Baseline, Progress), `schedule/router.py` (CRUD) | **30 %** | Schema exists. No PMXML/MSPDI import. No `EacScheduleLink`. No simulation, no S-curve dashboard, no mobile PWA, no AI auto-link. |
| §7 Tests + bench | `backend/tests/` (pytest), `frontend/e2e/` (Playwright) | n/a | Coverage targets and benchmarks must be applied per ticket; existing harness is fine. |
| §8 Migration v1→v2 | `validation_reports` table is full; no persistent `ValidationRule` table | n/a | Migration script needed: in-memory `RuleRegistry` → `eac_rules` rows. Round-trip parity test. |

**Summary:** EAC engine, aliases, block editor, Excel import, composition, and 4D import are essentially greenfield (despite scaffolding in adjacent modules). DuckDB-on-Parquet plumbing (`dashboards/duckdb_pool.py`, `bim_hub/dataframe_store.py`) is mature and is the right execution surface for the engine.

## 3. Locked decisions specific to EAC v2 (extending RFC 34 L1–L10)

| # | Decision | Rationale |
|---|---|---|
| L11 | **One engine, four output modes.** No parallel engines for QTO, validation, clash, issue. The `EacRule.output_mode` enum drives the formatter. | Spec §0.1 imperative; user-confirmed. Eliminates the duplicate-DSL trap. |
| L12 | **Rule definition lives in `eac_rules.definition_json` (JSONB) plus a stable JSON Schema (`EacRuleDefinition` v2.0).** Code never branches on rule shape; it parses the JSON. | Spec §1.5. Lets us version the schema, ship marketplace rule packs, and round-trip via IDS / Excel without code changes. |
| L13 | **Execution kernel = DuckDB over canonical Parquet (DDC-canonical), not row-by-row Python.** Selector + projection + predicate compile to one DuckDB query per rule; aggregates run in DuckDB SQL. | Spec NFR-1.1 (5 s / 100 k elements / 4 vCPU). Existing `dashboards/duckdb_pool.py` LRU-cached connections. |
| L14 | **Safe formula evaluator = `simpleeval` with whitelisted functions** (math, unit converters, IF/CASE, regex match). No `eval()`, no Python compile. | Spec §1.7 + RFC 34 L-stack adds `simpleeval`. ReDoS-safe regex via Python `re` with timeout. |
| L15 | **`/api/v2/eac/*` is the canonical surface.** `/api/v1/validation/*` and `/api/v1/boq/qto/*` continue to work for ≥6 months by proxying to v2. No big-bang flag flip. | Spec §0.2 + §8 migration plan. |
| L16 | **All EAC writes are tenant-scoped.** `eac_*` tables get RLS policies in the same migration that creates them, not in a follow-up — Wave 0 W0.4 must land before EAC ORMs go to staging. | RFC 34 L9 + spec §1.2 multi-tenant requirement. |
| L17 | **Block editor frontend uses `dnd-kit`** (not `react-dnd`) for drag-drop. | Spec §3.4 explicit preference. `dnd-kit` has WCAG 2.1 AA keyboard nav out of the box; `react-dnd` does not. |

## 4. Architectural shape

```
                    ┌──────────────────────────────────────┐
                    │  EAC v2 Engine (single kernel)       │
                    │  - Validator → ParsedRule            │
                    │  - Planner   → ExecutionPlan         │
                    │  - Executor  → DuckDB(canonical PQ)  │
                    │  - Formatter → {agg|bool|clash|issue}│
                    └──────────────┬───────────────────────┘
                                   │
        ┌──────────────┬───────────┼───────────┬──────────────┐
        ▼              ▼           ▼           ▼              ▼
   ┌─────────┐   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐
   │ §3      │   │ §4      │  │ §5      │  │ §6 4D    │  │ §1.7     │
   │ Block   │   │ Excel   │  │ Class.  │  │ Schedule │  │ Public   │
   │ Editor  │   │ Import  │  │ Compos. │  │ Links    │  │ REST API │
   └─────────┘   └─────────┘  └─────────┘  └──────────┘  └──────────┘
        │              │           │           │              │
        └──────────────┴───────────┴───────────┴──────────────┘
                                   │
                                   ▼
                    Aliases (§2) — name resolution layer

       Consumers: /api/v2/eac/* + UI features (validation, BoQ, 4D)
```

The block editor, Excel import, composition, and 4D linker are all **adapters**: each takes user intent in its own modality and emits an `EacRuleDefinition` which the engine evaluates uniformly.

## 5. Wave EAC-1 — engine core (4 weeks; replaces RFC 34 §W3.1–§W3.3)

### EAC-1.1 — Schema migration: `eac_rules`, `eac_rulesets`, `eac_runs`, `eac_run_result_items`, `eac_global_variables`, `eac_rule_versions`

- **Files**: `backend/app/modules/eac/manifest.py`, `models.py`, Alembic migration `XXXX_eac_v2_core.py`.
- **Schema** (full set — names match spec §1.4 verbatim so future spec updates merge cleanly):
  - `eac_rules` (id UUIDv7, ruleset_id, name, description, output_mode enum, definition_json JSONB, formula text, result_unit, tags string[], version int, is_active bool, tenant_id, project_id NULL, created_*, updated_*, **RLS on tenant_id**).
  - `eac_rulesets` (id, name, description, kind enum, classifier_id NULL, parent_ruleset_id NULL, tenant_id, project_id NULL, is_template bool, is_public_in_marketplace bool, tags, RLS).
  - `eac_runs` (id, ruleset_id, model_version_id, started_at, finished_at, status enum, summary_json JSONB, elements_evaluated int, elements_matched int, error_count int, triggered_by enum).
  - `eac_run_result_items` — **partition by run_id**, hot rows go to PG, cold rows spool to Parquet under `data/eac/runs/{run_id}/results.parquet`.
  - `eac_global_variables` (id, scope enum org|project, scope_id, name, value_type enum, value_json, description, is_locked bool).
  - `eac_rule_versions` (id, rule_id, version_number, definition_json, formula, changed_by_user_id, changed_at, change_reason).
- **Tests first**:
  - `tests/unit/eac/test_schema_migration.py` — `alembic downgrade base && alembic upgrade head` survives a fixture rule round-trip.
  - `tests/integration/eac/test_rls_eac_rules.py` — two-tenant adversarial test (RFC 34 W0.4 contract).
- **Acceptance**: schemas in PG, RLS enforced, golden fixture rule survives downgrade/upgrade.

### EAC-1.2 — Canonical JSON Schema (`EacRuleDefinition` v2.0)

- **Files**: `backend/app/modules/eac/schema/EacRuleDefinition.schema.json`, `eac/schemas.py` (Pydantic mirror), `packages/oe-schema/eac.ts` (TS mirror auto-generated).
- **Tests first**:
  - `tests/unit/eac/test_schema_jsonschema.py` — 30 valid, 30 invalid sample rules (each FR-1.4 selector kind, each FR-1.5 attribute kind, each FR-1.6 constraint operator) → schema accepts/rejects correctly. **100 % schema coverage** per AC-1.1.
  - `tests/unit/eac/test_schema_pydantic_parity.py` — Pydantic and JSON Schema agree on every fixture.
- **Acceptance**: schema published; round-trip `rule → JSON → rule` is identity (AC-1.5).

### EAC-1.3 — Validator + Planner

- **Files**: `eac/engine/validator.py`, `eac/engine/planner.py`.
- **Validator responsibilities**: schema check, alias_id / classifier_id / variable name existence, formula syntax (parse via `simpleeval` AST visitor), `between` ordering, ReDoS reject (compile regex with timeout, or use `re2` if env requires).
- **Planner responsibilities**: pull selector → DuckDB SQL `WHERE` clause; pull attribute set → projection list; emit `ExecutionPlan { duckdb_query, projection, post_python }`.
- **Tests first**:
  - `tests/unit/eac/test_validator.py` — 25 cases covering every FR-1.10 path (cyclic local var, unknown alias, malformed formula, treat_missing_as_fail edge, etc.).
  - `tests/unit/eac/test_planner.py` — assertion on the generated DuckDB SQL for 10 reference rules; selectors compose with AND/OR/NOT correctly.
- **Acceptance**: errors are structured (`code`, `path`, `message_i18n_key`); never raise unstructured exceptions to callers.

### EAC-1.4 — Executor + four output formatters

- **Files**: `eac/engine/executor.py`, `eac/engine/formatters/{aggregate,boolean,clash,issue}.py`.
- **Executor**: feeds `ExecutionPlan` to a pooled DuckDB connection on the canonical Parquet, projects only required columns, runs in a Celery task (RFC 34 L2), emits progress via `JobRun` (RFC 34 W0.1).
- **Formatters**:
  - `aggregate` — applies `simpleeval` formula per element, sums via DuckDB SQL, returns `{value, unit, per_element[]}`.
  - `boolean` — emits `(element_id, pass, attribute_snapshot)` rows; written to `eac_run_result_items` for ≤100k results, spooled to Parquet otherwise.
  - `clash` — calls existing/new geometry kernel (out of EAC-1; stubbed to return empty list with `WARNING: clash kernel not configured`); full impl lands in EAC-1.6.
  - `issue` — for each `pass=False` row, renders `IssueTemplate` via `simpleeval` template, emits BCF-compatible topic dataclass; persists to existing `PunchItem` table or a new `eac_issues` table — **decision deferred to EAC-1.5 ticket review**, default: new table.
- **Tests first**:
  - `tests/integration/eac/test_executor_aggregate.py` — golden DDC-canonical fixture (100 walls, 50 slabs, 30 doors); 10 reference rules each with expected aggregate.
  - `tests/integration/eac/test_executor_boolean.py` — same fixture, 10 boolean rules with expected pass/fail counts + attribute snapshots.
  - `tests/integration/eac/test_executor_idempotent.py` — same input twice → byte-identical output (FR-1.15).
  - `tests/integration/eac/test_executor_partial_errors.py` — divide-by-zero on one element → that element's `error` populated, other 99 elements still pass (FR-1.11).
- **Acceptance**: NFR-1.1 benchmark passes (5 s / 100 k / single rule on 4 vCPU dev box).

### EAC-1.5 — Issue formatter + `eac_issues` storage

- **Files**: `eac/engine/formatters/issue.py`, model `EacIssue` in `eac/models.py`.
- **Schema**: `eac_issues` (id, run_id FK, rule_id FK, element_id, title, description, topic_type enum, priority enum, stage, viewpoint_json, labels string[], tenant_id, RLS).
- **Why a new table, not reusing `PunchItem`**: PunchItem is field-report-shaped (photos, geolocation, trade, status); EAC issues are model-coordination-shaped (viewpoints, BCF labels). Bridging via `eac_issue.linked_punch_item_id` (NULL by default) lets a coordinator promote an EAC issue into a field punch when needed.
- **Tests first**: `tests/integration/eac/test_issue_formatter.py` — fail rule → issue persisted, BCF export shape ok, viewpoint coordinates plausible.
- **Acceptance**: issue rule against fixture produces 5 expected issues with stable IDs; promoting one to PunchItem leaves traceability link.

### EAC-1.6 — Clash kernel (deferred — placeholder ticket)

- **Files**: `eac/engine/clash/{kernel,obb,exact}.py`.
- Spec §1.7 ClashConfig (`exact|obb|sphere` × `min_distance|intersection_volume|enclosed`).
- **Recommendation**: defer to a separate spike. The DDC canonical Parquet already includes triangulated meshes (per ADR 002). The kernel is a CPU geometry library wrapper — likely `trimesh` or `pyvista` — and a spike must validate it against a 50 k-element fixture before we lock the API.
- **Acceptance for EAC-1.0 milestone**: clash mode returns a structured `ClashKernelNotConfigured` warning; UI hides the clash mode option until EAC-1.6 ships.

### EAC-1.7 — Public REST API `/api/v2/eac/`

- **Files**: `eac/router.py`, `eac/schemas_api.py`, `eac/dependencies.py`.
- Endpoints: 22 endpoints from spec §1.7 (rules CRUD, validate, dry-run, runs CRUD, runs compare, rulesets CRUD, rulesets export/import, global-vars CRUD).
- **Tests first**:
  - `tests/integration/eac/api/test_rules_crud.py` — full CRUD + version history.
  - `tests/integration/eac/api/test_dry_run.py` — sample_size=10 returns 10 results in <500 ms (perf budget §7.3).
  - `tests/integration/eac/api/test_run_async.py` — POST /runs returns 202 + run_id, polling reaches `success` with progress 0→100.
- **Acceptance**: OpenAPI 3.1 doc auto-generated, each endpoint has en/ru/de example response (NFR-1.6); generated TS client compiles with no manual edits.

**Wave EAC-1 deliverable**: spec §1 acceptance criteria AC-1.1 through AC-1.6 all green. Migration AC-1.7 lands in EAC-7.

## 6. Wave EAC-2 — parameter aliases (2 weeks)

### EAC-2.1 — Schema + resolver

- **Files**: model `EacParameterAlias`, `EacAliasSynonym`, `EacAliasSnapshot`; `eac/aliases/resolver.py`.
- **Resolver algorithm** (spec FR-2.5): sort synonyms by `priority` asc → for each, test against element properties (with `pset_filter`, `source_filter`, `case_sensitive`) → on match, apply `unit_multiplier`, return value.
- **Tests first**: `tests/unit/eac/test_alias_resolver.py` — 50-synonym alias on 100-property element completes in <10 ms (AC-2.2).

### EAC-2.2 — Built-in catalog seed (≥30 aliases × 9 langs)

- **Files**: Alembic data migration `XXXX_eac_alias_catalog_seed.py`, source dataset at `data/eac/aliases/catalog.json`.
- Coverage: `_Length`, `_Width`, `_Height`, `_Thickness`, `_Volume`, `_Area`, `_Perimeter`, `_Weight`, `_Mass`, `_Diameter`, `_Radius`, `_Depth`, `_Mark`, `_Code`, `_Name`, `_Description`, `_Comments`, `_Manufacturer`, `_Model`, `_SerialNumber`, `_Material`, `_StructuralMaterial`, `_Finish`, `_Color`, `_FireRating`, `_LoadBearing`, `_IsExternal`, `_AcousticRating`, `_ThermalResistance`, `_UValue`, `_Level`, `_Storey`, `_Zone`, `_Discipline`, `_Uniformat`, `_MasterFormat`, `_OmniClass`, `_Uniclass`, `_NRM`, `_DIN276`. **40 aliases** × **9 langs** = 360 synonym rows seeded.
- **Tests first**: `tests/unit/eac/test_alias_catalog_seed.py` — every spec'd alias present, every alias has ≥9 synonyms, no duplicate priority within an alias.

### EAC-2.3 — REST API + UI page

- Endpoints from spec §2.4 (CRUD + usages + test + bulk-resolve + import/export).
- UI page `/eac/aliases` — switch org/project, override badges, drawer editor, test panel.
- **Tests first**:
  - `tests/integration/eac/api/test_alias_test_endpoint.py` — round-trip resolve.
  - `tests/e2e/eac-aliases.spec.ts` — Playwright: create alias, override at project level, screenshot of override badge, then delete project-level → org-level visibility restores.
- **Visual**: `frontend/test-results/eac-aliases-list.png`, `eac-aliases-override-badge.png`.

**Wave EAC-2 deliverable**: spec §2 AC-2.1..AC-2.5 green.

## 7. Wave EAC-3 — visual block editor + IDS round-trip (5 weeks)

### EAC-3.1 — Block primitives library

- **Files**: `frontend/src/features/eac/components/{EacBlockPalette,EacCanvas,EacRuleHeader,EacSelectorBlock,EacPredicateBlock,EacAttributeBlock,EacConstraintBlock,EacFormulaEditor,EacLocalVariablePanel,EacTestPanel,EacInspector,EacOutputModeConfig,EacBlockChooserModal,EacTemplateGallery}.tsx`.
- Drag-drop via `dnd-kit` (L17). Color tokens per spec §3.2 (gray/green/purple/blue/yellow). Each block type has both color and icon (accessibility AC-3.6).
- **Tests first**: Storybook stories for every block + axe-core a11y assertion on each.

### EAC-3.2 — Canvas + slot system + nested logic

- Slots: Selector / Predicate / Formula (or Set A / Set B + ClashConfig for clash; Predicate + IssueTemplate for issue).
- AND/OR n-children, NOT 1-child, Triplet 2-children (Attribute + Constraint).
- Multi-select, bulk delete/duplicate, collapse/expand, undo/redo (unbounded stack).
- **Tests first**: `tests/e2e/eac-editor-build-rule.spec.ts` — Flow 3.5.1 (external walls thickness rule) end-to-end with screenshots at 5 stages.

### EAC-3.3 — Live element counter + test panel

- Counter: debounce 500 ms, abort-controller for stale requests (spec EC-3.2). Calls `/rules:dry-run` with `sample_size=0, count_only=true`.
- Test panel: 10 random + 10 first-matched dry-run; pass/fail color coding; "Open in 3D" hands off to `BIMViewer` with selected `element_ids`.
- **Tests first**: `tests/e2e/eac-editor-test-panel.spec.ts` — counter updates after edits; test panel displays per-element pass/fail.

### EAC-3.4 — Formula editor (Monaco)

- Monaco editor with custom language definition for the EAC formula DSL.
- Autocomplete: `${Volume}` (resolves through alias), local vars, global vars, function library.
- Inline syntax errors with squiggles.
- **Tests first**: `tests/unit/eac/formula/test_formula_parser.py` — 30 expressions cover every operator; `tests/e2e/eac-formula-autocomplete.spec.ts` — typing `${V` opens completion menu, selecting fills `${Volume}`.

### EAC-3.5 — Template gallery (≥20 templates × 9 langs)

- Categories from spec FR-3.8.
- Each template = JSON file under `data/eac/templates/{slug}.json` + i18n in `data/eac/templates/i18n/{lang}.json`.
- **Tests first**: `tests/unit/eac/templates/test_templates_validate.py` — every template parses against `EacRuleDefinition.schema.json`.

### EAC-3.6 — IDS XML round-trip

- **Files**: `eac/ids/{importer,exporter}.py` (already partial in `bim_requirements/parsers/ids_parser.py` — extend, not rewrite).
- IDS facets → EAC mapping table (spec FR-3.11.1):
  - `entity` → EntitySelector ifc_class.
  - `attribute` → AttributeRef pset_name=null + source_filter=instance.
  - `property` → AttributeRef with pset_name.
  - `classification` → EntitySelector classification_code.
  - `material` → predicate on material attribute.
  - `partOf` → predicate on parent-child (requires DDC canonical relation column — verify in W0.2 spike).
- **Tests first**:
  - `tests/unit/eac/ids/test_ids_roundtrip.py` — 10 buildingSMART sample IDS files, each: parse → EAC → export → byte-compare canonicalised XML (AC-3.2).
  - `tests/integration/eac/ids/test_ids_xsd_validate.py` — exported XML validates against the official IDS-1.0.xsd.
- **Acceptance**: round-trip lossless on the 10 reference IDS files; warning emitted on the 2 deliberately-malformed ones.

### EAC-3.7 — BCF export (issue mode)

- **Files**: `eac/bcf/exporter.py`. Hand-rolled XML or `bcf-py` (no IfcOpenShell — ADR 002).
- Topic = one `eac_issue` row; viewpoint rendered headless via Playwright on the existing `BIMViewer` (RFC 34 W2.2 reuse path).
- **Tests first**: round-trip — generated `.bcfzip` opens cleanly in any BCF-compatible tool (manual once + automated XSD validation always).
- **Visual**: `bcf-export-flow.png`.

**Wave EAC-3 deliverable**: spec §3 AC-3.1..AC-3.8 green.

## 8. Wave EAC-4 — Excel import (2 weeks)

### EAC-4.1 — Templates + parser

- **Files**: `eac/excel/{templates,parser,column_mapper}.py`. Use `openpyxl` (already installed).
- Simple template: 16 columns per spec FR-4.3. Extended: + local vars, issue/clash fields, separate sheets for global vars and aliases.
- Templates generated dynamically with i18n headers (≥9 langs per AC-4.1).
- **Tests first**: `tests/unit/eac/excel/test_template_generation.py` — every header in every language is non-null.

### EAC-4.2 — Two-phase import (preview → commit)

- POST `/excel:preview` returns `{rows, errors, warnings, suggested_column_mapping}` without persisting.
- POST `/excel:import` with explicit `import_mode=all_or_nothing|partial`.
- **Tests first**:
  - `tests/integration/eac/excel/test_preview_partial_commit.py` — 100-row file with 5 deliberate errors; preview shows them; partial commit creates 95 rows; errors exported back to Excel with `Error` column.
  - `tests/integration/eac/excel/test_import_1000_rows.py` — 1000 rows commit in <30 s (AC-4.2).

### EAC-4.3 — Round-trip export

- POST `/excel-templates:export-ruleset` exports an existing ruleset in the same format.
- **Tests first**: round-trip identity — export → re-import → ruleset semantically equal (AC-4.3).

### EAC-4.4 — Auto-column-mapping wizard (UI)

- **Files**: `frontend/src/features/eac/import/ExcelImportPage.tsx`, `ColumnMapperWizard.tsx`.
- Fuzzy-match column names via `rapidfuzz`.
- **Tests first**: `tests/e2e/eac-excel-import.spec.ts` — drop file → preview → fix one error → commit; screenshots at 4 stages.

**Wave EAC-4 deliverable**: spec §4 AC-4.1..AC-4.7 green.

## 9. Wave EAC-5 — classifier composition (5 weeks)

### EAC-5.1 — Classifier schema + bulk import

- **Files**: `eac/classifiers/{models,service,bulk_import}.py`. Tables `eac_classifiers`, `eac_classifier_items`, `eac_item_rules`.
- **Tests first**: `tests/unit/eac/classifiers/test_classifier_tree.py` — bulk import 1000-item tree, `parent_code` resolves, `level` computed, `unit` defaults applied.

### EAC-5.2 — Built-in classifier seed (10 classifiers)

- **Files**: `data/eac/classifiers/{cwicr,uniformat_ii,masterformat,omniclass_21,omniclass_22,omniclass_23,uniclass,nrm2,nrm3,din276,onorm_b1801,cobie}.parquet` + per-classifier i18n JSON.
- CWICR is already CSV in `data/cwicr/` — extend the existing seed task to also bulk-insert into `eac_classifier_items` with `is_built_in=true`.
- **Tests first**: `tests/integration/eac/classifiers/test_seeded.py` — every spec'd classifier present, every item has ≥1 language name.

### EAC-5.3 — Composition + mapping rules + parametric items

- **Files**: tables `eac_classifier_compositions`, `eac_composition_levels`, `eac_mapping_rules`. Service `eac/classifiers/composition_runner.py`.
- **Tests first**:
  - `tests/unit/eac/composition/test_parametric_split.py` — 100 walls of mixed thickness → split correctly across "120mm" / "250mm" / "380mm" CWICR rows.
  - `tests/integration/eac/composition/test_intermediate_items.py` — 50 walls, 30 matched by detail rules, 20 unmatched → auto-generated intermediate item with `auto_generated=true` and the 20 elements listed.
  - `tests/integration/eac/composition/test_conflict_resolution.py` — element matches 2 rules → behavior under each of `first_match | all_matches | error | manual`.

### EAC-5.4 — Auto-suggest mapping (rule-based + ML)

- Rule-based first (string match on classifier item names ↔ existing EAC rule selectors).
- ML pass via pgvector (RFC 34 L3): each classifier item gets a `bge-m3` embedding (RFC 34 L4); each existing EAC rule gets one too; top-K nearest cosine.
- **Tests first**: golden 50-item Uniformat ↔ CWICR fixture; recall@1 ≥ 0.70, recall@3 ≥ 0.90.

### EAC-5.5 — Composition runner + report

- POST `/compositions/{id}:run` returns hierarchical JSON: top-level Uniformat tree → CWICR children → per-element data.
- **Tests first**: `tests/integration/eac/composition/test_run_perf.py` — 1000 mapping rules, 100k elements, <60 s (AC-5.6 implication).

### EAC-5.6 — UI: composition editor + report viewer

- **Files**: `frontend/src/features/eac/classifiers/{CompositionEditorPage,CompositionReportPage}.tsx`.
- Tree view + flat view + pivot view + 3D view (raycast colored by top-level group).
- **Tests first**: `tests/e2e/eac-composition.spec.ts` — create composition, run, drill into intermediate item, screenshots at 4 stages.

**Wave EAC-5 deliverable**: spec §5 AC-5.1..AC-5.7 green.

## 10. Wave EAC-6 — 4D module (5 weeks; new — not in RFC 34)

### EAC-6.1 - PMXML / MSPDI / CSV import

- **Files**: `schedule/import/{pmxml,mspdi,csv,msproject_xml}.py`.
- PMXML: parse the schedule interchange XML, map to `Schedule` + `Activity` + `Relationship`.
- MSPDI: parse Project XML.
- **Tests first**:
  - `tests/integration/schedule/import/test_pmxml_real_files.py` — 5 real-world PMXML fixtures (open-source samples).
  - `tests/integration/schedule/import/test_mspdi.py` — full round-trip parse → re-export → byte-compare.

### EAC-6.2 — `EacScheduleLink` schema

- **Files**: model `EacScheduleLink` (table `eac_schedule_links`).
- Columns: id, task_id FK, rule_id NULL, predicate_json NULL (one of must be set), mode enum (`exact_match|partial_match|excluded`), tenant_id, RLS.
- **Tests first**: `tests/unit/eac/schedule/test_link_dryrun.py` — link with predicate `Category=Walls AND Level=1` resolves to expected element_ids on fixture model.

### EAC-6.3 — AI auto-link

- **Files**: `schedule/auto_link/agent.py`. Uses LLM provider abstraction from RFC 34 W5.6.
- Per task: extract action/object/location → propose top-3 EAC predicates with confidence + reasoning.
- **Tests first**: `tests/integration/schedule/auto_link/test_golden_50_tasks.py` — 50-task PMXML fixture; recall@1 ≥ 0.70.

### EAC-6.4 — Simulation engine

- **Files**: `schedule/simulation/{engine,renderer}.py`.
- Engine: for each date in `[from_date, to_date]`, compute element status (`not_started|in_progress|completed|delayed|ahead_of_schedule`) by joining tasks → links → elements.
- Renderer: integrates with `BIMViewer`; exports MP4 via Playwright + ffmpeg.
- **Tests first**:
  - `tests/integration/schedule/simulation/test_status_join.py` — 100 tasks × 1000 elements → expected status for 5 sample dates.
  - `tests/integration/schedule/simulation/test_perf_100k.py` — 100k elements, 30 fps target on dev box (AC-6.3).

### EAC-6.5 — S-curve / SPI / CPI dashboard

- **Files**: `schedule/dashboards/{router,service}.py` + `frontend/src/features/schedule/DashboardPage.tsx`.
- Endpoints from spec §6.4 dashboard.
- **Tests first**: golden fixture (100 tasks with planned + actual progress) → expected SPI / CPI / EAC / ETC values match hand-computed.

### EAC-6.6 — Mobile PWA — foreman view

- **Files**: `frontend/src/features/schedule/mobile/ForemanPage.tsx`. Service worker, IndexedDB queue, PWA manifest, icons.
- Camera capture, geolocation, voice notes via PWA APIs.
- Offline queue → sync on reconnect with conflict resolution (last-write-wins + warning).
- **Tests first**: `tests/e2e/schedule-foreman-offline.spec.ts` — Playwright in offline mode → mark complete → bring online → verify sync.

**Wave EAC-6 deliverable**: spec §6 AC-6.1..AC-6.8 green. Mobile PWA installs to home screen on iOS/Android.

## 11. Wave EAC-7 — migration v1 → v2 (1 week, threaded across other waves)

- Alembic data migration: walks `RuleRegistry` (in-memory rules from `core/validation/rules/*`), generates `eac_rules` rows with `migrated_from_legacy_id` populated.
- For each existing `ValidationReport` with `rule_id`, add `eac_rule_id` cross-reference (audit trail).
- `/api/v1/validation/*` proxy: shim that translates v1 calls to v2 internally; emits a `v1_proxy_call_total` Prometheus counter so we know when to sunset.
- **Tests first**: `tests/integration/eac/migration/test_v1_v2_parity.py` — same model + same rule → identical pass/fail counts and identical per-element results between v1 path and v2 proxied path.

## 12. Verification gates (inherited from RFC 34 §10)

All 10 RFC 34 gates apply to every EAC ticket: unit + integration + E2E + screenshot + OpenAPI + i18n + reversible migration + observability + ruff/mypy/coverage ≥85 % + manual browser check.

EAC-specific additions:
- **G11 — Schema parity:** every `EacRuleDefinition` change requires updating Pydantic + JSON Schema + TS types in the same PR; CI gate verifies the three are in lockstep.
- **G12 — IDS round-trip parity:** every editor change is followed by automated IDS export → re-import → AST-equal assertion against the 10 buildingSMART fixtures.
- **G13 — Tenant boundary on every EAC route:** integration test ensures each new endpoint enforces the RLS contract before merge.

## 13. Risks + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `simpleeval` whitelist too narrow → users want a custom function | Medium | Low | Add `register_function(name, callable)` extension point with strict signature constraints. |
| Block editor performance degrades on rules with >50 nested blocks | Medium | Medium | Virtualise nested rendering; spec EC-3.4 already permits suggesting refactor via local variables. |
| DuckDB query plan blows up on a 5 M-element model | Low | High | NFR-1.1 budget set at 100 k. Beyond that, partition by `level` or `discipline` and run rules per-partition (planner change, not engine change). |
| IDS spec drift (buildingSMART updates IDS-1.0 → IDS-1.1) | Low | Medium | Pin schema version in `EacRuleDefinition.metadata.ids_target=1.0`; add adapter in next minor. |
| 4D mobile PWA flaky on iOS Safari geolocation API | Medium | Medium | Feature-detect on capture; degrade gracefully without GPS; document on the foreman onboarding screen. |
| AI auto-link hallucinates predicates | High | Low | Confidence scores always shown; ≥0.85 = auto-apply; 0.65–0.85 = suggest; <0.65 = skip (matches RFC 34 W3.5 policy). |
| `_Length` alias resolves to wrong property on a multilingual model | High | Low | Test panel in editor (FR-3.4) shows attribute snapshot per element so user catches it before save. |

## 14. Success metrics (after Wave EAC-6 ships)

- Engine: NFR-1.1, NFR-1.2, NFR-1.3 all green on the reference dev box.
- Aliases: 40+ built-in aliases in 9 languages; AC-2.2 ≤10 ms.
- Editor: WCAG 2.1 AA via axe-core (zero violations); template gallery has ≥20 items.
- Excel: round-trip identity on the 5-fixture suite; 1 k rows ≤30 s.
- Composition: Uniformat ↔ CWICR auto-suggest recall@1 ≥0.70.
- 4D: simulation 30 fps on 100 k-element model; offline PWA reconciles 50-task batch in <2 s on reconnect.
- Migration: v1 vs v2 parity 100 % on the existing rule fixtures (≥60 rules in `core/validation/rules/`).

## 15. Dependency graph

```
RFC 34 W0 (foundation)
   │
   ├─→ EAC-1 Engine ──┬─→ EAC-2 Aliases (parallel after EAC-1.3)
   │                  ├─→ EAC-3 Block editor (frontend, parallel after EAC-1.7 API)
   │                  ├─→ EAC-4 Excel import (parallel after EAC-1.7)
   │                  ├─→ EAC-5 Composition (after EAC-1 + EAC-2)
   │                  └─→ EAC-6 4D module (after EAC-1)
   │
   └─→ EAC-7 Migration (threaded)
```

Single-track calendar: ~24 weeks. Parallel after EAC-1: ~14 weeks (EAC-2/3/4 parallel, then EAC-5/6 parallel).

## 16. Out of scope (explicit, per spec Appendix A)

- AI EAC-rule generator from PDF/Word requirements (separate RFC).
- BI connectors (separate RFC).
- npm `oce-viewer` package.
- Marketplace.
- Native mobile apps (PWA only).
- Real-time collaborative editing of rules (Phase 3).
- bSDD ontology resolution (Phase 2).

## 17. What I need to start

Building on the 5 questions in RFC 34 §15, plus four EAC-v2-specific:

6. **Confirm EAC-1 is the new W3** — formally retire RFC 34 W3.1–W3.6 in favor of EAC-1.1 through EAC-1.7? (Keeps one source of truth.)
7. **Confirm 4D becomes Wave 6** — adds 5 weeks to RFC 34's timeline; OK?
8. **Confirm `eac_issues` separate from `PunchItem`** — bridged via `linked_punch_item_id`, or merge them?
9. **Confirm clash mode deferred to EAC-1.6 spike** — block editor hides clash option until spike completes.

On confirmation, I open the per-wave RFC 36 (Wave 1 CDE close-out — unchanged from RFC 34) and start EAC-1.1 (schema migration) in parallel with RFC 34 W0.1 (Celery + Redis).
