import { test, expect } from '@playwright/test';

// AC-7: JSON over HTTP – a note has exactly id, title, body.

test('[AC-7] note JSON schema', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'Schema', body: 'X' } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json).toHaveProperty('title', 'Schema');
  expect(json).toHaveProperty('body', 'X');
  // No extra properties
  const keys = Object.keys(json);
  expect(keys.sort()).toEqual(['body','id','title']);
});
