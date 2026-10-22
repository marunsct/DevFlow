// Hidden acceptance tests for the fullstack-bookmarks benchmark, written from
// brief.md's Interface; never shown to the harness. Tests share one service,
// so each uses its own unique titles.
import { test, expect } from '@playwright/test';

const unique = (word) => `${word} ${Math.random().toString(36).slice(2, 8)}`;
const item = (page, title) => page.getByRole('listitem').filter({ hasText: title });

// A user saves one bookmark, sees it appear, then saves the next: a valid save
// waits for its item, as the person would.
async function save(page, title, url, tag = '', { valid = true } = {}) {
  await page.getByLabel('Title', { exact: true }).fill(title);
  await page.getByLabel('URL', { exact: true }).fill(url);
  await page.getByLabel('Tag', { exact: true }).fill(tag);
  await page.getByRole('button', { name: 'Save bookmark', exact: true }).click();
  if (valid) await expect(item(page, title)).toHaveCount(1);
}

test('saves a bookmark from the page and links to it', async ({ page }) => {
  const title = unique('Docs');
  await page.goto('/');
  await save(page, title, 'https://example.com/docs', 'work');
  await expect(item(page, title)).toHaveCount(1);
  await expect(item(page, title).getByRole('link', { name: title })).toHaveAttribute('href', 'https://example.com/docs');
  await expect(item(page, title)).toContainText('work');
});

test('the list survives a reload', async ({ page }) => {
  const title = unique('Kept');
  await page.goto('/');
  await save(page, title, 'https://example.com/kept');
  await expect(item(page, title)).toHaveCount(1);
  await page.reload();
  await expect(item(page, title)).toHaveCount(1);
});

test('refuses a bookmark without a title or with a bad URL', async ({ page, request }) => {
  const title = unique('Bad');
  await page.goto('/');
  await save(page, title, 'not-a-url', '', { valid: false });
  await save(page, '', 'https://example.com/untitled', '', { valid: false });
  await page.reload();
  await expect(item(page, title)).toHaveCount(0);
  const all = await (await request.get('/api/bookmarks')).json();
  expect(all.some((b) => b.title === title || b.url === 'https://example.com/untitled')).toBe(false);
});

test('deletes a bookmark from the page', async ({ page }) => {
  const title = unique('Gone');
  await page.goto('/');
  await save(page, title, 'https://example.com/gone');
  await item(page, title).getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(item(page, title)).toHaveCount(0);
  await page.reload();
  await expect(item(page, title)).toHaveCount(0);
});

test('filters the list by tag', async ({ page }) => {
  const tag = unique('tag').replace(' ', '-');
  const tagged = unique('Tagged');
  const other = unique('Other');
  await page.goto('/');
  await save(page, tagged, 'https://example.com/a', tag);
  await save(page, other, 'https://example.com/b', 'misc');
  await page.getByLabel('Filter by tag').fill(tag);
  await expect(item(page, tagged)).toHaveCount(1);
  await expect(item(page, other)).toHaveCount(0);
  await page.getByLabel('Filter by tag').fill('');
  await expect(item(page, other)).toHaveCount(1);
});

test('the API creates, lists newest first and deletes', async ({ request }) => {
  const first = await request.post('/api/bookmarks', { data: { title: unique('First'), url: 'https://a.example', tag: '' } });
  expect(first.status()).toBe(201);
  const second = await request.post('/api/bookmarks', { data: { title: unique('Second'), url: 'https://b.example', tag: 'x' } });
  const created = await second.json();
  const listed = await (await request.get('/api/bookmarks')).json();
  expect(listed[0].id).toBe(created.id);
  expect((await request.delete(`/api/bookmarks/${created.id}`)).status()).toBe(204);
  expect((await request.delete(`/api/bookmarks/${created.id}`)).status()).toBe(404);
});

test('the API refuses invalid input', async ({ request }) => {
  for (const data of [{ title: '', url: 'https://x.example' }, { title: 'No scheme', url: 'x.example' }]) {
    const response = await request.post('/api/bookmarks', { data });
    expect([400, 422]).toContain(response.status());
  }
});

test('the page shows bookmarks newest first', async ({ page }) => {
  const older = unique('Older');
  const newer = unique('Newer');
  await page.goto('/');
  await save(page, older, 'https://example.com/older');
  await save(page, newer, 'https://example.com/newer');
  await expect(item(page, newer)).toHaveCount(1);
  const titles = await page.getByRole('listitem').allInnerTexts();
  const position = (t) => titles.findIndex((text) => text.includes(t));
  expect(position(newer)).toBeLessThan(position(older));
});
