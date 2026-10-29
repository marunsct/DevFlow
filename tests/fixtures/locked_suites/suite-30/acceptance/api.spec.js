import { test, expect } from '@playwright/test';

// Load the CommonJS helper via dynamic import so this ESM file works.
async function loadService() {
  const mod = await import('./service.cjs');
  return mod;
}

// ─── AC-14: GET /health answers 200 ──────────────────────────────────────────

test('[AC-14] health endpoint returns 200', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toEqual({ status: 'ok' });
});

// ─── AC-1, AC-8: Create a note with title and body → 201 ─────────────────────

test('[AC-1][AC-8] create a note via POST /notes', async ({ request }) => {
  const response = await request.post('/notes', {
    data: { title: 'Test Note', body: 'Content' },
  });
  expect(response.status()).toBe(201);
  const note = await response.json();
  expect(typeof note.id).toBe('number');
  expect(note.title).toBe('Test Note');
  expect(note.body).toBe('Content');
});

// ─── AC-2, AC-9: List all notes → 200 with JSON array ────────────────────────

test('[AC-2][AC-9] list all notes via GET /notes', async ({ request }) => {
  const createResp = await request.post('/notes', {
    data: { title: 'List Item 1', body: 'Body 1' },
  });
  expect(createResp.status()).toBe(201);

  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  expect(Array.isArray(notes)).toBeTruthy();
  expect(notes.length).toBeGreaterThanOrEqual(1);
  const found = notes.find((n) => n.title === 'List Item 1');
  expect(found).toBeDefined();
});

// ─── AC-3, AC-7: Fetch one note by id → 200 with correct JSON shape ──────────

test('[AC-3][AC-7] fetch a note by id', async ({ request }) => {
  const createResp = await request.post('/notes', {
    data: { title: 'Fetch Me', body: 'Body' },
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  const note = await getResp.json();
  expect(note).toEqual({
    id: created.id,
    title: 'Fetch Me',
    body: 'Body',
  });
});

// ─── AC-3, AC-10: Fetch a non-existent note → 404 ─────────────────────────────

test('[AC-3][AC-10] fetch a non-existent note returns 404', async ({ request }) => {
  const response = await request.get('/notes/999999');
  expect(response.status()).toBe(404);
});

// ─── AC-4, AC-7, AC-11: Update a note → 200 with correct shape ────────────────

test('[AC-4][AC-7][AC-11] update an existing note via PUT /notes/:id', async ({
  request,
}) => {
  const createResp = await request.post('/notes', {
    data: { title: 'Old Title', body: 'Old Body' },
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  const putResp = await request.put(`/notes/${created.id}`, {
    data: { title: 'New Title', body: 'New Body' },
  });
  expect(putResp.status()).toBe(200);
  const updated = await putResp.json();
  expect(updated).toEqual({
    id: created.id,
    title: 'New Title',
    body: 'New Body',
  });
});

// ─── AC-11: Update a non-existent note → 404 ──────────────────────────────────

test('[AC-11] update a non-existent note returns 404', async ({ request }) => {
  const response = await request.put('/notes/999999', {
    data: { title: 'X', body: 'Y' },
  });
  expect(response.status()).toBe(404);
});

// ─── AC-5, AC-12: Delete a note → 204 ─────────────────────────────────────────

test('[AC-5][AC-12] delete an existing note', async ({ request }) => {
  const createResp = await request.post('/notes', {
    data: { title: 'To Delete', body: 'Gone' },
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  const delResp = await request.delete(`/notes/${created.id}`);
  expect(delResp.status()).toBe(204);

  // Confirm it is gone
  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(404);
});

// ─── AC-5, AC-12: Delete a non-existent note → 404 ────────────────────────────

test('[AC-5][AC-12] delete a non-existent note returns 404', async ({ request }) => {
  const response = await request.delete('/notes/999999');
  expect(response.status()).toBe(404);
});

// ─── AC-6, AC-17: Notes survive a restart of the service ──────────────────────

test('[AC-6][AC-17] notes persist across a server restart', async ({ request }) => {
  // Create a note via the first service instance so its dataDir receives the write.
  const { startService } = await loadService();
  const svc = await startService();

  try {
    const createResp = await request.post(`${svc.baseURL}/notes`, {
      data: { title: 'Persist Me', body: 'Stays' },
    });
    expect(createResp.status()).toBe(201);
    const created = await createResp.json();

    // Stop the first service and start a second one on the same dataDir.
    await svc.stop();

    const second = await startService({ dataDir: svc.dataDir });
    try {
      const listResp = await request.get(`${second.baseURL}/notes`);
      expect(listResp.status()).toBe(200);
      const notes = await listResp.json();
      expect(Array.isArray(notes)).toBeTruthy();
      const found = notes.find((n) => n.id === created.id);
      expect(found).toBeDefined();
      expect(found.title).toBe('Persist Me');
      expect(found.body).toBe('Stays');
    } finally {
      await second.stop();
    }
  } finally {
    // If svc is still running, stop it.
    try { await svc.stop(); } catch (_) {}
  }
});

// ─── AC-7: JSON shape is always {"id": int, "title": str, "body": str} ────────

test('[AC-7][AC-16] response shapes are correct for all CRUD operations', async ({
  request,
}) => {
  // POST → 201 with correct shape
  const postResp = await request.post('/notes', {
    data: { title: 'Shape Test', body: 'OK' },
  });
  expect(postResp.status()).toBe(201);
  const note = await postResp.json();
  expect(typeof note.id).toBe('number');
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');

  // GET single → 200 with correct shape
  const getResp = await request.get(`/notes/${note.id}`);
  expect(getResp.status()).toBe(200);
  const single = await getResp.json();
  expect(single).toEqual({ id: note.id, title: 'Shape Test', body: 'OK' });

  // PUT → 200 with correct shape
  const putResp = await request.put(`/notes/${note.id}`, {
    data: { title: 'Updated Shape', body: 'Still OK' },
  });
  expect(putResp.status()).toBe(200);
  const updated = await putResp.json();
  expect(updated).toEqual({ id: note.id, title: 'Updated Shape', body: 'Still OK' });

  // DELETE → 204 (no body)
  const delResp = await request.delete(`/notes/${note.id}`);
  expect(delResp.status()).toBe(204);
});

// ─── AC-13: Missing or empty title is refused with 400, nothing stored ─────────

test('[AC-13] POST /notes rejects empty title', async ({ request }) => {
  const before = await request.get('/notes');
  expect(before.status()).toBe(200);
  const beforeNotes = await before.json();

  const resp = await request.post('/notes', {
    data: { title: '', body: 'Content' },
  });
  expect(resp.status()).toBe(400);
  const errBody = await resp.json();
  expect(errBody).toEqual({ error: 'Title is required' });

  // Verify nothing was stored
  const after = await request.get('/notes');
  const afterNotes = await after.json();
  expect(afterNotes.length).toBe(beforeNotes.length);
});

// ─── AC-13, AC-9: Missing title field also rejected ────────────────────────────

test('[AC-13] POST /notes rejects missing title', async ({ request }) => {
  const before = await request.get('/notes');
  expect(before.status()).toBe(200);
  const beforeNotes = await before.json();

  const resp = await request.post('/notes', {
    data: { body: 'Content' },
  });
  expect(resp.status()).toBe(400);

  // Verify nothing was stored
  const after = await request.get('/notes');
  const afterNotes = await after.json();
  expect(afterNotes.length).toBe(beforeNotes.length);
});

// ─── AC-18: Invalid input is refused without storing anything ──────────────────

test('[AC-18] PUT /notes/:id with invalid title does not modify existing note', async ({
  request,
}) => {
  // Create a note first
  const createResp = await request.post('/notes', {
    data: { title: 'Original', body: 'Body' },
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  // Try to update with empty title
  const putResp = await request.put(`/notes/${created.id}`, {
    data: { title: '', body: 'New Body' },
  });
  expect(putResp.status()).toBe(400);

  // Verify the original note is unchanged
  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  const stillThere = await getResp.json();
  expect(stillThere.title).toBe('Original');
});

// ─── AC-18: Invalid ID format is refused ──────────────────────────────────────

test('[AC-18] GET /notes/abc returns 400', async ({ request }) => {
  const response = await request.get('/notes/abc');
  expect(response.status()).toBe(400);
});

// ─── AC-18: Zero is not a valid ID ────────────────────────────────────────────

test('[AC-18] GET /notes/0 returns 400', async ({ request }) => {
  const response = await request.get('/notes/0');
  expect(response.status()).toBe(400);
});
