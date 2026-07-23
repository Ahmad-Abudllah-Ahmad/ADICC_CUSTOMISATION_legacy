// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Icon-only sidebar mode.
 *
 * When iconified, the sidebar collapses to a 64px-wide strip showing
 * only icons — labels, group headers and search-bar text are hidden.
 * Native `title` tooltips surface labels on hover.
 *
 * The CSS variable `--oe-sidebar-width` drives both the aside's own
 * width (Tailwind `w-sidebar`) and the main content offset
 * (`lg:pl-sidebar`), so changing it in one place reflows the whole
 * layout consistently.
 */

import { create } from 'zustand';

const STORAGE_KEY = 'oe_sidebar_iconified';

function readIconified(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

interface SidebarCollapseState {
  iconified: boolean;
  setIconified: (v: boolean) => void;
  toggle: () => void;
}

export const useSidebarCollapseStore = create<SidebarCollapseState>((set, get) => ({
  iconified: readIconified(),
  setIconified: (v: boolean) => {
    try {
      localStorage.setItem(STORAGE_KEY, v ? '1' : '0');
    } catch {
      /* storage unavailable */
    }
    set({ iconified: v });
  },
  toggle: () => get().setIconified(!get().iconified),
}));

export const SIDEBAR_WIDTH_FULL = '248px';
export const SIDEBAR_WIDTH_ICON = '64px';
