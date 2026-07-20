import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('https://adicc-uae.com', { waitUntil: 'networkidle' });

// Find Pricing link in nav
const links = await page.$$eval('a', (as) => as.filter(a => a.textContent?.trim() === 'Pricing').map(a => ({
  href: a.getAttribute('href'),
  text: a.textContent.trim(),
  visible: a.offsetParent !== null,
})));
console.log('Pricing links found:', JSON.stringify(links, null, 2));

// Try clicking the visible nav Pricing link
const navPricing = await page.$('.nav-links a[href="#pricing"]');
console.log('nav .nav-links Pricing exists:', !!navPricing);
if (navPricing) {
  const beforeY = await page.evaluate(() => window.scrollY);
  await navPricing.click();
  await page.waitForTimeout(1500);
  const afterY = await page.evaluate(() => window.scrollY);
  const targetTop = await page.evaluate(() => {
    const el = document.getElementById('pricing');
    if (!el) return 'NO TARGET';
    const r = el.getBoundingClientRect();
    return { offsetTop: el.offsetTop, top: r.top };
  });
  const url = page.url();
  console.log('Before scroll Y:', beforeY);
  console.log('After scroll Y:', afterY);
  console.log('Pricing target:', JSON.stringify(targetTop));
  console.log('URL after click:', url);
}
await browser.close();
