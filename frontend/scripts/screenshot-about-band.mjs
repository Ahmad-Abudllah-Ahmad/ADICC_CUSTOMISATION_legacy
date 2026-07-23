import { chromium } from '@playwright/test';

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://localhost:5180/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const demoBtn = page.getByText('Admin', { exact: false }).first();
  if (await demoBtn.count()) {
    await demoBtn.click();
    await page.waitForTimeout(800);
  }
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  if (await signInBtn.count()) {
    await signInBtn.first().click();
    await page.waitForTimeout(2000);
  }

  await page.setViewportSize({ width: 1920, height: 1100 });
  await page.goto('http://localhost:5180/about', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);

  // Pin scope to the Documentation card (heading match with role) → scroll the 2-col band into view.
  const docHeading = page.getByRole('heading', { name: /^Documentation$/ });
  await docHeading.first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);

  // Bump up so the card top is visible, not chopped.
  await page.evaluate(() => window.scrollBy(0, -150));
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'qa-tests/_about-band-docs-license.png', fullPage: false });
  console.log('OK docs-license band');

  const supportHeading = page.getByRole('heading', { name: /Support OpenConstructionERP/i });
  await supportHeading.first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.evaluate(() => window.scrollBy(0, -120));
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'qa-tests/_about-band-support.png', fullPage: false });
  console.log('OK support band');

  const platformHeading = page.getByRole('heading', { name: /Platform Capabilities/i });
  await platformHeading.first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.evaluate(() => window.scrollBy(0, -200));
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'qa-tests/_about-band-header-platform.png', fullPage: false });
  console.log('OK platform band');

  await browser.close();
}
main().catch(e => { console.error(e); process.exit(1); });
