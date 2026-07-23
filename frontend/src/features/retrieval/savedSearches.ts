// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Local persistence for Find Records history. Recent searches are the last few
// committed queries (auto-recorded), saved searches are ones the user pinned to
// re-run later. Both live in localStorage so they survive reloads without a new
// backend endpoint. The preferences store has no slot for these, so this small
// helper owns the read/write. Every function is pure and swallows storage
// errors (private mode / quota) so a failure here never breaks search.

import type { RetrievalQuery } from './types';

const RECENT_KEY = 'oce.retrieval.recent';
const SAVED_KEY = 'oce.retrieval.saved';
const RECENT_LIMIT = 8;
const SAVED_LIMIT = 30;

/** A search the user pinned, with a human label and the facets to re-run. */
export interface SavedSearch {
  id: string;
  label: string;
  query: RetrievalQuery;
}

/** True when a query carries at least one non-empty facet worth remembering. */
export function isMeaningfulQuery(q: RetrievalQuery): boolean {
  return Object.values(q).some((v) => typeof v === 'string' && v.trim() !== '');
}

/** A stable signature so the same facets are de-duplicated in history. */
export function querySignature(q: RetrievalQuery): string {
  return JSON.stringify({
    text: q.text?.trim() ?? '',
    party: q.party?.trim() ?? '',
    record_type: q.record_type?.trim() ?? '',
    date_from: q.date_from?.trim() ?? '',
    date_to: q.date_to?.trim() ?? '',
    entity: q.entity?.trim() ?? '',
  });
}

function readList<T>(key: string): T[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function writeList<T>(key: string, list: T[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(list));
  } catch {
    /* private mode / quota - non-fatal, history just does not persist */
  }
}

/* ── Recent searches ──────────────────────────────────────────────────── */

export function readRecent(): RetrievalQuery[] {
  return readList<RetrievalQuery>(RECENT_KEY);
}

/** Record a committed query at the front of history (most-recent-first),
 *  dropping an earlier copy of the same facets. Empty queries are ignored. */
export function pushRecent(q: RetrievalQuery): RetrievalQuery[] {
  if (!isMeaningfulQuery(q)) return readRecent();
  const sig = querySignature(q);
  const next = [q, ...readRecent().filter((r) => querySignature(r) !== sig)].slice(0, RECENT_LIMIT);
  writeList(RECENT_KEY, next);
  return next;
}

export function clearRecent(): RetrievalQuery[] {
  writeList<RetrievalQuery>(RECENT_KEY, []);
  return [];
}

/* ── Saved searches ───────────────────────────────────────────────────── */

export function readSaved(): SavedSearch[] {
  return readList<SavedSearch>(SAVED_KEY);
}

/** Pin a query under `label`, replacing an earlier save of the same facets. */
export function saveSearch(label: string, q: RetrievalQuery): SavedSearch[] {
  const sig = querySignature(q);
  const id = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  const entry: SavedSearch = { id, label, query: q };
  const next = [entry, ...readSaved().filter((s) => querySignature(s.query) !== sig)].slice(
    0,
    SAVED_LIMIT,
  );
  writeList(SAVED_KEY, next);
  return next;
}

export function removeSaved(id: string): SavedSearch[] {
  const next = readSaved().filter((s) => s.id !== id);
  writeList(SAVED_KEY, next);
  return next;
}
