import { test, expect } from '@playwright/test';

// Each test starts a fresh browser context, clears localStorage before the page
// scripts run, and creates every record it acts on, with titles no other test uses.

async function clearStorage({ page }) {
  await page.addInitScript(() => localStorage.clear());
}

// Adds a task through the form as a user does. Waits until the new row is shown
// before returning, so the caller may type into the form again.
async function addTask(page, title, description = '') {
  await page.getByLabel('Title', { exact: true }).fill(title);
  if (description) {
    await page.getByLabel('Description', { exact: true }).fill(description);
  }
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(rowFor(page, title)).toBeVisible();
}

// A list item found by the text it shows. Used with toBeVisible/toHaveCount only,
// so a strict match is not needed: the count assertions prove uniqueness where it matters.
function rowFor(page, title) {
  return page.getByRole('listitem').filter({ hasText: title });
}

function checkboxFor(page, title) {
  return page.getByRole('checkbox', { name: title, exact: true });
}

function deleteButtonFor(page, title) {
  return page.getByRole('button', { name: `Delete task: ${title}`, exact: true });
}

function editButtonIn(page, title) {
  return rowFor(page, title).getByRole('button', { name: 'Edit', exact: true });
}

test('[AC-1] a task added with a title and description is listed with both, at the top, and the form is cleared', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 add title', 'AC1 add description');
  await expect(rowFor(page, 'AC1 add title')).toContainText('AC1 add description');
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Description', { exact: true })).toHaveValue('');
  const titles = await page.getByRole('listitem').allTextContents();
  expect(titles[0]).toContain('AC1 add title');
});

test('[AC-1] a second task can be added from the same page after the first', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 second first', 'AC1 second first desc');
  await addTask(page, 'AC1 second other', 'AC1 second other desc');
  await expect(rowFor(page, 'AC1 second first')).toBeVisible();
  await expect(rowFor(page, 'AC1 second other')).toBeVisible();
});

test('[AC-1][AC-5] a task can be added, edited inline with Save and deleted', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC5 flow original', 'AC5 flow desc');

  await editButtonIn(page, 'AC5 flow original').click();
  const row = rowFor(page, 'AC5 flow original');
  await row.getByLabel('Title', { exact: true }).fill('AC5 flow edited');
  await row.getByRole('button', { name: 'Save', exact: true }).click();

  await expect(rowFor(page, 'AC5 flow edited')).toBeVisible();
  await expect(page.getByText('AC5 flow original', { exact: true })).toHaveCount(0);

  await deleteButtonFor(page, 'AC5 flow edited').click();
  await expect(rowFor(page, 'AC5 flow edited')).toHaveCount(0);
});

test('[AC-1] an inline edit of the title and description is saved with Save and both show in the row', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 desc edit original', 'AC1 desc edit before');
  await editButtonIn(page, 'AC1 desc edit original').click();
  const row = rowFor(page, 'AC1 desc edit original');
  await row.getByLabel('Title', { exact: true }).fill('AC1 desc edit title');
  await row.getByLabel('Description', { exact: true }).fill('AC1 desc edit after');
  await row.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(rowFor(page, 'AC1 desc edit title')).toContainText('AC1 desc edit after');
  await expect(page.getByText('AC1 desc edit before', { exact: true })).toHaveCount(0);
  await expect(page.getByText('AC1 desc edit original', { exact: true })).toHaveCount(0);
});

test('[AC-1] an inline edit is saved with Enter in the title field', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 enter original');
  await editButtonIn(page, 'AC1 enter original').click();
  const row = rowFor(page, 'AC1 enter original');
  await row.getByLabel('Title', { exact: true }).fill('AC1 enter edited');
  await row.getByLabel('Title', { exact: true }).press('Enter');
  await expect(rowFor(page, 'AC1 enter edited')).toBeVisible();
  await expect(page.getByText('AC1 enter original', { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(rowFor(page, 'AC1 enter edited')).toBeVisible();
});

test('[AC-1] an inline edit is cancelled with the Cancel button and nothing changes', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 cancel original', 'AC1 cancel desc');

  await editButtonIn(page, 'AC1 cancel original').click();
  const row = rowFor(page, 'AC1 cancel original');
  await row.getByLabel('Title', { exact: true }).fill('AC1 cancel discarded');
  await row.getByRole('button', { name: 'Cancel', exact: true }).click();

  await expect(rowFor(page, 'AC1 cancel original')).toBeVisible();
  await expect(page.getByText('AC1 cancel discarded', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
  await page.reload();
  await expect(rowFor(page, 'AC1 cancel original')).toBeVisible();
  await expect(page.getByText('AC1 cancel discarded', { exact: true })).toHaveCount(0);
});

test('[AC-1] an inline edit is cancelled with Escape and nothing changes', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 escape original', 'AC1 escape desc');
  await editButtonIn(page, 'AC1 escape original').click();
  const row = rowFor(page, 'AC1 escape original');
  await row.getByLabel('Title', { exact: true }).fill('AC1 escape discarded');
  await row.getByLabel('Title', { exact: true }).press('Escape');
  await expect(rowFor(page, 'AC1 escape original')).toBeVisible();
  await expect(page.getByText('AC1 escape discarded', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
});

test('[AC-1] an inline edit with an empty title is refused and stays in edit mode', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC1 blank edit original');
  await editButtonIn(page, 'AC1 blank edit original').click();
  const row = rowFor(page, 'AC1 blank edit original');
  await row.getByLabel('Title', { exact: true }).fill('   ');
  await row.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Enter a title to add the task.', { exact: true })).toBeVisible();
  await expect(row.getByLabel('Title', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(row.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
});

test('[AC-2] a task can be marked complete and incomplete again', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 toggle title');
  const checkbox = checkboxFor(page, 'AC2 toggle title');
  await checkbox.click();
  await expect(checkbox).toBeChecked();
  await checkbox.click();
  await expect(checkbox).not.toBeChecked();
});

test('[AC-2] a completed task shows struck-through, dimmed title and loses that style when marked incomplete', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 style title');
  const title = page.getByText('AC2 style title', { exact: true });
  const before = await title.evaluate((el) => getComputedStyle(el).textDecorationLine);
  expect(before).not.toContain('line-through');
  await checkboxFor(page, 'AC2 style title').click();
  await expect(checkboxFor(page, 'AC2 style title')).toBeChecked();
  const done = await title.evaluate((el) => ({
    decoration: getComputedStyle(el).textDecorationLine,
    opacity: parseFloat(getComputedStyle(el).opacity),
  }));
  expect(done.decoration).toContain('line-through');
  expect(done.opacity).toBeLessThan(1);
  await checkboxFor(page, 'AC2 style title').click();
  await expect(checkboxFor(page, 'AC2 style title')).not.toBeChecked();
  const undone = await title.evaluate((el) => ({
    decoration: getComputedStyle(el).textDecorationLine,
    opacity: parseFloat(getComputedStyle(el).opacity),
  }));
  expect(undone.decoration).not.toContain('line-through');
  expect(undone.opacity).toBe(1);
});

test('[AC-2][AC-6] a completed task stays completed after a reload', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await addTask(page, 'AC2 reload title');
  await checkboxFor(page, 'AC2 reload title').click();
  await page.reload();
  await expect(checkboxFor(page, 'AC2 reload title')).toBeChecked();
});

test('[AC-2] a task description is shown under its title', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 described title', 'AC2 visible description');
  await expect(page.getByText('AC2 visible description', { exact: true })).toBeVisible();
});

test('[AC-2] the row checkbox is labelled by the task title and its state reads as checked and unchecked', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 labelled checkbox title');
  const checkbox = page.getByRole('checkbox', { name: 'AC2 labelled checkbox title', exact: true });
  await expect(checkbox).toHaveCount(1);
  await expect(checkbox).not.toBeChecked();
  await checkbox.click();
  await expect(checkbox).toBeChecked();
  await expect(rowFor(page, 'AC2 labelled checkbox title')).toHaveCount(1);
});

test('[AC-2] the row shows the description under the title and omits it when empty', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 para title', 'AC2 para description');
  await expect(rowFor(page, 'AC2 para title').getByText('AC2 para description', { exact: true })).toHaveCount(1);
  await addTask(page, 'AC2 no desc title');
  await expect(rowFor(page, 'AC2 no desc title').getByText('AC2 no desc title', { exact: true })).toHaveCount(1);
  await expect(rowFor(page, 'AC2 no desc title').locator('p')).toHaveCount(0);
});

test('[AC-3] deleting a task removes it at once with no confirmation', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC3 delete title');
  let dialogs = 0;
  page.on('dialog', async (dialog) => {
    dialogs += 1;
    await dialog.dismiss();
  });
  await deleteButtonFor(page, 'AC3 delete title').click();
  await expect(rowFor(page, 'AC3 delete title')).toHaveCount(0);
  expect(dialogs).toBe(0);
});

test('[AC-3] the Delete task button is named by its task title and removes that task', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC3 named delete title');
  const button = page.getByRole('button', { name: 'Delete task: AC3 named delete title', exact: true });
  await expect(button).toHaveCount(1);
  await expect(button).toHaveText('Delete');
  await button.click();
  await expect(rowFor(page, 'AC3 named delete title')).toHaveCount(0);
});

test('[AC-3] deleting a task announces Task deleted in the status region and the message is not shown before a delete', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC3 status title');
  await expect(page.getByRole('status')).not.toContainText('Task deleted');
  await deleteButtonFor(page, 'AC3 status title').click();
  await expect(page.getByRole('status')).toContainText('Task deleted');
});

test('[AC-3][AC-4] deleting a task while the Completed view is shown removes it from the view at once', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC3 view delete title');
  await checkboxFor(page, 'AC3 view delete title').click();
  await page.getByRole('radio', { name: 'Completed', exact: true }).check();
  await expect(rowFor(page, 'AC3 view delete title')).toBeVisible();
  await deleteButtonFor(page, 'AC3 view delete title').click();
  await expect(rowFor(page, 'AC3 view delete title')).toHaveCount(0);
  await expect(page.getByText('No completed tasks.', { exact: true })).toBeVisible();
});

test('[AC-4] the active counter shows the number of tasks left and updates on completion', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 counter one');
  await addTask(page, 'AC4 counter two');
  await expect(page.getByText('2 active tasks left', { exact: true })).toBeVisible();
  await checkboxFor(page, 'AC4 counter one').click();
  await expect(page.getByText('1 active task left', { exact: true })).toBeVisible();
  await checkboxFor(page, 'AC4 counter two').click();
  await expect(page.getByText('No active tasks left', { exact: true })).toBeVisible();
});

test('[AC-4] the counter is a status line that reads the active count and is announced politely', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 status counter one');
  await addTask(page, 'AC4 status counter two');
  await addTask(page, 'AC4 status counter three');
  const counter = page.getByRole('status').filter({ hasText: '3 active tasks left' });
  await expect(page.getByText('3 active tasks left', { exact: true })).toBeVisible();
  await expect(counter).toHaveCount(1);
  await checkboxFor(page, 'AC4 status counter one').click();
  await expect(page.getByText('2 active tasks left', { exact: true })).toBeVisible();
  await expect(page.getByText('3 active tasks left', { exact: true })).toHaveCount(0);
});

test('[AC-4] an empty Active view shows No active tasks.', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 empty active one');
  await checkboxFor(page, 'AC4 empty active one').click();
  await page.getByRole('radio', { name: 'Active', exact: true }).check();
  await expect(page.getByText('No active tasks.', { exact: true })).toBeVisible();
});

test('[AC-2] the checkbox, Delete button and description paragraph of a row are found by their names and text', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 row parts title', 'AC2 row parts description');
  await expect(page.getByRole('checkbox', { name: 'AC2 row parts title', exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Delete task: AC2 row parts title', exact: true })).toHaveCount(1);
  await expect(rowFor(page, 'AC2 row parts title').getByText('AC2 row parts description', { exact: true })).toHaveCount(1);
});

test('[AC-2] the description is shown in the row and is omitted when the description is empty', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC2 para only title', 'AC2 para only description');
  await expect(rowFor(page, 'AC2 para only title').getByText('AC2 para only description', { exact: true })).toHaveCount(1);
  await addTask(page, 'AC2 para empty title');
  await expect(rowFor(page, 'AC2 para empty title').getByText('AC2 para empty title', { exact: true })).toHaveCount(1);
  await expect(rowFor(page, 'AC2 para empty title').locator('p')).toHaveCount(0);
});

test('[AC-4] the status line reads 3 active tasks left and drops to 2 when a task is completed', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 line one');
  await addTask(page, 'AC4 line two');
  await addTask(page, 'AC4 line three');
  await expect(page.getByText('3 active tasks left', { exact: true })).toBeVisible();
  await checkboxFor(page, 'AC4 line one').click();
  await expect(page.getByText('2 active tasks left', { exact: true })).toBeVisible();
});

test('[AC-4] an empty list shows No tasks yet. Add one above.', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await expect(page.getByText('No tasks yet. Add one above.', { exact: true })).toBeVisible();
});

test('[AC-4][AC-7] filters show exactly the matching subset and update when a task is completed', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 active one');
  await addTask(page, 'AC4 done one');
  await checkboxFor(page, 'AC4 done one').click();

  await page.getByRole('radio', { name: 'All', exact: true }).check();
  await expect(rowFor(page, 'AC4 active one')).toBeVisible();
  await expect(rowFor(page, 'AC4 done one')).toBeVisible();

  await page.getByRole('radio', { name: 'Active', exact: true }).check();
  await expect(rowFor(page, 'AC4 active one')).toBeVisible();
  await expect(rowFor(page, 'AC4 done one')).toHaveCount(0);

  await page.getByRole('radio', { name: 'Completed', exact: true }).check();
  await expect(rowFor(page, 'AC4 done one')).toBeVisible();
  await expect(rowFor(page, 'AC4 active one')).toHaveCount(0);
});

test('[AC-4][AC-7] an empty Completed view shows No completed tasks.', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC4 never done');
  await page.getByRole('radio', { name: 'Completed', exact: true }).check();
  await expect(page.getByText('No completed tasks.', { exact: true })).toBeVisible();
});

test('[AC-4][AC-7] a task completed while Active is shown leaves that view at once', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC7 leaves active');
  await addTask(page, 'AC7 stays active');
  await page.getByRole('radio', { name: 'Active', exact: true }).check();
  await expect(rowFor(page, 'AC7 leaves active')).toBeVisible();
  await checkboxFor(page, 'AC7 leaves active').click();
  await expect(rowFor(page, 'AC7 leaves active')).toHaveCount(0);
  await expect(rowFor(page, 'AC7 stays active')).toBeVisible();
});

test('[AC-4][AC-7] a task un-completed while Completed is shown leaves that view at once', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC7 leaves completed');
  await checkboxFor(page, 'AC7 leaves completed').click();
  await page.getByRole('radio', { name: 'Completed', exact: true }).check();
  await expect(rowFor(page, 'AC7 leaves completed')).toBeVisible();
  await checkboxFor(page, 'AC7 leaves completed').click();
  await expect(rowFor(page, 'AC7 leaves completed')).toHaveCount(0);
});

test('[AC-4][AC-7] the active counter updates while the Active view is shown', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC7 counter view one');
  await addTask(page, 'AC7 counter view two');
  await page.getByRole('radio', { name: 'Active', exact: true }).check();
  await checkboxFor(page, 'AC7 counter view one').click();
  await expect(page.getByText('1 active task left', { exact: true })).toBeVisible();
  await expect(rowFor(page, 'AC7 counter view one')).toHaveCount(0);
});

test('[AC-6] tasks keep title, description and completed state after reload', async ({ page }) => {
  // Each test runs in a fresh browser context, so storage starts empty without clearing it.
  // clearStorage is not used here: its init script runs again on every reload and would wipe the saved tasks.
  const run = Date.now();
  const title = `AC6 persist title ${run}`;
  const description = `AC6 persist desc ${run}`;
  await page.goto('/');
  await addTask(page, title, description);
  await checkboxFor(page, title).click();
  await page.reload();
  await expect(checkboxFor(page, title)).toBeChecked();
  await expect(page.getByText(description, { exact: true })).toBeVisible();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('todo.tasks')));
  const mine = stored.filter((task) => task.title === title);
  expect(mine.length).toBe(1);
  expect(mine[0].description).toBe(description);
  expect(mine[0].completed).toBe(true);
});

test('[AC-6] an edited title and description persist after reload', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC6 edit before', 'AC6 edit desc before');
  await editButtonIn(page, 'AC6 edit before').click();
  const row = rowFor(page, 'AC6 edit before');
  await row.getByLabel('Title', { exact: true }).fill('AC6 edit after');
  await row.getByLabel('Description', { exact: true }).fill('AC6 edit desc after');
  await row.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(rowFor(page, 'AC6 edit after')).toBeVisible();
  await page.reload();
  await expect(rowFor(page, 'AC6 edit after')).toBeVisible();
  await expect(page.getByText('AC6 edit desc after', { exact: true })).toBeVisible();
  await expect(page.getByText('AC6 edit before', { exact: true })).toHaveCount(0);
});

test('[AC-6] a deleted task stays deleted after reload', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC6 deleted title');
  await deleteButtonFor(page, 'AC6 deleted title').click();
  await expect(rowFor(page, 'AC6 deleted title')).toHaveCount(0);
  await page.reload();
  await expect(rowFor(page, 'AC6 deleted title')).toHaveCount(0);
});

test('[AC-7] the Active filter shows two active tasks and the Completed filter shows one, with All showing all three', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await addTask(page, 'AC7 alpha active');
  await addTask(page, 'AC7 beta active');
  await addTask(page, 'AC7 gamma done');
  await checkboxFor(page, 'AC7 gamma done').click();

  await page.getByRole('radio', { name: 'Active', exact: true }).check();
  await expect(rowFor(page, 'AC7 alpha active')).toBeVisible();
  await expect(rowFor(page, 'AC7 beta active')).toBeVisible();
  await expect(rowFor(page, 'AC7 gamma done')).toHaveCount(0);

  await page.getByRole('radio', { name: 'Completed', exact: true }).check();
  await expect(rowFor(page, 'AC7 gamma done')).toBeVisible();
  await expect(rowFor(page, 'AC7 alpha active')).toHaveCount(0);
  await expect(rowFor(page, 'AC7 beta active')).toHaveCount(0);

  await page.getByRole('radio', { name: 'All', exact: true }).check();
  await expect(rowFor(page, 'AC7 alpha active')).toBeVisible();
  await expect(rowFor(page, 'AC7 beta active')).toBeVisible();
  await expect(rowFor(page, 'AC7 gamma done')).toBeVisible();
});

test('[AC-1][AC-6] an empty title is refused with a message and nothing is stored', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(page.getByText('Enter a title to add the task.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Title', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  const stored = await page.evaluate(() => localStorage.getItem('todo.tasks'));
  expect(stored).toBeNull();
});

test('[AC-1] a whitespace-only title is refused with the same message', async ({ page }) => {
  await clearStorage({ page });
  await page.goto('/');
  await page.getByLabel('Title', { exact: true }).fill('   \t  ');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(page.getByText('Enter a title to add the task.', { exact: true })).toBeVisible();
  const stored = await page.evaluate(() => localStorage.getItem('todo.tasks'));
  expect(stored).toBeNull();
});

test('[AC-8] the add-and-list flow fits a phone viewport with no horizontal scrollbar', async ({ page }) => {
  await clearStorage({ page });
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto('/');
  await addTask(page, 'AC8 phone title');
  const addBox = await page.getByRole('button', { name: 'Add task', exact: true }).boundingBox();
  const rowBox = await rowFor(page, 'AC8 phone title').boundingBox();
  expect(addBox.x + addBox.width).toBeLessThanOrEqual(375);
  expect(rowBox.x + rowBox.width).toBeLessThanOrEqual(375);
  const widths = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(widths[0]).toBe(widths[1]);
});

test('[AC-8] the add-and-list flow fits a desktop viewport with no horizontal scrollbar', async ({ page }) => {
  await clearStorage({ page });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/');
  await addTask(page, 'AC8 desktop title');
  const addBox = await page.getByRole('button', { name: 'Add task', exact: true }).boundingBox();
  const rowBox = await rowFor(page, 'AC8 desktop title').boundingBox();
  expect(addBox.x + addBox.width).toBeLessThanOrEqual(1280);
  expect(rowBox.x + rowBox.width).toBeLessThanOrEqual(1280);
  const widths = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(widths[0]).toBe(widths[1]);
});
