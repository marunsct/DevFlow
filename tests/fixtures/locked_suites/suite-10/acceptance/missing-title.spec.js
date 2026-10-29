import { test, expect } from '@playwright/test';

// [AC-13] POST /notes with missing title returns 400 or 422 and does not store note
test('[AC-13][AC-18] create without title returns error', async () => {
  const service = await import('./service.cjs');
  const svc = await service.startService();
  const payload = { body: 'No title' };
  const res = await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  expect([400,422]).toContain(res.status);
  const err = await res.json();
  expect(err).toHaveProperty('error');
  // ensure no note stored
  const listRes = await fetch(svc.baseURL + '/notes');
  const notes = await listRes.json();
  const found = notes.find(n => n.body === payload.body);
  expect(found).toBeUndefined();
});
