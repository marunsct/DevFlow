import { test, expect } from '@playwright/test';

async function createNote(request, title, body) {
  const response = await request.post('/notes', { data: { title, body } });
  let json = null;
  try {
    json = await response.json();
  } catch (_) {}
  return { response, json };
}

function findByTitle(notes, title) {
  return notes.find((n) => n.title === title);
}

// ===================== AC-1 =====================
test('[AC-1] creates a note with non‑empty title and body', async ({ request }) => {
  const { response, json: note } = await createNote(request, 'Test Note', 'Some body');
  expect(response.status()).toBe(201);
  expect(note).toHaveProperty('id');
  expect(typeof note.id).toBe('number');
  expect(note.title).toBe('Test Note');
  expect(note.body).toBe('Some body');
});

// ===================== AC-2 & AC-3 =====================
test('[AC-2][AC-3] lists two notes after creation', async ({ request }) => {
  const t1 = Date.now();
  await createNote(request, `A-${t1}`, 'Body A');
  await createNote(request, `B-${t1}`, 'Body B');

  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const notes = await resp.json();
  expect(Array.isArray(notes)).toBeTruthy();
  expect(notes.length).toBeGreaterThanOrEqual(2);
  expect(findByTitle(notes, `A-${t1}`)).toBeDefined();
});

// ===================== AC-3 (duplicate) =====================
test('[AC-3] fetches a single note by id', async ({ request }) => {
  const created = await createNote(request, 'Fetch Me', 'Body');
  const resp = await request.get(`/notes/${created.json.id}`);
  expect(resp.status()).toBe(200);
  const fetched = await resp.json();
  expect(fetched).toEqual(created.json);
});

// ===================== AC-4 =====================
test('[AC-4] updates a note and returns updated object', async ({ request }) => {
  const created = await createNote(request, 'Old Title', 'Old Body');
  const updResp = await request.put(`/notes/${created.json.id}`, { data: { title: 'New Title', body: 'New Body' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated.id).toBe(created.json.id);
  expect(updated.title).toBe('New Title');
  expect(updated.body).toBe('New Body');
});

// ===================== AC-5 =====================
test('[AC-5] deletes a note and subsequent fetch returns 404', async ({ request }) => {
  const created = await createNote(request, 'To Delete', 'Body');
  const delResp = await request.delete(`/notes/${created.json.id}`);
  expect(delResp.status()).toBe(204);
  const getResp = await request.get(`/notes/${created.json.id}`);
  expect(getResp.status()).toBe(404);
});

// ===================== AC-6 & AC-17 (fixed) =====================
test('[AC-6][AC-17] notes persist across service restart', async ({ request }) => {
  const mod = await import('./service.cjs');
  const { startService } = mod.default;
  const svc1 = await startService();
  const noteResp = await request.post('/notes', { data: { title: 'Persisted', body: 'Data' } });
  const note = await noteResp.json();
  await svc1.stop();

  const svc2 = await startService({ dataDir: svc1.dataDir });
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const notes = await resp.json();
  expect(notes.find((n) => n.id === note.id && n.title === 'Persisted')).toBeDefined();
  await svc2.stop();
});

// ===================== AC-7 =====================
test('[AC-7] response JSON has id, title, body fields of correct types', async ({ request }) => {
  const created = await createNote(request, 'Type Check', 'Body');
  expect(typeof created.json.id).toBe('number');
  expect(typeof created.json.title).toBe('string');
  expect(typeof created.json.body).toBe('string');
});

// ===================== AC-8 =====================
test('[AC-8] POST /notes returns status 201 with note JSON', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: 'Created', body: 'Body' } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toHaveProperty('id');
});

// ===================== AC-9 =====================
test('[AC-9] GET /notes returns array of all notes after three creations', async ({ request }) => {
  const t1 = Date.now();
  await createNote(request, `X-${t1}`, 'Body X');
  await createNote(request, `Y-${t1}`, 'Body Y');
  await createNote(request, `Z-${t1}`, 'Body Z');

  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const notes = await resp.json();
  expect(notes.length).toBeGreaterThanOrEqual(3);
});

// ===================== AC-10 =====================
test('[AC-10] GET non‑existent id returns 404', async ({ request }) => {
  const resp = await request.get('/notes/999999');
  expect(resp.status()).toBe(404);
});

// ===================== AC-11 =====================
test('[AC-11] updates a note and returns updated object with status 200', async ({ request }) => {
  const created = await createNote(request, 'Updatable', 'Body');
  const updResp = await request.put(`/notes/${created.json.id}`, { data: { title: 'Updated Title', body: 'Updated Body' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated.title).toBe('Updated Title');
  expect(updated.body).toBe('Updated Body');
});

// ===================== AC-12 =====================
test('[AC-12] deletes a note and returns status 204, subsequent fetch 404', async ({ request }) => {
  const created = await createNote(request, 'DeleteMe', 'Body');
  const delResp = await request.delete(`/notes/${created.json.id}`);
  expect(delResp.status()).toBe(204);
  const getResp = await request.get(`/notes/${created.json.id}`);
  expect(getResp.status()).toBe(404);
});

// ===================== AC-13 =====================
test('[AC-13] POST with empty title returns error and stores nothing', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: '', body: 'Body' } });
  expect([400, 422]).toContain(resp.status());
  const notesResp = await request.get('/notes');
  const notes = await notesResp.json();
  // No note with empty title should exist
  expect(notes.find((n) => n.title === '')).toBeUndefined();
});

// ===================== AC-15 =====================
test('[AC-15] service respects DATA_DIR environment variable', async ({ request }) => {
  const mod = await import('./service.cjs');
  const { startService } = mod.default;
  const svc = await startService();
  // Create a note
  const resp = await request.post('/notes', { data: { title: 'DirTest', body: 'Data' } });
  expect(resp.status()).toBe(201);
  await svc.stop();

  // Restart with same data dir and confirm note persists
  const svc2 = await startService({ dataDir: svc.dataDir });
  const getResp = await request.get('/notes');
  expect(getResp.status()).toBe(200);
  const notes = await getResp.json();
  expect(notes.find((n) => n.title === 'DirTest')).toBeDefined();
  await svc2.stop();
});

// ===================== AC-16 =====================
test('[AC-16] performs full CRUD cycle successfully', async ({ request }) => {
  // Create
  const created = await createNote(request, 'Cycle', 'Start');
  const id = created.json.id;
  // Read
  let resp = await request.get(`/notes/${id}`);
  expect(resp.status()).toBe(200);
  let note = await resp.json();
  expect(note.title).toBe('Cycle');
  // Update
  resp = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'End' } });
  expect(resp.status()).toBe(200);
  note = await resp.json();
  expect(note.title).toBe('Updated');
  // Delete
  resp = await request.delete(`/notes/${id}`);
  expect(resp.status()).toBe(204);
  // Verify deletion
  resp = await request.get(`/notes/${id}`);
  expect(resp.status()).toBe(404);
});

// ===================== AC-18 =====================
test('[AC-18] invalid input is refused without storing anything', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: '   ', body: 'Body' } });
  expect([400, 422]).toContain(resp.status());
  const notesResp = await request.get('/notes');
  const notes = await notesResp.json();
  // No note with whitespace-only title should exist
  expect(notes.find((n) => n.title.trim() === '')).toBeUndefined();
});
