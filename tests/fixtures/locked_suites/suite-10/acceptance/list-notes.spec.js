import { test, expect } from '@playwright/test';

// [AC-2] GET /notes returns all created notes
test('[AC-2][AC-9] list notes returns array of notes', async () => {
  const service = await import('./service.cjs');
  const svc = await service.startService();
  // create two notes
  const payload1 = { title: 'First', body: 'A' };
  const payload2 = { title: 'Second', body: 'B' };
  await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload1),
  });
  await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload2),
  });
  const res = await fetch(svc.baseURL + '/notes');
  expect(res.status).toBe(200);
  const notes = await res.json();
  expect(Array.isArray(notes)).toBe(true);
  // each has id, title, body
  for (const n of notes) {
    expect(n).toHaveProperty('id');
    expect(typeof n.id).toBe('number');
    expect(n).toHaveProperty('title');
    expect(n).toHaveProperty('body');
  }
});
