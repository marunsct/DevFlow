import { test, expect } from '@playwright/test';

// Helper to create a note and return its id and body
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  return json;
}

// AC-1, AC-8: Create a note with title and body
test('[AC-1][AC-8] POST /notes creates a note and returns it', async ({ request }) => {
  const note = await createNote(request, 'Test Title', 'Some body');
  expect(note.title).toBe('Test Title');
  expect(note.body).toBe('Some body');
});

// AC-2: List all notes
test('[AC-2][AC-9] GET /notes returns list of all notes', async ({ request }) => {
  const n1 = await createNote(request, 'First', 'One');
  const n2 = await createNote(request, 'Second', 'Two');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBeTruthy();
  // find the created notes by id
  const ids = list.map((x) => x.id);
  expect(ids).toContain(n1.id);
  expect(ids).toContain(n2.id);
});

// AC-3: Fetch one note by id and handle not found
test('[AC-3] GET /notes/:id returns the note or 404', async ({ request }) => {
  const created = await createNote(request, 'Unique', 'Only');
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual(created);

  const notRes = await request.get('/notes/9999');
  expect(notRes.status()).toBe(404);
  const err = await notRes.json();
  expect(err).toEqual({ error: 'not found' });
});

// AC-4: Update a note
test('[AC-4] PUT /notes/:id updates the note and returns it', async ({ request }) => {
  const orig = await createNote(request, 'Old', 'Body');
  const updRes = await request.put(`/notes/${orig.id}`, { data: { title: 'New', body: 'Updated' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Updated');

  // fetching shows update
  const getRes = await request.get(`/notes/${orig.id}`);
  const fetched = await getRes.json();
  expect(fetched).toEqual(updated);
});

// AC-5: Delete a note
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const toDelete = await createNote(request, 'Del', 'Erase');
  const delRes = await request.delete(`/notes/${toDelete.id}`);
  expect(delRes.status()).toBe(204);

  const getAfter = await request.get(`/notes/${toDelete.id}`);
  expect(getAfter.status()).toBe(404);
});
