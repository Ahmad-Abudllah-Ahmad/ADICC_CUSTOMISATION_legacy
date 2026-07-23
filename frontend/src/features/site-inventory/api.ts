// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for Site Inventory (on-site material stock ledger / metering).
 *
 * Every endpoint is project-scoped in the path and mounted under
 * /v1/site-inventory/projects/{projectId}/... (the backend module
 * oe_site_inventory is served at /api/v1/site-inventory). Money and
 * quantities cross the wire as canonical decimal STRINGS, never floats.
 */

import { apiGet, apiPost } from '@/shared/lib/api';

/* -- Types ----------------------------------------------------------------- */

export type MovementType = 'INBOUND' | 'CONSUMPTION' | 'WASTE' | 'TRANSFER';

export const MOVEMENT_TYPES: MovementType[] = ['INBOUND', 'CONSUMPTION', 'WASTE', 'TRANSFER'];

export interface StockLocation {
  id: string;
  project_id: string;
  name: string;
  code: string | null;
  latitude: string | null;
  longitude: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LocationCreate {
  name: string;
  code?: string;
  latitude?: string;
  longitude?: string;
  address?: string;
  is_active?: boolean;
}

export interface StockItem {
  id: string;
  project_id: string;
  name: string;
  sku: string | null;
  unit: string;
  boq_position_id: string | null;
  procurement_req_item_id: string | null;
  default_location_id: string | null;
  standard_unit_cost: string | null;
  currency: string;
  reorder_point: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StockItemCreate {
  name: string;
  sku?: string;
  unit?: string;
  default_location_id?: string;
  standard_unit_cost?: string;
  currency?: string;
  reorder_point?: string;
  is_active?: boolean;
}

export interface StockMovement {
  id: string;
  project_id: string;
  item_id: string;
  movement_type: MovementType;
  quantity: string;
  unit_cost: string;
  currency: string;
  location_id: string | null;
  to_location_id: string | null;
  boq_position_id: string | null;
  goods_receipt_id: string | null;
  occurred_at: string;
  actor_id: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface MovementCreate {
  item_id: string;
  movement_type: MovementType;
  quantity: string;
  unit_cost?: string;
  currency?: string;
  location_id?: string;
  to_location_id?: string;
  occurred_at?: string;
  note?: string;
}

export interface StockOnHandRow {
  item_id: string;
  name: string;
  unit: string;
  on_hand: string;
}

export interface StockOnHandResponse {
  project_id: string;
  location_id: string | null;
  item_count: number;
  rows: StockOnHandRow[];
}

/* -- Endpoint base --------------------------------------------------------- */

function base(projectId: string): string {
  return `/v1/site-inventory/projects/${projectId}`;
}

/* -- Locations ------------------------------------------------------------- */

export async function fetchLocations(projectId: string): Promise<StockLocation[]> {
  return apiGet<StockLocation[]>(`${base(projectId)}/locations`);
}

export async function createLocation(
  projectId: string,
  data: LocationCreate,
): Promise<StockLocation> {
  return apiPost<StockLocation, LocationCreate>(`${base(projectId)}/locations`, data);
}

/* -- Items ----------------------------------------------------------------- */

export async function fetchItems(projectId: string): Promise<StockItem[]> {
  return apiGet<StockItem[]>(`${base(projectId)}/items`);
}

export async function createItem(projectId: string, data: StockItemCreate): Promise<StockItem> {
  return apiPost<StockItem, StockItemCreate>(`${base(projectId)}/items`, data);
}

/* -- Movements ------------------------------------------------------------- */

export async function fetchMovements(projectId: string, limit = 200): Promise<StockMovement[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiGet<StockMovement[]>(`${base(projectId)}/movements?${params.toString()}`);
}

export async function recordMovement(
  projectId: string,
  data: MovementCreate,
): Promise<StockMovement> {
  return apiPost<StockMovement, MovementCreate>(`${base(projectId)}/movements`, data);
}

/* -- Derived reports ------------------------------------------------------- */

export async function fetchStockOnHand(projectId: string): Promise<StockOnHandResponse> {
  return apiGet<StockOnHandResponse>(`${base(projectId)}/stock-on-hand`);
}
