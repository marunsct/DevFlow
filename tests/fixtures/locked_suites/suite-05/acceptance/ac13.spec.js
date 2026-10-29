import { test, expect } from '@playwright/test';

test('[AC-13] POST /notes without title returns 400 and nothing stored', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'Title is required' });

  // Ensure list remains empty
  const listRes = await request.get('/notes');
  const list = await listRes.json();
  expect(Array.isArray(list)).toBe(true);
  expect(list.length).toBe(0);
});
