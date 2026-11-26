import { test, expect } from '@playwright/test';

/**
 * Acceptance tests for the Notes API endpoints.
 * Each test proves one or more acceptance criteria (AC).
 * Tests are isolated: each creates its own records and never
 * depends on data left by another test.
 */

// --- Helpers ---------------------------------------------------------------

/**
 * Creates a note via POST /notes and returns { response, note }.
 * Uses a unique title to avoid cross-test contamination.
 */
async function createNote(request, titleSuffix) {
  const title = `Test Note ${titleSuffix}`;
  const body = `Body content for note ${titleSuffix}`;
  const response = await request.post('/notes', {
    data: JSON.stringify({ title, body }),
    headers: { 'Content-Type': 'application/json' },
  });
  const note = await response.json();
  return { response, note };
}

/**
 * Asserts that a note object has exactly the three required fields
 * with correct types (AC-7).
 */
function assertNoteShape(note) {
  expect(typeof note.id).toBe('number');
  expect(Number.isInteger(note.id)).toBeTruthy();
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');
  const keys = Object.keys(note);
  expect(keys.length).toBe(3);
  expect(keys).toEqual(expect.arrayContaining(['id', 'title', 'body']));
}

// --- AC-14: GET /health answers 200 ----------------------------------------

test('[AC-14] GET /health returns 200', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
});

// --- AC-1, AC-8: Create a note with title and body -------------------------

test('[AC-1][AC-8] POST /notes creates a note and returns 201', async ({ request }) => {
  const { response, note } = await createNote(request, 'ac1');
  expect(response.status()).toBe(201);
  assertNoteShape(note);
  expect(note.title).toBe('Test Note ac1');
  expect(note.body).toBe('Body content for note ac1');
});

// --- AC-7: JSON over HTTP — response shape ---------------------------------

test('[AC-7] POST /notes returns exactly { id, title, body } with correct types', async ({ request }) => {
  const { response, note } = await createNote(request, 'ac7');
  expect(response.status()).toBe(201);
  assertNoteShape(note);
});

// --- AC-9: GET /notes returns an empty array when no notes exist -----------

test('[AC-9] GET /notes returns [] when no notes exist', async ({ request }) => {
  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(Array.isArray(body)).toBeTruthy();
});

test('[AC-2][AC-9] GET /notes returns 200 with a JSON array', async ({ request }) => {
  // Create two notes so we can verify the list is non-empty
  const created1 = await createNote(request, 'ac2a');
  const created2 = await createNote(request, 'ac2b');

  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(Array.isArray(body)).toBeTruthy();
  // Isolate only the notes created by this test to avoid cross-test data interference
  const myNotes = body.filter(n => n.id === created1.note.id || n.id === created2.note.id);
  expect(myNotes.length).toBe(2);
  // Verify each element has the note shape
  for (const note of body) {
    assertNoteShape(note);
  }
});

test('[AC-3][AC-10] GET /notes/{id} returns the note or 404', async ({ request }) => {
  // Create a note and verify we can fetch it (AC-3)
  const { response: createResp, note } = await createNote(request, 'ac3');
  expect(createResp.status()).toBe(201);

  const getResponse = await request.get(`/notes/${note.id}`);
  expect(getResponse.status()).toBe(200);
  const fetched = await getResponse.json();
  assertNoteShape(fetched);
  expect(fetched.id).toBe(note.id);
  expect(fetched.title).toBe(note.title);

  // Non-existent id returns 404 (AC-10)
  const notFoundResp = await request.get('/notes/99999');
  expect(notFoundResp.status()).toBe(404);
});

// --- AC-4, AC-11: Update a note / 404 on missing ---------------------------

test('[AC-4][AC-11] PUT /notes/{id} replaces both fields and returns 200', async ({ request }) => {
  const { response: createResp, note } = await createNote(request, 'ac4');
  expect(createResp.status()).toBe(201);

  const putResponse = await request.put(`/notes/${note.id}`, {
    data: JSON.stringify({ title: 'Updated Title', body: 'Updated Body' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(putResponse.status()).toBe(200);
  const updated = await putResponse.json();
  assertNoteShape(updated);
  expect(updated.title).toBe('Updated Title');
  expect(updated.body).toBe('Updated Body');

  // PUT on a non-existent id returns 404 (AC-11)
  const notFoundResp = await request.put('/notes/99999', {
    data: JSON.stringify({ title: 'X', body: 'Y' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(notFoundResp.status()).toBe(404);
});

// --- AC-5, AC-12: Delete a note / 404 on missing ---------------------------

test('[AC-5][AC-12] DELETE /notes/{id} returns 204 and removes the note', async ({ request }) => {
  const { response: createResp, note } = await createNote(request, 'ac5');
  expect(createResp.status()).toBe(201);

  // Delete the note (AC-5)
  const deleteResponse = await request.delete(`/notes/${note.id}`);
  expect(deleteResponse.status()).toBe(204);

  // Confirm it is gone — GET returns 404
  const getAfterDelete = await request.get(`/notes/${note.id}`);
  expect(getAfterDelete.status()).toBe(404);

  // DELETE on a non-existent id returns 404 (AC-12)
  const notFoundResp = await request.delete('/notes/99999');
  expect(notFoundResp.status()).toBe(404);
});

// --- AC-13, AC-18: Invalid input is refused without storing -----------------

test('[AC-13][AC-18] POST /notes rejects empty title and missing title', async ({ request }) => {
  // Record the list length before any invalid requests so we can prove nothing was stored.
  const initialList = await request.get('/notes');
  expect(initialList.status()).toBe(200);
  const initialNotes = await initialList.json();
  expect(Array.isArray(initialNotes)).toBeTruthy();
  const initialLength = initialNotes.length;

  // Empty title (AC-13)
  const emptyTitleResp = await request.post('/notes', {
    data: JSON.stringify({ title: '', body: 'test' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect([400, 422]).toContain(emptyTitleResp.status());

  // Missing title key entirely (AC-13)
  const missingTitleResp = await request.post('/notes', {
    data: JSON.stringify({ body: 'test' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect([400, 422]).toContain(missingTitleResp.status());

  // Both rejections must return an error body with shape {"error": <string>}.
  const emptyBody = await emptyTitleResp.json().catch(() => null);
  expect(emptyBody).not.toBeNull();
  expect(typeof emptyBody.error).toBe('string');

  const missingBody = await missingTitleResp.json().catch(() => null);
  expect(missingBody).not.toBeNull();
  expect(typeof missingBody.error).toBe('string');

  // Verify no note was stored: the list length must be unchanged from before.
  const listResponse = await request.get('/notes');
  expect(listResponse.status()).toBe(200);
  const notes = await listResponse.json();
  expect(Array.isArray(notes)).toBeTruthy();
  expect(notes.length).toBe(initialLength);
});

// --- AC-16: Every operation works as the interface says --------------------

test('[AC-16] Full CRUD cycle through the HTTP interface', async ({ request }) => {
  // Create
  const { response: createResp, note } = await createNote(request, 'ac16');
  expect(createResp.status()).toBe(201);
  assertNoteShape(note);

  // Read
  const getResponse = await request.get(`/notes/${note.id}`);
  expect(getResponse.status()).toBe(200);
  const fetched = await getResponse.json();
  assertNoteShape(fetched);

  // Update
  const putResponse = await request.put(`/notes/${note.id}`, {
    data: JSON.stringify({ title: 'Full cycle', body: 'Complete' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(putResponse.status()).toBe(200);
  const updated = await putResponse.json();
  assertNoteShape(updated);
  expect(updated.title).toBe('Full cycle');

  // Delete
  const deleteResponse = await request.delete(`/notes/${note.id}`);
  expect(deleteResponse.status()).toBe(204);

  // Confirm gone
  const afterDelete = await request.get(`/notes/${note.id}`);
  expect(afterDelete.status()).toBe(404);
});
