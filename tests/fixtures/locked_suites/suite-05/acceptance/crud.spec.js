import { test, expect } from '@playwright/test';

// Helper to delete all notes by fetching list and deleting each.
async function clearAllNotes(request) {
  const res = await request.get('/notes');
  if (res.status() !== 200) return;
  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// AC-1: Create a note with title and body.
test('[AC-1] POST /notes creates a note', async ({ request }) => {
  await clearAllNotes(request);
  const response = await await request.post('/notes', { data: { title: 'Test', body: 'Body' } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test');
  expect(json.body).toBe('Body');
});

// AC-2: List all notes.
test('[AC-2] GET /notes returns list of notes', async ({ request }) => {
  await clearAllNotes(request);
  // create two notes
    const a = await request.post('/notes', { data: { title: 'A', body: 'a' } });
    const b = await request.post('/notes', { data: { title: 'B', body: 'b' } });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  expect(list.length).toBe(2);
});

// AC-3: Fetch one note by id.
test('[AC-3] GET /notes/:id returns the note', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'X', body: 'x' } });
  const created = await post.json();
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual(created);
});

// AC-10: GET non-existent id returns 404.
test('[AC-10] GET /notes/:id with nonexistent id returns 404', async ({ request }) => {
  await clearAllNotes(request);
  const res = await request.get('/notes/9999');
  expect(res.status()).toBe(404);
  const json = await res.json();
  expect(json).toEqual({ error: 'Not found' });
});

// AC-4: Update a note.
test('[AC-11] PUT /notes/:id updates the note', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'Old', body: 'old' } });
  const created = await post.json();
  const upd = await request.put(`/notes/${created.id}`, { data: { title: 'New', body: 'new' } });
  expect(upd.status()).toBe(200);
  const json = await upd.json();
  expect(json.title).toBe('New');
  expect(json.body).toBe('new');
});

// AC-5: Delete a note.
test('[AC-12] DELETE /notes/:id deletes the note', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'Del', body: 'del' } });
  const created = await post.json();
  const del = await request.delete(`/notes/${created.id}`);
  expect(del.status()).toBe(204);
  // ensure it is gone
  const get = await request.get(`/notes/${created.id}`);
  expect(get.status()).toBe(404);
});

// AC-13: Missing title error.
test('[AC-8] POST /notes without title returns 400', async ({ request }) => {
  await clearAllNotes(request);
  const res = await request.post('/notes', { data: { body: 'no title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'Title is required' });
});
