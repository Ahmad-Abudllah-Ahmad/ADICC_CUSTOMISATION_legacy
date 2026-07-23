// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for the Supplier Catalogs module.
 *
 * Backed by /api/v1/supplier-catalogs/ — see backend/app/modules/supplier_catalogs/router.py
 */

import { apiGet, apiPost, apiPatch } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type VendorStatus = 'active' | 'suspended' | 'blacklisted' | 'pending';
export type PRStatus =
  | 'draft'
  | 'submitted'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'converted';
export type POStatus =
  | 'draft'
  | 'sent'
  | 'acknowledged'
  | 'partially_received'
  | 'received'
  | 'closed'
  | 'cancelled';
export type InvoiceStatus = 'received' | 'matched' | 'exception' | 'approved' | 'paid';
export type MatchStatus = 'pending' | 'auto_matched' | 'exception';

export interface Vendor {
  id: string;
  code: string;
  name: string;
  legal_name: string | null;
  tax_id: string | null;
  contact_id: string | null;
  status: VendorStatus;
  currency: string;
  payment_terms_days: number;
  rating: number | null;
  country_code: string | null;
  region: string | null;
  categories_json: unknown[];
  preferred_for_json: unknown[];
  contacts_json: unknown[];
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ItemCategory {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  level: number;
  classification_ref: string | null;
}

export interface CatalogItem {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  category_id: string | null;
  unit_of_measure: string;
  manufacturer: string | null;
  mpn: string | null;
  spec_json: Record<string, unknown>;
  hazard_class: string | null;
  shelf_life_days: number | null;
  reorder_point: number | string;
  active: boolean;
}

export interface PriceList {
  id: string;
  vendor_id: string;
  name: string;
  valid_from: string | null;
  valid_to: string | null;
  currency: string;
  status: string;
  uploaded_by: string | null;
}

export interface PriceComparisonRow {
  vendor_id: string;
  vendor_code: string;
  vendor_name: string;
  unit_price: number | string;
  currency: string;
  min_order_qty: number | string;
  lead_time_days: number;
  price_list_id: string;
  rating: number | null;
}

export interface PRLine {
  id: string;
  pr_id: string;
  catalog_item_id: string | null;
  description: string;
  quantity: number | string;
  unit_of_measure: string;
  estimated_unit_price: number | string;
  estimated_total: number | string;
}

export interface PR {
  id: string;
  number: string;
  project_id: string;
  requested_by: string | null;
  requested_at: string | null;
  needed_by: string | null;
  status: PRStatus;
  total_estimate: number | string;
  currency: string;
  notes: string | null;
  approval_chain_json: unknown[];
  lines: PRLine[];
}

export interface POLine {
  id: string;
  po_id: string;
  catalog_item_id: string | null;
  description: string;
  ordered_qty: number | string;
  unit_of_measure: string;
  unit_price: number | string;
  line_total: number | string;
  received_qty: number | string;
  invoiced_qty: number | string;
}

export interface PO {
  id: string;
  number: string;
  vendor_id: string;
  project_id: string;
  contract_id: string | null;
  pr_id: string | null;
  status: POStatus;
  order_date: string | null;
  expected_delivery: string | null;
  currency: string;
  subtotal: number | string;
  tax: number | string;
  total: number | string;
  terms: string | null;
  lines: POLine[];
}

export interface VendorInvoice {
  id: string;
  number: string;
  vendor_id: string;
  po_id: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  subtotal: number | string;
  tax: number | string;
  total: number | string;
  status: InvoiceStatus;
  three_way_match_status: MatchStatus;
  exception_reason: string | null;
}

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  project_id: string | null;
  address: string | null;
  manager_user_id: string | null;
  status: string;
}

export interface StockBalance {
  id: string;
  warehouse_id: string;
  catalog_item_id: string;
  batch_lot: string;
  quantity_on_hand: number | string;
  quantity_reserved: number | string;
  unit_cost_avg: number | string;
  last_movement_at: string | null;
}

/* ── Payloads ──────────────────────────────────────────────────────────── */

export interface CreateVendorPayload {
  code: string;
  name: string;
  legal_name?: string;
  tax_id?: string;
  currency?: string;
  payment_terms_days?: number;
  country_code?: string;
  region?: string;
  categories?: string[];
  preferred_for?: string[];
  notes?: string;
}

export interface CreateCatalogItemPayload {
  sku: string;
  name: string;
  description?: string;
  category_id?: string;
  unit_of_measure?: string;
  manufacturer?: string;
  mpn?: string;
  hazard_class?: string;
  shelf_life_days?: number;
  reorder_point?: number | string;
}

export interface CreatePRPayload {
  project_id: string;
  needed_by?: string;
  notes?: string;
  currency?: string;
  approval_chain?: string[];
  lines: Array<{
    catalog_item_id?: string;
    description: string;
    quantity: number;
    unit_of_measure?: string;
    estimated_unit_price?: number;
  }>;
}

export interface CreatePOPayload {
  vendor_id: string;
  project_id: string;
  pr_id?: string;
  order_date?: string;
  expected_delivery?: string;
  currency?: string;
  tax?: number;
  terms?: string;
  lines: Array<{
    catalog_item_id?: string;
    description: string;
    ordered_qty: number;
    unit_of_measure?: string;
    unit_price: number;
  }>;
}

export interface CreateWarehousePayload {
  code: string;
  name: string;
  project_id?: string;
  address?: string;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function qs(params: Record<string, string | number | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) s.set(k, String(v));
  }
  const out = s.toString();
  return out ? `?${out}` : '';
}

/* ── Vendors ───────────────────────────────────────────────────────────── */

export function listVendors(params?: {
  status?: string;
  country_code?: string;
  offset?: number;
  limit?: number;
}): Promise<Vendor[]> {
  return apiGet<Vendor[]>(`/v1/supplier-catalogs/vendors${qs(params || {})}`);
}

export function createVendor(data: CreateVendorPayload): Promise<Vendor> {
  return apiPost<Vendor>('/v1/supplier-catalogs/vendors', data);
}

export function suspendVendor(id: string, reason?: string): Promise<Vendor> {
  return apiPatch<Vendor>(`/v1/supplier-catalogs/vendors/${id}/suspend${qs({ reason })}`, {});
}

export function blacklistVendor(id: string, reason?: string): Promise<Vendor> {
  return apiPatch<Vendor>(`/v1/supplier-catalogs/vendors/${id}/blacklist${qs({ reason })}`, {});
}

export function rateVendor(id: string, rating: number, comment?: string): Promise<Vendor> {
  return apiPost<Vendor>(`/v1/supplier-catalogs/vendors/${id}/rating`, { rating, comment });
}

/* ── Catalog ───────────────────────────────────────────────────────────── */

export function listCatalogItems(params?: {
  category_id?: string;
  search?: string;
  offset?: number;
  limit?: number;
}): Promise<CatalogItem[]> {
  return apiGet<CatalogItem[]>(`/v1/supplier-catalogs/catalog-items${qs(params || {})}`);
}

export function createCatalogItem(data: CreateCatalogItemPayload): Promise<CatalogItem> {
  return apiPost<CatalogItem>('/v1/supplier-catalogs/catalog-items', data);
}

export function comparePrices(itemId: string): Promise<PriceComparisonRow[]> {
  return apiGet<PriceComparisonRow[]>(
    `/v1/supplier-catalogs/catalog-items/${itemId}/price-comparison`,
  );
}

/* ── Purchase Requisitions ─────────────────────────────────────────────── */

export function createPR(data: CreatePRPayload): Promise<PR> {
  return apiPost<PR>('/v1/supplier-catalogs/prs', data);
}

export function submitPR(id: string): Promise<PR> {
  return apiPost<PR>(`/v1/supplier-catalogs/prs/${id}/submit`, {});
}

export function approvePR(id: string): Promise<PR> {
  return apiPost<PR>(`/v1/supplier-catalogs/prs/${id}/approve`, {});
}

export function rejectPR(id: string, reason?: string): Promise<PR> {
  return apiPost<PR>(`/v1/supplier-catalogs/prs/${id}/reject${qs({ reason })}`, {});
}

export function convertPRToPO(id: string, vendorId: string): Promise<PO> {
  return apiPost<PO>(
    `/v1/supplier-catalogs/prs/${id}/convert-to-po${qs({ vendor_id: vendorId })}`,
    {},
  );
}

/* ── Purchase Orders ───────────────────────────────────────────────────── */

export function createPO(data: CreatePOPayload): Promise<PO> {
  return apiPost<PO>('/v1/supplier-catalogs/pos', data);
}

export function sendPO(id: string): Promise<PO> {
  return apiPost<PO>(`/v1/supplier-catalogs/pos/${id}/send`, {});
}

export function acknowledgePO(id: string): Promise<PO> {
  return apiPost<PO>(`/v1/supplier-catalogs/pos/${id}/acknowledge`, {});
}

export function closePO(id: string): Promise<PO> {
  return apiPost<PO>(`/v1/supplier-catalogs/pos/${id}/close`, {});
}

/* ── Warehouses ────────────────────────────────────────────────────────── */

export function listWarehouses(): Promise<Warehouse[]> {
  return apiGet<Warehouse[]>('/v1/supplier-catalogs/warehouses');
}

export function createWarehouse(data: CreateWarehousePayload): Promise<Warehouse> {
  return apiPost<Warehouse>('/v1/supplier-catalogs/warehouses', data);
}

export function listWarehouseBalances(warehouseId: string): Promise<StockBalance[]> {
  return apiGet<StockBalance[]>(`/v1/supplier-catalogs/warehouses/${warehouseId}/balances`);
}

/* ── Invoices (read endpoints not exposed; we surface 3-way match exceptions through invoice list ── */
/* Backend currently exposes only match action; we can't list invoices generically. */

export interface MatchResult {
  invoice_id: string;
  status: string;
  price_variance: number | string;
  qty_variance: number | string;
  tolerance_used_pct: number | string;
  exception_reason: string | null;
  tolerance_profile_name?: string;
  line_results?: Array<Record<string, unknown>>;
}

export function matchInvoice(
  invoiceId: string,
  tolerancePct?: number,
  toleranceProfile?: string,
): Promise<MatchResult> {
  const params: Record<string, string | number | undefined> = {};
  if (tolerancePct !== undefined) params.tolerance_pct = tolerancePct;
  if (toleranceProfile) params.tolerance_profile = toleranceProfile;
  return apiPost<MatchResult>(
    `/v1/supplier-catalogs/invoices/${invoiceId}/match${qs(params)}`,
    {},
  );
}

/* ── Commodity codes ───────────────────────────────────────────────────── */

export interface CommodityCode {
  id: string;
  scheme: 'unspsc' | 'eclass' | 'cpv';
  code: string;
  name: string;
  description: string | null;
  parent_code: string | null;
  level: number;
  active: boolean;
}

export function listCommodityCodes(params?: {
  scheme?: string;
  search?: string;
  parent_code?: string;
  level?: number;
  limit?: number;
  offset?: number;
}): Promise<CommodityCode[]> {
  return apiGet<CommodityCode[]>(
    `/v1/supplier-catalogs/commodity-codes${qs(params || {})}`,
  );
}

export function seedCommodityCodes(): Promise<Record<string, number>> {
  return apiPost<Record<string, number>>(
    '/v1/supplier-catalogs/commodity-codes/seed',
    {},
  );
}

/* ── Tolerance profiles ────────────────────────────────────────────────── */

export interface TolerianceProfile {
  id: string;
  name: string;
  description: string | null;
  price_tolerance_pct: number | string;
  price_tolerance_abs: number | string;
  qty_tolerance_pct: number | string;
  period_tolerance_days: number;
  require_gr: boolean;
  is_default: boolean;
}

export interface CreateToleranceProfilePayload {
  name: string;
  description?: string;
  price_tolerance_pct?: number;
  price_tolerance_abs?: number;
  qty_tolerance_pct?: number;
  period_tolerance_days?: number;
  require_gr?: boolean;
  is_default?: boolean;
}

export function listToleranceProfiles(): Promise<TolerianceProfile[]> {
  return apiGet<TolerianceProfile[]>(
    '/v1/supplier-catalogs/tolerance-profiles',
  );
}

export function createToleranceProfile(
  data: CreateToleranceProfilePayload,
): Promise<TolerianceProfile> {
  return apiPost<TolerianceProfile>(
    '/v1/supplier-catalogs/tolerance-profiles',
    data,
  );
}

export function updateToleranceProfile(
  id: string,
  data: Partial<CreateToleranceProfilePayload>,
): Promise<TolerianceProfile> {
  return apiPatch<TolerianceProfile>(
    `/v1/supplier-catalogs/tolerance-profiles/${id}`,
    data,
  );
}

/* ── KYC documents ─────────────────────────────────────────────────────── */

export type KYCDocType =
  | 'w9'
  | 'vat_cert'
  | 'gst'
  | 'trn'
  | 'coi'
  | 'iso'
  | 'other';

export interface KYCDocument {
  id: string;
  vendor_id: string;
  doc_type: KYCDocType;
  document_number: string | null;
  issued_on: string | null;
  expires_on: string | null;
  issuing_country: string | null;
  issuing_authority: string | null;
  file_url: string | null;
  status: string;
  verified_at: string | null;
  verified_by: string | null;
  notes: string | null;
}

export interface CreateKYCDocPayload {
  doc_type: KYCDocType;
  document_number?: string;
  issued_on?: string;
  expires_on?: string;
  issuing_country?: string;
  issuing_authority?: string;
  file_url?: string;
  notes?: string;
}

export function listVendorKYC(vendorId: string): Promise<KYCDocument[]> {
  return apiGet<KYCDocument[]>(
    `/v1/supplier-catalogs/vendors/${vendorId}/kyc`,
  );
}

export function addVendorKYC(
  vendorId: string,
  data: CreateKYCDocPayload,
): Promise<KYCDocument> {
  return apiPost<KYCDocument>(
    `/v1/supplier-catalogs/vendors/${vendorId}/kyc`,
    data,
  );
}

export function checkKYCExpiry(daysAhead = 30): Promise<{ expiring: number; expired: number }> {
  return apiPost<{ expiring: number; expired: number }>(
    `/v1/supplier-catalogs/kyc/check-expiry${qs({ days_ahead: daysAhead })}`,
    {},
  );
}

/* ── Scorecards ────────────────────────────────────────────────────────── */

export interface Scorecard {
  id: string;
  vendor_id: string;
  period_start: string;
  period_end: string;
  delivery_score: number | string;
  quality_score: number | string;
  price_score: number | string;
  esg_score: number | string;
  composite_score: number | string;
  inputs_json: Record<string, unknown>;
  weights_json: Record<string, unknown>;
  computed_at: string;
}

export interface ScorecardRecomputePayload {
  period_start: string;
  period_end: string;
  weights?: {
    delivery?: number;
    quality?: number;
    price?: number;
    esg?: number;
  };
}

export function recomputeScorecard(
  vendorId: string,
  data: ScorecardRecomputePayload,
): Promise<Scorecard> {
  return apiPost<Scorecard>(
    `/v1/supplier-catalogs/vendors/${vendorId}/scorecard/recompute`,
    data,
  );
}

export function listVendorScorecards(
  vendorId: string,
  limit = 24,
): Promise<Scorecard[]> {
  return apiGet<Scorecard[]>(
    `/v1/supplier-catalogs/vendors/${vendorId}/scorecards${qs({ limit })}`,
  );
}

/* ── PEPPOL invoice ingest ─────────────────────────────────────────────── */

export interface PeppolIngestResult {
  invoice_id: string;
  invoice_number: string;
  vendor_id: string;
  matched_status: string;
  line_count: number;
  total: number | string;
  currency: string;
  exception_reason: string | null;
  peppol_message_id: string | null;
}

export async function ingestPeppolInvoice(
  file: File,
  autoMatch = true,
): Promise<PeppolIngestResult> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(
    `/api/v1/supplier-catalogs/invoices/peppol${qs({ auto_match: autoMatch ? 'true' : 'false' })}`,
    {
      method: 'POST',
      body: fd,
      credentials: 'include',
    },
  );
  if (!res.ok) {
    throw new Error(`PEPPOL ingest failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as PeppolIngestResult;
}
