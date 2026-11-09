import { test, expect } from '@playwright/test';

// AC-13: Validation failure – missing or empty title should return 400 and not store.

test('[AC-13] validation error on create', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'title required' });

  // Ensure no note was created
  const list = await request.get('/notes');
  const notes = await list.json();
  expect(notes.length).toBe(0);
});
