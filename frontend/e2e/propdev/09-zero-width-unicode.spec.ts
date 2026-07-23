/**
 * Scenario #9 — Bug #2 regression: zero-width Unicode + Google Translate.
 *
 * Two angles of the same DOM-mutation hazard:
 *
 *   A. Zero-width characters (U+200B/200C/200D/2060/FEFF) embedded inside
 *      i18n defaultValue strings used to crash React's reconciler with
 *      ``Failed to execute 'insertBefore' on 'Node'`` whenever a re-render
 *      shuffled the children. The codebase strips those on commit
 *      (commit 6d1a9ea3, "fix(i18n): strip zero-width Unicode from
 *      defaultValue strings + add lint guard").
 *
 *   B. Google Translate walks every text node in the body and replaces
 *      nodeValue on the live DOM. React doesn't know about the swap and
 *      its next reconciler pass tries to insertBefore on a node that no
 *      longer matches the fiber tree → same NotFoundError.
 *
 * We simulate (B) by injecting a script that walks every text node and
 * mutates nodeValue between renders, then click around the page. Zero
 * console errors of the ``insertBefore`` / ``NotFoundError`` shape may
 * be emitted.
 *
 * The check runs against /property-dev AND /contracts to cover both
 * pages the bug originally surfaced on.
 */
import { expect, test, type Page } from '@playwright/test';
import {
  bootstrapDevelopmentGraph,
  createBuyer,
  teardownDevelopment,
} from './helpers/api-bootstrap';
import { demoLogin, hydrateAuth } from './helpers/auth';
import { ConsoleGuard } from './helpers/console-guard';
import { Shooter } from './helpers/screenshots';

test.describe.configure({ mode: 'serial' });

/**
 * Walk every text node in the body and replace its nodeValue with the
 * same string wrapped in zero-width characters. Done from `addInitScript`
 * so the patch runs BEFORE React mounts.
 */
async function installGoogleTranslateSim(page: Page): Promise<void> {
  await page.context().addInitScript(() => {
    const tick = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let n: Node | null = walker.nextNode();
      while (n) {
        // Re-set nodeValue with zero-width markers so any reconciler
        // diff that compares string identity (not equality) trips.
        if (n.nodeValue && n.nodeValue.trim().length > 0) {
          const original = n.nodeValue;
          // Sandwich the content with U+200B so the rendered length
          // technically differs while looking identical to a human.
          n.nodeValue = `​${original}​`;
        }
        n = walker.nextNode();
      }
    };
    // Defer until DOMContentLoaded so React has mounted at least once.
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        // Wait one frame so the initial paint completes.
        requestAnimationFrame(tick);
        // Apply once more 500ms in to catch async-loaded chunks.
        setTimeout(tick, 500);
      });
    } else {
      requestAnimationFrame(tick);
      setTimeout(tick, 500);
    }
  });
}

test('zero-width Unicode + Google Translate sim on /property-dev', async ({ page }) => {
  const shooter = new Shooter('zero_width');
  const guard = new ConsoleGuard(page);

  const admin = await demoLogin('admin');
  await hydrateAuth(page.context(), admin);

  const graph = await bootstrapDevelopmentGraph(admin.api, {
    name: 'R6 ZeroWidth Dev',
  });
  for (let i = 0; i < 3; i += 1) {
    await createBuyer(admin.api, graph.development_id, {
      full_name: `R6 ZW Buyer ${i + 1}`,
    });
  }

  // Install the simulation BEFORE the SPA boots.
  await installGoogleTranslateSim(page);
  guard.attach();
  await page.goto('/property-dev');
  await page.waitForLoadState('networkidle');
  await shooter.shoot(page, 'property_dev_after_translate_sim');

  // Click around — tabs, table rows, buttons — anything that triggers
  // a React re-render is sufficient to provoke the regression.
  const clickables = page.getByRole('button').or(page.getByRole('tab'));
  const count = Math.min(8, await clickables.count());
  for (let i = 0; i < count; i += 1) {
    const el = clickables.nth(i);
    if (await el.isVisible({ timeout: 1_000 }).catch(() => false)) {
      await el.click({ trial: false }).catch(() => undefined);
      await page.waitForTimeout(150);
    }
  }
  await shooter.shoot(page, 'after_clicking_around');

  // Force one more re-render by reloading the buyer list query.
  await page.evaluate(() => {
    // ReactQuery cache is exposed under window.__OE_RQ for dev hooks.
    type WithRQ = { __OE_RQ?: { invalidateQueries: (k: string) => void } };
    const w = window as unknown as WithRQ;
    w.__OE_RQ?.invalidateQueries('property-dev');
  });
  await page.waitForTimeout(500);

  guard.assertNoHardFailures();
  shooter.saveJson('console_entries', {
    total: guard.entries.length,
    hard_failures: guard.hardFailures.length,
  });
  guard.release();
  await teardownDevelopment(admin.api, graph.development_id);
});

test('zero-width Unicode + Google Translate sim on /contracts', async ({ page }) => {
  const shooter = new Shooter('zero_width');
  const guard = new ConsoleGuard(page);

  const admin = await demoLogin('admin');
  await hydrateAuth(page.context(), admin);
  await installGoogleTranslateSim(page);
  guard.attach();

  await page.goto('/contracts');
  await page.waitForLoadState('networkidle');
  await shooter.shoot(page, 'contracts_after_translate_sim');

  const clickables = page.getByRole('button').or(page.getByRole('tab'));
  const count = Math.min(6, await clickables.count());
  for (let i = 0; i < count; i += 1) {
    const el = clickables.nth(i);
    if (await el.isVisible({ timeout: 1_000 }).catch(() => false)) {
      await el.click({ trial: false }).catch(() => undefined);
      await page.waitForTimeout(120);
    }
  }
  await shooter.shoot(page, 'contracts_after_interactions');
  guard.assertNoHardFailures();
  guard.release();

  // Sanity: assertion that the page itself loaded — no 500/404 redirect.
  expect(page.url()).toContain('/contracts');
});
