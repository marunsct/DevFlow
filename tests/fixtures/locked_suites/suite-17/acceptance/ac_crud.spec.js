import { test, expect } from '@playwright/test';

// AC-16: All CRUD operations follow the interface
// This test covers creating, listing, fetching, updating and deleting a note.
test('[AC-16] CRUD operations work as defined', async ({ request }) => {
  const payload = { title: 'crud-test', body: 'initial' };
  // Create
  const createRes = await request.post('/notes', { data: payload });
  expect(createRes.status()).toBe(201);
  const note = await createRes.json();
  expect(note).toHaveProperty('id');
  expect(note.title).toBe(payload.title);

  // List
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const notesList = await listRes.json();
  const titles = notesList.map((n) => n.title);
  expect(titles).toContain(payload.title);

  // Get by id
  const getRes = await request.get(`/notes/${note.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(note);

  // Update
  const updPayload = { title: 'crud-test-updated', body: 'updated' };
  const updRes = await request.put(`/notes/${note.id}`, { data: updPayload });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe(updPayload.title);

  // Delete
  const delRes = await request.delete(`/notes/${note.id}`);
  expect(delRes.status()).toBe(204);

  // Verify deletion
  const afterDelRes = await request.get(`/notes/${note.id}`);
  expect(afterDelRes.status()).toBe(404);
});
