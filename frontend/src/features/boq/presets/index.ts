// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * BOQ custom-column presets — registry.
 *
 * Each preset is a curated set of columns that solves a single, real-world
 * BOQ workflow (procurement, quality, regional-standard compliance, etc).
 * Presets are organised into two regions:
 *
 *   - `universal` — applies anywhere (procurement, notes, schedule, ...)
 *   - country / standard codes — opt-in for specific markets
 *   - `integration` — cross-cutting integration columns (BIM, ERP, ...)
 *
 * Adding a preset to a BOQ creates its columns sequentially; existing
 * columns with the same `name` are skipped silently so re-applying a
 * preset is safe.
 *
 * Region values are the source of truth for the UI grouping in
 * `CustomColumnsDialog.tsx`. Keep regions stable — changing one shifts
 * a preset between the always-visible and collapsible sections.
 */
import {
  Package,
  FileText as NotesIcon,
  ShieldCheck,
  Leaf,
  Building2,
  FileCheck,
  Boxes,
  type LucideIcon,
  Flag,
  Gavel,
  Calendar as CalendarIcon,
  ClipboardList,
  Globe,
  Sparkles,
} from 'lucide-react';
import type { CustomColumnDef } from '../api';

export type PresetRegion =
  | 'universal'
  | 'germany'
  | 'austria'
  | 'usa'
  | 'australia'
  | 'brazil'
  | 'uk'
  | 'integration';

export interface ColumnPreset {
  id: string;
  region: PresetRegion;
  name: string;
  description: string;
  icon: LucideIcon;
  iconClass: string;
  columns: CustomColumnDef[];
}

/* ── Universal presets — apply anywhere ──────────────────────────────── */

const UNIVERSAL_PRESETS: ColumnPreset[] = [
  {
    id: 'procurement',
    region: 'universal',
    name: 'Procurement',
    description: 'Supplier, lead time, PO number, status - for purchasing tracking',
    icon: Package,
    iconClass: 'text-violet-600 bg-violet-500/10',
    columns: [
      { name: 'supplier', display_name: 'Supplier', column_type: 'text' },
      { name: 'lead_time_days', display_name: 'Lead Time (days)', column_type: 'number' },
      { name: 'po_number', display_name: 'PO Number', column_type: 'text' },
      {
        name: 'po_status',
        display_name: 'PO Status',
        column_type: 'select',
        options: ['Quoted', 'Ordered', 'In Transit', 'Delivered', 'Cancelled'],
      },
    ],
  },
  {
    id: 'notes',
    region: 'universal',
    name: 'Notes',
    description: 'Internal note + reference - quick context per position',
    icon: NotesIcon,
    iconClass: 'text-blue-600 bg-blue-500/10',
    columns: [
      { name: 'internal_note', display_name: 'Internal Note', column_type: 'text' },
      { name: 'reference', display_name: 'Reference', column_type: 'text' },
    ],
  },
  {
    id: 'quality',
    region: 'universal',
    name: 'Quality Control',
    description: 'Inspection status, inspector and date - for QA workflow',
    icon: ShieldCheck,
    iconClass: 'text-emerald-600 bg-emerald-500/10',
    columns: [
      {
        name: 'qc_status',
        display_name: 'QC Status',
        column_type: 'select',
        options: ['Pending', 'Passed', 'Failed', 'Rework', 'Waived'],
      },
      { name: 'inspector', display_name: 'Inspector', column_type: 'text' },
      { name: 'inspection_date', display_name: 'Inspection Date', column_type: 'date' },
    ],
  },
  {
    id: 'sustainability',
    region: 'universal',
    name: 'Sustainability',
    description: 'CO₂ footprint, EPD reference and material source',
    icon: Leaf,
    iconClass: 'text-green-600 bg-green-500/10',
    columns: [
      { name: 'co2_kg_per_unit', display_name: 'CO₂ kg/unit', column_type: 'number' },
      { name: 'epd_reference', display_name: 'EPD Reference', column_type: 'text' },
      { name: 'material_source', display_name: 'Material Source', column_type: 'text' },
    ],
  },
  {
    id: 'status_scope',
    region: 'universal',
    name: 'Status & Scope',
    description: 'Position status, scope flag, risk level and owner - for review workflows',
    icon: Flag,
    iconClass: 'text-amber-600 bg-amber-500/10',
    columns: [
      {
        name: 'position_status',
        display_name: 'Position Status',
        column_type: 'select',
        options: ['Draft', 'Confirmed', 'Awarded', 'In Progress', 'Done', 'On Hold'],
      },
      {
        name: 'scope_flag',
        display_name: 'Scope',
        column_type: 'select',
        options: ['In scope', 'Out of scope', 'Optional'],
      },
      {
        name: 'risk_level',
        display_name: 'Risk',
        column_type: 'select',
        options: ['Low', 'Medium', 'High'],
      },
      { name: 'owner', display_name: 'Owner', column_type: 'text' },
    ],
  },
  {
    id: 'tendering',
    region: 'universal',
    name: 'Tendering',
    description: 'Bidder, bid amount and award status - track tender packages per position',
    icon: Gavel,
    iconClass: 'text-indigo-600 bg-indigo-500/10',
    columns: [
      { name: 'tender_package', display_name: 'Tender Package', column_type: 'text' },
      { name: 'bidder', display_name: 'Bidder', column_type: 'text' },
      { name: 'bid_amount', display_name: 'Bid Amount', column_type: 'number' },
      { name: 'bid_date', display_name: 'Bid Date', column_type: 'date' },
      {
        name: 'award_status',
        display_name: 'Award Status',
        column_type: 'select',
        options: ['Pending', 'Accepted', 'Rejected', 'Tied'],
      },
    ],
  },
  {
    id: 'schedule',
    region: 'universal',
    name: 'Schedule',
    description: 'Start, end, duration and WBS code - link BOQ rows to the construction schedule',
    icon: CalendarIcon,
    iconClass: 'text-sky-600 bg-sky-500/10',
    columns: [
      { name: 'wbs_code', display_name: 'WBS Code', column_type: 'text' },
      { name: 'start_date', display_name: 'Start Date', column_type: 'date' },
      { name: 'end_date', display_name: 'End Date', column_type: 'date' },
      { name: 'duration_days', display_name: 'Duration (days)', column_type: 'number' },
      { name: 'predecessor', display_name: 'Predecessor', column_type: 'text' },
    ],
  },
];

/* ── Regional / standards-specific presets ──────────────────────────── */

const REGIONAL_PRESETS: ColumnPreset[] = [
  {
    id: 'gaeb_ava',
    region: 'germany',
    name: 'GAEB / AVA Style',
    description:
      'Splits unit rate into Lohn / Material / Geräte / Sonstiges + risk markup. Lohn/Material/Geräte auto-fill from position resources - no manual entry.',
    icon: FileCheck,
    iconClass: 'text-rose-600 bg-rose-500/10',
    columns: [
      { name: 'kg_bezug', display_name: 'KG-Bezug (DIN 276)', column_type: 'text' },
      // Lohn / Material / Geräte are derived from `metadata.resources[]`:
      // each one sums the per-unit subtotal of resources whose `type`
      // matches the role. ``Sonstiges`` is what's LEFT over (other +
      // operator + subcontractor) so the four EP columns add up to
      // ``unit_rate`` for any position that's been priced via resources.
      // ``Wagnis %`` stays a free-input number — it's a contractor
      // discretion knob and isn't carried on the position model.
      {
        name: 'lohn_ep',
        display_name: 'Lohn-EP',
        column_type: 'number',
        derived: 'resource_sum',
        resource_role: 'labor',
      },
      {
        name: 'material_ep',
        display_name: 'Material-EP',
        column_type: 'number',
        derived: 'resource_sum',
        resource_role: 'material',
      },
      {
        name: 'geraete_ep',
        display_name: 'Geräte-EP',
        column_type: 'number',
        derived: 'resource_sum',
        resource_role: 'equipment',
      },
      {
        name: 'sonstiges_ep',
        display_name: 'Sonstiges-EP',
        column_type: 'number',
        derived: 'resource_sum',
        // Catch-all bucket so Lohn + Material + Geräte + Sonstiges = unit_rate
        // even when the position carries operator / subcontractor resources.
        resource_role: ['other', 'operator', 'subcontractor'],
      },
      { name: 'wagnis_pct', display_name: 'Wagnis %', column_type: 'number' },
    ],
  },
  {
    id: 'oenorm_brz',
    region: 'austria',
    name: 'ÖNORM / BRZ Style',
    description:
      'LV position code, keyword, supplier + auto-computed labor share - matches Austrian ÖNORM B 2061 / A 2063 used in BRZ',
    icon: Building2,
    iconClass: 'text-orange-600 bg-orange-500/10',
    columns: [
      { name: 'lv_position', display_name: 'LV-Position', column_type: 'text' },
      { name: 'stichwort', display_name: 'Stichwort', column_type: 'text' },
      // Lohn-Anteil = labor share of unit rate, expressed as a percent.
      // Auto-derived from the position's resources so the user can't
      // accidentally enter an inconsistent value.
      {
        name: 'lohn_anteil_pct',
        display_name: 'Lohn-Anteil %',
        column_type: 'number',
        derived: 'percentage_of_unit_rate',
        resource_role: 'labor',
      },
      { name: 'aufschlag_pct', display_name: 'Aufschlag %', column_type: 'number' },
      { name: 'lieferant', display_name: 'Lieferant', column_type: 'text' },
    ],
  },
  {
    id: 'csi_masterformat',
    region: 'usa',
    name: 'USA - CSI MasterFormat',
    description:
      'Division / Section codes, crew, productivity and cost-data reference - matches CSI MasterFormat 2018',
    icon: ClipboardList,
    iconClass: 'text-blue-700 bg-blue-700/10',
    columns: [
      { name: 'csi_division', display_name: 'Division', column_type: 'text' },
      { name: 'csi_section', display_name: 'Section', column_type: 'text' },
      { name: 'crew_code', display_name: 'Crew Code', column_type: 'text' },
      { name: 'daily_output', display_name: 'Daily Output', column_type: 'number' },
      { name: 'cost_ref_code', display_name: 'Cost Ref Code', column_type: 'text' },
    ],
  },
  {
    id: 'aiqs_australia',
    region: 'australia',
    name: 'Australia - AIQS',
    description:
      'AIQS code, trade element, AS reference and floor area type - Australian QS measurement practice',
    icon: Globe,
    iconClass: 'text-yellow-600 bg-yellow-500/10',
    columns: [
      { name: 'aiqs_code', display_name: 'AIQS Code', column_type: 'text' },
      { name: 'trade_element', display_name: 'Trade Element', column_type: 'text' },
      { name: 'as_reference', display_name: 'Australian Standard', column_type: 'text' },
      { name: 'boma_group', display_name: 'BOMA Group', column_type: 'text' },
      {
        name: 'floor_area_type',
        display_name: 'Floor Area Type',
        column_type: 'select',
        options: ['GBA', 'NLA', 'Common'],
      },
    ],
  },
  {
    id: 'sinapi_brazil',
    region: 'brazil',
    name: 'Brazil - SINAPI',
    description:
      'SINAPI code, BDI, encargos and origin - matches Brazilian Caixa SINAPI cost-base format',
    icon: Sparkles,
    iconClass: 'text-lime-600 bg-lime-500/10',
    columns: [
      { name: 'sinapi_code', display_name: 'SINAPI Code', column_type: 'text' },
      {
        name: 'sinapi_tipo',
        display_name: 'Tipo',
        column_type: 'select',
        options: ['Insumo', 'Composição', 'Auxiliar'],
      },
      { name: 'bdi_pct', display_name: 'BDI %', column_type: 'number' },
      { name: 'encargos_pct', display_name: 'Encargos Sociais %', column_type: 'number' },
      { name: 'origem', display_name: 'Origem', column_type: 'text' },
    ],
  },
  {
    id: 'nrm2_uk',
    region: 'uk',
    name: 'UK - NRM2',
    description:
      'NRM2 code, element group / sub-element and cost-index reference - RICS New Rules of Measurement',
    icon: Building2,
    iconClass: 'text-purple-600 bg-purple-500/10',
    columns: [
      { name: 'nrm2_code', display_name: 'NRM2 Code', column_type: 'text' },
      { name: 'element_group', display_name: 'Element Group', column_type: 'text' },
      { name: 'sub_element', display_name: 'Sub-Element', column_type: 'text' },
      { name: 'measurement_unit', display_name: 'Measurement Unit', column_type: 'text' },
      { name: 'bcis_reference', display_name: 'Cost Index Reference', column_type: 'text' },
    ],
  },
  {
    id: 'bim',
    region: 'integration',
    name: 'BIM Integration',
    description:
      'IFC GUID, element ID, storey and lifecycle phase - for linking BoQ rows to BIM models',
    icon: Boxes,
    iconClass: 'text-cyan-600 bg-cyan-500/10',
    columns: [
      { name: 'ifc_guid', display_name: 'IFC GUID', column_type: 'text' },
      { name: 'element_id', display_name: 'Element ID', column_type: 'text' },
      { name: 'storey', display_name: 'Storey/Level', column_type: 'text' },
      {
        name: 'phase',
        display_name: 'Phase',
        column_type: 'select',
        options: ['Existing', 'Demolition', 'New Construction', 'Temporary'],
      },
    ],
  },
];

export const PRESETS: ColumnPreset[] = [...UNIVERSAL_PRESETS, ...REGIONAL_PRESETS];

export const UNIVERSAL_PRESET_IDS: ReadonlySet<string> = new Set(
  UNIVERSAL_PRESETS.map((p) => p.id),
);

export function isUniversalPreset(preset: ColumnPreset): boolean {
  return preset.region === 'universal';
}

export function getUniversalPresets(): readonly ColumnPreset[] {
  return UNIVERSAL_PRESETS;
}

export function getRegionalPresets(): readonly ColumnPreset[] {
  return REGIONAL_PRESETS;
}
