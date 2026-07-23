// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { takeoffApi, type MeasurementCreate, type MeasurementResponse } from '@/features/takeoff/api';
import {
  type PageScales,
  defaultScaleConfig,
  hydratePageScales,
  pageIsCalibrated,
  pageScalesHaveCalibration,
  reconcilePageScales,
  scaleForPage,
} from './data/page-scales';

/* ── Types (mirrored from TakeoffViewerModule) ──────────────────────── */

interface Point {
  x: number;
  y: number;
}

interface Measurement {
  id: string;
  type: 'distance' | 'polyline' | 'area' | 'volume' | 'count'
    | 'cloud' | 'arrow' | 'text' | 'rectangle' | 'highlight';
  points: Point[];
  value: number;
  unit: string;
  label: string;
  annotation: string;
  page: number;
  group: string;
  depth?: number;
  area?: number;
  text?: string;
  color?: string;
  width?: number;
  height?: number;
  /** Per-measurement fill opacity override (issue #311, 0..1). Round-trips via
   *  metadata; falls back to the per-type default alpha when unset. */
  fillAlpha?: number;
  /** Per-measurement stroke width override in CSS px (issue #312). Round-trips
   *  via metadata; falls back to the 2px hairline when unset. */
  strokeWidth?: number;
  /** Per-measurement stroke width in canonical METRES (issue #339). When set (and
   *  the page is calibrated) the band renders at the element's true real-world
   *  width via ``strokeWidthReal * pixelsPerUnit``, staying consistent across
   *  pages calibrated at different scales. Round-trips via metadata as
   *  ``stroke_width_real``; mutually exclusive with `strokeWidth`. */
  strokeWidthReal?: number;
  /** Per-measurement STROKE (line) opacity for linear types (issue #332).
   *  Round-trips via metadata; falls back to fully opaque when unset. */
  strokeAlpha?: number;
  /** True-surface slope / pitch factor for an area measurement (issue #332
   *  wave). Round-trips via metadata; falls back to 1 (flat) when unset. */
  slopeFactor?: number;
  /** Material wastage / allowance percent (issue #332 wave). Round-trips via
   *  metadata; falls back to 0 when unset. */
  wastagePct?: number;
  /** Typical-multiplier count of repeats (issue #332 wave). Round-trips via
   *  metadata; falls back to 1 when unset. */
  multiplier?: number;
  /** Custom colour of this measurement's GROUP (issue #313), distinct from the
   *  per-measurement `color` override. Round-trips via the metadata blob the
   *  same way `fillAlpha` / `strokeWidth` do, so a re-coloured group survives a
   *  server sync and is visible to other users (not localStorage-only). */
  groupColor?: string;
  /** Opening deduction (area void). Stored as positive gross area; the
   *  rollup subtracts it. Round-trips so a void survives a server sync. */
  isDeduction?: boolean;
  /** Server-side ID (set after first sync). */
  serverId?: string;
  /** BOQ link metadata carried through persistence. */
  linkedPositionId?: string;
  linkedPositionOrdinal?: string;
  linkedBoqId?: string;
  linkedPositionLabel?: string;
  /** AI-suggested but unconfirmed (issue #194): excluded from server sync
   *  and localStorage until the user accepts it (which clears the flag). */
  suggested?: boolean;
  /** Recognition confidence 0..1 on AI-sourced measurements. */
  confidence?: number;
}

interface ScaleConfig {
  pixelsPerUnit: number;
  unitLabel: string;
}

interface PersistedDocument {
  measurements: Measurement[];
  /** New per-page scale model. Optional so an older document (which only
   *  carried ``scale``) still parses; ``hydratePageScales`` migrates it. */
  pageScales?: PageScales;
  /** Legacy single document-wide scale. Kept for backward-compatible reads
   *  (and still written so a downgrade to an older build keeps working). */
  scale: ScaleConfig;
  savedAt: number;
}

/* ── localStorage helpers (fallback) ─────────────────────────────────── */

const STORAGE_PREFIX = 'oe_takeoff_';
const INDEX_KEY = 'oe_takeoff_index';

/**
 * Stable storage key for a document's measurements (issue #238).
 *
 * Identity is ``project_id`` + a stable document UUID, never the PDF
 * filename: two same-named PDFs (in one project, or across projects via the
 * old filename-only key) used to collide in one namespace. The composite
 * ``<projectId>__<documentId>`` key isolates them. Both halves are sanitised
 * so a stray char in an id can never break the key shape.
 */
function compositeKey(projectId: string, documentId: string): string {
  const safe = (s: string) => s.replace(/[^a-zA-Z0-9._-]/g, '_');
  return `${STORAGE_PREFIX}${safe(projectId)}__${safe(documentId)}`;
}

/**
 * Legacy filename-only key. Read-only: used once on load to migrate a
 * user's locally-saved measurements into the new composite key so an
 * upgrade doesn't lose them. Never written to any more.
 */
function legacyDocKey(fileName: string): string {
  return `${STORAGE_PREFIX}${fileName.replace(/[^a-zA-Z0-9._-]/g, '_')}`;
}

function readKey(key: string): PersistedDocument | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedDocument;
  } catch {
    return null;
  }
}

/**
 * One-time read of the legacy ``oe_takeoff_<filename>`` key. Returns the
 * parsed document if present so the caller can migrate it into the new
 * composite key. Read-only - it does not delete the legacy entry (a
 * downgrade to an older build would still find it).
 */
function loadLegacyFromStorage(fileName: string | null): PersistedDocument | null {
  if (!fileName) return null;
  return readKey(legacyDocKey(fileName));
}

function saveToStorage(projectId: string, documentId: string, data: PersistedDocument): void {
  try {
    const key = compositeKey(projectId, documentId);
    localStorage.setItem(key, JSON.stringify(data));
    const index = getDocumentIndex();
    if (!index.includes(key)) {
      index.push(key);
      localStorage.setItem(INDEX_KEY, JSON.stringify(index));
    }
  } catch {
    // localStorage full — silently fail
  }
}

export function removeFromStorage(projectId: string, documentId: string): void {
  try {
    const key = compositeKey(projectId, documentId);
    localStorage.removeItem(key);
    const index = getDocumentIndex().filter((n) => n !== key);
    localStorage.setItem(INDEX_KEY, JSON.stringify(index));
  } catch {
    // ignore
  }
}

export function getDocumentIndex(): string[] {
  try {
    const raw = localStorage.getItem(INDEX_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

/* ── Pending server-side deletions (issue #282) ──────────────────────────
 * A measurement deleted in the viewer must also be deleted on the server,
 * but the delete is debounced (it batches with the create/update sync). Until
 * it has been applied we remember the deleted ``serverId``s so that:
 *   - the next load does NOT resurrect a row we are about to delete, and
 *   - a reload BEFORE the debounced delete fired still removes it on the
 *     next sync (the set is persisted per document, keyed off the local key).
 * Stored under ``<localKey>__pending_deletes`` as a JSON array of serverIds.
 */
function pendingDeletesKey(localKey: string): string {
  return `${localKey}__pending_deletes`;
}

function readPendingDeletes(localKey: string | null): string[] {
  if (!localKey) return [];
  try {
    const raw = localStorage.getItem(pendingDeletesKey(localKey));
    if (!raw) return [];
    const arr = JSON.parse(raw) as unknown;
    return Array.isArray(arr) ? (arr.filter((x) => typeof x === 'string') as string[]) : [];
  } catch {
    return [];
  }
}

function writePendingDeletes(localKey: string | null, ids: Set<string>): void {
  if (!localKey) return;
  try {
    const key = pendingDeletesKey(localKey);
    if (ids.size === 0) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(Array.from(ids)));
  } catch {
    // localStorage full / unavailable - the in-memory ref still drives the
    // delete this session; only the cross-reload guarantee is lost.
  }
}

/* ── Unit canonicalization ───────────────────────────────────────────── */

/**
 * Map the display-glyph unit the viewer emits (`m²` / `m³` via the
 * superscript U+00B2 / U+00B3) to the canonical BOQ unit string
 * (`m2` / `m3`).
 *
 * Even though the backend now accepts the superscript form verbatim
 * (D-TKC-001 backend pairing), cross-module quantity sync — bim_hub
 * `_sync_boq_quantity_from_links`, BOQ linking, the catalogue/cost
 * matchers — keys on the canonical `m`/`m2`/`m3`/`pcs` vocabulary.
 * Persisting the canonical form keeps the server copy aligned with the
 * Export-to-BOQ / link-to-position paths (which already canonicalize),
 * and {@link displayUnit} restores the glyph on round-trip so the UI is
 * unchanged.
 */
function canonicalUnit(unit: string): string {
  switch (unit) {
    case 'm²':
      return 'm2';
    case 'm³':
      return 'm3';
    default:
      return unit || 'm';
  }
}

/** Inverse of {@link canonicalUnit}: restore the superscript display
 *  glyph from the canonical stored unit so a server round-trip renders
 *  identically to a freshly-drawn measurement. */
function displayUnit(unit: string): string {
  switch (unit) {
    case 'm2':
      return 'm²';
    case 'm3':
      return 'm³';
    default:
      return unit;
  }
}

/* ── Convert between frontend Measurement and backend API format ─────── */

function toApiFormat(
  m: Measurement,
  projectId: string,
  documentId: string,
  pageScales?: PageScales,
): MeasurementCreate {
  // Area measurements carry the polygon area in `m.value`; volume
  // measurements carry the area separately in `m.area`. Persist the
  // canonical dimension fields so bim_hub quantity sync / BOQ linking
  // can pick the right quantity instead of guessing from the unit
  // string alone (D-TKC-031).
  const areaValue =
    m.type === 'area' ? m.value : m.type === 'volume' ? (m.area ?? null) : null;
  // Per-page scale: send the scale of THIS measurement's page, not a single
  // document-wide ratio, so a sheet at 1:500 and a sheet at 1:50 each get
  // their own px-per-unit for the server-side B8 recompute.
  const scale = pageScales ? scaleForPage(pageScales, m.page) : undefined;
  const ppu =
    scale && scale.pixelsPerUnit > 0 ? scale.pixelsPerUnit : null;
  // Whether THIS measurement's page was explicitly calibrated by the user.
  // Persisted so a reload can tell a real per-sheet calibration apart from a
  // page still on the factory default - without it every measured page shows
  // a phantom "calibrated 1:N" badge after reload (issue #277).
  const scaleCalibrated = pageScales
    ? pageIsCalibrated(pageScales, m.page)
    : false;
  return {
    project_id: projectId,
    document_id: documentId,
    page: m.page,
    type: m.type,
    group_name: m.group || 'General',
    // Persist a colour ONLY when the user actually chose one (issue #299).
    // Injecting a default here used to make every reloaded measurement carry a
    // colour, which - now that the renderers honour `m.color` over the group
    // default - would wrongly override the group colour on a measurement the
    // user never recoloured.
    group_color: m.color || undefined,
    annotation: m.annotation || m.label || null,
    points: m.points,
    measurement_value: m.value || null,
    measurement_unit: canonicalUnit(m.unit),
    depth: m.depth ?? null,
    volume: m.type === 'volume' ? m.value : null,
    perimeter: m.type === 'polyline' ? m.value : null,
    count_value: m.type === 'count' ? Math.round(m.value) : null,
    // Send the calibration so the server-side recompute can verify the
    // client value against the raw geometry (Audit B8) instead of
    // trusting it blindly.
    scale_pixels_per_unit: ppu,
    // Opening deduction only applies to an area; the server enforces this
    // too but we keep the payload honest.
    is_deduction: m.type === 'area' ? Boolean(m.isDeduction) : false,
    linked_boq_position_id: m.linkedPositionId ?? null,
    metadata: {
      text: m.text,
      width: m.width,
      height: m.height,
      // Per-measurement appearance overrides (issues #311/#312/#332); round-trip
      // so a re-styled measurement survives a server sync.
      fill_alpha: m.fillAlpha,
      stroke_width: m.strokeWidth,
      // Real-world stroke width in canonical metres (issue #339); round-trips so a
      // true-width line survives a server sync and renders per each page's scale.
      stroke_width_real: m.strokeWidthReal,
      stroke_alpha: m.strokeAlpha,
      // Reported-quantity adjustments (issue #332 wave): slope / wastage /
      // typical-multiplier ride the metadata blob like the appearance overrides
      // so the effective quantity is reproduced after a server sync.
      slope_factor: m.slopeFactor,
      wastage_pct: m.wastagePct,
      multiplier: m.multiplier,
      // Group colour (issue #313): mirrored onto each measurement so the group
      // colour scheme round-trips server-side like the per-measurement styles.
      group_custom_color: m.groupColor,
      area: areaValue ?? undefined,
      frontend_id: m.id,
      // Per-page calibration intent (issue #277): distinguishes a real
      // calibration from a page left on the factory default on reload.
      scale_calibrated: scaleCalibrated,
      linked_boq_id: m.linkedBoqId,
      linked_position_ordinal: m.linkedPositionOrdinal,
      linked_position_label: m.linkedPositionLabel,
    },
  };
}

/**
 * Sync signature for a synced measurement (issue #282): every field an edit
 * can change that the server must hear about. When this string changes for a
 * row that already has a `serverId`, the row was edited and must be PATCHed.
 *
 * It deliberately covers BOTH the geometry-bearing fields that feed the
 * server-side recompute (Audit B8) AND the non-geometry properties (group,
 * colour, annotation/label, notes) that used to be state-only and never
 * persisted. {@link toApiUpdate} PATCHes the same union of fields, so a
 * change to any of them re-syncs the server copy.
 */
function syncSignature(m: Measurement): string {
  return JSON.stringify({
    // Geometry / quantity-bearing fields (server recomputes the value).
    p: m.points,
    d: m.depth ?? null,
    c: m.type === 'count' ? Math.round(m.value) : null,
    t: m.type,
    // The deduction flag flips a measurement between gross and void without
    // changing its geometry; include it so toggling it triggers a PATCH and
    // the server row stays in sync.
    x: m.type === 'area' ? Boolean(m.isDeduction) : false,
    // Non-geometry properties (issue #282): these never moved the billed
    // quantity, so the old geometry-only signature ignored them and they
    // never reached the server. They are now part of the signature so a
    // group / colour / annotation / notes edit re-syncs.
    g: m.group || 'General',
    col: m.color || '#3B82F6',
    // Appearance overrides (issues #311/#312/#332): an opacity or stroke-width
    // edit must re-sync so the server copy carries it.
    fa: m.fillAlpha ?? null,
    sw: m.strokeWidth ?? null,
    // Real-world stroke width (issue #339): a true-width edit is appearance-only
    // (no geometry move), so include it here or the PATCH would never fire.
    swr: m.strokeWidthReal ?? null,
    sa: m.strokeAlpha ?? null,
    // Reported-quantity adjustments (issue #332 wave): a slope / wastage /
    // multiplier edit changes the reported quantity, so it must re-sync.
    sf: m.slopeFactor ?? null,
    wp: m.wastagePct ?? null,
    mul: m.multiplier ?? null,
    // Group colour (issue #313): a group re-colour restyles every measurement
    // in the group, so include it here to trigger the PATCH that persists it.
    gc: m.groupColor ?? null,
    a: m.annotation || m.label || null,
    n: m.text ?? null,
  });
}

/**
 * Geometry-only signature (issue #334): just the fields that feed the
 * server-side value / volume / perimeter recompute (points, depth, count,
 * type). When this is unchanged for a synced row, an edit touched only
 * non-geometry properties (colour / label / opacity / group), so the PATCH must
 * NOT re-send the page scale or the ``scale_calibrated`` flag - re-stamping the
 * live view scale onto a row the user only recoloured is exactly how a real
 * calibration used to get wiped.
 */
function geometrySignature(m: Measurement): string {
  return JSON.stringify({
    p: m.points,
    d: m.depth ?? null,
    c: m.type === 'count' ? Math.round(m.value) : null,
    t: m.type,
  });
}

/** Build the PATCH body for a synced measurement (issue #282). Carries the
 *  geometry-bearing fields (the server recomputes `measurement_value` /
 *  `volume` / `perimeter` from these, so a client cannot inflate a quantity
 *  through this path) PLUS the non-geometry properties (group, colour,
 *  annotation/label, notes) that must now persist on an in-place edit.
 *
 *  ``metadata`` is sent merged: the server replaces the metadata blob
 *  wholesale, so we re-send the same fields {@link toApiFormat} writes on
 *  create (notes/dimensions/calibration intent/BOQ link mirror) to avoid
 *  dropping them on an annotation-only edit. */
function toApiUpdate(
  m: Measurement,
  scale?: ScaleConfig,
  scaleCalibrated = false,
  geometryChanged = true,
): Partial<MeasurementCreate> {
  const ppu = scale && scale.pixelsPerUnit > 0 ? scale.pixelsPerUnit : null;
  const areaValue =
    m.type === 'area' ? m.value : m.type === 'volume' ? (m.area ?? null) : null;
  const metadata: Record<string, unknown> = {
    text: m.text,
    width: m.width,
    height: m.height,
    // Per-measurement appearance overrides (issues #311/#312/#332); re-sent on
    // PATCH because the server replaces the metadata blob wholesale.
    fill_alpha: m.fillAlpha,
    stroke_width: m.strokeWidth,
    // Real-world stroke width in canonical metres (issue #339); re-sent on PATCH
    // because the server replaces the metadata blob wholesale.
    stroke_width_real: m.strokeWidthReal,
    stroke_alpha: m.strokeAlpha,
    // Reported-quantity adjustments (issue #332 wave); re-sent on PATCH for
    // the same reason (the server replaces the metadata blob wholesale).
    slope_factor: m.slopeFactor,
    wastage_pct: m.wastagePct,
    multiplier: m.multiplier,
    // Group colour (issue #313): re-sent on PATCH so a group re-colour /
    // rename persists server-side (the server replaces metadata wholesale).
    group_custom_color: m.groupColor,
    area: areaValue ?? undefined,
    frontend_id: m.id,
    linked_boq_id: m.linkedBoqId,
    linked_position_ordinal: m.linkedPositionOrdinal,
    linked_position_label: m.linkedPositionLabel,
  };
  // Always-safe, non-geometry properties (issue #282). These never move the
  // billed quantity and never touch the page scale.
  const body: Partial<MeasurementCreate> = {
    group_name: m.group || 'General',
    // Only persist a user-chosen colour (issue #299); see toApiFormat.
    group_color: m.color || undefined,
    annotation: m.annotation || m.label || null,
    linked_boq_position_id: m.linkedPositionId ?? null,
    is_deduction: m.type === 'area' ? Boolean(m.isDeduction) : false,
    metadata,
  };
  // Geometry-bearing fields + the page-scale stamp are sent ONLY when the
  // geometry actually moved (issue #334). On a pure colour / label / opacity
  // edit we omit them so the PATCH cannot rewrite ``scale_pixels_per_unit`` /
  // ``scale_calibrated`` (which used to wipe a real calibration by stamping the
  // live view scale) or trigger a needless server-side value recompute. The
  // calibration itself now lives at the document level, so the per-measurement
  // stamp is capture provenance only.
  if (geometryChanged) {
    body.points = m.points;
    body.type = m.type;
    body.depth = m.depth ?? null;
    body.count_value = m.type === 'count' ? Math.round(m.value) : null;
    body.scale_pixels_per_unit = ppu;
    // Per-page calibration intent (issue #277): re-sent with the geometry so a
    // reshape keeps the row's calibration provenance, but never on a
    // non-geometry edit (the server merges metadata, so omitting it preserves
    // the stored flag instead of overwriting it).
    metadata.scale_calibrated = scaleCalibrated;
  }
  return body;
}

function fromApiFormat(r: MeasurementResponse): Measurement {
  const meta = r.metadata || {};
  return {
    id: (meta.frontend_id as string) || r.id,
    serverId: r.id,
    type: r.type as Measurement['type'],
    points: r.points as Point[],
    value: r.measurement_value ?? r.count_value ?? 0,
    unit: displayUnit(r.measurement_unit),
    label: r.annotation || '',
    annotation: r.annotation || '',
    page: r.page,
    group: r.group_name,
    depth: r.depth ?? undefined,
    // Prefer the dedicated metadata.area; fall back to the canonical
    // server `volume`/`measurement_value` so an area survives even when
    // it was persisted before the dedicated field existed (D-TKC-031).
    area:
      (meta.area as number) ??
      (r.type === 'area' ? r.measurement_value ?? undefined : undefined),
    text: (meta.text as string) ?? undefined,
    color: r.group_color || undefined,
    width: (meta.width as number) ?? undefined,
    height: (meta.height as number) ?? undefined,
    fillAlpha: (meta.fill_alpha as number) ?? undefined,
    strokeWidth: (meta.stroke_width as number) ?? undefined,
    strokeWidthReal: (meta.stroke_width_real as number) ?? undefined,
    strokeAlpha: (meta.stroke_alpha as number) ?? undefined,
    slopeFactor: (meta.slope_factor as number) ?? undefined,
    wastagePct: (meta.wastage_pct as number) ?? undefined,
    multiplier: (meta.multiplier as number) ?? undefined,
    groupColor: (meta.group_custom_color as string) ?? undefined,
    isDeduction: r.is_deduction ?? undefined,
    linkedPositionId: r.linked_boq_position_id ?? undefined,
    linkedBoqId: (meta.linked_boq_id as string) ?? undefined,
    linkedPositionOrdinal: (meta.linked_position_ordinal as string) ?? undefined,
    linkedPositionLabel: (meta.linked_position_label as string) ?? undefined,
  };
}

/**
 * Reconcile the server's measurements (the base) with the localStorage copy's
 * locally-pending work (issue #281/#282).
 *
 * Merge rule (kept deliberately simple so it is auditable):
 *   - Server rows are the base, keyed by ``serverId``.
 *   - A local row WITHOUT a ``serverId`` is an unsynced create -> appended.
 *   - A local row WITH a ``serverId`` that also exists on the server is an
 *     edit that may not have synced yet. We prefer the LOCAL copy (it is at
 *     least as new as the server's) but keep the server's ``serverId``. The
 *     load effect seeds the sync baseline from the SERVER signature, so if the
 *     local copy differs it is re-PATCHed on the next tick - never lost.
 *   - A local row whose ``serverId`` is no longer on the server was deleted
 *     elsewhere; we drop it (the server is authoritative on existence).
 *
 * When there is no local copy we just return the server rows unchanged.
 */
function reconcileWithLocal(
  serverRows: Measurement[],
  localRows: Measurement[] | undefined,
): Measurement[] {
  if (!localRows || localRows.length === 0) return serverRows;
  const serverById = new Map(
    serverRows.filter((m) => m.serverId).map((m) => [m.serverId as string, m]),
  );
  // Start from the server rows, swapping in the local copy for any synced row
  // the user edited locally (prefer local, keep the serverId).
  const merged = serverRows.map((srv) => {
    if (!srv.serverId) return srv;
    const localEdit = localRows.find((l) => l.serverId === srv.serverId);
    return localEdit ? { ...localEdit, serverId: srv.serverId } : srv;
  });
  // Append unsynced local creates (no serverId, and not already represented).
  for (const l of localRows) {
    if (l.serverId) continue; // handled above (or deleted server-side)
    if (merged.some((m) => m.id === l.id)) continue;
    merged.push(l);
  }
  // Defensive: a local row pointing at a serverId the server no longer returns
  // was deleted elsewhere - it is simply not added back (serverById guards the
  // edit branch above).
  void serverById;
  return merged;
}

/**
 * Reconstruct a {@link PageScales} from server measurements.
 *
 * Each row carries the ``scale_pixels_per_unit`` of the page it was drawn on
 * plus a ``metadata.scale_calibrated`` flag recording whether the user
 * actually calibrated that sheet. We restore a page's scale ONLY when it was
 * genuinely calibrated, so a page still on the factory default never comes
 * back wearing a phantom "calibrated 1:N" badge (issue #277). Rows written
 * before the flag existed carry no field: those are inferred from the ratio
 * (the factory default is exactly 100 px/unit, so a legacy row still at 100
 * was uncalibrated, while any other ratio is a real calibration) - that keeps
 * an existing per-sheet calibration without resurrecting the phantom badge.
 *
 * Returns ``null`` when nothing was calibrated, so the caller keeps its own
 * (default) state and every page correctly reads "not calibrated". This
 * restores per-page calibration for a project opened on a device that has no
 * localStorage copy.
 */
function pageScalesFromServer(rows: MeasurementResponse[]): PageScales | null {
  const byPage: Record<number, ScaleConfig> = {};
  let sawCalibratedPage = false;
  for (const r of rows) {
    const ppu = r.scale_pixels_per_unit;
    if (typeof ppu !== 'number' || !Number.isFinite(ppu) || ppu <= 0) continue;
    const flag = (r.metadata as Record<string, unknown> | null | undefined)
      ?.scale_calibrated;
    // Explicit flag wins; a legacy row without one is calibrated unless it is
    // still sitting on the exact factory-default ratio (100 px/unit).
    const calibrated =
      flag === true ? true : flag === false ? false : ppu !== 100;
    if (calibrated) {
      // Scale is metric-canonical (always metres); only the ratio differs.
      byPage[r.page] = { pixelsPerUnit: ppu, unitLabel: 'm' };
      sawCalibratedPage = true;
    }
  }
  if (!sawCalibratedPage) return null;
  return { defaultScale: defaultScaleConfig(), byPage };
}

/* ── Hook ─────────────────────────────────────────────────────────────── */

interface UseMeasurementPersistenceOptions {
  /** Display-only filename. Used for the legacy-key migration on load and
   *  for the unsaved-changes UX; NEVER used as a storage or server key. */
  fileName: string | null;
  /** Stable document UUID (issue #238). Measurement identity is
   *  ``projectId`` + this id. ``null`` when no server document exists yet
   *  (a freshly dropped local file) - in that state we persist locally only
   *  and do NOT sync to the server. */
  documentId: string | null;
  measurements: Measurement[];
  setMeasurements: (measurements: Measurement[]) => void;
  /** Per-page (per-sheet) scale model. Persisted whole; a legacy
   *  single-scale document is migrated into the default on load. */
  pageScales: PageScales;
  setPageScales: (pageScales: PageScales) => void;
  /** The current page's effective scale, sent as ``scale_pixels_per_unit``
   *  on measurements so the server B8 recompute uses the same ratio.
   *  (Per-measurement page scale is resolved from ``pageScales``.) */
  scale: ScaleConfig;
  /** Active project ID for backend sync. */
  projectId?: string | null;
}

interface UseMeasurementPersistenceResult {
  hasPersistedData: boolean;
  saveNow: () => void;
  clearPersisted: () => void;
  savedDocumentCount: number;
  /** Whether data is being synced to the server. */
  syncing: boolean;
  /** Whether server sync has been done at least once. */
  syncedToServer: boolean;
  /**
   * Record that a measurement was deleted in the viewer so the server copy
   * is removed too (issue #282). Pass the deleted measurement's ``serverId``
   * if it had one (the row exists on the server -> schedule a DELETE) or
   * ``undefined`` for a never-synced row (nothing to do server-side). The
   * caller still removes it from React state; this only handles the server +
   * the resurrection guard. Safe to call for clear-all (one call per row).
   */
  registerDeletion: (serverId: string | undefined) => void;
  /**
   * Live check (issue #336) for whether any local-or-server write is still
   * pending: the debounced local-write / server-sync / edit-PATCH timers, the
   * document page-scale PUT, the in-flight PATCH set, or the queued server
   * deletes. A stable callback that reads the refs at call time so a
   * beforeunload handler can gate its "leave site?" prompt on genuinely unsaved
   * work instead of firing on every navigation.
   */
  hasUnsavedChanges: () => boolean;
}

export function useMeasurementPersistence({
  fileName,
  documentId,
  measurements,
  setMeasurements,
  pageScales,
  setPageScales,
  scale,
  projectId,
}: UseMeasurementPersistenceOptions): UseMeasurementPersistenceResult {
  // Server identity (issue #238): both a project AND a stable document UUID
  // must be present before we touch the server or use the composite local
  // key. Filename alone never qualifies.
  const canSync = Boolean(projectId && documentId);
  // Local-storage key. With a server UUID this is the project+document
  // composite (shared with the server-load path). A freshly dropped local
  // file has no UUID yet, so it gets a stable local-only key derived from
  // its filename - persisted locally, never synced - which migrates into
  // the composite key once a real UUID arrives.
  const localKey =
    projectId && documentId
      ? compositeKey(projectId, documentId)
      : fileName
        ? `${STORAGE_PREFIX}local__${fileName.replace(/[^a-zA-Z0-9._-]/g, '_')}`
        : null;
  // Identity used to detect when a *different* document is opened (so the
  // load effect re-runs). Filename is included so two unsynced local drops
  // with different names don't share a load.
  const identity = `${projectId ?? ''}|${documentId ?? ''}|${fileName ?? ''}`;

  const hasPersistedRef = useRef(false);
  const lastIdentityRef = useRef<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncedToServer, setSyncedToServer] = useState(false);
  const serverSyncRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Edit-PATCH tracking (#194 Feature 1, broadened for #282). `syncSigRef`
  // remembers the last full sync-signature we know the server has for each
  // `serverId` (geometry AND non-geometry props), so we only PATCH a row that
  // actually changed. `patchTimerRef` debounces and `inFlightPatchRef`
  // coalesces rapid edits of the same row (last-write-wins) so mid-drag churn
  // never floods the network.
  const syncSigRef = useRef<Map<string, string>>(new Map());
  // Geometry-only signature per serverId (issue #334). A PATCH re-stamps a
  // row's ``scale_pixels_per_unit`` / calibration flag - and triggers the
  // server-side value recompute - ONLY when the geometry actually moved. This
  // baseline lets the edit-PATCH effect tell a geometry reshape from a pure
  // colour / label / opacity edit so the latter never rewrites a calibration.
  const geomSigRef = useRef<Map<string, string>>(new Map());
  const patchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightPatchRef = useRef<Set<string>>(new Set());
  // Pending server-side deletions (issue #282): serverIds of rows deleted in
  // the viewer whose DELETE has not yet been applied. Seeded from localStorage
  // on the load effect so a reload before the debounced delete fired still
  // removes the row. Doubles as the load-reconciliation guard (a server row
  // whose id is in here is dropped instead of resurrected).
  const pendingDeletesRef = useRef<Set<string>>(new Set());
  // Document-level page-scale persistence (issue #334). ``pageScalesSyncRef``
  // holds the last serialisation we believe the server has, so a genuine
  // recalibration PATCHes the document once while a no-op re-render does not.
  // ``pageScalesPutTimerRef`` debounces that PUT. ``prevCanSyncRef`` catches a
  // local drop gaining a server UUID so a calibration made before sync is
  // persisted once the document becomes syncable.
  const pageScalesSyncRef = useRef<string | null>(null);
  const pageScalesPutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevCanSyncRef = useRef(false);
  // Read the QueryClient directly from context — ``useContext`` returns
  // ``undefined`` instead of throwing when the provider is absent (e.g. in
  // unit tests that render the hook in isolation). When present, we use
  // it to broadcast a refresh to the unified Markups hub.
  const qc = useContext(QueryClientContext);

  // Keep the latest setters in refs so the load effect can depend ONLY on the
  // document ``identity`` (issue #276). A caller may pass an inline-arrow
  // setter whose identity changes on every render; if such a setter sat in the
  // load effect's dependency array, a re-render WHILE the initial server fetch
  // was still in flight tore the effect down (cancelled = true) and the
  // resolved measurements were silently dropped - the saved takeoff failed to
  // reappear on reload.
  const setMeasurementsRef = useRef(setMeasurements);
  setMeasurementsRef.current = setMeasurements;
  const setPageScalesRef = useRef(setPageScales);
  setPageScalesRef.current = setPageScales;

  // Latest-value refs (issue #281/#282). The teardown flush and registerDeletion
  // run from event handlers / cleanup where a stale closure would persist the
  // wrong document's state. These mirror the current render's values so a flush
  // always writes the latest measurements under the latest key. Kept in sync on
  // every render (cheap; refs do not trigger re-renders).
  const measurementsRef = useRef(measurements);
  measurementsRef.current = measurements;
  const pageScalesRef = useRef(pageScales);
  pageScalesRef.current = pageScales;
  const scaleRef = useRef(scale);
  scaleRef.current = scale;
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const documentIdRef = useRef(documentId);
  documentIdRef.current = documentId;
  const localKeyRef = useRef(localKey);
  localKeyRef.current = localKey;
  const canSyncRef = useRef(canSync);
  canSyncRef.current = canSync;

  // Load persisted data when the document identity changes — try server
  // first (keyed by the stable document UUID, issue #238), fallback to
  // localStorage.
  //
  // Load reconciliation (issue #281/#282): the server copy is the BASE, but
  // it is never trusted blindly. We:
  //   1. drop any server row whose serverId is in the persisted pending-delete
  //      set, so a locally-deleted row never resurrects, and
  //   2. overlay the localStorage copy's locally-pending work on top - rows
  //      that have no serverId yet (unsynced creates) and edits to a synced
  //      row that the local copy made more recently than the last sync.
  // The merge keys on serverId for synced rows and on the frontend id for
  // unsynced ones, so local edits/creates survive a reload even when the
  // server has not caught up yet.
  useEffect(() => {
    if (!fileName || identity === lastIdentityRef.current) return;
    lastIdentityRef.current = identity;

    // Seed pending deletions for THIS document from localStorage so a reload
    // before the debounced DELETE fired still removes the row (and the load
    // below does not resurrect it).
    pendingDeletesRef.current = new Set(readPendingDeletes(localKey));

    let cancelled = false;

    async function loadData() {
      // The localStorage copy for this document, if any. Used both as the
      // offline fallback and as the source of local-pending overlay edits.
      const local = localKey ? readKey(localKey) : null;

      // Try server first, but only with BOTH a project and a stable document
      // UUID. Filename is never sent as the document key any more.
      if (canSync && projectId && documentId) {
        try {
          // Fetch the measurements AND the document in parallel: the document
          // carries the authoritative per-page calibration (issue #334). A
          // failed document fetch degrades to the legacy per-measurement stamps.
          const [serverData, doc] = await Promise.all([
            takeoffApi.list(projectId, documentId),
            takeoffApi.getDocument(documentId).catch(() => null),
          ]);
          if (!cancelled && serverData.length > 0) {
            hasPersistedRef.current = true;
            setSyncedToServer(true);
            // Drop rows we have locally deleted but not yet synced (#282).
            const pending = pendingDeletesRef.current;
            const mapped = serverData
              .map(fromApiFormat)
              .filter((m) => !(m.serverId && pending.has(m.serverId)));

            // Overlay local-pending work (#281/#282): start from the server
            // rows, then apply the localStorage copy's unsynced creates and
            // any locally-newer edits to a synced row.
            const merged = reconcileWithLocal(mapped, local?.measurements);

            // Seed the sync baseline from the SERVER copy of each synced row
            // (not the merged copy), so a locally-newer edit still looks dirty
            // and re-PATCHes on the next tick rather than being lost (#282).
            syncSigRef.current = new Map(
              mapped
                .filter((m) => m.serverId)
                .map((m) => [m.serverId as string, syncSignature(m)]),
            );
            // Geometry baseline (#334): remember each row's geometry so a later
            // pure-appearance edit does NOT re-stamp its page scale.
            geomSigRef.current = new Map(
              mapped
                .filter((m) => m.serverId)
                .map((m) => [m.serverId as string, geometrySignature(m)]),
            );
            // Restore the per-page calibration (issue #334). The DOCUMENT
            // page_scales column is the authoritative source; a document saved
            // before that column existed falls back to the per-measurement
            // scale stamps. Reconcile with the localStorage copy so a real
            // calibration on either side survives while a stale local DEFAULT
            // never overrides an explicit server one.
            const serverScales = doc?.page_scales
              ? hydratePageScales(doc.page_scales, null)
              : pageScalesFromServer(serverData);
            const localScales =
              local?.pageScales || local?.scale
                ? hydratePageScales(local.pageScales, local.scale)
                : null;
            const chosen = reconcilePageScales(localScales, serverScales);
            if (chosen) setPageScalesRef.current(chosen);
            setMeasurementsRef.current(merged);
            return;
          }
        } catch {
          // Server unavailable — fall through to localStorage
        }
      }

      // Fallback to localStorage (the composite project+document key, or the
      // local-only key for an unsynced fresh drop).
      if (!cancelled) {
        let data = local;
        // Back-compat (issue #238): nothing under the new composite key yet?
        // A user upgrading from a filename-keyed build still has their
        // measurements under ``oe_takeoff_<filename>``. Read it once and
        // rewrite it under the composite key so they don't lose local work.
        // Read-only on the legacy key (a downgrade still finds it).
        if (!data && projectId && documentId) {
          const legacy = loadLegacyFromStorage(fileName);
          if (legacy) {
            data = legacy;
            saveToStorage(projectId, documentId, legacy);
          }
        }
        if (data) {
          hasPersistedRef.current = true;
          // Even with no server rows, honour a pending delete: a row deleted
          // offline must not reappear from the localStorage copy either.
          const pending = pendingDeletesRef.current;
          const rows = pending.size
            ? data.measurements.filter((m) => !(m.serverId && pending.has(m.serverId)))
            : data.measurements;
          // Seed the sync baseline so a localStorage-loaded synced row does
          // not immediately re-PATCH on mount (its signature is known).
          syncSigRef.current = new Map(
            rows
              .filter((m) => m.serverId)
              .map((m) => [m.serverId as string, syncSignature(m)]),
          );
          // Geometry baseline (#334) alongside the full one.
          geomSigRef.current = new Map(
            rows
              .filter((m) => m.serverId)
              .map((m) => [m.serverId as string, geometrySignature(m)]),
          );
          setMeasurementsRef.current(rows);
          // Graceful migration: a document saved before per-page scale only
          // carried ``data.scale``; hydratePageScales promotes it to the
          // document default so every page reads the same number it always
          // did until the user re-calibrates an individual sheet.
          setPageScalesRef.current(hydratePageScales(data.pageScales, data.scale));
        } else {
          hasPersistedRef.current = false;
        }
      }
    }

    loadData();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity]);

  // Synchronous localStorage write of the LATEST state (issue #281). Shared by
  // the debounced auto-save, the manual ``saveNow`` button, and the teardown
  // flush so leaving a document always persists its latest measurements under
  // the right key. Reads refs (not the render closure) so a flush fired from a
  // cleanup writes the correct document. Never persists AI suggestions.
  const writeLocalNow = useCallback(() => {
    const key = localKeyRef.current;
    if (!key) return;
    const projectIdNow = projectIdRef.current;
    const documentIdNow = documentIdRef.current;
    // Persist BOTH the new per-page model and the legacy single ``scale`` (the
    // current page's, as a best-effort default) so a downgrade to an older
    // build that only reads ``scale`` still finds a usable value.
    const payload: PersistedDocument = {
      measurements: measurementsRef.current.filter((m) => !m.suggested),
      pageScales: pageScalesRef.current,
      scale: scaleRef.current,
      savedAt: Date.now(),
    };
    if (projectIdNow && documentIdNow) {
      saveToStorage(projectIdNow, documentIdNow, payload);
    } else {
      // Local-only key (fresh drop, no server UUID yet) - written directly and
      // not added to the document index (it isn't a synced document).
      try {
        localStorage.setItem(key, JSON.stringify(payload));
      } catch {
        // localStorage full — silently fail
      }
    }
  }, []);

  // Auto-save to localStorage with debounce (500ms). Keyed by the stable
  // project+document composite (issue #238), or a local-only key for an
  // unsynced fresh drop.
  useEffect(() => {
    if (!localKey) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      // Debounce fired: the latest state is now in localStorage, so the local
      // write is no longer pending (issue #336).
      debounceRef.current = null;
      writeLocalNow();
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [localKey, projectId, documentId, measurements, pageScales, scale, writeLocalNow]);

  // Apply pending server-side deletions (issue #282). A row is deleted on the
  // server ONLY when its serverId is still in the pending set AND it is no
  // longer present in ``measurements`` - so an undo that restored the deleted
  // measurement (it reappears in state with its serverId) cancels the delete
  // instead of orphaning the row. On success we clear it from the pending set
  // (+ localStorage mirror); on failure we leave it so the next pass retries.
  const applyPendingDeletes = useCallback(
    async (current: Measurement[]): Promise<boolean> => {
      const pending = pendingDeletesRef.current;
      if (pending.size === 0) return false;
      const liveServerIds = new Set(
        current.filter((m) => m.serverId).map((m) => m.serverId as string),
      );
      let changed = false;
      await Promise.all(
        Array.from(pending).map(async (serverId) => {
          // Undo brought it back -> cancel the delete.
          if (liveServerIds.has(serverId)) {
            pending.delete(serverId);
            changed = true;
            return;
          }
          try {
            await takeoffApi.delete(serverId);
            pending.delete(serverId);
            syncSigRef.current.delete(serverId);
            changed = true;
          } catch {
            // Leave it pending; the next sync pass retries.
          }
        }),
      );
      if (changed) writePendingDeletes(localKeyRef.current, pending);
      return changed;
    },
    [],
  );

  // The actual create + delete sync, callable from both the debounced effect
  // and the teardown flush. Reads the latest state via refs so a flush during
  // unmount writes the right document's rows. Returns nothing; updates state
  // (serverId stamps), the sync baseline, and the pending-delete set.
  const runServerSync = useCallback(async () => {
    const projectIdNow = projectIdRef.current;
    const documentIdNow = documentIdRef.current;
    if (!canSyncRef.current || !projectIdNow || !documentIdNow) return;
    const current = measurementsRef.current;
    const pageScalesNow = pageScalesRef.current;

    setSyncing(true);
    try {
      // Creates and deletes act on disjoint rows, so dispatch BOTH up front
      // (their network calls are invoked synchronously here) and await them
      // together. Invoking the create synchronously matters: callers that
      // advance a debounce inside a synchronous tick expect bulkCreate to have
      // been called by the time control returns.
      const deletePromise = applyPendingDeletes(current);

      const toCreate = current
        // Suggested-but-unconfirmed measurements are excluded; accepting a
        // suggestion clears `suggested` and the next tick syncs it (#194).
        .filter((m) => !m.serverId && !m.suggested)
        // Per-page scale: toApiFormat resolves each row's own page scale
        // from pageScales, so a multi-sheet set syncs correct ratios. The
        // document_id sent is the stable UUID, never the filename (#238).
        .map((m) => toApiFormat(m, projectIdNow, documentIdNow, pageScalesNow));
      const createPromise =
        toCreate.length > 0 ? takeoffApi.bulkCreate(toCreate) : null;

      await deletePromise;

      if (createPromise) {
        const created = await createPromise;
        // Update serverId on created measurements (map over the LATEST state).
        setMeasurementsRef.current(
          measurementsRef.current.map((m) => {
            if (m.serverId) return m;
            const match = created.find(
              (c) => (c.metadata?.frontend_id as string) === m.id,
            );
            if (!match) return m;
            // Seed the sync baseline for the freshly-synced row so a later
            // edit PATCHes, but a no-op tick does not (#194/#282). Seed the
            // geometry baseline too (#334) so the first appearance-only edit
            // after a create does not re-stamp the page scale.
            syncSigRef.current.set(match.id, syncSignature(m));
            geomSigRef.current.set(match.id, geometrySignature(m));
            return { ...m, serverId: match.id };
          }),
        );
        // Surface the new measurements in the unified Markups hub.
        qc?.invalidateQueries({ queryKey: ['unified-markups'] });
      }
      setSyncedToServer(true);
    } catch {
      // Server sync failed — data safe in localStorage
    } finally {
      setSyncing(false);
    }
  }, [applyPendingDeletes, qc]);

  // Auto-sync to server with debounce (3s). Both measurement and annotation
  // types persist now (v2.6.7) — backend schema accepts the full set.
  // Gated on a stable document UUID + project (issue #238): a filename alone
  // never triggers server sync, so an unsynced local drop stays local-only.
  // Runs even with zero measurements so a clear-all's pending deletions are
  // applied (the create pass is then a no-op).
  useEffect(() => {
    if (!canSync || !projectId || !documentId) return;
    const hasCreates = measurements.some((m) => !m.serverId && !m.suggested);
    if (!hasCreates && pendingDeletesRef.current.size === 0) return;

    if (serverSyncRef.current) clearTimeout(serverSyncRef.current);
    serverSyncRef.current = setTimeout(() => {
      // Debounce fired: no longer pending (issue #336). The in-flight network
      // phase is tracked separately (syncing + the PATCH/delete refs).
      serverSyncRef.current = null;
      void runServerSync();
    }, 3000);

    return () => {
      if (serverSyncRef.current) clearTimeout(serverSyncRef.current);
    };
  }, [canSync, projectId, documentId, measurements, runServerSync]);

  // Edit PATCH (#194 Feature 1, broadened for #282). When a measurement that
  // already has a `serverId` is edited - geometry reshaped in-canvas (Audit
  // B8) OR a non-geometry property changed (group / colour / annotation /
  // notes) - PATCH just that row so the server stays in sync. The dirty check
  // keys on {@link syncSignature}, which now spans both, so a colour or label
  // change is caught where the old geometry-only signature missed it.
  // Debounced 400ms off the last change; mid-drag churn never reaches the
  // network because the viewer only commits points on mouseup. Coalesced per
  // `serverId`: if a row is already in-flight we skip it this tick and the
  // changed signature keeps it dirty for the next pass (last-write-wins per
  // row). Gated on canSync (#238): a serverId only exists after a sync, but
  // gate explicitly so a stale row can't PATCH once the document id is gone.
  useEffect(() => {
    if (!canSync) return;
    if (measurements.length === 0) return;

    // Find synced rows whose sync-signature drifted from the server baseline.
    const dirty = measurements.filter((m) => {
      if (!m.serverId || m.suggested) return false;
      const prevSig = syncSigRef.current.get(m.serverId);
      // No baseline yet (e.g. a row hydrated before its baseline seeded)
      // -> record the current signature without firing a PATCH.
      if (prevSig === undefined) {
        syncSigRef.current.set(m.serverId, syncSignature(m));
        geomSigRef.current.set(m.serverId, geometrySignature(m));
        return false;
      }
      return prevSig !== syncSignature(m);
    });
    if (dirty.length === 0) return;

    if (patchTimerRef.current) clearTimeout(patchTimerRef.current);
    patchTimerRef.current = setTimeout(async () => {
      // The debounce has fired: no longer pending (issue #336 unsaved-changes).
      patchTimerRef.current = null;
      const reconciled: { frontendId: string; value: number; area?: number }[] = [];
      await Promise.all(
        dirty.map(async (m) => {
          const serverId = m.serverId!;
          if (inFlightPatchRef.current.has(serverId)) return; // coalesce
          inFlightPatchRef.current.add(serverId);
          const sig = syncSignature(m);
          // Only re-stamp the page scale when the geometry actually moved
          // (issue #334); a pure colour / label / opacity edit leaves the
          // stored calibration untouched.
          const geometryChanged =
            geomSigRef.current.get(serverId) !== geometrySignature(m);
          try {
            // Per-page scale: on a geometry change, PATCH with the measurement's
            // own page scale so the server B8 recompute uses the ratio that
            // sheet was drawn at, plus the page's calibration intent so the
            // metadata round-trips without resurrecting the #277 phantom badge.
            const updated = await takeoffApi.update(
              serverId,
              toApiUpdate(
                m,
                scaleForPage(pageScales, m.page),
                pageIsCalibrated(pageScales, m.page),
                geometryChanged,
              ),
            );
            // Mark this signature as known-on-server so we don't re-PATCH it.
            syncSigRef.current.set(serverId, sig);
            geomSigRef.current.set(serverId, geometrySignature(m));
            // Overwrite the optimistic value with the server-authoritative
            // recompute so the displayed quantity can never exceed what the
            // geometry justifies.
            const serverValue =
              updated.measurement_value ?? updated.volume ?? updated.count_value ?? m.value;
            reconciled.push({
              frontendId: m.id,
              value: serverValue,
              area: (updated.metadata?.area as number) ?? updated.measurement_value ?? undefined,
            });
          } catch {
            // PATCH failed - keep the optimistic value + the localStorage
            // copy (the 500ms effect above already persisted it). Leave the
            // signature stale so the next tick retries.
          } finally {
            inFlightPatchRef.current.delete(serverId);
          }
        }),
      );

      if (reconciled.length > 0) {
        setMeasurementsRef.current(
          measurementsRef.current.map((m) => {
            const r = reconciled.find((x) => x.frontendId === m.id);
            if (!r) return m;
            return {
              ...m,
              value: r.value,
              ...(m.type === 'volume' && r.area !== undefined ? { area: r.area } : {}),
            };
          }),
        );
        qc?.invalidateQueries({ queryKey: ['unified-markups'] });
      }
    }, 400);

    return () => {
      if (patchTimerRef.current) clearTimeout(patchTimerRef.current);
    };
  }, [canSync, projectId, documentId, measurements, pageScales, qc]);

  // A local drop that later gains a server UUID (canSync flips false -> true):
  // reset the page-scale baseline so a calibration made before the document was
  // syncable gets persisted to the new server document (issue #334). Defined
  // BEFORE the PUT effect so the reset lands before that effect re-evaluates.
  useEffect(() => {
    if (canSync && !prevCanSyncRef.current) {
      pageScalesSyncRef.current = null;
    }
    prevCanSyncRef.current = canSync;
  }, [canSync]);

  // Persist the per-page calibration to the DOCUMENT (issue #334). Calibration
  // is authoritative at the document level now (not a per-measurement echo), so
  // a reload / a second device restores the exact scales instead of losing them
  // or letting a stale local default win. Debounced. The first observed value
  // persists only when it already carries a real calibration (restored on load)
  // so an uncalibrated default never writes an empty scale; every later change
  // is a genuine recalibration and always persists.
  useEffect(() => {
    if (!canSync || !documentId) return;
    const sig = JSON.stringify(pageScales);
    const firstRun = pageScalesSyncRef.current === null;
    if (pageScalesSyncRef.current === sig) return;
    pageScalesSyncRef.current = sig;
    if (firstRun && !pageScalesHaveCalibration(pageScales)) return;
    if (pageScalesPutTimerRef.current) clearTimeout(pageScalesPutTimerRef.current);
    pageScalesPutTimerRef.current = setTimeout(() => {
      pageScalesPutTimerRef.current = null;
      void takeoffApi.saveDocumentScales(documentId, pageScales).catch(() => {
        // Offline / server down: the localStorage copy keeps the calibration
        // and the next load reconciles it back up.
      });
    }, 800);
    return () => {
      if (pageScalesPutTimerRef.current) clearTimeout(pageScalesPutTimerRef.current);
    };
  }, [canSync, documentId, pageScales]);

  // Manual save (the toolbar Save button). Persists locally now AND triggers
  // the server sync immediately rather than waiting out the 3s debounce, so a
  // deliberate Save reliably pushes creates/edits/deletes.
  const saveNow = useCallback(() => {
    writeLocalNow();
    void runServerSync();
  }, [writeLocalNow, runServerSync]);

  // Whether any local-or-server write is still pending (issue #336). ORs the
  // real pending sources - the debounced local-write + server-sync + edit-PATCH
  // timers, the document page-scale PUT, the in-flight PATCH set, and the queued
  // server deletes - so the "leave site?" prompt fires only when work is
  // genuinely unsaved, not on every navigation. A stable callback that reads the
  // refs live, so the beforeunload handler sees the freshest state at fire time
  // rather than a value snapshotted at render. Deliberately NOT derived from the
  // `syncing` boolean alone.
  const hasUnsavedChanges = useCallback(
    () =>
      debounceRef.current !== null ||
      serverSyncRef.current !== null ||
      patchTimerRef.current !== null ||
      pageScalesPutTimerRef.current !== null ||
      inFlightPatchRef.current.size > 0 ||
      pendingDeletesRef.current.size > 0,
    [],
  );

  /**
   * Record a viewer-side deletion (issue #282). For a synced row (has a
   * ``serverId``) we queue a server DELETE - persisted to localStorage so a
   * reload before the debounced sync still removes it, and tracked so the next
   * load does not resurrect it. The caller removes it from React state; the
   * debounced server-sync effect (or saveNow / the teardown flush) applies the
   * DELETE. A never-synced row has nothing on the server, so we only make sure
   * its localStorage copy is rewritten (handled by the auto-save effect when
   * state changes) - here it is a no-op.
   */
  const registerDeletion = useCallback((serverId: string | undefined) => {
    if (!serverId) return;
    pendingDeletesRef.current.add(serverId);
    writePendingDeletes(localKeyRef.current, pendingDeletesRef.current);
  }, []);

  const clearPersisted = useCallback(() => {
    if (projectId && documentId) {
      removeFromStorage(projectId, documentId);
    } else if (localKey) {
      try {
        localStorage.removeItem(localKey);
      } catch {
        // ignore
      }
    }
    hasPersistedRef.current = false;
  }, [projectId, documentId, localKey]);

  // Teardown flush (issue #281). All the debounced writes above only
  // clearTimeout on cleanup, so a measurement made just before leaving a
  // document used to be lost: SPA navigation never fires beforeunload, and the
  // viewer is remounted per-document (TakeoffPage keys it by document id), so
  // leaving a document unmounts this hook. The empty dependency array means
  // this cleanup runs ONLY on true unmount, at which point the refs still hold
  // the leaving-document's latest state. We flush it synchronously to
  // localStorage and kick a best-effort server sync (fire-and-forget; a
  // cleanup cannot await) so creates / edits / queued deletes are not stranded.
  // In-place identity changes (e.g. a local drop that later gains a server
  // UUID) keep the same measurements and are covered by the debounced
  // localStorage + server-sync effects above.
  useEffect(() => {
    return () => {
      writeLocalNow();
      void runServerSync();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    hasPersistedData: hasPersistedRef.current,
    saveNow,
    clearPersisted,
    savedDocumentCount: getDocumentIndex().length,
    syncing,
    syncedToServer,
    registerDeletion,
    hasUnsavedChanges,
  };
}
