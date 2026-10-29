import { test, expect } from '@playwright/test';

// AC-9: GET /notes returns array of all notes.

test('[AC-9] list all notes (full)', async ({ request }) => {
  await request.post('/notes', { data: { title: 'A' } });
  await request.post('/notes', { data: { title: 'B' } });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await res.json();
  expect(Array.isArray(notes)).toBe(true);
  // at least two
  expect(notes.length).toBeGreaterThanOrEqual(2);
});
