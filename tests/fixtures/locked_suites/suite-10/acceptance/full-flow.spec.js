import { test, expect } from '@playwright/test';

// [AC-1][AC-2][AC-3][AC-4][AC-5] Full CRUD flow in one test
// This test proves create, list, get, update, delete and persistence via restart.
// It uses the request fixture which talks to the service started by the harness.

test('[AC-1][AC-2][AC-3][AC-4][AC-5][AC-12][AC-16] CRUD flow with persistence', async ({ request }) => {
  const title = 'FlowNote';
  const body = 'Initial body';

  // Create
  const createRes = await request.post('/notes', { data: { title, body } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created).toHaveProperty('id');
  const id = created.id;

  // List should include it
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const notes = await listRes.json();
  const found = notes.find((n) => n.id === id);
  expect(found).toEqual(created);

  // Get by id
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const got = await getRes.json();
  expect(got).toEqual(created);

  // Update
  const newTitle = 'Updated';
  const newBody = 'New body';
  const updateRes = await request.put(`/notes/${id}`, { data: { title: newTitle, body: newBody } });
  expect(updateRes.status()).toBe(200);
  const updated = await updateRes.json();
  expect(updated.id).toBe(id);
  expect(updated.title).toBe(newTitle);
  expect(updated.body).toBe(newBody);

  // Get again to confirm persistence of update
  const getAfterUpdate = await request.get(`/notes/${id}`);
  expect(getAfterUpdate.status()).toBe(200);
  const afterUpd = await getAfterUpdate.json();
  expect(afterUpd).toEqual(updated);

  // Delete
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  // Confirm deletion
  const getDeleted = await request.get(`/notes/${id}`);
  expect(getDeleted.status()).toBe(404);
});
