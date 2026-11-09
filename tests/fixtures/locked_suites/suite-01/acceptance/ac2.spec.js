import { test, expect } from '@playwright/test';

// AC-2: List all notes – verifies 200 response and array length.

test('[AC-2] lists all notes', async ({ request }) => {
  // create two notes first
  await request.post('/notes', { data: { title: 'First', body: 'A' } });
  await request.post('/notes', { data: { title: 'Second', body: 'B' } });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await res.json();
  expect(Array.isArray(notes)).toBe(true);
  expect(notes.length).toBeGreaterThanOrEqual(2);
});
