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

  // Wide viewport sweep — capture page in vertical bands.
  await page.setViewportSize({ width: 1920, height: 1100 });
  await page.goto('http://localhost:5180/about', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Dismiss any onboarding tour modal.
  const closeTour = page.getByRole('button', { name: /close|skip/i });
  if (await closeTour.count()) {
    await closeTour.first().click().catch(() => {});
    await page.waitForTimeout(300);
  }
  // Press Escape to be safe.
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);

  const sections = [
    { name: 'band1-header-stats', y: 0 },
    { name: 'band2-about-project', y: 700 },
    { name: 'band3-consulting', y: 1500 },
    { name: 'band4-support', y: 2300 },
    { name: 'band5-guidebook', y: 3000 },
    { name: 'band6-docs-license', y: 3800 },
    { name: 'band7-changelog', y: 4500 },
  ];
  for (const s of sections) {
    await page.evaluate(y => window.scrollTo(0, y), s.y);
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `qa-tests/_about-wide-${s.name}.png`,
      fullPage: false,
    });
    console.log(`OK ${s.name} y=${s.y}`);
  }

  await browser.close();
}
main().catch(e => { console.error(e); process.exit(1); });
