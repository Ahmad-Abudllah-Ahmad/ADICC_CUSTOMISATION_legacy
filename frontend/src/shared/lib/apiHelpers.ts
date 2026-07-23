// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Normalize an API list response that may return either a bare array
 * or an object with an `items` array.  Used as a `select` transform
 * in React Query to provide a consistent array to components.
 *
 * Internal ref: ddc-lineage:a17f93c4-core-02
 */
export function normalizeListResponse<T>(data: T[] | { items: T[] } | undefined | null): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if ('items' in data && Array.isArray(data.items)) return data.items;
  return [];
}
