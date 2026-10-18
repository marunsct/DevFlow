// Accessibility measurement of the live UI (UI audit 2026-10-18): axe violations,
// live regions and nameless buttons on Home, Runs, Settings and one run's dashboard.
//   npm install --prefix scripts/ui playwright-core axe-core
//   node scripts/ui/axe_measure.mjs <run-id>
// Credentials: the loop operator from docs/HANDOVER.md §3 (UI_USER / UI_PASSWORD).
import { chromium } from 'playwright-core';
import fs from 'fs'; import os from 'os'; import path from 'path';
const EXE = process.env.CHROMIUM || path.join(os.homedir(), '.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell');
const BASE = 'http://localhost:8000';
const axe = fs.readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');
const USER = process.env.UI_USER || 'harness-test';
const PASSWORD = process.env.UI_PASSWORD || '';
const run = process.argv[2];
const browser = await chromium.launch({ headless: true, executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
await page.fill('input[type="text"]', USER);
await page.fill('input[type="password"]', PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL(u => !u.pathname.startsWith('/login'), { timeout: 15000 });
// Each theme (plan Part 15.2): axe on every page, and a screenshot of each into docs/ui/
// when SHOTS=1, for the handover. THEMES=graphite,paper narrows the set.
const themes = (process.env.THEMES || 'graphite,paper,contrast').split(',');
const out = {};
for (const theme of themes) {
  await page.evaluate((t) => localStorage.setItem('devflow.appearance', JSON.stringify({ theme: t, accent: 'blue', density: 'comfortable' })), theme);
  for (const [name, url] of [['home', '/'], ['runs', '/runs'], ['settings', '/settings'], ['run', `/runs/${run}`]]) {
    await page.goto(BASE + url, { waitUntil: 'networkidle' }); await page.waitForTimeout(2500);
    await page.addScriptTag({ content: axe });
    const r = await page.evaluate(async () => { const res = await window.axe.run(document, { resultTypes: ['violations'] }); return res.violations.map(v => [v.id, v.nodes.length]); });
    if (process.env.DETAIL) {
      const detail = await page.evaluate(async () => { const res = await window.axe.run(document, { resultTypes: ['violations'] });
        return res.violations.flatMap(v => v.nodes.slice(0, 4).map(n => `${v.id}: ${n.target.join(' ')} :: ${(n.any[0]?.message || n.failureSummary || '').slice(0, 150)}`)); });
      console.error(`--- ${theme}/${name}\n` + detail.join('\n'));
    }
    const live = await page.locator('[aria-live],[role="status"],[role="alert"],[role="log"]').count();
    const unlabeled = await page.evaluate(() => [...document.querySelectorAll('button')].filter(b => !(b.getAttribute('aria-label') || b.textContent.trim() || b.getAttribute('title'))).length);
    out[`${theme}/${name}`] = { violations: Object.fromEntries(r), total: r.reduce((a, [, n]) => a + n, 0), live, unlabeled_buttons: unlabeled, theme_attr: await page.evaluate(() => document.documentElement.dataset.theme) };
    if (process.env.SHOTS) {
      fs.mkdirSync('docs/ui', { recursive: true });
      await page.screenshot({ path: `docs/ui/${theme}-${name}.png`, fullPage: false });
    }
  }
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
