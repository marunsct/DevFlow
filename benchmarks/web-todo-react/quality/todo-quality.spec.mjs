// Quality tests for the web-todo benchmark: the brief held to its edges. Run by
// the scorer beside the hidden tests, never shown to the harness.
import { test, expect } from '@playwright/test';

async function add(page, title, description = '') {
  await page.getByLabel('Title', { exact: true }).fill(title);
  await page.getByLabel('Description', { exact: true }).fill(description);
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
}

const item = (page, title) => page.getByRole('listitem').filter({ hasText: title });

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('a title of only spaces is not a title', async ({ page }) => {
  await add(page, '   ', 'Blank title');
  await expect(page.getByRole('listitem').filter({ hasText: 'Blank title' })).toHaveCount(0);
});

test('markup in a title is shown as text and never run', async ({ page }) => {
  const title = '<img src=x onerror="window.__ran=1"><b>Bold</b>';
  await add(page, title, 'Markup');
  await expect(page.getByRole('listitem').filter({ hasText: '<b>Bold</b>' })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('listitem').filter({ hasText: '<b>Bold</b>' })).toHaveCount(1);
  expect(await page.evaluate(() => window.__ran)).toBeUndefined();
});

test('an edit to an empty title leaves a titled task', async ({ page }) => {
  await add(page, 'Named task');
  await item(page, 'Named task').getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Edit title').fill('');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.reload();
  const texts = await page.getByRole('listitem').allInnerTexts();
  expect(texts.length).toBe(1);
  expect(texts[0]).toContain('Named task');
});

test('text in any script is kept as written across a reload', async ({ page }) => {
  await add(page, 'Café ☕ 日本語', 'Ελληνικά — emoji 🎉');
  await page.reload();
  await expect(item(page, 'Café ☕ 日本語')).toHaveCount(1);
  await expect(item(page, 'Café ☕ 日本語')).toContainText('Ελληνικά — emoji 🎉');
});

test('a saved list it cannot read does not stop the page working', async ({ page }) => {
  await add(page, 'Before');
  await page.evaluate(() => {
    for (let i = 0; i < localStorage.length; i += 1) localStorage.setItem(localStorage.key(i), '{not json');
  });
  await page.reload();
  await add(page, 'After the damage');
  await expect(item(page, 'After the damage')).toHaveCount(1);
});

test('thirty tasks are all kept across a reload', async ({ page }) => {
  for (let i = 1; i <= 30; i += 1) await add(page, `Item number ${i}.`);
  await page.reload();
  for (const i of [1, 15, 30]) await expect(item(page, `Item number ${i}.`)).toHaveCount(1);
  await expect(page.getByRole('listitem')).toHaveCount(30);
});
