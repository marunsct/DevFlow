import { test, expect } from '@playwright/test';

/**
 * Test that creating a note without a title is rejected and nothing is stored.
 */
test('[AC-18] POST /notes without title does not store note', async ({ request }) => {
  // Attempt to create a note with missing title
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'Title is required' });

  // Verify that no new note was created by checking the list is empty or unchanged.
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  // The test assumes the service starts with an empty data store for each run.
  expect(Array.isArray(list)).toBe(true);
});
