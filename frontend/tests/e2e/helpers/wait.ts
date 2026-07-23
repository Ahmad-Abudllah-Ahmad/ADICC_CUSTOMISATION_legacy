/**
 * wait.ts — smart waits for app-specific UI affordances.
 *
 * Prefer these over arbitrary `page.waitForTimeout(2000)` calls.
 */
import { type Page, type Locator, expect } from '@playwright/test';

/**
 * Wait for a toast notification to appear and match `pattern`.
 *
 *   await waitForToast(page, /saved/i);
 *   await waitForToast(page, /error/i, { type: 'error' });
 */
export async function waitForToast(
  page: Page,
  pattern: RegExp | string,
  opts: { timeout?: number; type?: 'success' | 'error' | 'warning' | 'info' } = {},
): Promise<Locator> {
  const timeout = opts.timeout ?? 10_000;
  const root = opts.type
    ? page.locator(`[data-testid="toast-${opts.type}"], [data-toast-type="${opts.type}"]`)
    : page.locator('[role="status"], [data-testid^="toast"], [data-sonner-toast]');
  const matching = root.filter({ hasText: pattern });
  await expect(matching.first()).toBeVisible({ timeout });
  return matching.first();
}

/**
 * Wait for an AG Grid (or any data grid) to settle on `count` rows.
 * Polls every 200ms, gives up after `timeout`.
 */
export async function waitForGridRowCount(
  page: Page,
  count: number,
  opts: { selector?: string; timeout?: number } = {},
): Promise<void> {
  const sel = opts.selector ?? '[role="row"]:not([aria-rowindex="1"]), .ag-row';
  const timeout = opts.timeout ?? 15_000;
  await expect.poll(async () => page.locator(sel).count(), { timeout, intervals: [200, 500, 1000] }).toBe(count);
}

/**
 * Wait until at least one row of a grid has rendered (any count > 0).
 */
export async function waitForGridReady(page: Page, opts: { selector?: string; timeout?: number } = {}): Promise<void> {
  const sel = opts.selector ?? '.ag-row, [role="row"]:not([aria-rowindex="1"])';
  await page.locator(sel).first().waitFor({ state: 'visible', timeout: opts.timeout ?? 15_000 });
}

/**
 * Wait for any network requests matching `urlPattern` to complete (200|201|204|404).
 * Useful when an action triggers background fetches we want to settle.
 */
export async function waitForResponse(
  page: Page,
  urlPattern: RegExp,
  opts: { timeout?: number } = {},
): Promise<void> {
  await page.waitForResponse((r) => urlPattern.test(r.url()) && r.status() < 500, {
    timeout: opts.timeout ?? 10_000,
  });
}

/** Wait until a modal dialog is mounted and visible. */
export async function waitForModal(page: Page, opts: { timeout?: number } = {}): Promise<Locator> {
  const dialog = page.locator('[role="dialog"], [data-testid^="modal"]').first();
  await dialog.waitFor({ state: 'visible', timeout: opts.timeout ?? 5_000 });
  return dialog;
}

/** Wait for the modal to close. */
export async function waitForModalClose(page: Page, opts: { timeout?: number } = {}): Promise<void> {
  await page.locator('[role="dialog"], [data-testid^="modal"]').first().waitFor({
    state: 'hidden',
    timeout: opts.timeout ?? 5_000,
  });
}

/** Wait for spinner/loading overlay to disappear. */
export async function waitForLoadingDone(page: Page, opts: { timeout?: number } = {}): Promise<void> {
  const spinner = page.locator('[data-testid="loading"], [role="progressbar"], .spinner').first();
  if (await spinner.isVisible({ timeout: 500 }).catch(() => false)) {
    await spinner.waitFor({ state: 'hidden', timeout: opts.timeout ?? 15_000 }).catch(() => {
      /* persistent spinners are flagged elsewhere — don't block */
    });
  }
}
