import { test, expect } from '@playwright/test';

// Helper that returns status, parsed body (if JSON and not 204), and headers.
async function jsonResponse(resp) {
  const status = resp.status();
  let body = null;
  if (status !== 204 && resp.headers()['content-type']?.includes('json')) {
    try { body = await resp.json(); } catch (_) { body = null; }
  }
  return { status, body, headers: resp.headers() };
}

// -------------------------------------------
// AC-1 Create a note with title and body
// -------------------------------------------
test('[AC-1] Create a note with title and body', async ({ request }) => {
  const payload = { title: 'Test Note', body: 'Hello world' };
  const res = await request.post('/notes', { data: payload });
  const { status, body, headers } = await jsonResponse(res);
  expect(status).toBe(201);
  expect(body).toHaveProperty('id');
  expect(typeof body.id).toBe('number');
  expect(body.title).toBe(payload.title);
  expect(body.body).toBe(payload.body);
  const location = headers['location'];
  expect(location).toMatch(/\/notes\/[0-9]+$/);
});

// -------------------------------------------
// AC-2 List all notes
// -------------------------------------------
test('[AC-2][AC-9] List all notes', async ({ request }) => {
  const payload1 = { title: 'First', body: 'One' };
  const payload2 = { title: 'Second', body: 'Two' };
  await request.post('/notes', { data: payload1 });
  await request.post('/notes', { data: payload2 });

  const res = await request.get('/notes');
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(200);
  expect(Array.isArray(body)).toBe(true);
  const titles = body.map(n => n.title);
  expect(titles).toContain(payload1.title);
  expect(titles).toContain(payload2.title);
});

// -------------------------------------------
// AC-3 Fetch a note by id and handle missing
// -------------------------------------------
test('[AC-3] Fetch a note by id and handle missing', async ({ request }) => {
  const payload = { title: 'Fetch Me', body: 'Data' };
  const createRes = await request.post('/notes', { data: payload });
  const created = (await createRes.json());
  const id = created.id;

  const getRes = await request.get(`/notes/${id}`);
  const { status, body } = await jsonResponse(getRes);
  expect(status).toBe(200);
  expect(body.title).toBe(payload.title);
  expect(body.body).toBe(payload.body);

  const missRes = await request.get('/notes/999999');
  const { status: missStatus, body: missBody } = await jsonResponse(missRes);
  expect(missStatus).toBe(404);
  expect(missBody).toEqual({ error: 'Not found' });
});

// -------------------------------------------
// AC-4 Update a note
// -------------------------------------------
test('[AC-4] Update a note', async ({ request }) => {
  const payload = { title: 'Old Title', body: 'Old Body' };
  const createRes = await request.post('/notes', { data: payload });
  const created = (await createRes.json());
  const id = created.id;

  const updatePayload = { title: 'New Title', body: 'New Body' };
  const updRes = await request.put(`/notes/${id}`, { data: updatePayload });
  const { status, body } = await jsonResponse(updRes);
  expect(status).toBe(200);
  expect(body.id).toBe(id);
  expect(body.title).toBe(updatePayload.title);
  expect(body.body).toBe(updatePayload.body);

  const getRes = await request.get(`/notes/${id}`);
  const { body: getBody } = await jsonResponse(getRes);
  expect(getBody.title).toBe(updatePayload.title);
});

// -------------------------------------------
// AC-5 Delete a note
// -------------------------------------------
test('[AC-5] Delete a note', async ({ request }) => {
  const payload = { title: 'To Delete', body: '' };
  const createRes = await request.post('/notes', { data: payload });
  const created = (await createRes.json());
  const id = created.id;

  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${id}`);
  const { status, body } = await jsonResponse(getRes);
  expect(status).toBe(404);
  expect(body).toEqual({ error: 'Not found' });
});

// -------------------------------------------
// AC-6 & AC-17 Notes survive a restart of the service
// -------------------------------------------
test('[AC-6][AC-17] Notes survive a restart of the service', async () => {
  const { startService } = await import('./service.cjs');
  const first = await startService();
  const createRes = await fetch(first.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persisted', body: 'Data' }),
  });
  expect(createRes.status).toBe(201);
  const firstNote = await createRes.json();

  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const getRes = await fetch(second.baseURL + '/notes');
  expect(getRes.status).toBe(200);
  const notes = await getRes.json();
  expect(notes.length).toBeGreaterThanOrEqual(1);
  const found = notes.find(n => n.id === firstNote.id && n.title === 'Persisted');
  expect(found).toBeDefined();

  await second.stop();
});

// -------------------------------------------
// AC-7 Note JSON schema
// -------------------------------------------
test('[AC-7] Note JSON schema', async ({ request }) => {
  const payload = { title: 'Schema Test', body: 'Check' };
  const res = await request.post('/notes', { data: payload });
  const body = await res.json();
  expect(body).toHaveProperty('id');
  expect(typeof body.id).toBe('number');
  expect(body.title).toBe(payload.title);
  expect(body.body).toBe(payload.body);
  expect(Object.keys(body)).toEqual(['id', 'title', 'body']);
});

// -------------------------------------------
// AC-8 POST /notes returns Location header and port usage
// -------------------------------------------
test('[AC-8][AC-15] POST /notes returns Location header', async ({ request }) => {
  const payload = { title: 'Location', body: '' };
  const res = await request.post('/notes', { data: payload });
  const location = res.headers()['location'];
  expect(location).toMatch(/\/notes\/[0-9]+$/);
});

// -------------------------------------------
// AC-10 GET /notes/:id returns 404 for non-existent
// -------------------------------------------
test('[AC-10] GET /notes/:id returns 404 for non-existent', async ({ request }) => {
  const res = await request.get('/notes/1234567890');
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(404);
  expect(body).toEqual({ error: 'Not found' });
});

// -------------------------------------------
// AC-11 PUT /notes/:id for non-existent returns 404
// -------------------------------------------
test('[AC-11] PUT /notes/:id for non-existent returns 404', async ({ request }) => {
  const res = await request.put('/notes/9876543210', { data: { title: 'X', body: '' } });
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(404);
  expect(body).toEqual({ error: 'Not found' });
});

// -------------------------------------------
// AC-12 DELETE /notes/:id for non-existent returns 404
// -------------------------------------------
test('[AC-12] DELETE /notes/:id for non-existent returns 404', async ({ request }) => {
  const res = await request.delete('/notes/1122334455');
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(404);
  expect(body).toEqual({ error: 'Not found' });
});

// -------------------------------------------
// AC-13 Missing title is refused with 400
// -------------------------------------------
test('[AC-13] Missing title is refused with 400', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(400);
  expect(body).toEqual({ error: 'Title required' });
});

// -------------------------------------------
// AC-16 Full CRUD flow test
// -------------------------------------------
test('[AC-16] Full CRUD flow', async ({ request }) => {
  // Create
  const createRes = await request.post('/notes', { data: { title: 'CR', body: 'A' } });
  const created = await createRes.json();
  expect(createRes.status()).toBe(201);
  const id = created.id;

  // Read list contains it
  const listRes = await request.get('/notes');
  const listBody = await listRes.json();
  expect(listBody.some(n => n.id === id)).toBe(true);

  // Update
  const updRes = await request.put(`/notes/${id}`, { data: { title: 'CR Updated', body: 'B' } });
  const updBody = await updRes.json();
  expect(updRes.status()).toBe(200);
  expect(updBody.title).toBe('CR Updated');

  // Get single
  const getRes = await request.get(`/notes/${id}`);
  const getBody = await getRes.json();
  expect(getBody.body).toBe('B');

  // Delete
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  // Confirm deletion
  const afterDelRes = await request.get(`/notes/${id}`);
  const { status, body } = await jsonResponse(afterDelRes);
  expect(status).toBe(404);
});

// -------------------------------------------
// AC-18 Invalid input does not store data
// -------------------------------------------
test('[AC-18] Invalid input is refused without storing', async ({ request }) => {
  // Ensure no notes initially
  const listBefore = await request.get('/notes');
  const beforeBody = await listBefore.json();
  const initialCount = beforeBody.length;

  // Attempt invalid create
  const badRes = await request.post('/notes', { data: { body: 'No title' } });
  expect(badRes.status()).toBe(400);

  // Ensure count unchanged
  const listAfter = await request.get('/notes');
  const afterBody = await listAfter.json();
  expect(afterBody.length).toBe(initialCount);
});

// -------------------------------------------
// AC-14 GET /health returns ok
// -------------------------------------------
test('[AC-14] GET /health returns ok', async ({ request }) => {
  const res = await request.get('/health');
  const { status, body } = await jsonResponse(res);
  expect(status).toBe(200);
  expect(body).toEqual({ status: 'ok' });
});
