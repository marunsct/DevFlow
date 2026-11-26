const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // Start from the dev server that playwright test:acceptance starts
  // We'll just open about:blank and inject the app
  // Actually, let's just check what the Vite dev server serves
  await page.goto('http://127.0.0.1:5173/');
  
  // Wait a bit for the page to load
  await page.waitForTimeout(1000);
  
  // Check all buttons and their computed background colors
  const buttons = await page.locator('button').all();
  console.log('=== Button styles ===');
  for (const btn of buttons) {
    const name = await btn.textContent().catch(() => '???');
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const bgOrigin = await btn.evaluate(el => {
      // Check if inline style is set
      const inlineBg = el.style.backgroundColor;
      const computedBg = getComputedStyle(el).backgroundColor;
      return { inlineBg, computedBg };
    });
    console.log(`Button: "${name}" -> bgColor: ${bg}, inline: ${JSON.stringify(bgOrigin)}`);
  }
  
  // Also check the specific filter buttons
  console.log('\n=== Filter buttons specifically ===');
  for (const name of ['All', 'Active', 'Completed']) {
    const btn = page.getByRole('button', { name, exact: true });
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    console.log(`[${name}] computed bgColor: ${bg}, inline: "${inlineBg}"`);
  }
  
  await browser.close();
})();
