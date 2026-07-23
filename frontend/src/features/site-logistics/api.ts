// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for Site Logistics & Delivery.
 *
 * All endpoints are prefixed with /v1/site-logistics/. Trailing slashes match
 * the FastAPI routes exactly, avoiding a 307 redirect that some proxies rewrite
 * without forwarding the auth header (which would surface as an empty list).
 */

import { apiDelete, apiGet, apiPatch, apiPost } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type DeliveryStatus =
  | 'requested'
  | 'approved'
  | 'rejected'
  | 'arrived'
  | 'completed';

export interface Gate {
  id: string;
  project_id: string;
  name: string;
  open_time: string;
  close_time: string;
  capacity_per_slot: number;
  notes: string | null;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface LaydownZone {
  id: string;
  project_id: string;
  name: string;
  capacity_desc: string | null;
  usage_note: string | null;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DeliveryBooking {
  id: string;
  project_id: string;
  gate_id: string | null;
  supplier_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  vehicle_type: string | null;
  materials_desc: string | null;
  window_start: string;
  window_end: string;
  status: DeliveryStatus;
  po_ref: string | null;
  notes: string | null;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SiteLogisticsStats {
  total_deliveries: number;
  by_status: Record<string, number>;
  gate_count: number;
  laydown_zone_count: number;
  upcoming_approved: number;
}

export interface CreateGatePayload {
  project_id: string;
  name: string;
  open_time?: string;
  close_time?: string;
  capacity_per_slot?: number;
  notes?: string;
}

export type UpdateGatePayload = Partial<Omit<CreateGatePayload, 'project_id'>>;

export interface CreateLaydownZonePayload {
  project_id: string;
  name: string;
  capacity_desc?: string;
  usage_note?: string;
}

export type UpdateLaydownZonePayload = Partial<
  Omit<CreateLaydownZonePayload, 'project_id'>
>;

export interface CreateDeliveryPayload {
  project_id: string;
  gate_id?: string | null;
  supplier_name: string;
  contact_name?: string;
  contact_phone?: string;
  vehicle_type?: string;
  materials_desc?: string;
  window_start: string;
  window_end: string;
  status?: DeliveryStatus;
  po_ref?: string;
  notes?: string;
}

export type UpdateDeliveryPayload = Partial<
  Omit<CreateDeliveryPayload, 'project_id'>
>;

export interface DeliveryFilters {
  day?: string;
  gate_id?: string;
  status?: DeliveryStatus | '';
}

/* ── Gates ──────────────────────────────────────────────────────────────── */

export async function fetchGates(projectId: string): Promise<Gate[]> {
  return apiGet<Gate[]>(
    `/v1/site-logistics/gates/?project_id=${encodeURIComponent(projectId)}`,
  );
}

export async function createGate(data: CreateGatePayload): Promise<Gate> {
  return apiPost<Gate>('/v1/site-logistics/gates/', data);
}

export async function updateGate(id: string, data: UpdateGatePayload): Promise<Gate> {
  return apiPatch<Gate>(`/v1/site-logistics/gates/${id}`, data);
}

export async function deleteGate(id: string): Promise<void> {
  return apiDelete<void>(`/v1/site-logistics/gates/${id}`);
}

/* ── Laydown zones ──────────────────────────────────────────────────────── */

export async function fetchLaydownZones(projectId: string): Promise<LaydownZone[]> {
  return apiGet<LaydownZone[]>(
    `/v1/site-logistics/laydown-zones/?project_id=${encodeURIComponent(projectId)}`,
  );
}

export async function createLaydownZone(
  data: CreateLaydownZonePayload,
): Promise<LaydownZone> {
  return apiPost<LaydownZone>('/v1/site-logistics/laydown-zones/', data);
}

export async function updateLaydownZone(
  id: string,
  data: UpdateLaydownZonePayload,
): Promise<LaydownZone> {
  return apiPatch<LaydownZone>(`/v1/site-logistics/laydown-zones/${id}`, data);
}

export async function deleteLaydownZone(id: string): Promise<void> {
  return apiDelete<void>(`/v1/site-logistics/laydown-zones/${id}`);
}

/* ── Deliveries ─────────────────────────────────────────────────────────── */

export async function fetchDeliveries(
  projectId: string,
  filters?: DeliveryFilters,
): Promise<DeliveryBooking[]> {
  const params = new URLSearchParams();
  params.set('project_id', projectId);
  if (filters?.day) params.set('day', filters.day);
  if (filters?.gate_id) params.set('gate_id', filters.gate_id);
  if (filters?.status) params.set('status', filters.status);
  return apiGet<DeliveryBooking[]>(`/v1/site-logistics/deliveries/?${params.toString()}`);
}

export async function createDelivery(
  data: CreateDeliveryPayload,
): Promise<DeliveryBooking> {
  return apiPost<DeliveryBooking>('/v1/site-logistics/deliveries/', data);
}

export async function updateDelivery(
  id: string,
  data: UpdateDeliveryPayload,
): Promise<DeliveryBooking> {
  return apiPatch<DeliveryBooking>(`/v1/site-logistics/deliveries/${id}`, data);
}

export async function deleteDelivery(id: string): Promise<void> {
  return apiDelete<void>(`/v1/site-logistics/deliveries/${id}`);
}

export async function approveDelivery(
  id: string,
  reason?: string,
): Promise<DeliveryBooking> {
  return apiPost<DeliveryBooking>(`/v1/site-logistics/deliveries/${id}/approve/`, {
    reason,
  });
}

export async function rejectDelivery(
  id: string,
  reason?: string,
): Promise<DeliveryBooking> {
  return apiPost<DeliveryBooking>(`/v1/site-logistics/deliveries/${id}/reject/`, {
    reason,
  });
}

/* ── Stats ──────────────────────────────────────────────────────────────── */

export async function fetchSiteLogisticsStats(
  projectId: string,
): Promise<SiteLogisticsStats> {
  return apiGet<SiteLogisticsStats>(
    `/v1/site-logistics/stats/?project_id=${encodeURIComponent(projectId)}`,
  );
}
