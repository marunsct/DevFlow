import { test, expect } from '@playwright/test';

// Helper to delete all existing notes via the API
async function cleanAll(request) {
  const res = await request.get('/notes');

  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// Run cleanup before each test to ensure a predictable state
test.beforeEach(async ({ request }) => {
  await cleanAll(request);
});

// [AC-1] Create a note with a title and a body
test('[AC-1] create a note', async ({ request }) => {
  const payload = { title: 'Test', body: 'Body' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);
});

// [AC-2] List all notes
test('[AC-2] list all notes', async ({ request }) => {
  const payload1 = { title: 'A', body: 'One' };
  const payload2 = { title: 'B', body: 'Two' };
  await request.post('/notes', { data: payload1 });
  await request.post('/notes', { data: payload2 });

  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await res.json();
  expect(notes).toHaveLength(2);
  const titles = notes.map((n) => n.title);
  expect(titles).toContain('A');
  expect(titles).toContain('B');
});

// [AC-3] Fetch one note by its id and missing id
test('[AC-3] get a single note', async ({ request }) => {
  const payload = { title: 'Single', body: 'One' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);

  // missing id
  const missRes = await request.get('/notes/9999');
  expect(missRes.status()).toBe(404);
  const err = await missRes.json();
  expect(err.error).toBe('Note not found');
});

// [AC-4] Update a note's title and body
test('[AC-4] update a note', async ({ request }) => {
  const payload = { title: 'Old', body: 'OldBody' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const updatedPayload = { title: 'New', body: 'NewBody' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updatedPayload });
  expect(updRes.status()).toBe(200);
  const updJson = await updRes.json();
  expect(updJson.title).toBe(updatedPayload.title);
  expect(updJson.body).toBe(updatedPayload.body);

  // verify via GET
  const getRes = await request.get(`/notes/${created.id}`);
  const getJson = await getRes.json();
  expect(getJson.title).toBe(updatedPayload.title);
  expect(getJson.body).toBe(updatedPayload.body);
});

// [AC-5] Delete a note
test('[AC-5] delete a note', async ({ request }) => {
  const payload = { title: 'Del', body: 'ToDelete' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(404);
});

// [AC-6][AC-17] persistence across restart of the service
  test('[AC-6][AC-17] persistence across restart', async () => {
  const { startService } = await import('./service.cjs');
  const svc1 = await startService();
  // create note via fetch
  const createRes = await fetch(`${svc1.baseURL}/notes`, {
    method: 'POST',
    data: { title: 'Persist', body: 'Data' },
  });
  if (createRes.status() !== 201) throw new Error('Create failed');
  await svc1.stop();

  const svc2 = await startService({ dataDir: svc1.dataDir });
  const listRes = await fetch(`${svc2.baseURL}/notes`);
  if (listRes.status !== 200) throw new Error('List after restart failed');
  const notes = await listRes.json();
  if (!Array.isArray(notes)) throw new Error('Response not array');
  if (notes.length !== 1 || notes[0].title !== 'Persist') throw new Error('Note not persisted');
  await svc2.stop();
});

// [AC-7] JSON over HTTP schema
test('[AC-7] response bodies are JSON with id, title, body', async ({ request }) => {
  const payload = { title: 'Schema', body: 'Check' };
  const res = await request.post('/notes', { data: payload });
  const json = await res.json();
  expect(typeof json.id).toBe('number');
  expect(typeof json.title).toBe('string');
  expect(typeof json.body).toBe('string');
});

// [AC-8] POST /notes creates note and returns it
test('[AC-8] post creates note and returns it', async ({ request }) => {
  const payload = { title: 'Create', body: 'Body' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json.title).toBe(payload.title);
});

// [AC-9] GET /notes returns array of notes
test('[AC-9] get all notes returns array', async ({ request }) => {
  const payload = { title: 'All', body: 'List' };
  await request.post('/notes', { data: payload });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const arr = await res.json();
  expect(Array.isArray(arr)).toBe(true);
});

// [AC-10] GET /notes/:id returns 404 when none
test('[AC-10] get non-existent note', async ({ request }) => {
  const res = await request.get('/notes/123456');
  expect(res.status()).toBe(404);
});

// [AC-11] PUT /notes/:id returns 200 and updates; missing id returns 404
test('[AC-11] put updates note and handles missing', async ({ request }) => {
  const payload = { title: 'Update', body: 'Body' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const updPayload = { title: 'Updated', body: 'NewBody' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updPayload });
  expect(updRes.status()).toBe(200);

  const missingRes = await request.put('/notes/9999', { data: updPayload });
  expect(missingRes.status()).toBe(404);
});

// [AC-12] DELETE /notes/:id returns 204 and missing case
test('[AC-12] delete note and missing case', async ({ request }) => {
  const payload = { title: 'ToDelete2', body: '' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  const missingDel = await request.delete('/notes/9999');
  expect(missingDel.status()).toBe(404);
});

// [AC-13] Missing or empty title rejected with 400
test('[AC-13][AC-18] missing title', async ({ request }) => {
  const beforeRes = await request.get('/notes');
  const before = await beforeRes.json();
  const beforeCount = before.length;

  const res1 = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(res1.status()).toBe(400);
  const err1 = await res1.json();
  expect(err1.error).toBe('Title is required');

  const res2 = await request.post('/notes', { data: { title: '   ', body: 'Empty' } });
  expect(res2.status()).toBe(400);
  const err2 = await res2.json();
  expect(err2.error).toBe('Title is required');

  const afterRes = await request.get('/notes');
  const after = await afterRes.json();
  expect(after.length).toBe(beforeCount);
});

// [AC-14] GET /health returns 200
test('[AC-14][AC-15] health check', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
