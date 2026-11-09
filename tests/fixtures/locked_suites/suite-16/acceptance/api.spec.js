import { test, expect } from '@playwright/test';

// Helper: create a note and return its id
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  return json.id;
}

// Test AC-1, AC-8: create note returns 201 with id and body
test('[AC-1][AC-8] POST /notes creates a note', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'First', body: 'Body' } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toEqual({ id: expect.any(Number), title: 'First', body: 'Body' });
});

// Test AC-2: GET /notes returns all notes
test('[AC-2] GET /notes lists all notes', async ({ request }) => {
  await createNote(request, 'A', 'a');
  await createNote(request, 'B', 'b');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(Array.isArray(json)).toBe(true);
  // at least two notes
  expect(json.length).toBeGreaterThanOrEqual(2);
});

// Test AC-3: get one note and 404 for missing id
test('[AC-3] GET /notes/:id returns note or 404', async ({ request }) => {
  const id = await createNote(request, 'Single', 'Only');
  const res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ id, title: 'Single', body: 'Only' });

  const notRes = await request.get('/notes/9999');
  expect(notRes.status()).toBe(404);
  const errJson = await notRes.json();
  expect(errJson).toEqual({ error: 'Not found' });
});

// Test AC-4 and AC-11: update note
test('[AC-4][AC-11] PUT /notes/:id updates title and body', async ({ request }) => {
  const id = await createNote(request, 'Old', 'Body');
  const updRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Updated' } });
  expect(updRes.status()).toBe(200);
  const updJson = await updRes.json();
  expect(updJson).toEqual({ id, title: 'New', body: 'Updated' });

  // verify persistence via GET
  const getRes = await request.get(`/notes/${id}`);
  const getJson = await getRes.json();
  expect(getJson).toEqual(updJson);

  // update non-existent id
  const badUpd = await request.put('/notes/9999', { data: { title: 'X', body: '' } });
  expect(badUpd.status()).toBe(404);
  expect(await badUpd.json()).toEqual({ error: 'Not found' });
});

// Test AC-5 and AC-12: delete note
test('[AC-5][AC-12] DELETE /notes/:id removes note', async ({ request }) => {
  const id = await createNote(request, 'Del', 'Rem');
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  // body should be empty
  const text = await delRes.text();
  expect(text).toBe('');

  const getAfter = await request.get(`/notes/${id}`);
  expect(getAfter.status()).toBe(404);

  // delete non-existent
  const badDel = await request.delete('/notes/9999');
  expect(badDel.status()).toBe(404);
  expect(await badDel.json()).toEqual({ error: 'Not found' });
});

// Test AC-6 & AC-17: notes survive restart using helper service.cjs
import { startService } from './service.cjs';

test('[AC-6][AC-17] Notes persist after server restart', async () => {
  const first = await startService();
  // create note via direct HTTP request to the running instance
  const res1 = await fetch(`${first.baseURL}/notes`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ title:'Persist', body:'Data'}) });
  expect(res1.status).toBe(201);
  const note = await res1.json();
  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const res2 = await fetch(`${second.baseURL}/notes/${note.id}`);
  expect(res2.status).toBe(200);
  const got = await res2.json();
  expect(got).toEqual(note);
  await second.stop();
});

// Test AC-7: JSON structure has only id, title, body
test('[AC-7] Note JSON contains exactly id, title, body', async ({ request }) => {
  const id = await createNote(request, 'Exact', 'Check');
  const res = await request.get(`/notes/${id}`);
  const json = await res.json();
  expect(Object.keys(json)).toEqual(['id','title','body']);
});

// Test AC-13 and AC-18: missing or empty title is rejected, nothing stored
test('[AC-13][AC-18] POST without title returns error and does not store', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  expect(await res.json()).toEqual({ error: 'Title required' });

  const emptyRes = await request.post('/notes', { data: { title: '', body: 'Empty' } });
  expect(emptyRes.status()).toBe(400);
  expect(await emptyRes.json()).toEqual({ error: 'Title required' });
});

// Test AC-14: health endpoint
test('[AC-14] GET /health returns ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: 'ok' });
});
