import { test, expect } from '@playwright/test';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { startService } = require('./service.cjs');
const { existsSync, statSync } = require('fs');
const { dirname, join } = require('path');

const acceptanceDir = dirname(require.resolve('./service.cjs'));
const startShPath = join(acceptanceDir, '..', 'start.sh');

// ── AC-14 ───────────────────────────────────────────────────────────────────
// Proves the health endpoint answers 200 with {"status": "ok"}.
test('[AC-14] health check returns 200 with ok status', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toEqual({ status: 'ok' });
  expect(response.headers()['content-type']).toContain('application/json');
});

// ── AC-15 ───────────────────────────────────────────────────────────────────
// Verifies start.sh exists and is executable. The running product proves the
// service starts on PORT, uses DATA_DIR for persistence, and binds to 127.0.0.1.
test('[AC-15] start.sh exists and is executable', () => {
  expect(existsSync(startShPath)).toBe(true);
  const stats = statSync(startShPath);
  const isExecutable = (stats.mode & 0o111) !== 0;
  expect(isExecutable).toBe(true);
});

// ── AC-1 [AC-8] ─────────────────────────────────────────────────────────────
// POST /notes with a valid JSON body creates a note and returns 201 with the
// note payload (id, title, body).  Verifies exact response shape.
test('[AC-1][AC-8] create a note with title and body', async ({ request }) => {
  const response = await request.post('/notes', {
    data: { title: 'Test Note', body: 'Test Body' }
  });
  expect(response.status()).toBe(201);
  const note = await response.json();
  // Verify exact response shape matches interface contract: id (integer), title (string), body (string)
  expect(note).toEqual({ id: expect.any(Number), title: 'Test Note', body: 'Test Body' });
  expect(Number.isInteger(note.id)).toBe(true);
});

// ── AC-2 [AC-9] ─────────────────────────────────────────────────────────────
// GET /notes returns 200 with a JSON array containing every note, ordered by id ASC.
test('[AC-2][AC-9] list all notes', async ({ request }) => {
  // Create two notes so we can verify ordering.
  const createResp1 = await request.post('/notes', {
    data: { title: 'List Test A', body: 'Body for list A' }
  });
  expect(createResp1.status()).toBe(201);
  const created1 = await createResp1.json();

  const createResp2 = await request.post('/notes', {
    data: { title: 'List Test B', body: 'Body for list B' }
  });
  expect(createResp2.status()).toBe(201);
  const created2 = await createResp2.json();

  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const notes = await response.json();
  expect(Array.isArray(notes)).toBe(true);

  // Verify notes are ordered by id ASC.
  for (let i = 1; i < notes.length; i++) {
    expect(notes[i].id).toBeGreaterThan(notes[i - 1].id);
  }

  // Find our own notes; do not count all notes (other tests may leave data).
  const found1 = notes.find(n => n.id === created1.id);
  const found2 = notes.find(n => n.id === created2.id);
  expect(found1).toBeDefined();
  expect(found1.title).toBe('List Test A');
  expect(found1.body).toBe('Body for list A');
  expect(found2).toBeDefined();
  expect(found2.title).toBe('List Test B');
  expect(found2.body).toBe('Body for list B');
});

// ── AC-3 [AC-10] ────────────────────────────────────────────────────────────
// GET /notes/{id} returns 200 with the note for an existing id, or 404 when
// the note does not exist.
test('[AC-3][AC-10] fetch a note by id and 404 for non-existent', async ({ request }) => {
  // Create a note to obtain its id.
  const createResp = await request.post('/notes', {
    data: { title: 'Fetch Test', body: 'Body for fetch' }
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  // Existing note → 200.
  const response = await request.get(`/notes/${created.id}`);
  expect(response.status()).toBe(200);
  const note = await response.json();
  expect(note.id).toBe(created.id);
  expect(note.title).toBe('Fetch Test');
  expect(note.body).toBe('Body for fetch');

  // Non-existent note → 404.
  const notFound = await request.get('/notes/999999');
  expect(notFound.status()).toBe(404);
});

// ── AC-4 [AC-11] ────────────────────────────────────────────────────────────
// PUT /notes/{id} replaces both title and body and returns 200 with the note
// for an existing id, or 404 when the note does not exist.
test('[AC-4][AC-11] update a note and 404 for non-existent', async ({ request }) => {
  // Create a note to obtain its id.
  const createResp = await request.post('/notes', {
    data: { title: 'Update Test', body: 'Original body' }
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  // Existing note → 200 with updated data.
  const response = await request.put(`/notes/${created.id}`, {
    data: { title: 'Updated Title', body: 'Updated Body' }
  });
  expect(response.status()).toBe(200);
  const note = await response.json();
  expect(note.id).toBe(created.id);
  expect(note.title).toBe('Updated Title');
  expect(note.body).toBe('Updated Body');

  // Non-existent note → 404.
  const notFound = await request.put('/notes/999999', {
    data: { title: 'Nope', body: 'Nope' }
  });
  expect(notFound.status()).toBe(404);
});

// ── AC-5 [AC-12] ────────────────────────────────────────────────────────────
// DELETE /notes/{id} returns 204 for an existing note (and removes it), or
// 404 when the note does not exist.
test('[AC-5][AC-12] delete a note and 404 for non-existent', async ({ request }) => {
  // Create a note to obtain its id.
  const createResp = await request.post('/notes', {
    data: { title: 'Delete Test', body: 'Body for delete' }
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

  // Existing note → 204, then verify it is gone.
  const response = await request.delete(`/notes/${created.id}`);
  expect(response.status()).toBe(204);

  const afterDelete = await request.get(`/notes/${created.id}`);
  expect(afterDelete.status()).toBe(404);

  // Non-existent note → 404.
  const notFound = await request.delete('/notes/999999');
  expect(notFound.status()).toBe(404);
});

// ── AC-6 [AC-17] ────────────────────────────────────────────────────────────
// Notes survive a restart of the service.  Uses the harness helper to stop the
// running service, start a new one on the same DATA_DIR, and verify the note
// is still present.
test('[AC-6][AC-17] notes persist across service restart', async ({ request }) => {
  // Start a service using the harness helper (separate from the webServer).
  const first = await startService();

  // Create a note on the first instance.
  const createResp = await request.post(first.baseURL + '/notes', {
    data: { title: 'Persist Test', body: 'Body for persist' }
  });
  expect(createResp.status()).toBe(201);
  const note = await createResp.json();

  // Stop the first service.
  await first.stop();

  // Start a second service pointing at the same data directory.
  const second = await startService({ dataDir: first.dataDir });

  // Verify the note survived the restart.
  const notesResp = await request.get(second.baseURL + '/notes');
  expect(notesResp.status()).toBe(200);
  const notes = await notesResp.json();
  expect(Array.isArray(notes)).toBe(true);
  const found = notes.find(n => n.id === note.id);
  expect(found).toBeDefined();
  expect(found.title).toBe('Persist Test');
  expect(found.body).toBe('Body for persist');

  await second.stop();
});

// ── AC-13 [AC-18] ───────────────────────────────────────────────────────────
// A title that is missing, empty, or whitespace-only is refused with 400 and
// {"error": "Title is required"}, and nothing is stored.
test('[AC-13][AC-18] missing or empty title is refused and nothing is stored', async ({ request }) => {
  // Missing title (title key absent).
  const r1 = await request.post('/notes', {
    data: { body: 'No title' }
  });
  expect(r1.status()).toBe(400);
  const b1 = await r1.json();
  expect(b1).toEqual({ error: 'Title is required' });

  // Empty title string.
  const r2 = await request.post('/notes', {
    data: { title: '', body: 'Empty title' }
  });
  expect(r2.status()).toBe(400);
  const b2 = await r2.json();
  expect(b2).toEqual({ error: 'Title is required' });

  // Whitespace-only title.
  const r3 = await request.post('/notes', {
    data: { title: '   ', body: 'Whitespace title' }
  });
  expect(r3.status()).toBe(400);
  const b3 = await r3.json();
  expect(b3).toEqual({ error: 'Title is required' });

  // Verify neither bad request stored anything.
  const notesResp = await request.get('/notes');
  expect(notesResp.status()).toBe(200);
  const notes = await notesResp.json();
  const hasBadNote = notes.some(
    n => n.body === 'No title' || n.body === 'Empty title' || n.body === 'Whitespace title'
  );
  expect(hasBadNote).toBe(false);
});

// ── AC-7 ────────────────────────────────────────────────────────────────────
// JSON over HTTP: a note is exactly {"id": <integer>, "title": <string>,
// "body": <string>} — three keys, correct types, no extras.
test('[AC-7] note has correct JSON shape with exactly three keys', async ({ request }) => {
  const response = await request.post('/notes', {
    data: { title: 'Shape Test', body: 'Body for shape' }
  });
  expect(response.status()).toBe(201);
  const note = await response.json();

  // Verify exact shape: exactly 3 keys, no extras, correct types.
  expect(note).toEqual({ id: expect.any(Number), title: 'Shape Test', body: 'Body for shape' });
  expect(Number.isInteger(note.id)).toBe(true);
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');
});

// ── AC-18 ───────────────────────────────────────────────────────────────────
// Invalid input (invalid JSON, non-integer ID) is refused without storing anything.
test('[AC-18] invalid input is refused without storing anything', async ({ request }) => {
  // Invalid JSON on POST /notes.
      const r1 = await request.post('/notes', {
          data: 'not valid json'
        });
    expect(r1.status()).toBe(400);
    const b1 = await r1.json();
    expect(b1).toEqual({ error: 'Invalid JSON' });

    // Non-integer ID on GET /notes/{id}.
  const r2 = await request.get('/notes/abc');
  expect(r2.status()).toBe(400);
  const b2 = await r2.json();
  expect(b2).toEqual({ error: 'Invalid note id' });

  // Invalid JSON on PUT /notes/{id}.
  const createResp = await request.post('/notes', {
    data: { title: 'AC18 Test', body: 'Body for AC18' }
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();

          const r3 = await request.put(`/notes/${created.id}`, {
            data: 'not valid json'
          });
    expect(r3.status()).toBe(400);
    const b3 = await r3.json();
    expect(b3).toEqual({ error: 'Invalid JSON' });

  // Verify the note was not corrupted by invalid requests.
  const r4 = await request.get(`/notes/${created.id}`);
  expect(r4.status()).toBe(200);
  const note = await r4.json();
  expect(note).toEqual({ id: created.id, title: 'AC18 Test', body: 'Body for AC18' });

  // Non-integer ID on DELETE /notes/{id}.
  const r5 = await request.delete('/notes/abc');
  expect(r5.status()).toBe(400);
  const b5 = await r5.json();
  expect(b5).toEqual({ error: 'Invalid note id' });
});
test('[AC-16] every operation works as the interface says', async ({ request }) => {
  // 1. Create a note via POST /notes → 201
  const createResp = await request.post('/notes', {
    data: { title: 'AC16 Note', body: 'Full lifecycle test' }
  });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();
  expect(created).toEqual({
    id: expect.any(Number),
    title: 'AC16 Note',
    body: 'Full lifecycle test'
  });
  expect(Number.isInteger(created.id)).toBe(true);
  const noteId = created.id;

  // 2. List all notes via GET /notes → 200, find our note
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  expect(Array.isArray(notes)).toBe(true);
  const found = notes.find(n => n.id === noteId);
  expect(found).toBeDefined();
  expect(found.title).toBe('AC16 Note');
  expect(found.body).toBe('Full lifecycle test');

  // 3. Fetch by id via GET /notes/{id} → 200
  const fetchResp = await request.get(`/notes/${noteId}`);
  expect(fetchResp.status()).toBe(200);
  const fetched = await fetchResp.json();
  expect(fetched.id).toBe(noteId);
  expect(fetched.title).toBe('AC16 Note');
  expect(fetched.body).toBe('Full lifecycle test');

  // 4. Update via PUT /notes/{id} → 200
  const updateResp = await request.put(`/notes/${noteId}`, {
    data: { title: 'AC16 Updated', body: 'Updated body' }
  });
  expect(updateResp.status()).toBe(200);
  const updated = await updateResp.json();
  expect(updated.id).toBe(noteId);
  expect(updated.title).toBe('AC16 Updated');
  expect(updated.body).toBe('Updated body');

  // 5. List again — verify the updated note is there
  const listAfterUpdate = await request.get('/notes');
  expect(listAfterUpdate.status()).toBe(200);
  const notesAfterUpdate = await listAfterUpdate.json();
  const updatedFound = notesAfterUpdate.find(n => n.id === noteId);
  expect(updatedFound).toBeDefined();
  expect(updatedFound.title).toBe('AC16 Updated');
  expect(updatedFound.body).toBe('Updated body');

  // 6. Fetch again — verify the update persisted
  const fetchAfterUpdate = await request.get(`/notes/${noteId}`);
  expect(fetchAfterUpdate.status()).toBe(200);
  const fetchedAfterUpdate = await fetchAfterUpdate.json();
  expect(fetchedAfterUpdate.title).toBe('AC16 Updated');
  expect(fetchedAfterUpdate.body).toBe('Updated body');

  // 7. Delete via DELETE /notes/{id} → 204
  const deleteResp = await request.delete(`/notes/${noteId}`);
  expect(deleteResp.status()).toBe(204);

  // 8. List again — verify the note is gone
  const listAfterDelete = await request.get('/notes');
  expect(listAfterDelete.status()).toBe(200);
  const notesAfterDelete = await listAfterDelete.json();
  const stillThere = notesAfterDelete.find(n => n.id === noteId);
  expect(stillThere).toBeUndefined();

  // 9. Fetch the deleted note — verify 404
  const fetchAfterDelete = await request.get(`/notes/${noteId}`);
  expect(fetchAfterDelete.status()).toBe(404);
  const deleteBody = await fetchAfterDelete.json();
  expect(deleteBody).toEqual({ error: 'Note not found' });
});
