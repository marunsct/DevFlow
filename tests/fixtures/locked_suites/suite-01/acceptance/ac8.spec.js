import { test, expect } from '@playwright/test';

// AC-8: POST /notes returns 201 with created note and Location header.

test('[AC-8] creates a note with location', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'Loc', body: 'Body' } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json.title).toBe('Loc');
  const loc = res.headers()['location'];
  expect(loc).toMatch(/^\/notes\/[0-9]+$/);
});
