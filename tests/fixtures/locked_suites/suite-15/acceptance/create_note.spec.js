import { test, expect } from '@playwright/test';

// AC-1: Create a note with title and body
test('[AC-1][AC-7][AC-8] POST /notes creates a note and returns 201 with the note', async ({ request }) => {
  // Ensure no prior notes – the harness starts with an empty data dir.
  const res = await request.post('/notes', { data: { title: 'Test', body: 'Body' } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test');
  expect(json.body).toBe('Body');
});
