import { test, expect } from '@playwright/test';

// Helper to delete all notes before a test runs.
async function clearAll(request) {
  const res = await request.get('/notes');
  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// Test AC-11: PUT /notes/:id updates title and body, returns 200 with updated note.
test('[AC-11] PUT /notes/:id updates a note', async ({ request }) => {
  await clearAll(request);
  const createRes = await request.post('/notes', { data: { title: 'Old', body: 'Data' } });
  const created = await createRes.json();
  const updateBody = { title: 'New', body: 'Info' };
  const resUpdate = await request.put(`/notes/${created.id}`, { data: updateBody });
  expect(resUpdate.status()).toBe(200);
  const updated = await resUpdate.json();
  expect(updated.title).toBe(updateBody.title);
  expect(updated.body).toBe(updateBody.body);
});

// Test AC-12: DELETE /notes/:id returns 204, and subsequent GET returns 404.
test('[AC-12] DELETE /notes/:id removes the note', async ({ request }) => {
  await clearAll(request);
  const createRes = await request.post('/notes', { data: { title: 'Del', body: 'Bye' } });
  const created = await createRes.json();
  const resDelete = await request.delete(`/notes/${created.id}`);
  expect(resDelete.status()).toBe(204);
  // Verify that the note is gone
  const resGet = await request.get(`/notes/${created.id}`);
  expect(resGet.status()).toBe(404);
});

// Test AC-16: Every operation works as the interface says.
test('[AC-16] CRUD operations conform to the interface', async ({ request }) => {
  await clearAll(request);
  // Create
  const createRes = await request.post('/notes', { data: { title: 'Test', body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created).toHaveProperty('id');
  // List
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const notesList = await listRes.json();
  expect(notesList).toContainEqual(created);
  // Get by id
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(created);
  // Update
  const updateBody = { title: 'Updated', body: 'New Body' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updateBody });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe(updateBody.title);
  expect(updated.body).toBe(updateBody.body);
  // Delete
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);
  // Verify deletion
  const afterDelGet = await request.get(`/notes/${created.id}`);
  expect(afterDelGet.status()).toBe(404);
});
