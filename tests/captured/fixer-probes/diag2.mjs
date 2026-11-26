import { chromium } from '@playwright/test';
import { spawn } from 'child_process';

const vite = spawn('npx', ['vite', 'dev', '--port', '5174', '--host', '127.0.0.1'], {
  cwd: '/workspace/simple-to-do-list-app',
  stdio: 'pipe',
  env: process.env
});

await new Promise(r => setTimeout(r, 3000));

const browser = await chromium.launch();
const page = await browser.newPage();

try {
  await page.goto('http://127.0.0.1:5174/');
  await page.waitForTimeout(1000);

  console.log('=== Initial state (filter=all) ===');
  const buttons = await page.locator('button').all();
  for (const btn of buttons) {
    const name = (await btn.textContent() || '').trim();
    if (!name) continue;
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    console.log(`[${name}] computedBg=${bg} inlineBg="${inlineBg}"`);
  }

  // Create a task
  await page.fill('input[aria-label="Title"]', 'Test task');
  await page.click('button:has-text("Add task")');
  await page.waitForTimeout(500);

  console.log('\n=== After adding task ===');
  const buttons2 = await page.locator('button').all();
  for (const btn of buttons2) {
    const name = (await btn.textContent() || '').trim();
    if (!name) continue;
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    console.log(`[${name}] computedBg=${bg} inlineBg="${inlineBg}"`);
  }

  // Click Active filter
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await page.waitForTimeout(500);

  console.log('\n=== After clicking Active ===');
  const buttons3 = await page.locator('button').all();
  for (const btn of buttons3) {
    const name = (await btn.textContent() || '').trim();
    if (!name) continue;
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    console.log(`[${name}] computedBg=${bg} inlineBg="${inlineBg}"`);
  }

  // Check the actual filter buttons specifically
  console.log('\n=== Filter buttons detail ===');
  for (const name of ['All', 'Active', 'Completed']) {
    const btn = page.getByRole('button', { name, exact: true });
    const bg = await btn.evaluate(el => getComputedStyle(el).backgroundColor);
    const inlineBg = await btn.evaluate(el => el.style.backgroundColor);
    const styleAttr = await btn.evaluate(el => el.getAttribute('style'));
    console.log(`[${name}] computedBg=${bg} inlineBg="${inlineBg}"`);
    console.log(`  style attr: ${styleAttr}`);
  }

} finally {
  vite.kill();
  await browser.close();
}
