// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Floating chat widget store.
 *
 * Holds the open/closed state of the bottom-right floating chat panel and a
 * pointer to the active session (so the user can resume the most recent
 * conversation across route changes and even page reloads). Also tracks an
 * "unread" counter for the badge on the floating button — every time the
 * assistant produces a message while the panel is closed, the counter ticks
 * up; opening the panel resets it.
 *
 * Persists to localStorage so the user's last-used session is restored on
 * reload, matching how `useProjectContextStore` keeps the active project
 * sticky across navigations.
 */

import { useEffect, useState, useSyncExternalStore } from 'react';
import { create } from 'zustand';

const STORAGE_KEY = 'oe_floating_chat_v1';

interface PersistedState {
  activeSessionId: string | null;
  lastReadAt: string; // ISO timestamp
}

interface FloatingChatState {
  isOpen: boolean;
  activeSessionId: string | null;
  lastReadAt: string;
  unreadCount: number;
  /**
   * Session-only flag: when the user clicks "Skip" on the "Configure AI"
   * onboarding banner we hide the banner for the rest of this browser
   * session. We intentionally DO NOT persist this to localStorage — the
   * onboarding nudge should reappear next visit so the user is reminded
   * they still need to configure their key.
   */
  onboardingBannerDismissed: boolean;
  /**
   * One-shot text to drop into the composer the next time the panel is open.
   * Set by `seedPrompt` (e.g. the BIM viewer's "Ask AI about this element"
   * action) and consumed once by the panel, which prefills the input and
   * clears it. Deliberately NOT persisted: it is a transient hand-off, not a
   * draft to survive reloads. We prefill rather than auto-send so the user
   * reviews and submits, matching the platform's human-confirmed AI stance.
   */
  pendingPrompt: string | null;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setActiveSession: (id: string | null) => void;
  markRead: () => void;
  bumpUnread: () => void;
  dismissOnboardingBanner: () => void;
  resetOnboardingBanner: () => void;
  /** Open the panel and stage `prompt` to prefill the composer. */
  seedPrompt: (prompt: string) => void;
  /** Clear the staged prompt (called by the panel once it has consumed it). */
  clearPendingPrompt: () => void;
}

function readPersisted(): PersistedState {
  if (typeof window === 'undefined') {
    return { activeSessionId: null, lastReadAt: new Date(0).toISOString() };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { activeSessionId: null, lastReadAt: new Date(0).toISOString() };
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    return {
      activeSessionId:
        typeof parsed.activeSessionId === 'string' ? parsed.activeSessionId : null,
      lastReadAt:
        typeof parsed.lastReadAt === 'string' ? parsed.lastReadAt : new Date(0).toISOString(),
    };
  } catch {
    return { activeSessionId: null, lastReadAt: new Date(0).toISOString() };
  }
}

function writePersisted(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Quota exceeded / privacy mode — non-fatal.
  }
}

const initial = readPersisted();

export const useFloatingChatStore = create<FloatingChatState>((set, get) => ({
  isOpen: false,
  activeSessionId: initial.activeSessionId,
  lastReadAt: initial.lastReadAt,
  unreadCount: 0,
  onboardingBannerDismissed: false,
  pendingPrompt: null,

  open: () => {
    const now = new Date().toISOString();
    set({ isOpen: true, lastReadAt: now, unreadCount: 0 });
    writePersisted({ activeSessionId: get().activeSessionId, lastReadAt: now });
  },

  close: () => {
    set({ isOpen: false });
  },

  toggle: () => {
    const s = get();
    if (s.isOpen) {
      set({ isOpen: false });
    } else {
      const now = new Date().toISOString();
      set({ isOpen: true, lastReadAt: now, unreadCount: 0 });
      writePersisted({ activeSessionId: s.activeSessionId, lastReadAt: now });
    }
  },

  setActiveSession: (id: string | null) => {
    set({ activeSessionId: id });
    writePersisted({ activeSessionId: id, lastReadAt: get().lastReadAt });
  },

  markRead: () => {
    const now = new Date().toISOString();
    set({ lastReadAt: now, unreadCount: 0 });
    writePersisted({ activeSessionId: get().activeSessionId, lastReadAt: now });
  },

  bumpUnread: () => {
    // Only bump when the panel is actually closed — the caller is responsible
    // for the open check too, but defending here keeps the store honest.
    if (get().isOpen) return;
    set((s) => ({ unreadCount: s.unreadCount + 1 }));
  },

  dismissOnboardingBanner: () => {
    set({ onboardingBannerDismissed: true });
  },

  resetOnboardingBanner: () => {
    set({ onboardingBannerDismissed: false });
  },

  seedPrompt: (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    // Open the panel and stage the text; the panel consumes it on the next
    // render. Mirrors `open()` so the unread badge and read-marker stay
    // consistent whether the user opened the panel or the seed did.
    const now = new Date().toISOString();
    set({ pendingPrompt: trimmed, isOpen: true, lastReadAt: now, unreadCount: 0 });
    writePersisted({ activeSessionId: get().activeSessionId, lastReadAt: now });
  },

  clearPendingPrompt: () => {
    if (get().pendingPrompt !== null) set({ pendingPrompt: null });
  },
}));

/**
 * Small helper that returns `true` after the component has mounted on the
 * client. We use this to defer reading `window.matchMedia` until after
 * hydration / first paint — Vite SSR is not in play here, but it also keeps
 * the initial render deterministic and avoids re-render flashes.
 */
export function useIsMobileViewport(breakpointPx = 640): boolean {
  const subscribe = (callback: () => void): (() => void) => {
    if (typeof window === 'undefined') return () => {};
    const mq = window.matchMedia(`(max-width: ${breakpointPx - 1}px)`);
    mq.addEventListener('change', callback);
    return () => mq.removeEventListener('change', callback);
  };
  const getSnapshot = (): boolean => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(`(max-width: ${breakpointPx - 1}px)`).matches;
  };
  const getServerSnapshot = (): boolean => false;
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/**
 * Returns `true` once the component has mounted on the client. Used to avoid
 * rendering portals (and the floating button itself) before the auth store
 * has hydrated from sessionStorage — without this the button briefly flashes
 * on /login on a hard reload.
 */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  return mounted;
}
