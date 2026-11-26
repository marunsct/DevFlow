import { test, expect } from '@playwright/test';

// ──────────────────────────────────────────────────
// AC-1  Create a note with a title and a body
// AC-8  POST /notes -> 201 with the created note
// AC-7  JSON shape: exactly {id, title, body}
// ──────────────────────────────────────────────────

test('[AC-1][AC-7][AC-8] POST /notes creates a note and returns 201', async ({ request }) => {
  // Create a note via the product's API (user-facing path)
  const createRes = await request.post('/notes', {
    data: { title: 'First note', body: 'Hello world' },
  });

  // AC-8: status must be 201
  expect(createRes.status()).toBe(201);

  // Parse the response body as JSON
  const body = await createRes.json();

  // AC-7 / TS-9: response has exactly three fields with correct types
  const keys = Object.keys(body);
  expect(keys).toEqual(['id', 'title', 'body']);
  expect(typeof body.id).toBe('number');
  expect(typeof body.title).toBe('string');
  expect(typeof body.body).toBe('string');

  // AC-1: the returned values match what we sent
  expect(body.title).toBe('First note');
  expect(body.body).toBe('Hello world');

  // Store the id for downstream tests (AC-3, AC-10)
  globalThis._createdNoteId = body.id;
});

// ──────────────────────────────────────────────────
// AC-2  List all notes
// AC-9  GET /notes -> 200 with array ordered by id ASC
// ──────────────────────────────────────────────────

test('[AC-2][AC-9][AC-16] GET /notes lists notes in insertion order', async ({ request }) => {
  // Create a second note so we can verify ordering (oldest first)
  const createRes = await request.post('/notes', {
    data: { title: 'Second note', body: 'Second body' },
  });
  const secondId = (await createRes.json()).id;

  // Create a third note
  const createRes3 = await request.post('/notes', {
    data: { title: 'Third note', body: 'Third body' },
  });
  const thirdId = (await createRes3.json()).id;

  // Fetch all notes
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);

  const notes = await listRes.json();
  expect(Array.isArray(notes)).toBeTruthy();

  // AC-9: must be ordered by id ASC (insertion order)
  const ids = notes.map((n) => n.id);
  expect(ids).toEqual([
    globalThis._createdNoteId,
    secondId,
    thirdId,
  ]);

  // Each note has exactly three fields
  for (const note of notes) {
    expect(Object.keys(note)).toEqual(['id', 'title', 'body']);
  }
});

// ──────────────────────────────────────────────────
// AC-3  Fetch one note by its id
// AC-10 GET /notes/{id} -> 200 or 404
// ──────────────────────────────────────────────────

test('[AC-3][AC-10] GET /notes/{id} returns the note or 404', async ({ request }) => {
  // AC-3: fetch the note we created earlier — must exist
  const getRes = await request.get(`/notes/${globalThis._createdNoteId}`);
  expect(getRes.status()).toBe(200);

  const note = await getRes.json();
  expect(note.id).toBe(globalThis._createdNoteId);
  expect(note.title).toBe('First note');
  expect(note.body).toBe('Hello world');

  // AC-10: fetch a non-existent id — must return 404
  const notFoundRes = await request.get('/notes/999999');
  expect(notFoundRes.status()).toBe(404);

  const errBody = await notFoundRes.json();
  expect(errBody).toHaveProperty('error');
});

// ──────────────────────────────────────────────────
// AC-4  Update a note's title and body
// AC-11 PUT /notes/{id} -> 200 or 404
// ──────────────────────────────────────────────────

test('[AC-4][AC-11] PUT /notes/{id} updates the note or returns 404', async ({ request }) => {
  const id = globalThis._createdNoteId;

  // AC-4: update both title and body — must replace entirely
  const putRes = await request.put(`/notes/${id}`, {
    data: { title: 'Updated title', body: 'Updated body' },
  });
  expect(putRes.status()).toBe(200);

  const updated = await putRes.json();
  expect(updated.id).toBe(id);
  expect(updated.title).toBe('Updated title');
  expect(updated.body).toBe('Updated body');

  // AC-11: PUT on a non-existent id — must return 404
  const notFoundRes = await request.put('/notes/999999', {
    data: { title: 'Ghost', body: 'Nope' },
  });
  expect(notFoundRes.status()).toBe(404);

  const errBody = await notFoundRes.json();
  expect(errBody).toHaveProperty('error');
});

// ──────────────────────────────────────────────────
// AC-5  Delete a note
// AC-12 DELETE /notes/{id} -> 204 or 404
// ──────────────────────────────────────────────────

test('[AC-5][AC-12] DELETE /notes/{id} removes the note or returns 404', async ({ request }) => {
  const id = globalThis._createdNoteId;

  // AC-5: delete — must return 204 with no content body
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  // Verify the note is gone
  const getAfterDel = await request.get(`/notes/${id}`);
  expect(getAfterDel.status()).toBe(404);

  // AC-12: delete a non-existent id — must return 404
  const delNotFoundRes = await request.delete('/notes/999999');
  expect(delNotFoundRes.status()).toBe(404);

  const errBody = await delNotFoundRes.json();
  expect(errBody).toHaveProperty('error');
});
