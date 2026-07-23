// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for the Design Options module.
 *
 * A design option set holds two or more competing design options for the same
 * project (for example a concrete frame versus a steel frame). Each option can
 * carry its own BIM/CAD model, which is converted and priced into its own bill
 * of quantities, so the options can be compared like for like on cost, quantity
 * and completeness.
 *
 * Backed by /api/v1/design-options/ - see backend/app/modules/design_options.
 *
 * Money, quantity, rate and ratio values ride as Decimal-as-string in JSON so
 * large totals round-trip without binary-float drift and stay locale-neutral.
 * Every such field below is typed `string`; parse to a number only for display
 * formatting, never for storage or arithmetic that feeds a bill of quantities.
 */

import {
  apiGet,
  apiPost,
  apiDelete,
  getAuthToken,
  extractErrorMessageFromBody,
  triggerDownload,
  API_BASE,
} from '@/shared/lib/api';

const BASE = '/v1/design-options';

/* ── Domain types ──────────────────────────────────────────────────────── */

/** Lifecycle of a single design option. */
export type DesignOptionStatus =
  | 'draft'
  | 'model_attached'
  | 'converting'
  | 'boq_generating'
  | 'priced'
  | 'failed';

/** Lifecycle of an option set. */
export type DesignOptionSetStatus = 'draft' | 'active' | 'decided' | 'archived';

/** Traffic-light validation state carried per option / per comparison column. */
export type OptionValidationStatus = 'pending' | 'passed' | 'warnings' | 'errors';

/** One elemental line of an option's cost breakdown (stable `key` for i18n). */
export interface DesignOptionBreakdownRow {
  key: string;
  label: string;
  /** Share of the option total, as a percentage string. */
  cost_share_pct: string;
  /** Element total money, Decimal-as-string. */
  amount: string;
}

/** A single design option persisted under a set. */
export interface DesignOption {
  id: string;
  set_id: string;
  project_id: string;
  name: string;
  sort_order: number;
  source_document_id: string | null;
  bim_model_id: string | null;
  /** The bill of quantities paired to this option (the pricing target). */
  boq_id: string | null;
  match_session_id: string | null;
  status: DesignOptionStatus;
  /** Human-readable failure reason when `status === 'failed'`. */
  error: string;
  /** Money fields, Decimal-as-string. */
  direct_cost: string;
  markups_total: string;
  grand_total: string;
  cost_per_m2: string;
  /** Gross floor area used for the cost-per-area figure, Decimal-as-string. */
  gfa: string;
  gfa_unit: string;
  currency: string;
  element_count: number;
  position_count: number;
  breakdown: DesignOptionBreakdownRow[];
  validation_status: OptionValidationStatus;
  /** Validation score 0-1, Decimal-as-string, or null when not yet validated. */
  validation_score: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** A set of competing design options for one project. */
export interface DesignOptionSet {
  id: string;
  project_id: string;
  name: string;
  status: DesignOptionSetStatus;
  baseline_option_id: string | null;
  comparison_currency: string;
  decision_criteria: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  /** The set detail endpoint returns its options inline. */
  options?: DesignOption[];
}

/* ── Comparison contract ───────────────────────────────────────────────── */

/** Set-level fairness verdict for the comparison (drives the banner traffic
 *  light): 'ok' green, 'warnings' amber, 'error' red. */
export type FairnessStatus = 'ok' | 'warnings' | 'error';

/** Severity of a single fairness notice. */
export type FairnessSeverity = 'info' | 'warning' | 'error';

/**
 * One fairness notice on the comparison as a whole. `key` is an i18n key
 * (`designOptions.fairness.<name>`); `severity` drives the notice icon; `context`
 * carries interpolation values (a count, a currency code) for the localised text.
 */
export interface DesignOptionFairnessWarning {
  key: string;
  severity: FairnessSeverity;
  context: Record<string, unknown>;
}

/** One option column of the comparison, already rebased to the set currency. */
export interface DesignOptionColumn {
  option_id: string;
  name: string;
  direct_cost: string;
  markups_total: string;
  grand_total: string;
  /** Signed money delta versus the baseline option, Decimal-as-string. */
  delta_vs_baseline: string;
  /** Signed percentage delta versus the baseline, Decimal-as-string, or null
   *  when there is no baseline or the baseline total is zero (no meaningful %). */
  delta_pct: string | null;
  cost_per_m2: string;
  gfa: string;
  currency: string;
  element_count: number;
  position_count: number;
  validation_status: OptionValidationStatus;
}

/** One option's quantity and cost for a single trade row. */
export interface TradeDeltaPerOption {
  option_id: string;
  quantity: string;
  unit: string;
  cost: string;
}

/** One by-trade comparison row across every option. */
export interface TradeDeltaRow {
  key: string;
  label: string;
  /** Classification the row is grouped by, e.g. 'din276' | 'masterformat' | 'nrm' | 'trade'. */
  classification_system: string;
  baseline_quantity: string;
  baseline_cost: string;
  per_option: TradeDeltaPerOption[];
}

/** AI-suggested recommendation (human still confirms the decision). */
export interface DesignOptionRecommendation {
  option_id: string | null;
  /** The winner's relative margin over the runner-up, 0..1 Decimal-as-string: a
   *  clear winner reads high, a near tie reads near zero. Parse only for display. */
  confidence: string;
  reason_key: string;
}

/** Set-level fairness banner payload. */
export interface DesignOptionFairness {
  status: FairnessStatus;
  warnings: DesignOptionFairnessWarning[];
}

/** Full N-option comparison response. */
export interface DesignOptionComparisonResponse {
  set_id: string;
  set_name: string;
  comparison_currency: string;
  baseline_option_id: string | null;
  options: DesignOptionColumn[];
  by_trade: TradeDeltaRow[];
  recommendation: DesignOptionRecommendation;
  fairness: DesignOptionFairness;
}

/* ── Generate (dry-run preview + apply) ────────────────────────────────── */

/**
 * Result of generating a priced BOQ for an option. When `dry_run` is true the
 * server returns a preview only and applies nothing; the caller shows the
 * preview and the user confirms before a second call with `dry_run: false`
 * actually writes the matches to the option's BOQ (AI-augmented, human-confirmed).
 */
/**
 * One would-be (dry run) or applied BOQ line in a generate preview. Money and
 * quantity fields are Decimal-as-string; `section_path` is the hierarchical
 * section the line would land under.
 */
export interface DesignOptionGeneratePreviewLine {
  group_key: string;
  description: string;
  unit: string;
  quantity: string;
  unit_rate: string;
  currency: string;
  line_total: string;
  section_path: string[];
}

export interface DesignOptionGenerateResponse {
  option_id: string;
  dry_run: boolean;
  boq_id: string | null;
  method: string;
  status: DesignOptionStatus;
  positions_created: number;
  element_count: number;
  position_count: number;
  /** Element groups matched and, of those, auto/confirmed for apply. */
  groups_total: number;
  groups_confirmed: number;
  /** Money fields, Decimal-as-string. */
  direct_cost: string;
  markups_total: string;
  grand_total: string;
  cost_per_m2: string;
  gfa: string;
  gfa_unit: string;
  currency: string;
  /** True when the option's own bill mixes currencies (comparison stays honest). */
  is_mixed_currency: boolean;
  breakdown: DesignOptionBreakdownRow[];
  /** The would-be or applied lines; on a dry run nothing is persisted. */
  preview: DesignOptionGeneratePreviewLine[];
  warnings: string[];
}

/* ── Sets ──────────────────────────────────────────────────────────────── */

export function listOptionSets(projectId: string): Promise<DesignOptionSet[]> {
  return apiGet<DesignOptionSet[]>(
    `${BASE}/sets/?project_id=${encodeURIComponent(projectId)}`,
  );
}

export function getOptionSet(setId: string): Promise<DesignOptionSet> {
  return apiGet<DesignOptionSet>(`${BASE}/sets/${encodeURIComponent(setId)}`);
}

export function createOptionSet(body: {
  project_id: string;
  name: string;
}): Promise<DesignOptionSet> {
  return apiPost<DesignOptionSet>(`${BASE}/sets/`, body);
}

export function deleteOptionSet(setId: string): Promise<void> {
  return apiDelete(`${BASE}/sets/${encodeURIComponent(setId)}`);
}

export function setBaseline(
  setId: string,
  optionId: string,
): Promise<DesignOptionSet> {
  return apiPost<DesignOptionSet>(
    `${BASE}/sets/${encodeURIComponent(setId)}/baseline/`,
    { option_id: optionId },
  );
}

export function getComparison(
  setId: string,
): Promise<DesignOptionComparisonResponse> {
  return apiGet<DesignOptionComparisonResponse>(
    `${BASE}/sets/${encodeURIComponent(setId)}/comparison/`,
  );
}

/* ── Options ───────────────────────────────────────────────────────────── */

export function createOption(
  setId: string,
  body: { name: string },
): Promise<DesignOption> {
  return apiPost<DesignOption>(
    `${BASE}/sets/${encodeURIComponent(setId)}/options/`,
    body,
  );
}

export function deleteOption(optionId: string): Promise<void> {
  return apiDelete(`${BASE}/options/${encodeURIComponent(optionId)}`);
}

/** Link an already-imported BIM model to an option (no file upload). */
export function linkBimModel(
  optionId: string,
  bimModelId: string,
): Promise<DesignOption> {
  return apiPost<DesignOption>(
    `${BASE}/options/${encodeURIComponent(optionId)}/attach-model/`,
    { bim_model_id: bimModelId },
  );
}

/**
 * Generate (or re-generate) the priced BOQ for an option.
 *
 * Pass `dryRun: true` first to fetch a preview that applies nothing, then
 * `dryRun: false` once the user confirms. The backend routes the option's
 * attached model through the match pipeline and totals the resulting BOQ.
 */
export function generateOption(
  optionId: string,
  dryRun: boolean,
): Promise<DesignOptionGenerateResponse> {
  return apiPost<DesignOptionGenerateResponse>(
    `${BASE}/options/${encodeURIComponent(optionId)}/generate/`,
    { dry_run: dryRun },
    // Conversion + matching can be heavy on a small box; opt into the long budget.
    { longRunning: true },
  );
}

/**
 * Attach a CAD file to an option by uploading it. The server picks the right
 * importer by file extension (BIM/CAD conversion, tabular cad2data import, or a
 * document-derived model) and kicks off background processing; poll the option
 * status for the result. Raw multipart, so this bypasses the JSON helpers and
 * assembles its own Authorization header (mirrors the BIM upload helper).
 */
export async function attachModelFile(
  optionId: string,
  file: File,
  signal?: AbortSignal,
): Promise<DesignOption> {
  const formData = new FormData();
  formData.append('file', file);
  const params = new URLSearchParams({ name: file.name });

  const token = getAuthToken();
  const headers: HeadersInit = {
    Accept: 'application/json',
    'X-DDC-Client': 'OE/1.0',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}${BASE}/options/${encodeURIComponent(optionId)}/attach-model/?${params.toString()}`,
      { method: 'POST', headers, body: formData, signal },
    );
  } catch (networkErr) {
    if (networkErr instanceof DOMException && networkErr.name === 'AbortError') {
      throw networkErr;
    }
    throw new Error(
      'Cannot connect to server. Please check that the backend is running and try again.',
    );
  }

  if (!response.ok) {
    let detail = `Upload failed (HTTP ${response.status})`;
    try {
      const body = await response.json();
      detail = extractErrorMessageFromBody(body) ?? detail;
    } catch {
      // ignore body parse errors and keep the status-based message
    }
    throw new Error(detail);
  }

  return response.json() as Promise<DesignOption>;
}

/**
 * Download the comparison as an .xlsx file. Fetches with the Bearer token (the
 * JWT lives in the auth store, not a cookie) and triggers an anchor download,
 * so the sheet is never opened in a blank tab that silently 401s.
 */
export async function downloadComparisonXlsx(
  setId: string,
  filename: string,
): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}${BASE}/sets/${encodeURIComponent(setId)}/comparison.xlsx`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) {
    let detail = `Export failed (HTTP ${response.status})`;
    try {
      const body = await response.json();
      detail = extractErrorMessageFromBody(body) ?? detail;
    } catch {
      // ignore body parse errors and keep the status-based message
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  triggerDownload(blob, filename);
}
