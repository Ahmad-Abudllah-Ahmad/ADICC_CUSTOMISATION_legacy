/**
 * assert.ts — domain-specific assertions reused across the suite.
 */
import { type Page, type APIResponse, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Money / decimal contract: the backend always returns money as a STRING
 * (not float) to avoid precision loss. UI components also display strings.
 *
 *   expectDecimalMoneyString('1234.56')      // ok
 *   expectDecimalMoneyString('1234,56')      // ok (comma-locale)
 *   expectDecimalMoneyString(1234.56)        // FAILS — number, not string
 */
export function expectDecimalMoneyString(value: unknown): void {
  expect(typeof value, `money must be string, got ${typeof value}`).toBe('string');
  const s = value as string;
  // Accept "1234.56", "1,234.56", "1.234,56" — anything that looks decimal.
  expect(s, `money string "${s}" does not look like a decimal`).toMatch(/^-?[\d.,\s]+$/);
}

/**
 * IDOR check: a request that hits another tenant's resource must return
 * 404 (preferred — don't reveal existence) or 403. Anything else (200,
 * 500, 422) is a security bug.
 */
export async function expectIDORReturns404(res: APIResponse | Promise<APIResponse>): Promise<void> {
  const r = await res;
  expect([403, 404]).toContain(r.status());
}

/**
 * Axe-core a11y scan; fails on `serious` + `critical` violations.
 * `WCAG 2.1 AA` tags are enabled by default. Passes a clean snapshot.
 *
 * Use `expectA11yClean(page, { tolerate: [...] })` to allow known issues
 * (e.g. a third-party widget) — pass the rule ids to skip.
 */
export async function expectA11yClean(
  page: Page,
  opts?: { tolerate?: string[]; severities?: Array<'minor' | 'moderate' | 'serious' | 'critical'> },
): Promise<void> {
  const severities = opts?.severities ?? ['serious', 'critical'];
  const tolerate = new Set(opts?.tolerate ?? []);
  const builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']);
  const results = await builder.analyze();
  const blocking = results.violations.filter(
    (v) => severities.includes(v.impact as 'serious' | 'critical' | 'moderate' | 'minor') && !tolerate.has(v.id),
  );
  if (blocking.length > 0) {
    const summary = blocking
      .map((v) => `  - [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`)
      .join('\n');
    throw new Error(`a11y: ${blocking.length} blocking violation(s)\n${summary}`);
  }
}

/**
 * Confirms no JS error was logged to the console during the page lifetime.
 * Call early in a test: `const errors = collectConsoleErrors(page);`
 * then later: `expectNoConsoleErrors(errors)`.
 */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    errors.push(err.message);
  });
  return errors;
}

export function expectNoConsoleErrors(errors: string[], allow: RegExp[] = []): void {
  const real = errors.filter((e) => !allow.some((r) => r.test(e)));
  expect(real, `unexpected console errors:\n${real.join('\n')}`).toHaveLength(0);
}

/**
 * Backend health: returns `{ status, version, ... }`.
 *
 * Accepts both "healthy" (everything green) and "degraded" (one or more
 * subsystems impaired but API still responsive — e.g. alembic head
 * mismatch on a freshly-cloned dev box). Only "down" or missing status
 * fails the assertion.
 */
export function expectHealthShape(body: unknown): asserts body is { status: string; version: string } {
  expect(typeof body).toBe('object');
  const b = body as Record<string, unknown>;
  expect(b.status, `unexpected health status "${b.status}"`).toMatch(/^(healthy|degraded)$/);
  expect(typeof b.version).toBe('string');
  expect((b.version as string).length).toBeGreaterThan(0);
}
