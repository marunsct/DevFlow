import { test, expect } from '@playwright/test';

// AC-16: Every operation works as the interface says – combined test.
test('[AC-16] CRUD flow all work together', async ({ request }) => {
  // Create
  const createRes = await request.post('/notes', { data: { title: 'AllOps', body: 'Start' } });
  expect(createRes.status()).toBe(201);
  const note = await createRes.json();
  expect(note).toHaveProperty('id');

  // Read list includes it
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  expect(list.some(n => n.id === note.id)).toBeTruthy();

  // Fetch by id
  const getRes = await request.get(`/notes/${note.id}`);
  expect(getRes.status()).toBe(200);
  expect(await getRes.json()).toEqual(note);

  // Update
  const updRes = await request.put(`/notes/${note.id}`, { data: { title: 'AllOpsUpdated', body: 'End' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('AllOpsUpdated');

  // Delete
  const delRes = await request.delete(`/notes/${note.id}`);
  expect(delRes.status()).toBe(204);
});
