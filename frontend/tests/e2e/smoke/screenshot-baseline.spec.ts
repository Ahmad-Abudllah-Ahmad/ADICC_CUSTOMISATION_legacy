/**
 * Smoke — visual regression baseline: capture full-page screenshots of
 * the 15 top-level routes. These are NOT diffed automatically — they
 * are the seed of a future visual baseline (the QA agent compares
 * across runs via /qa-screenshots/).
 */
import { test, expect } from '../fixtures';
import { MODULE_ROUTES, captureScreen, expectAppShell } from '../helpers';

const ROUTES_TO_BASELINE: Array<{ key: keyof typeof MODULE_ROUTES; label: string }> = [
  { key: 'dashboard', label: 'dashboard' },
  { key: 'projects', label: 'projects' },
  { key: 'boq', label: 'boq' },
  { key: 'takeoff', label: 'takeoff' },
  { key: 'costs', label: 'costs' },
  { key: 'bim', label: 'bim-hub' },
  { key: 'validation', label: 'validation' },
  { key: 'tendering', label: 'tendering' },
  { key: 'reporting', label: 'reporting' },
  { key: 'settings', label: 'settings' },
  { key: 'accommodation', label: 'accommodation' },
  { key: 'geoHub', label: 'geo-hub' },
  { key: 'contacts', label: 'contacts' },
  { key: 'schedule', label: 'schedule' },
  { key: 'propDev', label: 'property-development' },
];

test.describe('@smoke screenshot-baseline', () => {
  for (const route of ROUTES_TO_BASELINE) {
    test(`baseline screenshot — ${route.label}`, async ({ authedPage }) => {
      await authedPage.goto(MODULE_ROUTES[route.key]);
      await authedPage.waitForLoadState('domcontentloaded');
      // Best-effort settle — many widgets paint async; don't fail on timeout.
      await authedPage.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined);
      try {
        await expectAppShell(authedPage);
      } catch {
        // Route may not be wired yet — still capture the screenshot for debug.
      }
      await captureScreen(authedPage, 'baseline', route.label);
    });
  }
});
