/**
 * nav.ts — central navigation helpers.
 *
 * Use these instead of literal `page.goto('/boq')` so route renames or
 * sidebar restructures only need a single update.
 *
 * Every helper prefers `data-testid` selectors when the component
 * exposes one, and falls back to role/text only when no testid exists.
 */
import { type Page, expect } from '@playwright/test';

/** Canonical module slugs → primary route paths. */
export const MODULE_ROUTES = {
  dashboard: '/',
  projects: '/projects',
  boq: '/boq',
  takeoff: '/takeoff',
  costs: '/costs',
  bim: '/bim-hub',
  validation: '/validation',
  tendering: '/tendering',
  reporting: '/reporting',
  settings: '/settings',
  accommodation: '/accommodation',
  geoHub: '/geo-hub',
  contacts: '/contacts',
  schedule: '/schedule',
  propDev: '/property-development',
} as const;

export type ModuleKey = keyof typeof MODULE_ROUTES;

/** Navigate to a module by canonical key and wait for the body to settle. */
export async function gotoModule(page: Page, key: ModuleKey): Promise<void> {
  const path = MODULE_ROUTES[key];
  await page.goto(path);
  await page.waitForLoadState('domcontentloaded');
  // Brief settle: the React app may stream chunks after DOMContentLoaded.
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {
    /* a busy app may never reach networkidle; that's OK */
  });
}

/** Open the sidebar (mobile) — no-op on desktop where it's always visible. */
export async function openSidebar(page: Page): Promise<void> {
  const burger = page.locator('[data-testid="sidebar-toggle"], button[aria-label*="menu" i]').first();
  if (await burger.isVisible({ timeout: 1_000 }).catch(() => false)) {
    await burger.click();
  }
}

/** Close the sidebar (mobile) if it's currently open. */
export async function closeSidebar(page: Page): Promise<void> {
  const close = page.locator('[data-testid="sidebar-close"]').first();
  if (await close.isVisible({ timeout: 500 }).catch(() => false)) {
    await close.click();
  }
}

/** Open the global command palette (Cmd/Ctrl+K). */
export async function openCommandPalette(page: Page): Promise<void> {
  const isMac = process.platform === 'darwin';
  await page.keyboard.press(isMac ? 'Meta+K' : 'Control+K');
}

/** Open the keyboard-shortcuts help (?). */
export async function openShortcutsHelp(page: Page): Promise<void> {
  await page.keyboard.press('Shift+Slash');
}

/**
 * Confirm the navbar/header is mounted and the app shell rendered — a
 * cheap sanity check after any goto so we know we're not on a white
 * screen or an error boundary.
 */
export async function expectAppShell(page: Page): Promise<void> {
  // Either the explicit testid OR the role-based fallback should be present.
  const shell = page.locator(
    '[data-testid="app-shell"], [data-testid="app-header"], header, [role="banner"]',
  ).first();
  await expect(shell).toBeVisible({ timeout: 15_000 });
}

/** Switch UI language via the language switcher dropdown. */
export async function switchLanguage(page: Page, lang: 'en' | 'de' | 'ru' | 'ar' | 'es' | 'fr' | 'pt' | 'it' | 'pl' | 'ja' | 'ko' | 'zh'): Promise<void> {
  // Preferred: data-testid; fallback: aria-label.
  const trigger = page.locator(
    '[data-testid="language-switcher"], button[aria-label*="language" i]',
  ).first();
  if (await trigger.isVisible({ timeout: 1_000 }).catch(() => false)) {
    await trigger.click();
    const opt = page.locator(`[data-testid="lang-${lang}"], [role="option"][data-value="${lang}"]`).first();
    if (await opt.isVisible({ timeout: 1_000 }).catch(() => false)) {
      await opt.click();
      return;
    }
  }
  // Last-resort: poke i18next via the global query param the app respects.
  const url = new URL(page.url());
  url.searchParams.set('locale', lang);
  await page.goto(url.toString());
}
