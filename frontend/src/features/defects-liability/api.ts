// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for the Defects Liability module.
 *
 * Post-handover warranty / defects-liability-period (DLP) governance: the
 * per-project register of warranty / DLP entries, the defect notices raised
 * against them, and the derived register rollup plus retention-release
 * readiness view (the money signal: which entries have finished their DLP
 * clean and are clear for the final retention).
 *
 * Every endpoint is project-scoped IN THE PATH, mounted under
 * `/api/v1/defects-liability/projects/{projectId}/...` (the DB table prefix is
 * `oe_dlp_` but the route name is `defects-liability`). The filter helpers below
 * mirror the server-side query params, though the page filters client-side over
 * a full project fetch so the defect -> warranty reference map is always complete.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* -- Vocabularies (in lock-step with backend register.py) ------------------ */

export type WarrantyType =
  | 'workmanship'
  | 'manufacturer'
  | 'latent_defect'
  | 'extended'
  | 'other';

export type WarrantyStatus = 'in_dlp' | 'expiring' | 'expired' | 'closed' | 'on_hold';

export type DefectStatus = 'open' | 'rectifying' | 'rectified' | 'rejected' | 'closed';

export type DefectSeverity = 'minor' | 'major' | 'critical';

export const WARRANTY_TYPES: WarrantyType[] = [
  'workmanship',
  'manufacturer',
  'latent_defect',
  'extended',
  'other',
];

export const WARRANTY_STATUSES: WarrantyStatus[] = [
  'in_dlp',
  'expiring',
  'expired',
  'closed',
  'on_hold',
];

export const DEFECT_STATUSES: DefectStatus[] = [
  'open',
  'rectifying',
  'rectified',
  'rejected',
  'closed',
];

export const DEFECT_SEVERITIES: DefectSeverity[] = ['minor', 'major', 'critical'];

/* -- Entity types ---------------------------------------------------------- */

/** A warranty / DLP entry (WarrantyResponse). Dates are ISO `YYYY-MM-DD`. */
export interface Warranty {
  id: string;
  project_id: string;
  reference: string;
  title: string;
  element_description: string | null;
  subcontractor_id: string | null;
  subcontractor_name: string | null;
  work_package: string | null;
  warranty_type: WarrantyType | null;
  handover_date: string | null;
  warranty_start_date: string | null;
  warranty_months: number | null;
  warranty_end_date: string | null;
  dlp_end_date: string | null;
  status: WarrantyStatus;
  retention_release_date: string | null;
  contract_id: string | null;
  document_id: string | null;
  sort_order: number;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** WarrantyCreate payload. `reference` and `title` are required by the server. */
export interface WarrantyCreate {
  reference: string;
  title: string;
  element_description?: string | null;
  subcontractor_name?: string | null;
  work_package?: string | null;
  warranty_type?: WarrantyType | null;
  handover_date?: string | null;
  warranty_start_date?: string | null;
  warranty_months?: number | null;
  warranty_end_date?: string | null;
  dlp_end_date?: string | null;
  status?: WarrantyStatus;
  retention_release_date?: string | null;
  sort_order?: number;
  notes?: string | null;
}

/** WarrantyUpdate payload: only provided fields change (null clears). */
export type WarrantyUpdate = Partial<WarrantyCreate>;

/** A defect notice (DefectResponse). */
export interface Defect {
  id: string;
  project_id: string;
  warranty_id: string;
  reference: string;
  description: string;
  severity: DefectSeverity | null;
  raised_date: string | null;
  due_date: string | null;
  status: DefectStatus;
  rectified_date: string | null;
  responsible_party: string | null;
  punchlist_id: string | null;
  ncr_id: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** DefectCreate payload. `reference` and `description` are required. */
export interface DefectCreate {
  reference: string;
  description: string;
  severity?: DefectSeverity | null;
  raised_date?: string | null;
  due_date?: string | null;
  status?: DefectStatus;
  rectified_date?: string | null;
  responsible_party?: string | null;
}

/** DefectUpdate payload: only provided fields change (null clears). */
export type DefectUpdate = Partial<DefectCreate>;

/* -- Derived register views ------------------------------------------------ */

/** Lightweight reference to an entry, used in expiring / ready lists. */
export interface WarrantyRef {
  warranty_id: string | null;
  reference: string;
  title: string;
  status: string;
  subcontractor_name: string | null;
  work_package: string | null;
  warranty_type: string | null;
  dlp_end_date: string | null;
  warranty_end_date: string | null;
  open_defect_count: number;
  retention_release_ready: boolean;
}

/** One overdue defect carrying its owning warranty's identity. */
export interface OverdueDefectRef {
  warranty_id: string | null;
  warranty_reference: string;
  title: string;
  severity: string | null;
  status: string;
  due_date: string | null;
}

/** Post-handover DLP health rollup for one subcontractor. */
export interface SubcontractorDlpHealth {
  subcontractor: string;
  total: number;
  open_defects: number;
  overdue_defects: number;
  /** Percentage as a plain decimal string (e.g. "100.00"), or null when undefined. */
  health_score: string | null;
}

/** The full defects-liability register rollup (DlpRegisterResponse). */
export interface DlpRegister {
  project_id: string;
  as_of: string;
  horizon_days: number;
  total: number;
  per_status: Record<string, number>;
  per_warranty_type: Record<string, number>;
  total_open_defects: number;
  /** Percentage as a plain decimal string, or null when the register is empty. */
  overall_health_score: string | null;
  is_clean: boolean;
  expiring: WarrantyRef[];
  expired: WarrantyRef[];
  overdue_defects: OverdueDefectRef[];
  retention_release_ready: WarrantyRef[];
  subcontractors: SubcontractorDlpHealth[];
}

/** The entries clear for final retention release (RetentionReleaseReadinessResponse). */
export interface RetentionReleaseReadiness {
  project_id: string;
  as_of: string;
  total: number;
  ready_count: number;
  ready: WarrantyRef[];
}

/* -- API functions --------------------------------------------------------- */

const BASE = '/v1/defects-liability';

/** List a project's warranty / DLP entries (optionally filtered server-side). */
export async function fetchWarranties(
  projectId: string,
  filters?: { status?: WarrantyStatus; warranty_type?: WarrantyType; work_package?: string },
): Promise<Warranty[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set('status', filters.status);
  if (filters?.warranty_type) params.set('warranty_type', filters.warranty_type);
  if (filters?.work_package) params.set('work_package', filters.work_package);
  const qs = params.toString();
  return apiGet<Warranty[]>(`${BASE}/projects/${projectId}/warranties${qs ? `?${qs}` : ''}`);
}

/** Create a warranty / DLP entry on a project. */
export async function createWarranty(
  projectId: string,
  payload: WarrantyCreate,
): Promise<Warranty> {
  return apiPost<Warranty, WarrantyCreate>(
    `${BASE}/projects/${projectId}/warranties`,
    payload,
  );
}

/** Patch a warranty / DLP entry (only provided fields change). */
export async function updateWarranty(
  projectId: string,
  warrantyId: string,
  payload: WarrantyUpdate,
): Promise<Warranty> {
  return apiPatch<Warranty, WarrantyUpdate>(
    `${BASE}/projects/${projectId}/warranties/${warrantyId}`,
    payload,
  );
}

/** Delete a warranty / DLP entry and its defects. */
export async function deleteWarranty(projectId: string, warrantyId: string): Promise<void> {
  return apiDelete<void>(`${BASE}/projects/${projectId}/warranties/${warrantyId}`);
}

/** List a project's defect notices (optionally filtered server-side). */
export async function fetchDefects(
  projectId: string,
  filters?: { warranty_id?: string; status?: DefectStatus; severity?: DefectSeverity },
): Promise<Defect[]> {
  const params = new URLSearchParams();
  if (filters?.warranty_id) params.set('warranty_id', filters.warranty_id);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.severity) params.set('severity', filters.severity);
  const qs = params.toString();
  return apiGet<Defect[]>(`${BASE}/projects/${projectId}/defects${qs ? `?${qs}` : ''}`);
}

/** Raise a defect notice against a warranty (warranty is taken from the path). */
export async function createDefect(
  projectId: string,
  warrantyId: string,
  payload: DefectCreate,
): Promise<Defect> {
  return apiPost<Defect, DefectCreate>(
    `${BASE}/projects/${projectId}/warranties/${warrantyId}/defects`,
    payload,
  );
}

/** Patch (or close) a defect notice (only provided fields change). */
export async function updateDefect(
  projectId: string,
  defectId: string,
  payload: DefectUpdate,
): Promise<Defect> {
  return apiPatch<Defect, DefectUpdate>(
    `${BASE}/projects/${projectId}/defects/${defectId}`,
    payload,
  );
}

/** Full defects-liability register rollup: counts, expiry, defect load, health. */
export async function fetchRegister(
  projectId: string,
  params?: { as_of?: string; horizon_days?: number },
): Promise<DlpRegister> {
  const q = new URLSearchParams();
  if (params?.as_of) q.set('as_of', params.as_of);
  if (params?.horizon_days != null) q.set('horizon_days', String(params.horizon_days));
  const qs = q.toString();
  return apiGet<DlpRegister>(`${BASE}/projects/${projectId}/register${qs ? `?${qs}` : ''}`);
}

/** Entries whose DLP has ended clean, clear for final retention release. */
export async function fetchRetentionReadiness(
  projectId: string,
  asOf?: string,
): Promise<RetentionReleaseReadiness> {
  const q = new URLSearchParams();
  if (asOf) q.set('as_of', asOf);
  const qs = q.toString();
  return apiGet<RetentionReleaseReadiness>(
    `${BASE}/projects/${projectId}/retention-release-readiness${qs ? `?${qs}` : ''}`,
  );
}
