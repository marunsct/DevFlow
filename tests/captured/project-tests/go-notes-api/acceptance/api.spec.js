// Acceptance tests for the Notes API HTTP endpoints.
// Each test is named with the acceptance-criterion id(s) it proves,
// e.g. [AC-1][AC-2] …  so the harness can track coverage.
//
// Tests use Playwright's `request` fixture which sends real HTTP calls
// to the service started by playwright.config.js' webServer block.

import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// AC-14: GET /health answers 200 with Content-Type: application/json
// AC-15: start.sh starts the service on 127.0.0.1 at PORT, data under DATA_DIR
// Proven by the running product — the webServer block uses start.sh and we
// verify the service actually responds on the configured port with JSON.
// ---------------------------------------------------------------------------
test('[AC-14][AC-15] GET /health returns 200 with JSON content type', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/json');
  const body = await response.json();
  expect(body).toHaveProperty('status');
});

// ---------------------------------------------------------------------------
// AC-1: Create a note with a title and a body
// AC-8: POST /notes -> 201 with the created note
// AC-7: Note shape validation (exactly three fields)
// ---------------------------------------------------------------------------
test('[AC-1][AC-7][AC-8] POST /notes creates a note and returns 201', async ({ request }) => {
  const title = 'Acceptance Test Note';
  const body = 'This is the body text for acceptance testing';

  const response = await request.post('/notes', {
    data: JSON.stringify({ title, body }),
    headers: { 'Content-Type': 'application/json' },
  });

  expect(response.status()).toBe(201);
  expect(response.headers()['content-type']).toContain('application/json');

  const note = await response.json();
  // AC-7: exactly three fields, id is integer
  expect(Object.keys(note).sort()).toEqual(['body', 'id', 'title']);
  expect(typeof note.id).toBe('number');
  expect(Number.isInteger(note.id)).toBeTruthy();
  expect(note.title).toBe(title);
  expect(note.body).toBe(body);
});

// ---------------------------------------------------------------------------
// AC-2: List all notes
// AC-9: GET /notes -> 200 with a JSON array of every note
// ---------------------------------------------------------------------------
test('[AC-2][AC-9] GET /notes lists all notes', async ({ request }) => {
  // Create two notes to verify the list endpoint
  const noteA = await request.post('/notes', {
    data: JSON.stringify({ title: 'List Test A', body: 'Body A' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(noteA.status()).toBe(201);
  const noteAJson = await noteA.json();

  const noteB = await request.post('/notes', {
    data: JSON.stringify({ title: 'List Test B', body: 'Body B' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(noteB.status()).toBe(201);
  const noteBJson = await noteB.json();

  // GET /notes
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  expect(listResp.headers()['content-type']).toContain('application/json');

  const notes = await listResp.json();
  expect(Array.isArray(notes)).toBeTruthy();

  // Find our notes (there may be others from previous tests)
  const foundA = notes.find((n) => n.id === noteAJson.id);
  const foundB = notes.find((n) => n.id === noteBJson.id);
  expect(foundA).toBeDefined();
  expect(foundB).toBeDefined();

  // AC-7: shape check on each returned note
  for (const n of notes) {
    expect(Object.keys(n).sort()).toEqual(['body', 'id', 'title']);
    expect(typeof n.id).toBe('number');
    expect(Number.isInteger(n.id)).toBeTruthy();
    expect(typeof n.title).toBe('string');
    expect(typeof n.body).toBe('string');
  }

  // Insertion order — noteA appeared first in the array
  const idxA = notes.findIndex((n) => n.id === noteAJson.id);
  const idxB = notes.findIndex((n) => n.id === noteBJson.id);
  expect(idxA).toBeLessThan(idxB);
});

// ---------------------------------------------------------------------------
// AC-3: Fetch one note by its id
// AC-5: GET /notes/{id} -> 200 with the note
// ---------------------------------------------------------------------------
test('[AC-3] GET /notes/{id} fetches one note by id', async ({ request }) => {
  const created = await request.post('/notes', {
    data: JSON.stringify({ title: 'Fetch By Id Note', body: 'Body for fetch' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(created.status()).toBe(201);
  const createdJson = await created.json();

  // GET the note back by id
  const getResp = await request.get(`/notes/${createdJson.id}`);
  expect(getResp.status()).toBe(200);
  expect(getResp.headers()['content-type']).toContain('application/json');

  const fetched = await getResp.json();
  expect(fetched.id).toBe(createdJson.id);
  expect(fetched.title).toBe('Fetch By Id Note');
  expect(fetched.body).toBe('Body for fetch');
});

// ---------------------------------------------------------------------------
// AC-10 (404 case): GET /notes/{id} -> 404 when note does not exist
// Also checks Content-Type so the test fails until the product returns
// application/json on error responses (not Go's default text/plain).
// ---------------------------------------------------------------------------
test('[AC-10] GET /notes/{id} returns 404 for missing note', async ({ request }) => {
  const resp = await request.get('/notes/99999');
  expect(resp.status()).toBe(404);
  expect(resp.headers()['content-type']).toContain('application/json');
});

// ---------------------------------------------------------------------------
// AC-10 (non-integer case): GET /notes/{id} where id is not a valid integer
// -> 404. Also checks Content-Type for the same reason as above.
// ---------------------------------------------------------------------------
test('[AC-10] GET /notes/{id} with non-integer id returns 404', async ({ request }) => {
  const resp = await request.get('/notes/abc');
  expect(resp.status()).toBe(404);
  expect(resp.headers()['content-type']).toContain('application/json');
});

// ---------------------------------------------------------------------------
// AC-4: Update a note's title and body
// AC-7: Note shape after update
// ---------------------------------------------------------------------------
test('[AC-4] PUT /notes/{id} updates a note', async ({ request }) => {
  const created = await request.post('/notes', {
    data: JSON.stringify({ title: 'Original Title', body: 'Original Body' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(created.status()).toBe(201);
  const createdJson = await created.json();
  const noteId = createdJson.id;

  const putResp = await request.put(`/notes/${noteId}`, {
    data: JSON.stringify({ title: 'Updated Title', body: 'Updated Body' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(putResp.status()).toBe(200);
  expect(putResp.headers()['content-type']).toContain('application/json');

  const updated = await putResp.json();
  expect(updated.id).toBe(noteId); // id unchanged
  expect(updated.title).toBe('Updated Title');
  expect(updated.body).toBe('Updated Body');
});

// ---------------------------------------------------------------------------
// AC-11 (404 case): PUT /notes/{id} -> 404 when note does not exist
// Verifies no new note was created by the failed PUT.
// ---------------------------------------------------------------------------
test('[AC-11] PUT /notes/{id} returns 404 for missing note', async ({ request }) => {
  // Capture the list of notes before the PUT attempt.
  const beforeCount = await request.get('/notes');
  expect(beforeCount.status()).toBe(200);
  const beforeNotes = await beforeCount.json();

  const resp = await request.put('/notes/99999', {
    data: JSON.stringify({ title: 'No One Here', body: 'x' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(404);

  // Verify no new note was created
  const afterCount = await request.get('/notes');
  expect(afterCount.status()).toBe(200);
  const afterNotes = await afterCount.json();
  expect(afterNotes.length).toBe(beforeNotes.length);
});

// ---------------------------------------------------------------------------
// AC-5: Delete a note
// AC-10 (404 case): subsequent GET returns 404
// ---------------------------------------------------------------------------
test('[AC-5] DELETE /notes/{id} deletes a note', async ({ request }) => {
  const created = await request.post('/notes', {
    data: JSON.stringify({ title: 'Delete Me', body: 'Will be deleted' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(created.status()).toBe(201);
  const createdJson = await created.json();
  const noteId = createdJson.id;

  const delResp = await request.delete(`/notes/${noteId}`);
  expect(delResp.status()).toBe(204);

  // Subsequent GET should return 404
  const getResp = await request.get(`/notes/${noteId}`);
  expect(getResp.status()).toBe(404);
});

// ---------------------------------------------------------------------------
// AC-12 (404 case): DELETE /notes/{id} -> 404 when note does not exist
// Also checks Content-Type so the test fails until the product returns
// application/json on error responses.
// ---------------------------------------------------------------------------
test('[AC-12] DELETE /notes/{id} returns 404 for missing note', async ({ request }) => {
  const resp = await request.delete('/notes/99999');
  expect(resp.status()).toBe(404);
  expect(resp.headers()['content-type']).toContain('application/json');
});

// ---------------------------------------------------------------------------
// AC-13: Title missing or empty is refused with 422, nothing stored
// ---------------------------------------------------------------------------
test('[AC-13] POST /notes rejects empty title', async ({ request }) => {
  const resp = await request.post('/notes', {
    data: JSON.stringify({ title: '', body: 'x' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);

  // Verify no note was stored — check GET /notes does not include a note with empty title
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  for (const n of notes) {
    expect(n.title.trim()).not.toBe('');
  }
});

// ---------------------------------------------------------------------------
// AC-13: Missing title field (not just empty string) is also refused
// ---------------------------------------------------------------------------
test('[AC-13] POST /notes rejects missing title field', async ({ request }) => {
  const resp = await request.post('/notes', {
    data: JSON.stringify({ body: 'x' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);

  // Verify nothing stored
  const listResp = await request.get('/notes');
  const notes = await listResp.json();
  for (const n of notes) {
    expect(n.title.trim()).not.toBe('');
  }
});

// ---------------------------------------------------------------------------
// AC-13: Whitespace-only title is refused
// ---------------------------------------------------------------------------
test('[AC-13] POST /notes rejects whitespace-only title', async ({ request }) => {
  const resp = await request.post('/notes', {
    data: JSON.stringify({ title: '   \t\n  ', body: 'x' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);
});

// ---------------------------------------------------------------------------
// AC-7: Body field may be omitted or empty; stored as empty string
// ---------------------------------------------------------------------------
test('[AC-7] POST /notes accepts missing body field', async ({ request }) => {
  const resp = await request.post('/notes', {
    data: JSON.stringify({ title: 'No Body Note' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(201);
  const note = await resp.json();
  expect(note.title).toBe('No Body Note');
  expect(note.body).toBe('');
});

// ---------------------------------------------------------------------------
// AC-7: Every note object has exactly three fields: id, title, body
// Verified on every endpoint that returns a note.
// ---------------------------------------------------------------------------
test('[AC-7] All returned notes have exactly three fields', async ({ request }) => {
  // Create
  const createResp = await request.post('/notes', {
    data: JSON.stringify({ title: 'Shape Check', body: 'Verify shape' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(createResp.status()).toBe(201);
  const createdJson = await createResp.json();
  expect(Object.keys(createdJson).sort()).toEqual(['body', 'id', 'title']);

  // GET by id
  const getResp = await request.get(`/notes/${createdJson.id}`);
  expect(getResp.status()).toBe(200);
  const fetched = await getResp.json();
  expect(Object.keys(fetched).sort()).toEqual(['body', 'id', 'title']);

  // PUT
  const putResp = await request.put(`/notes/${createdJson.id}`, {
    data: JSON.stringify({ title: 'Shape Check Updated', body: 'Still exactly three' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(putResp.status()).toBe(200);
  const updated = await putResp.json();
  expect(Object.keys(updated).sort()).toEqual(['body', 'id', 'title']);

  // GET /notes (list)
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  for (const n of notes) {
    expect(Object.keys(n).sort()).toEqual(['body', 'id', 'title']);
  }
});

// ---------------------------------------------------------------------------
// AC-6 / AC-17: Notes survive a restart of the service.
// Uses the harness helper `startService` to manage restarts with the same
// DATA_DIR, exercising the full persistence contract end-to-end.
// ---------------------------------------------------------------------------
test('[AC-6][AC-17] Notes persist across service restarts', async ({ request }) => {
  // Import the restart helper at runtime so the test can start/stop the
  // service independently of the webServer that playwright.config.js starts.
  const { startService } = await import('./service.cjs');

  // Start a fresh service for this test (independent of webServer).
  const first = await startService({ timeoutMs: 30000 });

  // Create a note on the first instance.
  const created = await request.post(first.baseURL + '/notes', {
    data: JSON.stringify({ title: 'Persistence Test', body: 'Must survive restart' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(created.status()).toBe(201);
  const createdJson = await created.json();

  // Stop the first service — data should be flushed to disk.
  await first.stop();

  // Start a new service with the same DATA_DIR.
  const second = await startService({ dataDir: first.dataDir, timeoutMs: 30000 });

  // Verify both notes exist after restart.
  const listResp = await request.get(second.baseURL + '/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  expect(Array.isArray(notes)).toBeTruthy();

  const found1 = notes.find((n) => n.id === createdJson.id);
  expect(found1).toBeDefined();
  expect(found1.title).toBe('Persistence Test');
  expect(found1.body).toBe('Must survive restart');

  // Create another note on the restarted service — id should be monotonically increasing.
  const created2 = await request.post(second.baseURL + '/notes', {
    data: JSON.stringify({ title: 'Second After Restart', body: 'Also survives' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(created2.status()).toBe(201);
  const created2Json = await created2.json();

  // AC-12: IDs are monotonically increasing across restarts.
  expect(created2Json.id).toBeGreaterThan(createdJson.id);

  await second.stop();
});

// ---------------------------------------------------------------------------
// AC-13 / AC-18: Invalid input is refused without storing anything.
// Tests several invalid inputs in sequence and verifies the list is unchanged.
// ---------------------------------------------------------------------------
test('[AC-13][AC-18] Invalid input is refused without storing anything', async ({ request }) => {
  const beforeList = await request.get('/notes');
  expect(beforeList.status()).toBe(200);
  const beforeNotes = await beforeList.json();

  // Empty title
  let resp = await request.post('/notes', {
    data: JSON.stringify({ title: '', body: 'x' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);

  // Missing title field
  resp = await request.post('/notes', {
    data: JSON.stringify({ body: 'y' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);

  // Whitespace-only title
  resp = await request.post('/notes', {
    data: JSON.stringify({ title: '   ', body: 'z' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.status()).toBe(422);

  // After all invalid inputs, the list should be unchanged.
  const afterList = await request.get('/notes');
  expect(afterList.status()).toBe(200);
  const afterNotes = await afterList.json();
  expect(afterNotes.length).toBe(beforeNotes.length);
});

// ---------------------------------------------------------------------------
// AC-16: Every operation works as the interface says.
// End-to-end CRUD lifecycle test that chains create → read (list) → read
// (single) → update → delete → verify deletion, exercising the full
// HTTP interface contract in a single test.
// ---------------------------------------------------------------------------
test('[AC-16] Full CRUD lifecycle works as the interface says', async ({ request }) => {
  // Create — POST /notes -> 201 with note shape.
  const createResp = await request.post('/notes', {
    data: JSON.stringify({ title: 'CRUD Test Note', body: 'End-to-end test' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(createResp.status()).toBe(201);
  const note = await createResp.json();
  expect(note.title).toBe('CRUD Test Note');
  expect(note.body).toBe('End-to-end test');
  const noteId = note.id;
  expect(typeof noteId).toBe('number');
  expect(Number.isInteger(noteId)).toBeTruthy();

  // Read (list) — GET /notes -> 200 with array containing our note.
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notes = await listResp.json();
  expect(Array.isArray(notes)).toBeTruthy();
  const foundInList = notes.find((n) => n.id === noteId);
  expect(foundInList).toBeDefined();
  expect(foundInList.title).toBe('CRUD Test Note');

  // Read (single) — GET /notes/{id} -> 200 with the note.
  const getResp = await request.get(`/notes/${noteId}`);
  expect(getResp.status()).toBe(200);
  const fetched = await getResp.json();
  expect(fetched.id).toBe(noteId);
  expect(fetched.title).toBe('CRUD Test Note');
  expect(fetched.body).toBe('End-to-end test');

  // Update — PUT /notes/{id} -> 200 with updated note, id unchanged.
  const putResp = await request.put(`/notes/${noteId}`, {
    data: JSON.stringify({ title: 'Updated CRUD Note', body: 'Modified' }),
    headers: { 'Content-Type': 'application/json' },
  });
  expect(putResp.status()).toBe(200);
  const updated = await putResp.json();
  expect(updated.id).toBe(noteId);
  expect(updated.title).toBe('Updated CRUD Note');
  expect(updated.body).toBe('Modified');

  // Verify update reflected in list.
  const listAfterUpdate = await request.get('/notes');
  expect(listAfterUpdate.status()).toBe(200);
  const notesAfterUpdate = await listAfterUpdate.json();
  const foundUpdated = notesAfterUpdate.find((n) => n.id === noteId);
  expect(foundUpdated.title).toBe('Updated CRUD Note');

  // Delete — DELETE /notes/{id} -> 204.
  const delResp = await request.delete(`/notes/${noteId}`);
  expect(delResp.status()).toBe(204);

  // Verify deleted — GET /notes/{id} -> 404.
  const getAfterDelete = await request.get(`/notes/${noteId}`);
  expect(getAfterDelete.status()).toBe(404);
});
