import { test, expect } from '@playwright/test';

async function createNote(request, payload) {
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  return await res.json();
}

// AC-3: GET /notes/:id returns the note or 404
test('[AC-3] GET /notes/:id returns the note or 404', async ({ request }) => {
  const created = await createNote(request, { title: 'Fetch Me' });
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const fetched = await res.json();
  expect(fetched).toEqual(created);

  const nfRes = await request.get('/notes/999999');
  expect(nfRes.status()).toBe(404);
  const nfBody = await nfRes.json();
  expect(nfBody).toEqual({ error: 'Not found' });
});

// AC-4: PUT /notes/:id updates the note and returns 200
test('[AC-4][AC-11] PUT /notes/:id updates the note and returns 200', async ({ request }) => {
  const created = await createNote(request, { title: 'Old Title' });
  const updatePayload = { title: 'New Title', body: 'Updated Body' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updatePayload });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated).toEqual({ id: created.id, ...updatePayload });

  const getRes = await request.get(`/notes/${created.id}`);
  const gotten = await getRes.json();
  expect(gotten).toEqual(updated);
});

// AC-5: DELETE /notes/:id removes the note and returns 204
test('[AC-5] DELETE /notes/:id removes the note and returns 204', async ({ request }) => {
  const created = await createNote(request, { title: 'Delete Me' });
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(404);
});
