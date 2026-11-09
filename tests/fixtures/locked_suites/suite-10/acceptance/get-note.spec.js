import { test, expect } from '@playwright/test';

// [AC-3] GET /notes/:id returns note or 404
test('[AC-3][AC-10] get note by id', async () => {
  const service = await import('./service.cjs');
  const svc = await service.startService();
  // create a note
  const payload = { title: 'GetTest', body: 'Body' };
  const postRes = await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const created = await postRes.json();
  // get existing
  const res = await fetch(svc.baseURL + '/notes/' + created.id);
  expect(res.status).toBe(200);
  let note; if (res.status === 200) { note = await res.json(); }
  expect(note).toEqual(created);
  // get non-existing
  const notRes = await fetch(svc.baseURL + '/notes/99999');
  expect(notRes.status).toBe(404);
});
