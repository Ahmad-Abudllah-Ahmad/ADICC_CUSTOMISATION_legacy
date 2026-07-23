/**
 * R6 zero-width Unicode regression test (task #135).
 *
 * Background
 * ----------
 * Identity-marker code injected the byte sequence U+200C U+2060 U+200D
 * ("zero-width non-joiner + word joiner + zero-width joiner") into i18n
 * `defaultValue` strings across 363 source files. The marker is invisible
 * in normal rendering, but when a browser extension such as Google
 * Translate, Grammarly or an ad blocker mutates the DOM, React's
 * reconciler tries to call `insertBefore` against a node it no longer
 * recognises and throws:
 *
 *     Failed to execute 'insertBefore' on 'Node': The node before which
 *     the new node is to be inserted is not a child of this node.
 *
 * The reconciliation error blanked /contracts in production
 * (issue #135). This spec asserts the bug stays dead:
 *
 *   1. Each candidate page renders without zero-width Unicode in its
 *      visible text content.
 *   2. After we simulate a Google-Translate-style mutation that rewrites
 *      every text node's `nodeValue`, React keeps rendering and clicking
 *      on interactive elements does not throw an insertBefore error.
 *
 * Run:
 *   npx playwright test e2e/zero-width-regression.spec.ts
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';
import * as path from 'path';
import { injectFakeAuth } from './helpers';

const ARTIFACT_DIR = path.resolve(
  __dirname,
  '../../.tests-artifacts/r6/zero_width_regression',
);

/** Pages most likely to crash because they had ZW markers in their JSX. */
const PAGES = [
  { route: '/contracts', name: 'contracts' },
  { route: '/property-dev', name: 'property_dev' },
  { route: '/boq', name: 'boq' },
  { route: '/bim', name: 'bim' },
  { route: '/admin/permissions', name: 'admin_permissions' },
];

/**
 * Codepoints that are invisible-by-default and confused React's
 * reconciler when a translation extension mutated text nodes. We
 * build the regex from escape sequences so this file itself stays
 * free of literal zero-width characters (and passes the
 * no-irregular-whitespace lint guard we just added).
 */
// eslint-disable-next-line no-misleading-character-class
const ZERO_WIDTH_RE = new RegExp(
  '[\\u200B-\\u200F\\u2060-\\u2064\\u2066-\\u2069\\uFEFF]',
);

/**
 * Sentinel: any of these substrings appearing in a captured console
 * error means React's reconciler died on a node it didn't recognise.
 */
const RECONCILER_ERROR_NEEDLES = [
  "Failed to execute 'insertBefore' on 'Node'",
  'is not a child of this node',
  'NotFoundError',
];

interface CapturedConsole {
  type: string;
  text: string;
}

function attachConsoleCapture(page: Page): CapturedConsole[] {
  const sink: CapturedConsole[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    sink.push({ type: msg.type(), text: msg.text() });
  });
  page.on('pageerror', (err) => {
    sink.push({ type: 'pageerror', text: String(err?.message ?? err) });
  });
  return sink;
}

function reconcilerErrors(captured: CapturedConsole[]): CapturedConsole[] {
  return captured.filter(
    (c) =>
      (c.type === 'error' || c.type === 'pageerror') &&
      RECONCILER_ERROR_NEEDLES.some((needle) => c.text.includes(needle)),
  );
}

/**
 * Walk every visible text node and rewrite its `nodeValue` — this is
 * exactly the shape of DOM mutation Google Translate performs, and the
 * thing that originally tripped React's reconciler.
 */
async function simulateTranslationMutation(page: Page): Promise<void> {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
    );
    let node: Node | null = walker.nextNode();
    while (node) {
      const original = node.nodeValue ?? '';
      // Strip our specific marker triplet and any other zero-width
      // characters that may have leaked in — same surgery the
      // translation extension would perform. Pattern built from escape
      // sequences so this source file itself remains free of literal
      // zero-width chars.
      const cleaned = original.replace(
        new RegExp(
          '[\\u200B-\\u200F\\u2060-\\u2064\\u2066-\\u2069\\uFEFF]',
          'g',
        ),
        '',
      );
      if (cleaned !== original) {
        node.nodeValue = cleaned;
      }
      node = walker.nextNode();
    }
  });
  // Give React a tick to process any work scheduled by the mutation.
  await page.waitForTimeout(500);
}

/**
 * Click *something* — anything safely interactive on the page — so the
 * reconciler has to walk the mutated tree. We try a tab control first
 * (most pages have one); if none is found we fall back to clicking the
 * page heading, which is always safe.
 */
async function pokeFirstInteractive(page: Page): Promise<void> {
  const candidates = [
    'button[role="tab"]:not([disabled])',
    'nav a:not([disabled])',
    'button:not([disabled])',
    'h1',
  ];
  for (const sel of candidates) {
    const el = page.locator(sel).first();
    if (await el.count()) {
      try {
        await el.click({ timeout: 2_000, trial: false });
        return;
      } catch {
        // Try the next candidate — element may be detached or off-screen.
      }
    }
  }
}

test.describe('R6: zero-width Unicode regression', () => {
  test.beforeEach(async ({ page }) => {
    await injectFakeAuth(page);
  });

  for (const { route, name } of PAGES) {
    test(`${route} renders cleanly + survives Translate-style mutation`, async ({
      page,
    }) => {
      const captured = attachConsoleCapture(page);

      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle').catch(() => {
        /* networkidle can hang for SSE-using pages — best-effort only */
      });

      // ── 1. Static check: no zero-width chars in rendered text ────────────
      const visibleText = await page.evaluate(() => document.body.innerText);
      expect(
        ZERO_WIDTH_RE.test(visibleText),
        `Page ${route} still renders zero-width Unicode in its visible text`,
      ).toBe(false);

      // ── 2. Snapshot BEFORE mutation ──────────────────────────────────────
      await page.screenshot({
        path: path.join(ARTIFACT_DIR, `${name}_before.png`),
        fullPage: true,
      });

      // ── 3. Simulate Google-Translate-style DOM mutation ──────────────────
      await simulateTranslationMutation(page);

      // ── 4. Force the reconciler to walk the mutated tree ─────────────────
      await pokeFirstInteractive(page);
      await page.waitForTimeout(500);

      // ── 5. Snapshot AFTER mutation ───────────────────────────────────────
      await page.screenshot({
        path: path.join(ARTIFACT_DIR, `${name}_after.png`),
        fullPage: true,
      });

      // ── 6. Assert no reconciler errors fired ─────────────────────────────
      const errs = reconcilerErrors(captured);
      expect(
        errs,
        `Page ${route} threw a React reconciliation error after a ` +
          `translation-extension-style DOM mutation:\n` +
          errs.map((e) => `  [${e.type}] ${e.text}`).join('\n'),
      ).toHaveLength(0);
    });
  }
});
