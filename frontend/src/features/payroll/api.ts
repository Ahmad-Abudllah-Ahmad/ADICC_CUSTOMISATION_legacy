// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for Payroll.
 *
 * All endpoints are prefixed with /v1/payroll/ and are manager-scoped.
 * Money is returned as Decimal-as-string; the UI parses with Number(...)
 * only for display.
 */

import { apiDelete, apiGet, apiPatch, apiPost, getAuthToken } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type PayrollStatus = 'draft' | 'submitted' | 'approved' | 'posted';

export type DeductionType = 'tax' | 'social' | 'pension' | 'other';
export type DeductionMode = 'fixed' | 'percentage';

export interface PayrollDeduction {
  id: string;
  entry_id: string;
  label: string;
  deduction_type: DeductionType;
  mode: DeductionMode;
  value: string;
  base_amount: string;
  amount: string;
  currency: string;
  ordinal: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PayrollEntry {
  id: string;
  batch_id: string;
  resource_id: string | null;
  worker: string;
  work_date: string | null;
  hours: string;
  /** Gross pay (hours x rate, in batch currency). */
  amount: string;
  /** Net pay = gross - sum(deductions). Equals gross when there are none. */
  net_amount: string;
  rate: string;
  currency: string;
  source: string;
  metadata: Record<string, unknown>;
  deductions: PayrollDeduction[];
  created_at: string;
  updated_at: string;
}

export interface PayrollBatch {
  id: string;
  project_id: string;
  period_label: string;
  period_start: string | null;
  period_end: string | null;
  status: PayrollStatus;
  currency: string;
  total_hours: string;
  /** Batch gross pay (sum of entry gross amounts). Posts to cost / GL. */
  total_amount: string;
  /** Sum of all deductions across the batch. */
  total_deductions: string;
  /** Batch net pay = total_amount - total_deductions. */
  total_net: string;
  entry_count: number;
  notes: string;
  created_by: string | null;
  submitted_at: string | null;
  submitted_by: string | null;
  approved_at: string | null;
  approved_by: string | null;
  posted_at: string | null;
  posted_by: string | null;
  gl_transaction_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReconciliationRow {
  worker_key: string;
  work_date: string | null;
  resource_id: string | null;
  batch_hours: string;
  source_hours: string;
  delta_hours: string;
  matched: boolean;
}

export interface Reconciliation {
  batch_id: string;
  project_id: string;
  batch_total_hours: string;
  source_total_hours: string;
  delta_total_hours: string;
  balanced: boolean;
  rows: ReconciliationRow[];
}

export interface PayrollBatchDetail extends PayrollBatch {
  entries: PayrollEntry[];
}

export interface LabourCost {
  project_id: string;
  currency: string;
  labour_cost: string;
  total_hours: string;
}

export interface GenerateBatchPayload {
  date_from?: string | null;
  date_to?: string | null;
  period_label?: string | null;
  notes?: string;
}

/* ── API functions ─────────────────────────────────────────────────────── */

export async function fetchPayrollBatches(projectId: string): Promise<PayrollBatch[]> {
  if (!projectId) return [];
  const res = await apiGet<PayrollBatch[]>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
  );
  return Array.isArray(res) ? res : [];
}

export async function fetchPayrollBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiGet<PayrollBatchDetail>(`/v1/payroll/batches/${encodeURIComponent(batchId)}`);
}

export async function generatePayrollBatch(
  projectId: string,
  payload: GenerateBatchPayload,
): Promise<PayrollBatchDetail> {
  return apiPost<PayrollBatchDetail, GenerateBatchPayload>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
    payload,
  );
}

export async function fetchLabourCost(projectId: string): Promise<LabourCost | null> {
  if (!projectId) return null;
  return apiGet<LabourCost>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/labour-cost/`,
  );
}

/**
 * Finalize (approve) a draft batch: transitions it to `approved` and posts its
 * labour cost to the project budget. Idempotent - calling twice on an
 * already-approved batch returns the unchanged batch.
 */
export async function finalizeBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/finalize/`,
  );
}

/** Submit a draft batch for approval (no money moved). Idempotent. */
export async function submitBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/submit/`,
  );
}

/** Post an approved batch to the finance ledger (terminal). Idempotent. */
export async function postBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/post/`,
  );
}

export interface AddDeductionPayload {
  label: string;
  deduction_type: DeductionType;
  mode: DeductionMode;
  /** Fixed amount, or a percentage (0-100) when mode is 'percentage'. */
  value: string;
  /** Optional explicit base for a percentage; defaults to the entry gross. */
  base_amount?: string | null;
}

/**
 * Add a deduction line to a payslip (entry). The server derives the amount and
 * recomputes net pay + batch totals, returning the full refreshed batch detail.
 * Only allowed while the batch is draft/submitted.
 */
export async function addDeduction(
  batchId: string,
  entryId: string,
  payload: AddDeductionPayload,
): Promise<PayrollBatchDetail> {
  return apiPost<PayrollBatchDetail, AddDeductionPayload>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/entries/${encodeURIComponent(
      entryId,
    )}/deductions/`,
    payload,
  );
}

/**
 * Remove a deduction line from a payslip. Recomputes net + batch totals and
 * returns the refreshed batch detail. Only allowed while draft/submitted.
 */
export async function removeDeduction(
  batchId: string,
  entryId: string,
  deductionId: string,
): Promise<PayrollBatchDetail> {
  return apiDelete<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/entries/${encodeURIComponent(
      entryId,
    )}/deductions/${encodeURIComponent(deductionId)}/`,
  );
}

/** Reconcile a batch's hours against the live field-labour sources (read-only). */
export async function reconcileBatch(batchId: string): Promise<Reconciliation> {
  return apiGet<Reconciliation>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/reconcile/`,
  );
}

/**
 * Fetch a batch export (CSV or JSON) with the auth token attached and trigger a
 * browser download. The export endpoints are auth-gated, so a bare anchor href
 * would 401 - we fetch the blob with the Bearer token and save it client-side.
 */
export async function downloadBatchExport(batchId: string, format: 'csv' | 'json'): Promise<void> {
  const token = getAuthToken();
  const res = await fetch(
    `/api/v1/payroll/batches/${encodeURIComponent(batchId)}/export.${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `payroll-batch-${batchId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
