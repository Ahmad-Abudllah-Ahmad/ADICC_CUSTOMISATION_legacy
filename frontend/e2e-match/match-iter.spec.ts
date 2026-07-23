/* Iterative /match-elements probe across every project in the system.
 *
 * For each project, navigates to /match-elements?project=<id>, waits for
 * the page to settle, captures a full-page screenshot, and harvests
 * the visible text so we can grep it for universality red flags
 * (hardcoded EUR / English-only labels / DIN-276-everywhere).
 *
 * Output: qa-tests/_match-iter-<date>/<region>-<seq>-<name>.png + a
 * findings.json with per-project notes.
 *
 * Run: npx playwright test --config playwright.match.config.ts --grep "iter"
 */

import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const TODAY = new Date().toISOString().slice(0, 10);
const OUT = path.resolve(__dirname_esm, `../../qa-tests/_match-iter-${TODAY}`);
fs.mkdirSync(OUT, { recursive: true });

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'demo@openconstructionerp.com', password: 'DemoPass1234!' };

interface Project {
  id: string;
  name: string;
  region?: string | null;
  currency?: string | null;
}

interface MatchFinding {
  session_id: string | null;
  groups_total: number;
  candidate_currencies: Record<string, number>;
  api_error?: string;
}

interface Finding {
  id: string;
  name: string;
  region?: string | null;
  currency?: string | null;
  status_code: number;
  visible_text_sample: string;
  red_flags: string[];
  match?: MatchFinding;
}

function fileSafe(s: string): string {
  return s
    .replace(/[\\/:"*?<>|]+/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 60);
}

test.describe('match-elements iterative probe', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('iter — every project gets a screenshot + findings dump', async ({ page, request }) => {
    test.setTimeout(180_000);

    // 1. Login + hydrate localStorage
    const loginRes = await request.post(`${BACKEND}/api/v1/users/auth/login/`, {
      data: USER,
      failOnStatusCode: false,
    });
    expect(loginRes.ok()).toBeTruthy();
    const { access_token, refresh_token } = await loginRes.json();

    await page.goto(`${FRONTEND}/about`);
    await page.evaluate(
      ({ access, refresh, email }) => {
        localStorage.setItem('oe_access_token', access);
        localStorage.setItem('oe_refresh_token', refresh);
        localStorage.setItem('oe_user_email', email);
      },
      { access: access_token, refresh: refresh_token ?? access_token, email: USER.email },
    );

    // 2. Pull project list
    const projRes = await request.get(`${BACKEND}/api/v1/projects/`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(projRes.ok()).toBeTruthy();
    const projects: Project[] = await projRes.json();
    console.log(`probing ${projects.length} projects`);

    const findings: Finding[] = [];

    for (let i = 0; i < projects.length; i++) {
      const p = projects[i];
      const tag = `${String(i + 1).padStart(2, '0')}-${p.region ?? 'none'}-${fileSafe(p.name)}`;
      console.log(`\n[${i + 1}/${projects.length}] ${p.region ?? '?'} · ${p.name}`);

      // Set the project context the SPA picks up via the project store
      await page.evaluate((id) => {
        localStorage.setItem('oe_active_project_id', id);
      }, p.id);

      const resp = await page.goto(`${FRONTEND}/match-elements?project=${p.id}`, {
        waitUntil: 'domcontentloaded',
      });
      const status = resp?.status() ?? 0;
      await page.waitForLoadState('networkidle').catch(() => null);
      // Give the page time to paint summary cards + region rail.
      await page.waitForTimeout(2500);

      await page.screenshot({
        path: path.join(OUT, `${tag}.png`),
        fullPage: true,
      });

      const visible = await page.locator('main, [role="main"], body').first().innerText().catch(() => '');
      const sample = visible.slice(0, 600).replace(/\s+/g, ' ');
      const flags: string[] = [];

      // Helper — capture a 80-char window around the first whole-word
      // match so the human reviewer can see *where* the currency leak
      // came from without dumping the full body.
      const ctx = (re: RegExp): string => {
        const m = visible.match(re);
        if (!m || m.index === undefined) return '';
        return visible
          .slice(Math.max(0, m.index - 40), m.index + 40)
          .replace(/\s+/g, ' ');
      };

      // Red-flag heuristics — tuned for the universality concerns:
      // 1. Wrong currency surfaced (EUR shown on a non-EUR project,
      //    or USD when the project says BRL). Match WHOLE-WORD token
      //    only — "EUR" inside "OpenConstructionERP" is a false hit.
      const expectedCcy = (p.currency ?? '').toUpperCase();
      const ccyTokens = ['EUR', 'USD', 'GBP', 'BRL', 'RUB', 'CNY', 'JPY', 'INR'];
      for (const tk of ccyTokens) {
        const re = new RegExp(`\\b${tk}\\b`);
        if (re.test(visible) && expectedCcy && tk !== expectedCcy) {
          flags.push(`foreign-currency-token:${tk} ctx="${ctx(re)}"`);
        }
      }

      // 2. DIN 276 references on a non-DACH project (universal bias check).
      if (
        (p.region ?? '').toUpperCase() !== 'DACH' &&
        /\bDIN\s?276\b|\bKG\s?\d{3}\b/.test(visible)
      ) {
        flags.push('din276-on-non-dach');
      }

      // 3. Empty-state or 0-groups indicators — useful UX baseline.
      if (/no\s+groups|no\s+matches|0\s+groups/i.test(visible)) {
        flags.push('empty-state');
      }

      // 4. Untranslated strings that suggest English leakage —
      //    "Unclassified", "Loading", "no data" are the usual ones.
      if (/Unclassified/.test(visible)) flags.push('english-Unclassified');

      // 5. Trigger a fresh match run via API and inspect candidate
      //    currencies — this is the deepest universality check.
      //    A USD project should never see EUR candidates returned by
      //    the matcher; if it does, the fix at the SQL/payload filter
      //    layer didn't take effect.
      const match: MatchFinding = {
        session_id: null,
        groups_total: 0,
        candidate_currencies: {},
      };
      try {
        // Find or create a session for this project.
        const sessionsRes = await request.get(
          `${BACKEND}/api/v1/match_elements/sessions?project_id=${p.id}`,
          { headers: { Authorization: `Bearer ${access_token}` } },
        );
        let sessionId: string | null = null;
        if (sessionsRes.ok()) {
          const sessions = await sessionsRes.json();
          if (Array.isArray(sessions) && sessions.length > 0) {
            sessionId = sessions[0]?.id ?? null;
          }
        }
        if (!sessionId) {
          const createRes = await request.post(
            `${BACKEND}/api/v1/match_elements/sessions`,
            {
              data: { project_id: p.id, source: 'bim' },
              headers: { Authorization: `Bearer ${access_token}` },
            },
          );
          if (createRes.ok()) {
            const sess = await createRes.json();
            sessionId = sess?.id ?? null;
          }
        }
        match.session_id = sessionId;

        if (sessionId) {
          // Fetch group list to learn how many groups exist.
          const groupsRes = await request.get(
            `${BACKEND}/api/v1/match_elements/sessions/${sessionId}/groups?limit=200`,
            { headers: { Authorization: `Bearer ${access_token}` } },
          );
          if (groupsRes.ok()) {
            const list = await groupsRes.json();
            match.groups_total = list?.total ?? 0;

            // Tally currencies on whatever per-group suggested_currency
            // already exists from prior match runs (if any).
            for (const g of list?.groups ?? []) {
              const ccy = (g?.suggested_currency ?? '').toString();
              if (!ccy) continue;
              match.candidate_currencies[ccy] =
                (match.candidate_currencies[ccy] ?? 0) + 1;
            }

            // Trigger a fresh lexical run on up to 3 groups so we
            // exercise the new project_currency filter.
            if (match.groups_total > 0) {
              const runRes = await request.post(
                `${BACKEND}/api/v1/match_elements/sessions/${sessionId}/match`,
                {
                  data: { method: 'lexical', max_groups: 3, top_k: 5 },
                  headers: { Authorization: `Bearer ${access_token}` },
                },
              );
              if (runRes.ok()) {
                const fresh = await runRes.json();
                for (const g of fresh ?? []) {
                  const ccy = (g?.suggested_currency ?? '').toString();
                  if (!ccy) continue;
                  match.candidate_currencies[`(fresh) ${ccy}`] =
                    (match.candidate_currencies[`(fresh) ${ccy}`] ?? 0) + 1;
                }
              } else {
                match.api_error = `match run http=${runRes.status()}`;
              }
            }
          }
        }
      } catch (err) {
        match.api_error = err instanceof Error ? err.message : String(err);
      }

      // 6. Flag any candidate currency that diverges from project currency.
      const expectedCcyMatch = (p.currency ?? '').toUpperCase();
      for (const ccyKey of Object.keys(match.candidate_currencies)) {
        const bare = ccyKey.replace(/^\(fresh\)\s+/, '').toUpperCase();
        if (bare && expectedCcyMatch && bare !== expectedCcyMatch) {
          flags.push(`candidate-ccy-mismatch:${ccyKey} (expected ${expectedCcyMatch})`);
        }
      }

      findings.push({
        id: p.id,
        name: p.name,
        region: p.region ?? null,
        currency: p.currency ?? null,
        status_code: status,
        visible_text_sample: sample,
        red_flags: flags,
        match,
      });
      console.log(
        `  status=${status} groups=${match.groups_total} ccy=${JSON.stringify(match.candidate_currencies)} flags=${flags.join(',') || 'none'}`,
      );
    }

    fs.writeFileSync(
      path.join(OUT, 'findings.json'),
      JSON.stringify(findings, null, 2),
      'utf-8',
    );
    console.log(`\nfindings written: ${path.join(OUT, 'findings.json')}`);

    // Don't fail the run on red flags — we want the dump for the human
    // to read. Hard failures only when basic navigation breaks.
    for (const f of findings) {
      expect(f.status_code, `${f.name} navigation`).toBeLessThan(400);
    }
  });
});
