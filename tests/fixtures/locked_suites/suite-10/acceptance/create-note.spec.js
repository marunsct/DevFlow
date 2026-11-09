import { test, expect } from '@playwright/test';

// [AC-1] Create a note with title and body, expect 201 and returned note
test('[AC-1][AC-8] create note returns 201 with note', async ({ request }) => {
  const payload = { title: 'Test Note', body: 'Body content' };
  const service = await import('./service.cjs');
  const { startService } = await service;
  const svc = await startService();
  const response = await fetch(svc.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  expect(response.status).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);
});
