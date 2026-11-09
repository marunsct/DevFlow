import { test, expect } from '@playwright/test';

// [AC-5] DELETE /notes/:id removes note and returns 204
test('[AC-5] delete note returns 204 and removes it', async () => {
  const service = await import('./service.cjs');
  const svc = await service.startService();
  // create a note
  const payload = { title: 'DeleteMe', body: 'To be deleted' };
  const postRes = await fetch(svc.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const created = await postRes.json();
  // delete
  const delRes = await fetch(svc.baseURL + '/notes/' + created.id, {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' },
  });
  expect(delRes.status).toBe(204);
  // confirm not found
  const getRes = await fetch(svc.baseURL + '/notes/' + created.id);
  expect(getRes.status).toBe(404);
});
