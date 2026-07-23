/**
 * Playwright PWA install + Lighthouse scaffold — SKIPPED by default.
 *
 * Running Lighthouse on Windows CI requires a Chromium with HTTP/2 +
 * a writable user-data-dir, neither of which is available reliably
 * from the headless container we run unit tests in.  Leave this spec
 * in place so the moment we move PWA verification into a dedicated
 * Linux job we can drop the ``.skip`` and the suite light up.
 *
 * Run locally:
 *   cd frontend && npx playwright test scripts/pwa-install.spec.ts --headed
 *
 * Manual checklist this scaffold is intended to automate:
 *   1. Visit the app — service worker registers without console errors.
 *   2. ``beforeinstallprompt`` fires within 10 s on a fresh profile.
 *   3. Clicking our "Install" button drives the native install dialog
 *      and resolves with ``outcome === 'accepted'`` when accepted.
 *   4. After install, ``display-mode: standalone`` matches.
 *   5. The manifest scores 100 on the Lighthouse "Installable" audit.
 */
import { test, expect } from '@playwright/test';

test.describe.skip('PWA install + Lighthouse', () => {
  test('service worker registers without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Service worker should be registered by now.
    const swRegistered = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return false;
      const reg = await navigator.serviceWorker.getRegistration();
      return !!reg;
    });

    expect(swRegistered).toBe(true);
    expect(errors).toEqual([]);
  });

  test('install prompt surfaces and accepts', async ({ page }) => {
    await page.goto('/');

    // Dispatch a synthetic beforeinstallprompt event so the UI shows
    // even outside a real Chrome-with-install-criteria scenario.
    await page.evaluate(() => {
      const ev = new Event('beforeinstallprompt') as unknown as {
        prompt: () => Promise<void>;
        userChoice: Promise<{ outcome: 'accepted'; platform: string }>;
      } & Event;
      (ev as { prompt: () => Promise<void> }).prompt = async () => undefined;
      (ev as { userChoice: Promise<unknown> }).userChoice = Promise.resolve({
        outcome: 'accepted',
        platform: 'web',
      });
      window.dispatchEvent(ev as Event);
    });

    const prompt = page.getByTestId('pwa-install-prompt');
    await expect(prompt).toBeVisible({ timeout: 5_000 });

    await prompt.getByRole('button', { name: /install/i }).click();
    await expect(prompt).toBeHidden();
  });
});
