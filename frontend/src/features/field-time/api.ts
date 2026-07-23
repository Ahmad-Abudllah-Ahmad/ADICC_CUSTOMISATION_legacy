// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for Field Time (cost-coded, signed field timesheets).
 *
 * All endpoints are mounted at /api/v1/field-time/. Hours are decimal
 * strings in and out (the platform-wide "money / quantity as string"
 * convention) so a precise value never loses digits through a JS Number.
 * The app runs with redirect_slashes disabled, so every path keeps its
 * trailing slash.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

const BASE = '/v1/field-time/timesheets';

/* -- Types ---------------------------------------------------------------- */

export type TimesheetStatus = 'draft' | 'submitted' | 'approved' | 'reversed';
export type LineKind = 'labour' | 'plant';

export interface FieldTimesheetLine {
  id: string;
  timesheet_id: string;
  resource_id: string | null;
  equipment_id: string | null;
  hours: string;
  cost_code: string;
  wbs: string | null;
  is_daywork: boolean;
  variation_id: string | null;
  daywork_sheet_id: string | null;
  note: string | null;
  /** Derived server-side: "labour" (a resource) or "plant" (equipment). */
  kind: LineKind;
  created_at: string;
  updated_at: string;
}

export interface FieldTimesheet {
  id: string;
  project_id: string;
  reference: string;
  date: string;
  status: TimesheetStatus;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  reverses_id: string | null;
  note: string | null;
  metadata: Record<string, unknown>;
  lines: FieldTimesheetLine[];
  labour_hours: string;
  plant_hours: string;
  created_at: string;
  updated_at: string;
}

export interface FieldTimeSummary {
  total: number;
  by_status: Record<string, number>;
  labour_hours: string;
  plant_hours: string;
}

export interface CostCodeSuggestion {
  code: string;
  label: string;
  /** 0..1 model confidence - shown to the user, never auto-applied. */
  confidence: number;
}

export interface SuggestCostCodesResponse {
  suggestions: CostCodeSuggestion[];
  applied: boolean;
}

export interface FieldTimeValidationResult {
  rule_id: string;
  rule_name: string;
  severity: string;
  category: string;
  passed: boolean;
  message: string;
  element_ref: string | null;
  suggestion: string | null;
}

export interface FieldTimeValidationReport {
  status: string;
  score: number | null;
  counts: Record<string, number>;
  results: FieldTimeValidationResult[];
}

export interface CreateTimesheetPayload {
  project_id: string;
  date: string;
  note?: string | null;
  metadata?: Record<string, unknown>;
}

export interface UpdateTimesheetPayload {
  date?: string;
  note?: string | null;
  metadata?: Record<string, unknown>;
}

export interface LineCreatePayload {
  resource_id?: string | null;
  equipment_id?: string | null;
  hours: string;
  cost_code: string;
  wbs?: string | null;
  is_daywork?: boolean;
  variation_id?: string | null;
  note?: string | null;
}

export interface LineUpdatePayload {
  resource_id?: string | null;
  equipment_id?: string | null;
  hours?: string;
  cost_code?: string;
  wbs?: string | null;
  is_daywork?: boolean;
  variation_id?: string | null;
  note?: string | null;
}

export interface ListTimesheetsFilters {
  status?: TimesheetStatus | '';
  date_from?: string;
  date_to?: string;
  offset?: number;
  limit?: number;
}

export interface ReverseTimesheetPayload {
  note?: string | null;
}

/* -- Formatting ----------------------------------------------------------- */

/**
 * Render an hours decimal string for display / input seeding, trimming
 * trailing zeros ("8.0000" -> "8", "1.5000" -> "1.5"). Hours are bounded
 * (<= 100000, 4 dp) so a Number round-trip is always exact here.
 */
export function formatHours(raw: string | null | undefined): string {
  if (raw == null || raw === '') return '0';
  const n = Number(raw);
  return Number.isFinite(n) ? String(n) : raw;
}

/* -- Timesheets ----------------------------------------------------------- */

export async function listTimesheets(
  projectId: string,
  filters?: ListTimesheetsFilters,
): Promise<FieldTimesheet[]> {
  if (!projectId) return [];
  const params = new URLSearchParams({ project_id: projectId });
  if (filters?.status) params.set('status', filters.status);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  if (filters?.offset !== undefined) params.set('offset', String(filters.offset));
  if (filters?.limit !== undefined) params.set('limit', String(filters.limit));
  const res = await apiGet<FieldTimesheet[]>(`${BASE}/?${params.toString()}`);
  return Array.isArray(res) ? res : [];
}

export async function fetchTimesheet(id: string): Promise<FieldTimesheet> {
  return apiGet<FieldTimesheet>(`${BASE}/${id}/`);
}

export async function fetchTimesheetSummary(projectId: string): Promise<FieldTimeSummary | null> {
  if (!projectId) return null;
  return apiGet<FieldTimeSummary>(
    `${BASE}/summary/?project_id=${encodeURIComponent(projectId)}`,
  );
}

export async function createTimesheet(data: CreateTimesheetPayload): Promise<FieldTimesheet> {
  return apiPost<FieldTimesheet>(`${BASE}/`, data);
}

export async function updateTimesheet(
  id: string,
  data: UpdateTimesheetPayload,
): Promise<FieldTimesheet> {
  return apiPatch<FieldTimesheet>(`${BASE}/${id}/`, data);
}

export async function deleteTimesheet(id: string): Promise<void> {
  return apiDelete(`${BASE}/${id}/`);
}

/* -- Lines ---------------------------------------------------------------- */

export async function addLine(id: string, data: LineCreatePayload): Promise<FieldTimesheet> {
  return apiPost<FieldTimesheet>(`${BASE}/${id}/lines/`, data);
}

export async function updateLine(
  id: string,
  lineId: string,
  data: LineUpdatePayload,
): Promise<FieldTimesheet> {
  return apiPatch<FieldTimesheet>(`${BASE}/${id}/lines/${lineId}/`, data);
}

export async function deleteLine(id: string, lineId: string): Promise<FieldTimesheet> {
  return apiDelete<FieldTimesheet>(`${BASE}/${id}/lines/${lineId}/`);
}

/* -- Lifecycle ------------------------------------------------------------ */

export async function submitTimesheet(id: string): Promise<FieldTimesheet> {
  return apiPost<FieldTimesheet>(`${BASE}/${id}/submit/`, {});
}

export async function approveTimesheet(id: string): Promise<FieldTimesheet> {
  return apiPost<FieldTimesheet>(`${BASE}/${id}/approve/`, {});
}

export async function reverseTimesheet(
  id: string,
  data: ReverseTimesheetPayload,
): Promise<FieldTimesheet> {
  return apiPost<FieldTimesheet>(`${BASE}/${id}/reverse/`, data);
}

/* -- Validation ----------------------------------------------------------- */

export async function fetchTimesheetValidation(id: string): Promise<FieldTimeValidationReport> {
  return apiGet<FieldTimeValidationReport>(`${BASE}/${id}/validation/`);
}

/* -- Cost-code assist (AI-augmented, human-confirmed) --------------------- */

export async function suggestCostCodes(
  projectId: string,
  text: string,
  limit = 5,
): Promise<SuggestCostCodesResponse> {
  return apiPost<SuggestCostCodesResponse>(
    `${BASE}/suggest-cost-codes/?project_id=${encodeURIComponent(projectId)}`,
    { text, limit },
  );
}
