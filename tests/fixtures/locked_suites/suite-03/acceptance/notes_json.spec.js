import { test, expect } from '@playwright/test';

// Test that a created note has the required JSON shape (AC-7)
test('[AC-7] POST /notes returns note with id, title and body', async ({ request }) => {
  const title = 'Shape Note';
  const body = 'Body content';
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
});
