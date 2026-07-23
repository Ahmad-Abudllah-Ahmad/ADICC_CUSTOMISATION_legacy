// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for Punch List.
 *
 * All endpoints are prefixed with /v1/punchlist/.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type PunchPriority = 'low' | 'medium' | 'high' | 'critical';
// Full lifecycle FSM mirrored from the backend (punchlist/service.py
// VALID_TRANSITIONS): open -> assigned -> in_progress -> resolved ->
// verified -> closed, and any state can go back to open (reopen). The
// 'assigned' stage lets a snag be owned before work actually starts.
export type PunchStatus =
  | 'open'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'verified'
  | 'closed';
export type PunchCategory =
  | 'structural'
  | 'mechanical'
  | 'electrical'
  | 'architectural'
  | 'plumbing'
  | 'finishing'
  | 'fire_safety'
  | 'hvac'
  | 'exterior'
  | 'landscaping'
  | 'general';

export interface PunchItem {
  id: string;
  project_id: string;
  title: string;
  description: string;
  priority: PunchPriority;
  status: PunchStatus;
  category: PunchCategory | null;
  assigned_to: string | null;
  due_date: string | null;
  document_id: string | null;
  page: number | null;
  location_x: number | null;
  location_y: number | null;
  photos: string[];
  trade: string | null;
  resolution_notes: string | null;
  verified_by: string | null;
  metadata: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  verified_at: string | null;
  reopen_history?: ReopenHistoryEntry[];
}

export interface ReopenHistoryEntry {
  reopened_at: string;
  reopened_by: string | null;
  previous_status: string;
  reason?: string;
}

export interface BulkCloseResponse {
  closed: number;
  skipped: number;
  errors: { id: string; error: string }[];
}

export interface PunchSummary {
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  overdue: number;
  avg_days_to_close: number | null;
}

export interface PunchFilters {
  search?: string;
  priority?: PunchPriority | '';
  status?: PunchStatus | '';
  category?: PunchCategory | '';
  assigned_to?: string;
}

export interface CreatePunchPayload {
  project_id: string;
  title: string;
  description?: string;
  priority?: PunchPriority;
  category?: PunchCategory;
  assigned_to?: string;
  due_date?: string;
  document_id?: string;
  /** 1-based sheet page the pin sits on (backend accepts page>=1). */
  page?: number;
  location_x?: number | null;
  location_y?: number | null;
  trade?: string;
}

export interface UpdatePunchPayload {
  title?: string;
  description?: string;
  priority?: PunchPriority;
  category?: PunchCategory;
  assigned_to?: string | null;
  due_date?: string | null;
  document_id?: string | null;
  location_x?: number | null;
  location_y?: number | null;
  trade?: string | null;
  resolution_notes?: string | null;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  avatar_url: string | null;
}

/* ── API Functions ─────────────────────────────────────────────────────── */

export async function fetchPunchItems(
  projectId: string,
  filters?: PunchFilters,
): Promise<PunchItem[]> {
  if (!projectId) return [];
  const params = new URLSearchParams({ project_id: projectId });
  if (filters?.search) params.set('search', filters.search);
  if (filters?.priority) params.set('priority', filters.priority);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.category) params.set('category', filters.category);
  if (filters?.assigned_to) params.set('assigned_to', filters.assigned_to);
  const res = await apiGet<PunchItem[] | { items: PunchItem[] }>(
    `/v1/punchlist/items/?${params.toString()}`,
  );
  return Array.isArray(res) ? res : res.items ?? [];
}

export async function createPunchItem(data: CreatePunchPayload): Promise<PunchItem> {
  return apiPost<PunchItem>('/v1/punchlist/items/', data);
}

export async function updatePunchItem(id: string, data: UpdatePunchPayload): Promise<PunchItem> {
  return apiPatch<PunchItem>(`/v1/punchlist/items/${id}`, data);
}

export async function deletePunchItem(id: string): Promise<void> {
  return apiDelete(`/v1/punchlist/items/${id}`);
}

export async function transitionPunchStatus(
  id: string,
  newStatus: PunchStatus,
  notes?: string,
): Promise<PunchItem> {
  // `notes` is optional and, when present, is stored by the backend as the
  // resolution note (or the reopen reason on a reopen). Existing callers that
  // pass only (id, status) are unaffected.
  const body: { new_status: PunchStatus; notes?: string } = { new_status: newStatus };
  const trimmed = notes?.trim();
  if (trimmed) body.notes = trimmed;
  return apiPost<PunchItem>(`/v1/punchlist/items/${id}/transition/`, body);
}

/** Fetch a single punch item by id (used by the detail drawer to stay fresh). */
export async function fetchPunchItem(id: string): Promise<PunchItem> {
  return apiGet<PunchItem>(`/v1/punchlist/items/${id}`);
}

export async function bulkClose(
  ids: string[],
  projectId: string,
  comment?: string,
): Promise<BulkCloseResponse> {
  return apiPost<BulkCloseResponse>('/v1/punchlist/bulk-close/', {
    ids,
    project_id: projectId,
    comment,
  });
}

export async function uploadPunchPhoto(id: string, file: File): Promise<PunchItem> {
  const formData = new FormData();
  formData.append('file', file);
  const token = localStorage.getItem('oe_access_token');
  const res = await fetch(`/api/v1/punchlist/items/${id}/photos/`, {
    method: 'POST',
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
      'X-DDC-Client': 'OE/1.0',
    },
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

/** Remove a photo from a punch item by its index in the photos array. */
export async function deletePunchPhoto(id: string, index: number): Promise<void> {
  return apiDelete(`/v1/punchlist/items/${id}/photos/${index}`);
}

/** Payload for pinning a punch item to a location on a drawing sheet. */
export interface PinToSheetPayload {
  /** Document (drawing) the pin sits on. */
  document_id?: string;
  /** Sheet id, accepted by the backend as an alternative to document_id. */
  sheet_id?: string;
  /** 1-based page the pin sits on. */
  page: number;
  /** Normalised pin coordinates on the sheet (0..1). */
  location_x: number;
  location_y: number;
}

/**
 * Pin a punch item to a normalised (0..1) location on a drawing sheet.
 * Wraps POST /v1/punchlist/items/{id}/pin-to-sheet/.
 */
export async function pinPunchToSheet(id: string, payload: PinToSheetPayload): Promise<PunchItem> {
  return apiPost<PunchItem>(`/v1/punchlist/items/${id}/pin-to-sheet/`, payload);
}

/** A project document as returned by the documents list endpoint. */
export interface PunchDocument {
  id: string;
  name: string;
  description?: string;
  category?: string;
}

/**
 * Photos uploaded to a punch item are stored as relative paths and
 * cross-linked as Document records (category "photo", name = the stored
 * filename). There is no static route that serves the raw path, so to show a
 * thumbnail we resolve the photo's basename to its cross-linked document and
 * stream that through the authenticated documents download endpoint. This
 * returns the photo-category documents for the project so the caller can build
 * a filename -> document-id map.
 */
export async function fetchPunchPhotoDocuments(projectId: string): Promise<PunchDocument[]> {
  if (!projectId) return [];
  const rows = await apiGet<PunchDocument[] | { items: PunchDocument[] }>(
    `/v1/documents/?project_id=${projectId}&category=photo&limit=500`,
  );
  return Array.isArray(rows) ? rows : rows.items ?? [];
}

/** A drawing/document option for the pin board and pin picker. */
export interface PunchDrawing {
  id: string;
  filename: string;
}

/** List the project documents that can be used as pin-board drawings. */
export async function fetchPunchDrawings(projectId: string): Promise<PunchDrawing[]> {
  if (!projectId) return [];
  const rows = await apiGet<{ id: string; filename?: string; name?: string }[]>(
    `/v1/documents/?project_id=${projectId}&limit=500`,
  );
  return (Array.isArray(rows) ? rows : []).map((r) => ({
    id: r.id,
    filename: r.filename ?? r.name ?? '',
  }));
}

export async function fetchPunchSummary(projectId: string): Promise<PunchSummary> {
  if (!projectId) return { total: 0, by_status: {}, by_priority: {}, overdue: 0, avg_days_to_close: null };
  return apiGet<PunchSummary>(`/v1/punchlist/summary/?project_id=${projectId}`);
}

interface UserListEntry {
  id: string;
  email: string;
  full_name?: string | null;
  is_active?: boolean;
}

export async function fetchTeamMembers(projectId: string): Promise<TeamMember[]> {
  if (!projectId) return [];
  // No project-scoped /members endpoint exists (frontend was 404'ing on it);
  // fall back to the tenant-wide user list and map onto the assignment shape.
  const users = await apiGet<UserListEntry[] | { items: UserListEntry[] }>('/v1/users/?limit=100');
  const list = Array.isArray(users) ? users : users.items ?? [];
  return list
    .filter((u) => u.is_active !== false)
    .map((u) => ({
      id: u.id,
      name: u.full_name?.trim() || u.email,
      email: u.email,
      avatar_url: null,
    }));
}
