// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Recent items store.
 *
 * Tracks the last few entities the user visited (projects, BOQs, RFIs, tasks, etc.)
 * so the sidebar can show a "Recent" section for quick re-access.
 *
 * Persists to localStorage under `oe_recent_items`.
 */

import { create } from 'zustand';

const STORAGE_KEY = 'oe_recent_items';
const MAX_ITEMS = 5;

export interface RecentItem {
  type: string; // 'project' | 'boq' | 'rfi' | 'task' | 'schedule' | 'contact' etc.
  id: string;
  title: string;
  url: string;
  visitedAt: number;
}

function readItems(): RecentItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistItems(items: RecentItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* ignore */
  }
}

interface RecentState {
  items: RecentItem[];
  addRecent: (item: Omit<RecentItem, 'visitedAt'>) => void;
  clearRecent: () => void;
}

export const useRecentStore = create<RecentState>((set, get) => ({
  items: readItems(),

  addRecent: (item) => {
    const now = Date.now();
    const current = get().items;
    // Remove any existing entry with the same id to avoid duplicates
    const filtered = current.filter((existing) => existing.id !== item.id);
    const next = [{ ...item, visitedAt: now }, ...filtered].slice(0, MAX_ITEMS);
    persistItems(next);
    set({ items: next });
  },

  clearRecent: () => {
    persistItems([]);
    set({ items: [] });
  },
}));
