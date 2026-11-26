import { test, expect } from '@playwright/test';

// ─── Helper: clear localStorage after page load so every test starts fresh ───
async function clearStorage(page) {
  // Must navigate first; accessing storage before goto throws SecurityError.
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
}

// ─── AC-6: UI labels present on initial render ──────────────────────────────
test('[AC-6] the form fields and add button are present on load', async ({
  page,
}) => {
  await clearStorage(page);

  // Title text field
  const titleInput = page.getByLabel('Title', { exact: true });
  await expect(titleInput).toBeVisible();

  // Description textarea
  const descArea = page.getByLabel('Description', { exact: true });
  await expect(descArea).toBeVisible();

  // Verify element types as required by brief: Title is <input type='text'>, Description is <textarea>
  expect(await titleInput.evaluate(el => el.tagName.toLowerCase())).toBe('input');
  expect(await titleInput.evaluate(el => el.getAttribute('type'))).toBe('text');
  expect(await descArea.evaluate(el => el.tagName.toLowerCase())).toBe('textarea');

  // Add task button
  const addBtn = page.getByRole('button', { name: 'Add task', exact: true });
  await expect(addBtn).toBeVisible();
});

// ─── AC-1: Add new tasks with title and description ─────────────────────────
test('[AC-1] adding a task with title and description shows it in the list', async ({
  page,
}) => {
  await clearStorage(page);

  // Fill form
  await page.getByLabel('Title', { exact: true }).fill('Buy groceries');
  await page.getByLabel('Description', { exact: true }).fill('Milk and bread');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Task should appear in the list with title and description
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Buy groceries',
  });
  await expect(listItem).toBeVisible();
  await expect(listItem).toContainText('Milk and bread');
});

// ─── AC-7: Cannot add without a title ────────────────────────────────────────
test('[AC-7] adding with empty title does not create a task', async ({ page }) => {
  await clearStorage(page);

  // Only fill description, leave title empty
  await page.getByLabel('Description', { exact: true }).fill('some description');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // No new list item should appear
  const listItems = page.getByRole('listitem');
  await expect(listItems).toHaveCount(0);

  // Description field must retain its value after the failed add attempt (TS-7)
  await expect(page.getByLabel('Description', { exact: true })).toHaveValue('some description');
});

// ─── AC-8: Task list item shows title and description ────────────────────────
test('[AC-8] a task list item contains its title and description text', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Show me');
  await page.getByLabel('Description', { exact: true }).fill('And my details');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Find the list item and assert both texts are present
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Show me',
  });
  await expect(listItem).toBeVisible();
  const textContent = await listItem.textContent();
  expect(textContent).toContain('Show me');
  expect(textContent).toContain('And my details');
});

// ─── AC-9: Checkbox labelled "Done" toggles completion ───────────────────────
test('[AC-9] the Done checkbox toggles task completion state', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task first
  await page.getByLabel('Title', { exact: true }).fill('Walk dog');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Find the Done checkbox on this task's list item
  const listItem = page.getByRole('listitem').filter({ hasText: 'Walk dog' });
  const doneCheckbox = listItem.getByLabel('Done', { exact: true });

  // Initially unchecked
  await expect(doneCheckbox).not.toBeChecked();

  // Click to mark complete
  await doneCheckbox.click();
  await expect(doneCheckbox).toBeChecked();

  // Click again to mark incomplete
  await doneCheckbox.click();
  await expect(doneCheckbox).not.toBeChecked();
});

// ─── AC-2: Mark tasks as complete/incomplete (combined with visual feedback) ──
test('[AC-2] marking a task complete toggles its completed state', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Walk dog');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  const doneCheckbox = page
    .getByRole('listitem')
    .filter({ hasText: 'Walk dog' })
    .getByLabel('Done', { exact: true });

  // Initially unchecked
  await expect(doneCheckbox).not.toBeChecked();

  // Click to mark complete
  await doneCheckbox.click();
  await expect(doneCheckbox).toBeChecked();

  // Click again to mark incomplete — both directions tested (review fix)
  await doneCheckbox.click();
  await expect(doneCheckbox).not.toBeChecked();
});

// ─── AC-3: Edit a task's title ──────────────────────────────────────────────
test('[AC-3] editing a task title updates the list', async ({ page }) => {
  await clearStorage(page);

  // Add a task with original title
  await page.getByLabel('Title', { exact: true }).fill('Original title');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Click Edit button
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Original title',
  });
  await listItem.getByRole('button', { name: 'Edit', exact: true }).click();

  // Edit title field and Save button should now be visible
  const editInput = page.getByLabel('Edit title', { exact: true });
  await expect(editInput).toBeVisible();
  const saveBtn = page.getByRole('button', { name: 'Save', exact: true });
  await expect(saveBtn).toBeVisible();

  // Type new title and save
  await editInput.fill('Updated title');
  await saveBtn.click();

  // List item should now show the updated title
  const updatedItem = page.getByRole('listitem').filter({
    hasText: 'Updated title',
  });
  await expect(updatedItem).toBeVisible();
});

// ─── AC-10: Edit workflow with "Edit title" field and "Save" button ──────────
test('[AC-10] the edit flow shows Edit title field and Save button then commits', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Before edit');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Click Edit to reveal controls
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Before edit',
  });
  await listItem.getByRole('button', { name: 'Edit', exact: true }).click();

  // Verify "Edit title" field is visible (pre-filled with current title)
  const editInput = page.getByLabel('Edit title', { exact: true });
  await expect(editInput).toBeVisible();
  await expect(editInput).toHaveValue('Before edit');

  // Verify Save button is visible
  await expect(
    page.getByRole('button', { name: 'Save', exact: true })
  ).toBeVisible();

  // Type new title and save
  await editInput.fill('After edit');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  // After saving, the list item should show the new title
  const updatedItem = page.getByRole('listitem').filter({
    hasText: 'After edit',
  });
  await expect(updatedItem).toBeVisible();
});

// ─── AC-4: Delete tasks ──────────────────────────────────────────────────────
test('[AC-4] deleting a task removes it from the list', async ({ page }) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Temporary task');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Delete it
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Temporary task',
  });
  await listItem.getByRole('button', { name: 'Delete', exact: true }).click();

  // Task should no longer be visible
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Temporary task' })
  ).not.toBeVisible();
});

// ─── AC-11: Delete button removes task (explicit) ────────────────────────────
test('[AC-11] the Delete button on a task removes it', async ({ page }) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Delete me');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Click Delete
  const listItem = page.getByRole('listitem').filter({
    hasText: 'Delete me',
  });
  await listItem.getByRole('button', { name: 'Delete', exact: true }).click();

  // Verify no list items remain
  await expect(page.getByRole('listitem')).toHaveCount(0);
});

// ─── AC-5 & AC-12 & AC-15: Filter buttons (All, Active, Completed) ──────────
test('[AC-5][AC-12][AC-15] filter buttons show correct tasks for each state', async ({
  page,
}) => {
  await clearStorage(page);

  // Add three tasks
  await page.getByLabel('Title', { exact: true }).fill('Task A');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  await page.getByLabel('Title', { exact: true }).fill('Task B');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Mark one task as completed
  const listItemA = page.getByRole('listitem').filter({ hasText: 'Task A' });
  await listItemA.getByLabel('Done', { exact: true }).click();

  // Verify all three appear under "All" (default)
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task A' })
  ).toBeVisible();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task B' })
  ).toBeVisible();

  // Click "Active" filter — only Task B (active) should show
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task A' })
  ).not.toBeVisible();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task B' })
  ).toBeVisible();

  // Click "Completed" filter — only Task A (completed) should show
  await page
    .getByRole('button', { name: 'Completed', exact: true })
    .click();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task A' })
  ).toBeVisible();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task B' })
  ).not.toBeVisible();

  // Click "All" — both should appear again
  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task A' })
  ).toBeVisible();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Task B' })
  ).toBeVisible();
});

// ─── AC-13: Users can add, edit, delete tasks (combined workflow) ────────────
test('[AC-13] users can add, edit, and delete tasks in sequence', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('My first task');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Verify it appears
  await expect(
    page.getByRole('listitem').filter({ hasText: 'My first task' })
  ).toBeVisible();

  // Edit the task
  const listItem = page.getByRole('listitem').filter({
    hasText: 'My first task',
  });
  await listItem.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Edit title', { exact: true }).fill('My edited task');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  // Verify edit
  const updatedItem = page.getByRole('listitem').filter({
    hasText: 'My edited task',
  });
  await expect(updatedItem).toBeVisible();

  // Delete the task
  await updatedItem
    .getByRole('button', { name: 'Delete', exact: true })
    .click();

  // Verify deletion
  await expect(
    page.getByRole('listitem').filter({ hasText: 'My edited task' })
  ).not.toBeVisible();
});

// ─── AC-14: Tasks persist between page refreshes ─────────────────────────────
test('[AC-14] tasks persist after a page reload', async ({ page }) => {
  await clearStorage(page);

  // Add a task
  await page.getByLabel('Title', { exact: true }).fill('Persist me');
  await page.getByLabel('Description', { exact: true }).fill('I should survive reload');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // Verify it appears
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Persist me' })
  ).toBeVisible();

  // Reload the page
  await page.reload();

  // Task should still be visible after reload
  const persistedItem = page.getByRole('listitem').filter({
    hasText: 'Persist me',
  });
  await expect(persistedItem).toBeVisible();
  await expect(persistedItem).toContainText('I should survive reload');
});

// ─── AC-16: Responsive design for mobile and desktop ────────────────────────
test('[AC-16] the page layout is visible on mobile and desktop viewports', async ({
  page,
}) => {
  await clearStorage(page);

  // Add a task so there is content to check
  await page.getByLabel('Title', { exact: true }).fill('Responsive test');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();

  // ── Mobile viewport ──
  await page.setViewportSize({ width: 375, height: 812 });

  // Add-form fields should be visible
  await expect(
    page.getByLabel('Title', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByLabel('Description', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Add task', exact: true })
  ).toBeVisible();

  // Task list should be visible
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Responsive test' })
  ).toBeVisible();

  // Filter buttons should be visible
  await expect(
    page.getByRole('button', { name: 'All', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Active', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Completed', exact: true })
  ).toBeVisible();

  // ── Desktop viewport ──
  await page.setViewportSize({ width: 1920, height: 1080 });

  // All controls should still be visible
  await expect(
    page.getByLabel('Title', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByLabel('Description', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Add task', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('listitem').filter({ hasText: 'Responsive test' })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'All', exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Active', exact: true })
  ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Completed', exact: true })
    ).toBeVisible();
  });

  // ─── Narrowing-view + action tests (review gap fix) ──────────────────────
  // Verifies that performing an action while a filter is active updates the
  // view correctly — a product that only re-renders on filter switch would
  // leave stale items showing.

  // While "Active" filter is on, delete a task → it should disappear from Active view
  test('[AC-4][AC-5][AC-12][AC-15] deleting a task while the Active filter is active removes it from the list', async ({
    page,
  }) => {
    await clearStorage(page);

    // Add two tasks
    await page.getByLabel('Title', { exact: true }).fill('Active one');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();
    await page.getByLabel('Title', { exact: true }).fill('Active two');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();

    // Mark one as completed so it won't show under Active
    const itemA = page.getByRole('listitem').filter({ hasText: 'Active one' });
    await itemA.getByLabel('Done', { exact: true }).click();

    // Switch to Active filter — only "Active two" should show
    await page.getByRole('button', { name: 'Active', exact: true }).click();
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Active two' })
    ).toBeVisible();
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Active one' })
    ).not.toBeVisible();

    // Delete the remaining active task while Active filter is on
    const itemB = page.getByRole('listitem').filter({ hasText: 'Active two' });
    await itemB.getByRole('button', { name: 'Delete', exact: true }).click();

    // Active view should now be empty of "Active two"
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Active two' })
    ).not.toBeVisible();
  });

  // While "Active" filter is on, toggle a task complete → it should leave Active view immediately
  test('[AC-2][AC-5][AC-12][AC-15] toggling a task complete while the Active filter is active removes it from the list', async ({
    page,
  }) => {
    await clearStorage(page);

    // Add two tasks
    await page.getByLabel('Title', { exact: true }).fill('Active one');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();
    await page.getByLabel('Title', { exact: true }).fill('Active two');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();

    // Switch to Active filter
    await page.getByRole('button', { name: 'Active', exact: true }).click();

    // Toggle "Active one" complete — it should disappear from the Active view
    const itemA = page.getByRole('listitem').filter({ hasText: 'Active one' });
    const doneCheckbox = itemA.getByLabel('Done', { exact: true });
    await doneCheckbox.click();

    // "Active one" should no longer appear in the Active filter view
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Active one' })
    ).not.toBeVisible();

    // "Active two" should still be visible
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Active two' })
    ).toBeVisible();
  });

  // While "Completed" filter is on, toggle a task incomplete → it should leave Completed view immediately
  test('[AC-2][AC-5][AC-12][AC-15] toggling a task incomplete while the Completed filter is active removes it from the list', async ({
    page,
  }) => {
    await clearStorage(page);

    // Add two tasks and mark both complete
    await page.getByLabel('Title', { exact: true }).fill('Completed one');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();
    await page.getByLabel('Title', { exact: true }).fill('Completed two');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();

    // Mark both as completed
    const itemA = page.getByRole('listitem').filter({ hasText: 'Completed one' });
    await itemA.getByLabel('Done', { exact: true }).click();
    const itemB = page.getByRole('listitem').filter({ hasText: 'Completed two' });
    await itemB.getByLabel('Done', { exact: true }).click();

    // Switch to Completed filter
    await page.getByRole('button', { name: 'Completed', exact: true }).click();

    // Toggle "Completed one" incomplete — it should disappear from the Completed view
    const doneCheckbox = itemA.getByLabel('Done', { exact: true });
    await doneCheckbox.click();

    // "Completed one" should no longer appear in the Completed filter view
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Completed one' })
    ).not.toBeVisible();

    // "Completed two" should still be visible
    await expect(
      page.getByRole('listitem').filter({ hasText: 'Completed two' })
    ).toBeVisible();
  });

  // While "Active" filter is on, edit a task title → the updated title should show in Active view
  test('[AC-3][AC-5][AC-12][AC-15] editing a task title while the Active filter is active updates the list', async ({
    page,
  }) => {
    await clearStorage(page);

    // Add a task
    await page.getByLabel('Title', { exact: true }).fill('Active task');
    await page.getByRole('button', { name: 'Add task', exact: true }).click();

    // Switch to Active filter
    await page.getByRole('button', { name: 'Active', exact: true }).click();

    // Edit the task title
    const listItem = page.getByRole('listitem').filter({ hasText: 'Active task' });
    await listItem.getByRole('button', { name: 'Edit', exact: true }).click();

    // Type new title and save
    await page.getByLabel('Edit title', { exact: true }).fill('Renamed active task');
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    // The list item should now show the updated title in the Active view
    const updatedItem = page.getByRole('listitem').filter({
      hasText: 'Renamed active task',
    });
    await expect(updatedItem).toBeVisible();
  });
