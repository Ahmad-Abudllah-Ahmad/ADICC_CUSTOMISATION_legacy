/**
 * Single re-export so specs use one import to get every fixture:
 *
 *   import { test, expect } from '../fixtures';
 *
 * Composition chain (Playwright merges parent fixtures automatically):
 *   auth → api → tenant → screenshot → seed
 *
 * So a spec that imports `test` here has access to every fixture above.
 */
export { test, expect } from './seed.fixture';
export { DEMO_USER } from './auth.fixture';
export { API_URL } from './api.fixture';
export type { TypedApiClient } from './api.fixture';
export type { Project } from './tenant.fixture';
export type { ScreenshotHelper } from './screenshot.fixture';
export { SCREENSHOT_ROOT } from './screenshot.fixture';
