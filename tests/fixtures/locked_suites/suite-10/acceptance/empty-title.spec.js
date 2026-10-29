import { test, expect } from '@playwright/test';

// [AC-13] Creating a note with an empty title should be refused and not stored
// This test verifies that the API returns the expected error status (422) and message,
// and that no new note is persisted when the title is an empty string.

test('[AC-13] create note with empty title fails', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: '', body: 'foo' } });
  expect(res.status()).toBe(422);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title is required' });

  // Verify that the note was not persisted.
  const listRes = await request.get('/notes');
  const notes = await listRes.json();
  const found = notes.find((n) => n.body === 'foo');
  expect(found).toBeUndefined();
});
