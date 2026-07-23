/**
 * E2E happy-path for the Geo Hub module.
 *
 * Steps:
 *  - Log in as the test user.
 *  - Visit /geo (the global all-projects map).
 *  - Verify the page heading renders and the Cesium container mounts.
 *  - Verify the sidebar Geo Hub entry is present.
 *
 * Skipped in CI by default because the headless Cesium viewer needs
 * a Cesium ion key for the default terrain provider — without one the
 * ellipsoid terrain fallback paints a flat earth, which is what we
 * actually want for the test. Run locally with PLAYWRIGHT_GEO=1.
 */

import { test, expect } from '@playwright/test';
import { login } from './helpers';

const SKIP_REASON =
  'Skipped by default — set PLAYWRIGHT_GEO=1 to run. Needs Cesium installed.';

test.describe('Geo Hub happy-path', () => {
  test.skip(!process.env.PLAYWRIGHT_GEO, SKIP_REASON);

  test('sidebar shows Geo Hub entry after login', async ({ page }) => {
    await login(page);
    await expect(page.getByRole('link', { name: /geo hub/i })).toBeVisible();
  });

  test('/geo page renders the Cesium container', async ({ page }) => {
    await login(page);
    await page.goto('/geo');
    await expect(
      page.getByRole('heading', { name: /geo hub/i }),
    ).toBeVisible();
    // The viewer container always renders (even before Cesium loads).
    await expect(
      page.getByTestId('geo-hub-cesium-container'),
    ).toBeVisible();
  });

  test('/projects/:projectId/geo loads the per-project bundle', async ({
    page, request,
  }) => {
    await login(page);
    // Pick the first project the user can see.
    const projectsRes = await request.get('/api/v1/projects/');
    expect(projectsRes.ok()).toBeTruthy();
    const projects = await projectsRes.json();
    if (!Array.isArray(projects) || projects.length === 0) {
      test.skip(true, 'No projects in dev DB — seed a project first.');
      return;
    }
    const projectId = projects[0].id;

    await page.goto(`/projects/${projectId}/geo`);
    await expect(
      page.getByRole('heading', { name: /project map/i }),
    ).toBeVisible();
    await expect(
      page.getByTestId('geo-hub-cesium-container'),
    ).toBeVisible();
  });
});
