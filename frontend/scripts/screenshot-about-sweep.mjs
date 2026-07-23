import { chromium } from '@playwright/test';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://localhost:5180/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const demoBtn = page.getByText('Admin', { exact: false }).first();
  if (await demoBtn.count()) { await demoBtn.click(); await page.waitForTimeout(1000); }
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  if (await signInBtn.count()) { await signInBtn.first().click(); await page.waitForTimeout(2500); }
  await page.setViewportSize({ width: 1920, height: 1100 });
  await page.goto('http://localhost:5180/about', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);

  for (let i = 0; i < 8; i++) {
    const y = i * 900;
    await page.evaluate(yy => window.scrollTo(0, yy), y);
    await page.waitForTimeout(350);
    await page.screenshot({ path: `qa-tests/_sweep-${String(i).padStart(2,'0')}-y${y}.png`, fullPage: false });
    console.log('y=' + y);
  }
  await browser.close();
})();
