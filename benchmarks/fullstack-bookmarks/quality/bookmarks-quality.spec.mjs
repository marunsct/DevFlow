// Quality tests for the bookmarks benchmarks: the brief held to its edges. Run
// by the scorer beside the hidden tests, never shown to the harness. Tests share
// one service, so each uses its own unique titles.
import { test, expect } from '@playwright/test';

const unique = (word) => `${word} ${Math.random().toString(36).slice(2, 8)}`;
const item = (page, title) => page.getByRole('listitem').filter({ hasText: title });
const titles = async (request) => (await (await request.get('/api/bookmarks')).json()).map((b) => b.title);

async function save(page, title, url, tag = '') {
  await page.getByLabel('Title', { exact: true }).fill(title);
  await page.getByLabel('URL', { exact: true }).fill(url);
  await page.getByLabel('Tag', { exact: true }).fill(tag);
  await page.getByRole('button', { name: 'Save bookmark', exact: true }).click();
}

test('markup in a title is shown as text and never run', async ({ page }) => {
  const title = `<img src=x onerror="window.__ran=1"><b>${unique('Bold')}</b>`;
  await page.goto('/');
  await save(page, title, 'https://example.com/markup');
  await expect(page.getByRole('listitem').filter({ hasText: title })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('listitem').filter({ hasText: title })).toHaveCount(1);
  expect(await page.evaluate(() => window.__ran)).toBeUndefined();
});

test('a body that is not JSON is refused and nothing is stored', async ({ request }) => {
  const before = (await titles(request)).length;
  const response = await request.post('/api/bookmarks', {
    headers: { 'Content-Type': 'application/json' }, data: '{"title": "Broken", "url": ',
  });
  expect([400, 422]).toContain(response.status());
  expect((await titles(request)).length).toBe(before);
});

test('fields of the wrong type are refused and the service keeps answering', async ({ request }) => {
  for (const data of [{ title: 'Url as a list', url: ['https://x.example'] }, ['https://a.example'],
    { title: { text: 'An object' }, url: 'https://o.example' }]) {
    const response = await request.post('/api/bookmarks', { data });
    expect([400, 422]).toContain(response.status());
  }
  expect((await request.get('/api/bookmarks')).status()).toBe(200);
});

test('a title of only spaces is refused', async ({ request }) => {
  const response = await request.post('/api/bookmarks', { data: { title: '   ', url: 'https://blank.example' } });
  expect([400, 422]).toContain(response.status());
});

test('twenty bookmarks saved at once are all kept', async ({ request }) => {
  const batch = Array.from({ length: 20 }, (_, i) => unique(`Batch ${i}`));
  const answers = await Promise.all(batch.map((title) => request.post('/api/bookmarks', { data: { title, url: 'https://batch.example', tag: 'batch' } })));
  expect(answers.map((a) => a.status())).toEqual(batch.map(() => 201));
  const ids = new Set(await Promise.all(answers.map(async (a) => (await a.json()).id)));
  expect(ids.size).toBe(20);
  const kept = await titles(request);
  expect(batch.filter((title) => !kept.includes(title))).toEqual([]);
});

test('text in any script is kept as written', async ({ request, page }) => {
  const title = unique('Café ☕ 日本語 🎉');
  const created = await request.post('/api/bookmarks', { data: { title, url: 'https://example.com/ü', tag: 'ελληνικά' } });
  expect(created.status()).toBe(201);
  await page.goto('/');
  await expect(item(page, title)).toHaveCount(1);
  await expect(item(page, title)).toContainText('ελληνικά');
});

test('a delete of an id that is not a number is refused, and deletes nothing', async ({ request }) => {
  const before = (await titles(request)).length;
  expect([400, 404, 422]).toContain((await request.delete('/api/bookmarks/not-a-number')).status());
  expect((await titles(request)).length).toBe(before);
});
