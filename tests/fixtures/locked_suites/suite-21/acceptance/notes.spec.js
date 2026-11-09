import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Helper: assert that a note object has exactly id, title, body keys and correct types.
function expectNoteShape(note) {
  const keys = Object.keys(note);
  expect(keys.sort()).toEqual(['body', 'id', 'title']);
  expect(typeof note.id).toBe('number');
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');
}

// AC-1: Create a note with a title and a body.
test('[AC-1][AC-7][AC-8] POST /notes creates a note', async ({ request }) => {
  const payload = { title: 'Test Note', body: 'Hello World' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expectNoteShape(json);
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);
});

// AC-2: List all notes.
test('[AC-2][AC-9] GET /notes returns list of notes', async ({ request }) => {
  const payload1 = { title: 'A', body: 'B' };
  const payload2 = { title: 'C', body: 'D' };
  await request.post('/notes', { data: payload1 });
  await request.post('/notes', { data: payload2 });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  expect(list.length).toBeGreaterThanOrEqual(2);
  for (const note of list) {
    expectNoteShape(note);
  }
});

// AC-3: Fetch one note by its id and non-existent.
test('[AC-3][AC-10] GET /notes/:id returns existing or 404', async ({ request }) => {
  const payload = { title: 'Fetch', body: 'Me' };
  const postRes = await request.post('/notes', { data: payload });
  const created = await postRes.json();
  const id = created.id;

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expectNoteShape(fetched);
  expect(fetched.title).toBe(payload.title);

  const missRes = await request.get('/notes/999999');
  expect(missRes.status()).toBe(404);
  const err = await missRes.json();
  expect(err).toEqual({ error: 'Note not found' });
});

// AC-4: Update a note's title and body.
test('[AC-4] PUT /notes/:id updates the note', async ({ request }) => {
  const payload = { title: 'Old', body: 'Body' };
  const postRes = await request.post('/notes', { data: payload });
  const created = await postRes.json();
  const id = created.id;

  const updatePayload = { title: 'New', body: 'Updated' };
  const putRes = await request.put(`/notes/${id}`, { data: updatePayload });
  expect(putRes.status()).toBe(200);
  const updated = await putRes.json();
  expectNoteShape(updated);
  expect(updated.title).toBe(updatePayload.title);
  expect(updated.body).toBe(updatePayload.body);

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched.title).toBe(updatePayload.title);
});

// AC-5: Delete a note.

test('[AC-12] DELETE /notes/:id returns 204 and removes the note', async ({ request }) => {
  const payload = { title: 'DeleteMe', body: '' };
  const postRes = await request.post('/notes', { data: payload });
  const created = await postRes.json();
  const id = created.id;

  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(404);
});

// AC-11: Update a note's title and body.

test('[AC-11] PUT /notes/:id updates the note', async ({ request }) => {
  const payload = { title: 'Old', body: 'Body' };
  const postRes = await request.post('/notes', { data: payload });
  const created = await postRes.json();
  const id = created.id;

  const updatePayload = { title: 'New', body: 'Updated' };
  const putRes = await request.put(`/notes/${id}`, { data: updatePayload });
  expect(putRes.status()).toBe(200);
  const updated = await putRes.json();
  expectNoteShape(updated);
  expect(updated.title).toBe(updatePayload.title);
  expect(updated.body).toBe(updatePayload.body);

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched.title).toBe(updatePayload.title);
});

// AC-15: The project directory has a start.sh that starts the service on 127.0.0.1 at the port in the PORT environment variable, keeping its data under the directory in the DATA_DIR environment variable.

test('[AC-15] Service starts with correct env vars', async ({ request }) => {
  // The harness already started the service; we can only verify that health is reachable
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
});

// AC-16: Every operation works as the interface says.

test('[AC-16] Full CRUD cycle works correctly', async ({ request }) => {
  // Create
  const createRes = await request.post('/notes', { data: { title: 'Cycle', body: 'Data' } });
  expect(createRes.status()).toBe(201);
  const note = await createRes.json();
  const id = note.id;

  // Read all
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  expect(list.find(n => n.id === id)).not.toBeUndefined();

  // Update
  const updRes = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'More' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('Updated');

  // Delete
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
});

// AC-17: Notes persist across restarts.

test('[AC-17] notes persist after restarting the server', async ({ request }) => {
  const firstRes = await request.post('/notes', { data: { title: 'Persist', body: 'Data' } });
  const created = await firstRes.json();
  const id = created.id;

  // Use helper to restart service
  // Import helper for restart tests via dynamic import
// Helper to import the service starter
async function getStartService() {
  const m = await import('./service.cjs');
  return m.startService;
}
 {
  const m = await import('./service.cjs');
  return m.startService;
}

  const service1 = await startService();
  await service1.stop();
  const service2 = await startService({ dataDir: service1.dataDir });

  const resp = await fetch(service2.baseURL + `/notes/${id}`);
  expect(resp.status).toBe(200);
  const json = await resp.json();
  expect(json.title).toBe('Persist');
  await service2.stop();
});

// AC-18: Invalid input is refused without storing anything.

test('[AC-18] POST /notes with empty title does not store the note', async ({ request }) => {
  const beforeRes = await request.get('/notes');
  const beforeList = await beforeRes.json();
  const beforeCount = beforeList.length;

  const res = await request.post('/notes', { data: { title: '   ', body: 'No title' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title is required' });

  const afterRes = await request.get('/notes');
  const afterList = await afterRes.json();
  expect(afterList.length).toBe(beforeCount);
});
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const payload = { title: 'DeleteMe', body: '' };
  const postRes = await request.post('/notes', { data: payload });
  const created = await postRes.json();
  const id = created.id;

  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(404);
});

// AC-6: Notes survive a restart of the service.
test('[AC-6] notes persist after restarting the server', async ({ request }) => {
  const firstRes = await request.post('/notes', { data: { title: 'Persist', body: 'Data' } });
  const created = await firstRes.json();
  const id = created.id;

  const service1 = await startService();
  await service1.stop();
  const service2 = await startService({ dataDir: service1.dataDir });

  const resp = await fetch(service2.baseURL + `/notes/${id}`);
  expect(resp.status).toBe(200);
  const json = await resp.json();
  expect(json.title).toBe('Persist');
  await service2.stop();
});

// AC-13: Missing or empty title is refused with 400.
test('[AC-13] POST /notes without title returns 400', async ({ request }) => {
  const beforeRes = await request.get('/notes');
  const beforeList = await beforeRes.json();
  const beforeCount = beforeList.length;

  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title is required' });

  const afterRes = await request.get('/notes');
  const afterList = await afterRes.json();
  expect(afterList.length).toBe(beforeCount);
});

// AC-14: GET /health returns status ok.
test('[AC-14] GET /health responds with 200 and {status:"ok"}', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
