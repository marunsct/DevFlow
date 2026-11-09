import { test, expect } from '@playwright/test';

// Helper to create a note and return the parsed JSON
async function createNote(request, title, body) {
  const response = await request.post('/notes', {
    data: { title, body },
  });
  expect(response.status()).toBe(201);
  const json = await response.json();
  return json;
}

// Use a unique suffix per test to avoid interference between tests
const uniq = () => Math.random().toString(36).slice(2, 8);

test('[AC-8] POST /notes creates a note and returns 201 with the note', async ({ request }) => {
  const title = 'Test' + uniq();
  const body = 'Body';
  const json = await createNote(request, title, body);
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.id).toBeGreaterThan(0);
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
});

test('[AC-9] GET /notes returns a list of notes', async ({ request }) => {
  // create two notes with unique titles
  const title1 = 'ListTest1' + uniq();
  const title2 = 'ListTest2' + uniq();
  await createNote(request, title1, 'Body1');
  await createNote(request, title2, 'Body2');

  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  // find the two notes we just created
  const found1 = list.find((n) => n.title === title1 && n.body === 'Body1');
  const found2 = list.find((n) => n.title === title2 && n.body === 'Body2');
  expect(found1).toBeDefined();
  expect(found2).toBeDefined();
});

test('[AC-10] GET /notes/:id returns 404 for non‑existent and 200 for existing', async ({ request }) => {
  const resNotFound = await request.get('/notes/99999999');
  expect(resNotFound.status()).toBe(404);
  let err; try { err = await resNotFound.json(); } catch (e) { err = {}; }
  expect(err).toEqual({ error: 'Note not found' });

  // create a note and get it by id
  const title = 'FindTest' + uniq();
  const body = 'Body';
  const created = await createNote(request, title, body);
  const resFound = await request.get(`/notes/${created.id}`);
  expect(resFound.status()).toBe(200);
  const json = await resFound.json();
  expect(json).toEqual(created);
});

test('[AC-11] PUT /notes/:id updates a note and returns the updated note', async ({ request }) => {
  const title = 'UpdateTest' + uniq();
  const body = 'Old';
  const created = await createNote(request, title, body);

  const newTitle = 'Updated' + uniq();
  const newBody = 'New Body';
  const res = await request.put(`/notes/${created.id}`, {
    data: { title: newTitle, body: newBody },
  });
  expect(res.status()).toBe(200);
  const updated = await res.json();
  expect(updated.title).toBe(newTitle);
  expect(updated.body).toBe(newBody);

  // Verify subsequent GET returns updated data
  const getRes = await request.get(`/notes/${created.id}`);
  const getJson = await getRes.json();
  expect(getJson).toEqual(updated);
});

test('[AC-12] DELETE /notes/:id removes the note and returns 204', async ({ request }) => {
  const title = 'DeleteTest' + uniq();
  const body = 'To be deleted';
  const created = await createNote(request, title, body);

  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  // subsequent GET should be 404
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(404);
});

test('[AC-13] POST /notes with missing or empty title returns error and stores nothing', async ({ request }) => {
  // Missing title
  let res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const err1 = await res.json();
  expect(err1).toEqual({ error: 'Title is required' });

  // Empty title
  res = await request.post('/notes', { data: { title: '', body: 'Empty' } });
  expect(res.status()).toBe(400);
  const err2 = await res.json();
  expect(err2).toEqual({ error: 'Title is required' });

  // Ensure no new note was created (list length unchanged)
  const listRes = await request.get('/notes');
  const notes = await listRes.json();
  const titles = notes.map((n) => n.title);
  expect(titles).not.toContain('No title');
  expect(titles).not.toContain('');
});

test('[AC-14] GET /health returns status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
