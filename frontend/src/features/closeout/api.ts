// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { apiGet, apiPost, apiPatch, apiDelete, getAuthToken } from '@/shared/lib/api';

const BASE = '/v1/closeout';

// ── Types ─────────────────────────────────────────────────────────────────

export type SlotStatus = 'empty' | 'bound' | 'verified';

export interface CloseoutBinding {
  id: string;
  slot_id: string;
  document_id: string | null;
  document_name: string | null;
  external_url: string | null;
  is_verified: boolean;
  verified_by: string | null;
  verified_at: string | null;
  suggested_by_ai: boolean;
  ai_confidence: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface CloseoutSlot {
  id: string;
  package_id: string;
  slot_key: string;
  title: string;
  category: string;
  discipline: string | null;
  is_required: boolean;
  source_kind: string;
  generated_artifact: string | null;
  ordinal: number;
  metadata: Record<string, unknown>;
  status: SlotStatus;
  binding: CloseoutBinding | null;
}

export interface OutstandingWork {
  punch: number;
  inspection: number;
  commissioning: number;
  defects: number;
}

export interface CloseoutPackage {
  id: string;
  project_id: string;
  title: string;
  project_type: string;
  status: string;
  checklist_template: string;
  required_slot_count: number;
  delivered_slot_count: number;
  completeness_pct: number;
  last_built_job_id: string | null;
  last_built_at: string | null;
  has_built_package: boolean;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  issued_at: string | null;
  issued_by: string | null;
  slots: CloseoutSlot[];
  gaps: string[];
  ready: boolean;
  outstanding_work: OutstandingWork | null;
}

export interface BuildPackageResponse {
  job_id: string;
  status: string;
  progress_percent: number;
  package_id: string;
}

export interface BindingSuggestion {
  slot_id: string;
  slot_key: string;
  document_id: string;
  document_name: string;
  confidence: number;
  reason: string;
}

export interface JobRunRead {
  id: string;
  kind: string;
  status: string;
  progress_percent: number;
  result: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
}

export type CloseoutProjectType =
  | 'residential'
  | 'commercial'
  | 'infrastructure'
  | 'fitout'
  | 'custom';

// ── Package ─────────────────────────────────────────────────────────────────

export function getCloseoutPackage(projectId: string): Promise<CloseoutPackage> {
  return apiGet<CloseoutPackage>(`${BASE}/projects/${projectId}/package`);
}

export function createCloseoutPackage(
  projectId: string,
  projectType: CloseoutProjectType,
  title?: string,
): Promise<CloseoutPackage> {
  return apiPost<CloseoutPackage>(`${BASE}/projects/${projectId}/package`, {
    project_type: projectType,
    title,
  });
}

export function getPackage(packageId: string): Promise<CloseoutPackage> {
  return apiGet<CloseoutPackage>(`${BASE}/packages/${packageId}`);
}

// ── Slots ─────────────────────────────────────────────────────────────────

export interface AddSlotPayload {
  slot_key: string;
  title: string;
  category?: string;
  discipline?: string | null;
  is_required?: boolean;
  source_kind?: string;
  generated_artifact?: string | null;
  ordinal?: number;
  metadata?: Record<string, unknown>;
}

export function addSlot(packageId: string, payload: AddSlotPayload): Promise<CloseoutSlot> {
  return apiPost<CloseoutSlot>(`${BASE}/packages/${packageId}/slots`, payload);
}

export interface UpdateSlotPayload {
  title?: string;
  category?: string;
  discipline?: string | null;
  is_required?: boolean;
  source_kind?: string;
  generated_artifact?: string | null;
  ordinal?: number;
  metadata?: Record<string, unknown>;
}

export function updateSlot(slotId: string, payload: UpdateSlotPayload): Promise<CloseoutSlot> {
  return apiPatch<CloseoutSlot>(`${BASE}/slots/${slotId}`, payload);
}

export function deleteSlot(slotId: string): Promise<void> {
  return apiDelete(`${BASE}/slots/${slotId}`);
}

export interface BindSlotPayload {
  document_id?: string | null;
  external_url?: string | null;
  mark_verified?: boolean;
  metadata?: Record<string, unknown>;
}

export function bindSlot(slotId: string, payload: BindSlotPayload): Promise<CloseoutSlot> {
  return apiPost<CloseoutSlot>(`${BASE}/slots/${slotId}/bind`, payload);
}

export function unbindSlot(slotId: string): Promise<CloseoutSlot> {
  return apiPost<CloseoutSlot>(`${BASE}/slots/${slotId}/unbind`, {});
}

export function verifySlot(slotId: string, isVerified = true): Promise<CloseoutSlot> {
  return apiPost<CloseoutSlot>(`${BASE}/slots/${slotId}/verify`, { is_verified: isVerified });
}

// ── AI suggest / build / download ───────────────────────────────────────────

export function suggestBindings(packageId: string): Promise<{ suggestions: BindingSuggestion[] }> {
  return apiPost<{ suggestions: BindingSuggestion[] }>(
    `${BASE}/packages/${packageId}/suggest-bindings`,
    {},
  );
}

export function buildPackage(packageId: string): Promise<BuildPackageResponse> {
  return apiPost<BuildPackageResponse>(`${BASE}/packages/${packageId}/build`, {});
}

/**
 * Issue the package to the client, reaching the terminal `issued` state.
 * The backend returns 409 unless every required item is delivered and every
 * certifying artifact's live work (punch closure, final inspection) is complete.
 */
export function issuePackage(packageId: string): Promise<CloseoutPackage> {
  return apiPost<CloseoutPackage>(`${BASE}/packages/${packageId}/issue`, {});
}

export function getJob(jobId: string): Promise<JobRunRead> {
  return apiGet<JobRunRead>(`/v1/jobs/${jobId}`);
}

/**
 * Stream-download the built closeout ZIP.
 *
 * The endpoint is HTTPBearer-guarded, so a plain `<a href>` would 401.
 * Mirrors property-dev `exportHandoverPackage`: authenticated `fetch` ->
 * Blob for the `URL.createObjectURL` + temp `<a download>` flow.
 */
export async function downloadPackage(
  packageId: string,
): Promise<{ blob: Blob; filename: string }> {
  const token = getAuthToken();
  const headers: Record<string, string> = { Accept: 'application/zip' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${BASE}/packages/${packageId}/download`, {
    method: 'GET',
    headers,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? `closeout_${packageId}.zip`;
  const blob = await res.blob();
  return { blob, filename };
}

/**
 * Trigger a browser download of an already-fetched Blob via a temp anchor.
 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
