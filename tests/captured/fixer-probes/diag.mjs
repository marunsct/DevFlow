import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage();

// Start the Vite dev server ourselves for this diagnostic
const { spawn } = await import('child_process');
const vite = spawn('npx', ['vite', 'dev', '--port', '5174', '--host', '127.0.0.1'], {
  cwd: '/workspace/simple-to-do-list-app',
  stdio: 'pipe'
});

await new Promise(r => setTimeout(r, 3000));

try {
  await page.goto('http://127.0.0.1:5174/');
  await page.waitForTimeout(1000);

  // Check all buttons and their computed background colors
  console.log('=== Button styles (initial, filter=all) ===');
  const buttons = await page.locator('button').all();
  for (const btn of buttons) {
    const name = await btn.textContent().catch(() => '???');
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    console.log(`Button: "${name.trim()}" -> computed bgColor: ${bg}, inline: "${inlineBg}"`);
  }

  // Click "Active" filter
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await page.waitForTimeout(500);

  console.log('\n=== Button styles (after clicking Active) ===');
  const buttons2 = await page.locator('button').all();
  for (const btn of buttons2) {
    const name = await btn.textContent().catch(() => '???');
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    const styleAttr = await btn.evaluate(el => el.getAttribute('style'));
    console.log(`Button: "${name.trim()}" -> computed bgColor: ${bg}, inline: "${inlineBg}", attr: "${styleAttr?.substring(0, 120)}..."`);
  }

} finally {
  vite.kill();
  await browser.close();
}
