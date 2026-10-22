// Accessibility measure of the component kit (plan UI-P gate: axe <= 5 per theme).
// Runs against the dev server's `/dev/ui` page, which needs no login and no deploy:
//   (cd langchain-ui && npx vite --port 5179 &)   then   node scripts/ui/axe_kit.mjs
// KIT_URL overrides the address; THEMES narrows the set; SHOTS=1 writes docs/ui/kit-<theme>.png.
import { chromium } from 'playwright-core';
import fs from 'fs'; import os from 'os'; import path from 'path';
const EXE = process.env.CHROMIUM || path.join(os.homedir(), '.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell');
const URL_ = process.env.KIT_URL || 'http://localhost:5179/dev/ui';
const axe = fs.readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');
const themes = (process.env.THEMES || 'graphite,paper,contrast').split(',');
const browser = await chromium.launch({ headless: true, executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const out = {};
const measure = async () => {
  await page.addScriptTag({ content: axe });
  return page.evaluate(async () => {
    const res = await window.axe.run(document, { resultTypes: ['violations'] });
    return res.violations.map(v => ({ id: v.id, nodes: v.nodes.length, first: v.nodes[0]?.target.join(' ') }));
  });
};
for (const theme of themes) {
  await page.goto(URL_, { waitUntil: 'networkidle' });
  await page.evaluate((t) => localStorage.setItem('devflow.appearance', JSON.stringify({ theme: t, accent: 'blue', density: 'comfortable' })), theme);
  await page.goto(URL_, { waitUntil: 'networkidle' }); await page.waitForTimeout(500);
  const pageViolations = await measure();
  // The dialog open as well: a modal is measured in the state a person meets it.
  await page.getByRole('button', { name: 'Open a dialog' }).click(); await page.waitForTimeout(200);
  const dialogViolations = await measure();
  await page.keyboard.press('Escape');
  // The command palette with its runs listed, and the shortcuts sheet.
  await page.keyboard.press('Control+k'); await page.getByRole('listbox', { name: 'Commands' }).getByRole('option').first().waitFor();
  const paletteViolations = await measure();
  await page.keyboard.press('Escape');
  await page.locator('body').focus(); await page.keyboard.press('?'); await page.waitForTimeout(200);
  const sheetViolations = await measure();
  await page.keyboard.press('Escape');
  const all = [...pageViolations, ...dialogViolations, ...paletteViolations, ...sheetViolations];
  out[theme] = { total: all.reduce((sum, v) => sum + v.nodes, 0), page: pageViolations, dialog: dialogViolations,
    palette: paletteViolations, sheet: sheetViolations,
    theme_attr: await page.evaluate(() => document.documentElement.dataset.theme) };
  if (process.env.SHOTS) { fs.mkdirSync('docs/ui', { recursive: true }); await page.screenshot({ path: `docs/ui/kit-${theme}.png`, fullPage: true }); }
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
process.exit(Object.values(out).some(r => r.total > 5) ? 1 : 0);
