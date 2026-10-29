import { test, expect } from '@playwright/test';

// [AC-4] PUT /notes/:id updates note and returns updated object
test('[AC-4][AC-11] update note replaces title and body', async () => {
  const service = await import('./service.cjs');
  const svc = await service.startService();
  // create a note
  const payload = { title: 'Old', body: 'Body' };
  const postRes = await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const created = await postRes.json();
  // update
  const newPayload = { title: 'New', body: 'Updated' };
  const putRes = await fetch(svc.baseURL + '/notes/' + created.id, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newPayload),
  });
  expect(putRes.status).toBe(200);
  const updated = await putRes.json();
  expect(updated.id).toBe(created.id);
  expect(updated.title).toBe(newPayload.title);
  expect(updated.body).toBe(newPayload.body);
  // confirm persistence
  const getRes = await fetch(svc.baseURL + '/notes/' + created.id);
  const gotten = await getRes.json();
  expect(gotten).toEqual(updated);
});
