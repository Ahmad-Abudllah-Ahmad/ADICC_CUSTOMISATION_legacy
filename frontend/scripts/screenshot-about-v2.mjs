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

  const closeTour = page.getByRole('button', { name: /close|skip/i });
  if (await closeTour.count()) {
    await closeTour.first().click().catch(() => {});
    await page.waitForTimeout(300);
  }
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);

  // First — measure actual page height to derive band y positions.
  const docs = await page.evaluate(() => document.documentElement.scrollHeight);
  console.log('page height =', docs);

  // Anchor on the section H2 texts so it doesn't drift when content moves.
  const anchors = [
    { name: 'header', selector: 'h1:has-text("OpenConstructionERP")' },
    { name: 'platform', selector: 'h2:has-text("Platform Capabilities")' },
    { name: 'about-project', selector: 'h2:has-text("About the project")' },
    { name: 'consulting', selector: 'h2:has-text("Consulting")' },
    { name: 'support', selector: 'h2:has-text("Support OpenConstructionERP")' },
    { name: 'guidebook', selector: 'h2:has-text("Data-Driven Construction")' },
    { name: 'docs', selector: 'h2:has-text("Documentation")' },
    { name: 'license', selector: 'h2:has-text("License & Open Source")' },
  ];

  for (const a of anchors) {
    const loc = page.locator(a.selector).first();
    const count = await loc.count();
    if (!count) {
      console.log(`  MISS ${a.name}: selector not found`);
      continue;
    }
    const box = await loc.boundingBox();
    if (!box) {
      console.log(`  MISS ${a.name}: no bounding box`);
      continue;
    }
    const target = Math.max(0, Math.round(box.y - 60));
    await page.evaluate(y => window.scrollTo(0, y), target);
    await page.waitForTimeout(350);
    await page.screenshot({
      path: `qa-tests/_about-v2-${a.name}.png`,
      fullPage: false,
    });
    console.log(`  OK ${a.name} y=${target}`);
  }

  await browser.close();
}
main().catch(e => { console.error(e); process.exit(1); });
