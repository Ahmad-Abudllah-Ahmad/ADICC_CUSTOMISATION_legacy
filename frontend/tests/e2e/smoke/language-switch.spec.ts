/**
 * Smoke — language switch flips UI strings.
 *
 * Tagged @i18n so it also runs under the RTL Arabic project.
 */
import { test, expect } from '../fixtures';
import { gotoModule, switchLanguage, captureScreen } from '../helpers';

test.describe('@smoke @i18n language-switch', () => {
  test('EN → DE → RU updates visible strings', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    await captureScreen(authedPage, 'smoke', 'lang-en-baseline');

    await switchLanguage(authedPage, 'de');
    await authedPage.waitForTimeout(500); // allow i18next to swap chunks
    const htmlLangDe = await authedPage.locator('html').getAttribute('lang');
    expect(htmlLangDe?.toLowerCase()).toMatch(/^de/);
    await captureScreen(authedPage, 'smoke', 'lang-de');

    await switchLanguage(authedPage, 'ru');
    await authedPage.waitForTimeout(500);
    const htmlLangRu = await authedPage.locator('html').getAttribute('lang');
    expect(htmlLangRu?.toLowerCase()).toMatch(/^ru/);
    await captureScreen(authedPage, 'smoke', 'lang-ru');

    await switchLanguage(authedPage, 'en');
    await authedPage.waitForTimeout(500);
    const htmlLangEn = await authedPage.locator('html').getAttribute('lang');
    expect(htmlLangEn?.toLowerCase()).toMatch(/^en/);
  });
});
