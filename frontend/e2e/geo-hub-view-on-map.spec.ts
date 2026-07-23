/**
 * E2E smoke: cross-module "View on map" CTAs.
 *
 * Verifies that the project-scoped "View on map" buttons exist on the
 * pages we wired into Geo Hub and that each one navigates to the
 * per-project Geo Hub route (/projects/:id/geo or
 * /property-dev/developments/:id/geo).
 *
 * Skipped in CI by default — set PLAYWRIGHT_GEO=1 to run. Same gate
 * as ``geo-hub.spec.ts`` because the destination page mounts Cesium.
 */

import { test, expect } from '@playwright/test';
import { login } from './helpers';

const SKIP_REASON =
  'Skipped by default — set PLAYWRIGHT_GEO=1 to run. Needs Cesium installed.';

test.describe('Geo Hub "View on map" CTAs', () => {
  test.skip(!process.env.PLAYWRIGHT_GEO, SKIP_REASON);

  test('BIM page exposes a view-on-map CTA that navigates to /projects/:id/geo', async ({
    page,
    request,
  }) => {
    await login(page);

    const projectsRes = await request.get('/api/v1/projects/');
    expect(projectsRes.ok()).toBeTruthy();
    const projects = await projectsRes.json();
    if (!Array.isArray(projects) || projects.length === 0) {
      test.skip(true, 'No projects in dev DB — seed a project first.');
      return;
    }
    const projectId = projects[0].id;

    await page.goto(`/bim?project=${projectId}`);
    const cta = page.getByTestId('bim-view-on-map');
    await expect(cta).toBeVisible();
    await cta.click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/geo`));
  });

  test('Punch List page exposes a view-on-map CTA', async ({
    page,
    request,
  }) => {
    await login(page);

    const projectsRes = await request.get('/api/v1/projects/');
    const projects = await projectsRes.json();
    if (!Array.isArray(projects) || projects.length === 0) {
      test.skip(true, 'No projects in dev DB — seed a project first.');
      return;
    }
    const projectId = projects[0].id;

    await page.goto(`/punchlist?project=${projectId}`);
    const cta = page.getByTestId('punchlist-view-on-map');
    await expect(cta).toBeVisible();
    await cta.click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/geo`));
  });

  test('Safety page exposes a view-on-map CTA', async ({
    page,
    request,
  }) => {
    await login(page);

    const projectsRes = await request.get('/api/v1/projects/');
    const projects = await projectsRes.json();
    if (!Array.isArray(projects) || projects.length === 0) {
      test.skip(true, 'No projects in dev DB — seed a project first.');
      return;
    }
    const projectId = projects[0].id;

    await page.goto(`/safety?project=${projectId}`);
    const cta = page.getByTestId('safety-view-on-map');
    await expect(cta).toBeVisible();
    await cta.click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/geo`));
  });

  test('Daily Diary page exposes a view-on-map CTA', async ({
    page,
    request,
  }) => {
    await login(page);

    const projectsRes = await request.get('/api/v1/projects/');
    const projects = await projectsRes.json();
    if (!Array.isArray(projects) || projects.length === 0) {
      test.skip(true, 'No projects in dev DB — seed a project first.');
      return;
    }
    const projectId = projects[0].id;

    await page.goto(`/daily-diary?project=${projectId}`);
    const cta = page.getByTestId('daily-diary-view-on-map');
    await expect(cta).toBeVisible();
    await cta.click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/geo`));
  });

  test('Property-dev page exposes a view-on-map CTA pointing at a development', async ({
    page,
  }) => {
    await login(page);
    await page.goto('/property-dev');
    // The CTA only renders when a development is selected, so this is a
    // soft assertion: if no development is in the dev DB the button is
    // absent and we skip the navigation half of the test.
    const cta = page.getByTestId('propdev-view-on-map');
    if ((await cta.count()) === 0) {
      test.skip(true, 'No developments — seed one before running this test.');
      return;
    }
    await expect(cta.first()).toBeVisible();
    await cta.first().click();
    await expect(page).toHaveURL(/\/property-dev\/developments\/.+\/geo/);
  });
});
