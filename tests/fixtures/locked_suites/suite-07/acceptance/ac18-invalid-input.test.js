import { test, expect } from '@playwright/test';

test('[AC-18] Invalid input is refused without storing anything', async ({ request }) => {
  const beforeResp = await request.get('/notes');
  const beforeNotes = await beforeResp.json();
  const lenBefore = Array.isArray(beforeNotes) ? beforeNotes.length : 0;

  const r = await request.post('/notes', { data: { body: 'Missing title' } });
  expect(r.status()).toBe(422);

  const afterResp = await request.get('/notes');
  const afterNotes = await afterResp.json();
  expect(Array.isArray(afterNotes)).toBeTruthy();
  expect(afterNotes.length).toBe(lenBefore);
});
