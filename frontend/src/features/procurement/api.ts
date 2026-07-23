// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Procurement API clients - typed wrappers over fetch.
 *
 * Wave 2 / T4 introduces two read endpoints (3-way match status + supplier
 * scorecard) that the procurement UI surfaces. The existing list / create
 * calls still live inline in `ProcurementPage.tsx`; this module is a
 * landing pad for the new clients and any future additions.
 */

import { apiGet, apiPost } from '@/shared/lib/api';

/* ── 3-way match status ───────────────────────────────────────────────── */

export type POLineMatchTag =
  | 'ok'
  | 'partial'
  | 'over_received'
  | 'over_invoiced'
  | 'unmatched';

export interface POLineMatchStatus {
  line_id: string;
  description: string;
  ordered_qty: string;
  received_qty: string;
  invoiced_qty: string;
  match_status: POLineMatchTag;
}

export interface POMatchStatusResponse {
  po_id: string;
  po_number: string;
  overall_status: POLineMatchTag;
  lines: POLineMatchStatus[];
}

export function getPOMatchStatus(poId: string): Promise<POMatchStatusResponse> {
  return apiGet<POMatchStatusResponse>(`/v1/procurement/${poId}/match-status/`);
}

/* ── Supplier scorecard ───────────────────────────────────────────────── */

export interface SupplierScorecardResponse {
  supplier_contact_id: string;
  supplier_name: string | null;
  project_id: string | null;
  period_days: number;
  total_po_count: number;
  total_po_value: string;
  currency: string;
  on_time_delivery_pct: number;
  qty_variance_pct: number;
  gr_rejection_rate: number;
  total_gr_count: number;
  // Numerator of on_time_delivery_pct - GRs delivered on/before their PO's
  // delivery_date. The backend returns it so the UI can show "X of Y on time".
  on_time_count: number;
  // GRs whose parent PO carried no delivery_date - excluded from the on-time
  // denominator. Without surfacing this, a supplier whose deliveries are all
  // unscheduled shows a misleading 0% on-time figure (see SupplierScorecardModal).
  unscheduled_count: number;
}

export function getSupplierScorecard(
  contactId: string,
  options: { projectId?: string; periodDays?: number } = {},
): Promise<SupplierScorecardResponse> {
  const params = new URLSearchParams();
  if (options.projectId) params.set('project_id', options.projectId);
  if (options.periodDays) params.set('period_days', String(options.periodDays));
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : '';
  return apiGet<SupplierScorecardResponse>(
    `/v1/procurement/suppliers/${contactId}/scorecard/${suffix}`,
  );
}

/* ── Vendor prequalification status (TOP-30 #20) ──────────────────────── */

export interface VendorEligibility {
  contact_id: string;
  known: boolean;
  subcontractor_id: string | null;
  legal_name: string | null;
  awardable: boolean;
  prequalification_status: string | null;
  is_blocked: boolean;
  rating_score: string | null;
  reasons: string[];
}

/**
 * Resolve a PO vendor's prequalification / block status from its CRM
 * contact id. Returns ``known=false`` for an ad-hoc supplier that is not a
 * registered subcontractor (no badge shown).
 */
export function getVendorEligibility(
  contactId: string,
): Promise<VendorEligibility> {
  return apiGet<VendorEligibility>(
    `/v1/subcontractors/vendors/by-contact/${contactId}/eligibility`,
  );
}

/* ── Retainage (Gap F) ─────────────────────────────────────────────────── */

export interface PORetainageRelease {
  id: string;
  po_id: string;
  release_date: string;
  release_amount: string;
  release_reason: string | null;
  released_by_id: string | null;
  created_at: string;
}

export interface PORetainageReleaseList {
  items: PORetainageRelease[];
  total: number;
}

export function listPORetainageReleases(
  poId: string,
): Promise<PORetainageReleaseList> {
  return apiGet<PORetainageReleaseList>(
    `/v1/procurement/${poId}/retainage-releases/`,
  );
}

export function releasePORetainage(
  poId: string,
  body: { amount: string; reason?: string },
): Promise<PORetainageRelease> {
  return apiPost<PORetainageRelease, { amount: string; reason?: string }>(
    `/v1/procurement/${poId}/release-retainage/`,
    body,
  );
}

/* ── PO retainage reconciliation report (Gap F) ────────────────────────── */

export interface RetainageReportRow {
  po_id: string;
  po_number: string;
  vendor_name: string;
  issue_date: string | null;
  status: string;
  amount_total: string;
  currency: string;
  retention_percent: string;
  retainage_withheld: string;
  retainage_released_ytd: string;
  retainage_held: string;
}

export interface RetainageReportSummary {
  total_committed: string;
  total_withheld: string;
  total_released: string;
  total_held: string;
  currency: string;
  mixed_currency: boolean;
}

export interface RetainageReconciliationReport {
  report_type: string;
  project_id: string;
  project_name: string;
  period_start: string;
  period_end: string;
  currencies: string[];
  summary: RetainageReportSummary;
  summary_by_currency: Record<
    string,
    {
      total_committed: string;
      total_withheld: string;
      total_released: string;
      total_held: string;
    }
  >;
  po_rows: RetainageReportRow[];
}

export function getRetainageReconciliation(options: {
  projectId: string;
  periodStart: string;
  periodEnd: string;
}): Promise<RetainageReconciliationReport> {
  const params = new URLSearchParams({
    project_id: options.projectId,
    period_start: options.periodStart,
    period_end: options.periodEnd,
  });
  return apiGet<RetainageReconciliationReport>(
    `/v1/reporting/po-retainage-reconciliation/?${params.toString()}`,
  );
}
