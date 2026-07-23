// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for the Tendering module — integrated-5D-estimating-suite-style addenda + bid leveling.
 *
 * Backed by /api/v1/tendering/ — see backend/app/modules/tendering/router.py
 */

import { apiGet, apiPost, apiDelete } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export interface AddendumAckEntry {
  bidder_id: string;
  acknowledged_at: string;
  user_id?: string;
}

export interface Addendum {
  id: string;
  package_id: string;
  revision_no: number;
  title: string;
  body: string | null;
  published_at: string | null;
  published_by_user_id: string | null;
  acknowledged_by: AddendumAckEntry[];
  created_at: string;
  updated_at: string;
}

export interface BidLevelingSummary {
  bid_id: string;
  company_name: string;
  /** Money fields ride as Decimal-as-string in JSON (v3 §10). */
  raw_amount: number | string;
  leveled_amount: number | string;
  matched_lines: number;
  scaled_lines: number;
  imputed_lines: number;
  currency: string;
}

export interface LevelingMatrixCell {
  bid_id: string;
  company_name: string;
  raw_total: number;
  leveled_total: number;
  status: '' | 'matched' | 'scaled' | 'imputed';
  /** Money field - Decimal-as-string in JSON (v3 §10). */
  unit_rate: number | string;
}

export interface LevelingMatrixRow {
  position_id: string | null;
  line_code: string;
  description: string;
  unit: string;
  reference_quantity: number;
  reference_rate: number;
  reference_total: number;
  cells: LevelingMatrixCell[];
}

export interface LevelingMatrix {
  package_id: string;
  package_name: string;
  /** ISO currency the matrix is computed in (the package currency). */
  currency: string;
  /** Bids excluded because they were quoted in a different currency. */
  excluded_off_currency: number;
  bid_summaries: BidLevelingSummary[];
  rows: LevelingMatrixRow[];
}

export interface LevelBidsResponse {
  package_id: string;
  package_name: string;
  /** ISO currency the leveling was computed in (the package currency). */
  currency: string;
  /** Bids excluded because they were quoted in a different currency. */
  excluded_off_currency: number;
  bid_count: number;
  reference_line_count: number;
  bid_summaries: BidLevelingSummary[];
}

/* ── Addenda ──────────────────────────────────────────────────────────── */

export function listAddenda(packageId: string): Promise<Addendum[]> {
  return apiGet<Addendum[]>(`/v1/tendering/packages/${packageId}/addenda/`);
}

export function createAddendum(
  packageId: string,
  body: { title: string; body?: string },
): Promise<Addendum> {
  return apiPost<Addendum>(`/v1/tendering/packages/${packageId}/addenda/`, body);
}

export function publishAddendum(addendumId: string): Promise<Addendum> {
  return apiPost<Addendum>(`/v1/tendering/addenda/${addendumId}/publish/`, {});
}

/** Minimal bidder shape needed to record an addendum acknowledgement. */
export interface BidderSummary {
  id: string;
  company_name: string;
}

export function listPackageBidders(
  packageId: string,
): Promise<BidderSummary[]> {
  return apiGet<BidderSummary[]>(
    `/v1/tendering/packages/${packageId}/bids/`,
  );
}

export function acknowledgeAddendum(
  addendumId: string,
  bidderId: string,
): Promise<Addendum> {
  return apiPost<Addendum>(`/v1/tendering/addenda/${addendumId}/acknowledge/`, {
    bidder_id: bidderId,
  });
}

/* ── Bid leveling ─────────────────────────────────────────────────────── */

export function levelBids(packageId: string): Promise<LevelBidsResponse> {
  return apiPost<LevelBidsResponse>(
    `/v1/tendering/packages/${packageId}/level-bids/`,
    {},
  );
}

export function getLevelingMatrix(packageId: string): Promise<LevelingMatrix> {
  return apiGet<LevelingMatrix>(
    `/v1/tendering/packages/${packageId}/leveling-matrix/`,
  );
}

/* ── Distribution ─────────────────────────────────────────────────────── */

export interface Recipient {
  id: string;
  company_name: string;
  email: string;
  subcontractor_id: string | null;
  /** "pending" before the first send, then "sent" or "failed". */
  status: string;
  sent_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface DistributeResultEntry {
  recipient_id: string;
  company_name: string;
  email: string;
  status: 'sent' | 'failed' | 'skipped';
  detail: string;
}

export interface DistributeResponse {
  package_id: string;
  package_name: string;
  /** Resolved email backend ("console" | "smtp" | "noop" | "memory"). */
  backend: string;
  /** True only when EMAIL_BACKEND=smtp and SMTP_HOST is configured. */
  smtp_configured: boolean;
  sent_count: number;
  failed_count: number;
  skipped_count: number;
  results: DistributeResultEntry[];
}

export function listRecipients(packageId: string): Promise<Recipient[]> {
  return apiGet<Recipient[]>(
    `/v1/tendering/packages/${packageId}/recipients/`,
  );
}

export function addRecipient(
  packageId: string,
  body: { company_name: string; email: string; subcontractor_id?: string | null },
): Promise<Recipient> {
  return apiPost<Recipient>(
    `/v1/tendering/packages/${packageId}/recipients/`,
    body,
  );
}

export function removeRecipient(
  packageId: string,
  recipientId: string,
): Promise<void> {
  return apiDelete(
    `/v1/tendering/packages/${packageId}/recipients/${recipientId}`,
  );
}

export function distributePackage(
  packageId: string,
  body: { recipient_ids?: string[]; resend?: boolean; message?: string },
): Promise<DistributeResponse> {
  return apiPost<DistributeResponse>(
    `/v1/tendering/packages/${packageId}/distribute/`,
    body,
  );
}
