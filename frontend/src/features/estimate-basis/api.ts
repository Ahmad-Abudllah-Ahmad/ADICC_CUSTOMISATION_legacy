// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Typed client for the basis-of-estimate module (/api/v1/estimate-basis).
//
// The document derives from the finished estimate: which trades are present,
// absent or flagged by the coverage check. Trade rollup totals arrive as
// Decimal-compatible strings (never a float); the UI formats them for display
// and never does arithmetic on them.

import { apiGet, apiPost, apiPut } from '@/shared/lib/api';

export type QualificationCategory = 'inclusion' | 'exclusion' | 'assumption';

export interface QualificationItem {
  id: string;
  category: QualificationCategory;
  text: string;
  trade_code: string | null;
  trade_label: string | null;
  basis: string;
  source: 'auto' | 'manual';
  enabled: boolean;
}

export interface TradePresence {
  code: string;
  label: string;
  core: boolean;
  position_count: number;
  /** Rolled-up total for the trade, as a Decimal string. */
  total: string;
}

export interface TradeRef {
  code: string;
  label: string;
}

export interface CoverageSummary {
  present_trades: TradePresence[];
  absent_trades: TradeRef[];
  total_positions: number;
  classified_positions: number;
  unclassified_positions: number;
  zero_rate_positions: number;
  missing_quantity_positions: number;
  provisional_positions: number;
  by_others_positions: number;
}

export interface EstimateBasisDocument {
  id: string;
  project_id: string;
  boq_id: string | null;
  title: string;
  status: string;
  notes: string;
  inclusions: QualificationItem[];
  exclusions: QualificationItem[];
  assumptions: QualificationItem[];
  coverage: CoverageSummary;
  generated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EstimateBasisSummary {
  id: string;
  project_id: string;
  boq_id: string | null;
  title: string;
  status: string;
  inclusion_count: number;
  exclusion_count: number;
  assumption_count: number;
  generated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EstimateBasisList {
  project_id: string;
  items: EstimateBasisSummary[];
}

export interface GenerateBasisRequest {
  project_id: string;
  boq_id?: string | null;
  title?: string | null;
  currency?: string;
  base_date?: string | null;
}

export interface UpdateBasisRequest {
  title?: string | null;
  status?: 'draft' | 'final' | null;
  notes?: string | null;
  inclusions?: QualificationItem[] | null;
  exclusions?: QualificationItem[] | null;
  assumptions?: QualificationItem[] | null;
}

const BASE = '/v1/estimate-basis';

/** Draft and store a fresh basis-of-estimate from the project's estimate. */
export function generateBasis(
  body: GenerateBasisRequest,
  init?: { signal?: AbortSignal },
): Promise<EstimateBasisDocument> {
  return apiPost<EstimateBasisDocument, GenerateBasisRequest>(`${BASE}/generate`, body, init);
}

/** List every basis-of-estimate document drafted for a project, newest first. */
export function listBasis(projectId: string): Promise<EstimateBasisList> {
  return apiGet<EstimateBasisList>(`${BASE}/projects/${encodeURIComponent(projectId)}`);
}

/** Fetch one basis-of-estimate document. */
export function getBasis(documentId: string): Promise<EstimateBasisDocument> {
  return apiGet<EstimateBasisDocument>(`${BASE}/documents/${encodeURIComponent(documentId)}`);
}

/** Persist user edits to a basis-of-estimate document. */
export function updateBasis(
  documentId: string,
  body: UpdateBasisRequest,
): Promise<EstimateBasisDocument> {
  return apiPut<EstimateBasisDocument, UpdateBasisRequest>(
    `${BASE}/documents/${encodeURIComponent(documentId)}`,
    body,
  );
}
