import { test, expect } from '@playwright/test';

// helper to create a note via request fixture
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  return await res.json();
}
function uniq() { return Math.random().toString(36).slice(2,8); }

// AC-1 Create a note with a title and a body
test('[AC-1] POST /notes creates a note with title and body', async ({ request }) => {
  const title = 'AC1' + uniq();
  const body = 'Body for AC1';
  const json = await createNote(request, title, body);
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
});

// AC-2 List all notes
test('[AC-2] GET /notes returns list of all notes', async ({ request }) => {
  const t1 = 'List' + uniq();
  const t2 = 'List' + uniq();
  await createNote(request, t1, 'B1');
  await createNote(request, t2, 'B2');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  const found1 = list.find(n => n.title === t1 && n.body === 'B1');
  const found2 = list.find(n => n.title === t2 && n.body === 'B2');
  expect(found1).toBeDefined();
  expect(found2).toBeDefined();
});

// AC-3 Fetch one note by its id
test('[AC-3] GET /notes/:id returns the note', async ({ request }) => {
  const title = 'Find' + uniq();
  const body = 'Body';
  const created = await createNote(request, title, body);
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual(created);
});

// AC-4 Update a note's title and body
test('[AC-4] PUT /notes/:id updates title and body', async ({ request }) => {
  const title = 'Upd' + uniq();
  const body = 'Old';
  const created = await createNote(request, title, body);
  const newTitle = 'New' + uniq();
  const newBody = 'New Body';
  const res = await request.put(`/notes/${created.id}`, { data: { title: newTitle, body: newBody } });
  expect(res.status()).toBe(200);
  const updated = await res.json();
  expect(updated.title).toBe(newTitle);
  expect(updated.body).toBe(newBody);
});

// AC-5 Delete a note
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const title = 'Del' + uniq();
  const body = 'To delete';
  const created = await createNote(request, title, body);
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(404);
});

// AC-7 JSON over HTTP note structure
test('[AC-7] Note JSON contains id, title, body', async ({ request }) => {
  const title = 'JSON' + uniq();
  const body = 'Body';
  const json = await createNote(request, title, body);
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
});

// AC-15 start.sh launches service on 127.0.0.1 with PORT and DATA_DIR
import { startService } from './service.cjs';
test('[AC-15] Service starts on localhost with env vars', async () => {
  const svc = await startService();
  try {
    const res = await fetch(`${svc.baseURL}/health`);
    expect(res.status).toBe(200);
  } finally { await svc.stop(); }
});

// AC-16 Every operation works as the interface says (covered by previous tests)
// AC-18 Invalid input is refused without storing anything
test('[AC-18] POST /notes with missing title returns 400 and does not store', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title is required' });
  const listRes = await request.get('/notes');
  const notes = await listRes.json();
  expect(notes.some(n => n.body === 'No title')).toBe(false);
});
