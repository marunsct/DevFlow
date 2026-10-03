// Hidden acceptance tests for the web-todo benchmark. Written from brief.md's
// Interface section; never shown to the harness.
import { test, expect } from '@playwright/test';

async function add(page, title, description = '') {
  await page.getByLabel('Title', { exact: true }).fill(title);
  if (description) await page.getByLabel('Description', { exact: true }).fill(description);
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
}

const item = (page, title) => page.getByRole('listitem').filter({ hasText: title });

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('adds a task with its title and description', async ({ page }) => {
  await add(page, 'Buy milk', 'Two litres');
  await expect(item(page, 'Buy milk')).toHaveCount(1);
  await expect(item(page, 'Buy milk')).toContainText('Two litres');
});

test('refuses a task without a title', async ({ page }) => {
  await add(page, '', 'No title here');
  await expect(page.getByRole('listitem').filter({ hasText: 'No title here' })).toHaveCount(0);
});

test('tasks persist across a reload', async ({ page }) => {
  await add(page, 'First task');
  await add(page, 'Second task');
  await page.reload();
  await expect(item(page, 'First task')).toHaveCount(1);
  await expect(item(page, 'Second task')).toHaveCount(1);
});

test('marks a task complete and keeps it complete after a reload', async ({ page }) => {
  await add(page, 'Water plants');
  await item(page, 'Water plants').getByLabel('Done').check();
  await page.reload();
  await expect(item(page, 'Water plants').getByLabel('Done')).toBeChecked();
  await item(page, 'Water plants').getByLabel('Done').uncheck();
  await page.reload();
  await expect(item(page, 'Water plants').getByLabel('Done')).not.toBeChecked();
});

test('edits a task title and keeps the edit after a reload', async ({ page }) => {
  await add(page, 'Old name');
  await item(page, 'Old name').getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Edit title').fill('New name');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(item(page, 'New name')).toHaveCount(1);
  await expect(item(page, 'Old name')).toHaveCount(0);
  await page.reload();
  await expect(item(page, 'New name')).toHaveCount(1);
});

test('deletes a task and it stays deleted after a reload', async ({ page }) => {
  await add(page, 'Keep me');
  await add(page, 'Remove me');
  await item(page, 'Remove me').getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(item(page, 'Remove me')).toHaveCount(0);
  await page.reload();
  await expect(item(page, 'Remove me')).toHaveCount(0);
  await expect(item(page, 'Keep me')).toHaveCount(1);
});

test('filters by active and completed', async ({ page }) => {
  await add(page, 'Open task');
  await add(page, 'Finished task');
  await item(page, 'Finished task').getByLabel('Done').check();
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await expect(item(page, 'Open task')).toHaveCount(1);
  await expect(item(page, 'Finished task')).toHaveCount(0);
  await page.getByRole('button', { name: 'Completed', exact: true }).click();
  await expect(item(page, 'Open task')).toHaveCount(0);
  await expect(item(page, 'Finished task')).toHaveCount(1);
  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(item(page, 'Open task')).toHaveCount(1);
  await expect(item(page, 'Finished task')).toHaveCount(1);
});

test('a task completed while filtered to active leaves the active list', async ({ page }) => {
  await add(page, 'Soon done');
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  // A click, not check(): the item may leave the list the moment it is done.
  await item(page, 'Soon done').getByLabel('Done').click();
  await expect(item(page, 'Soon done')).toHaveCount(0);
});

test('works on a phone-sized screen without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await page.reload();
  await add(page, 'Mobile task', 'From a phone');
  await expect(item(page, 'Mobile task')).toHaveCount(1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('declares a viewport for mobile browsers', async ({ page }) => {
  await expect(page.locator('meta[name="viewport"]')).toHaveCount(1);
});
