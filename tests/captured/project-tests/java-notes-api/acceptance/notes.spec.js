import { test, expect } from '@playwright/test';

// Acceptance tests for CRUD operations, validation, and JSON structure.
// Each test creates its own data so it does not depend on other tests' state.

// AC-1: Create a note with a title and a body
// AC-8: POST /notes creates a note and answers 201 with the note
// AC-7: JSON over HTTP – a note is {"id": <int>, "title": <string>, "body": <string>}
test('[AC-1][AC-7][AC-8] create a note via POST /notes', async ({ request }) => {
  const response = await request.post('/notes', {
    data: { title: 'Test note', body: 'Hello world' },
  });
  expect(response.status()).toBe(201);
  const body = await response.json();
  // AC-7: response is a JSON object with exactly id, title, body
  expect(Object.keys(body).sort()).toEqual(['body', 'id', 'title']);
  // id is a non-negative integer
  expect(Number.isInteger(body.id)).toBeTruthy();
  expect(body.id).toBeGreaterThanOrEqual(0);
  expect(body.title).toBe('Test note');
  expect(body.body).toBe('Hello world');
  return body.id;
});

// AC-2: List all notes
// AC-9: GET /notes answers 200 with a JSON array of every note
test('[AC-2][AC-9] list all notes via GET /notes', async ({ request }) => {
  const created = await request.post('/notes', {
    data: { title: 'List item', body: 'For listing' },
  });
  expect(created.status()).toBe(201);
  const createdBody = await created.json();

  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const notes = await response.json();
  expect(Array.isArray(notes)).toBeTruthy();
  // The array must contain the note we just created
  const found = notes.filter((n) => n.id === createdBody.id);
  expect(found.length).toBe(1);
  expect(found[0].title).toBe('List item');
  expect(found[0].body).toBe('For listing');
});

// AC-3: Fetch one note by its id
// AC-10: GET /notes/{id} answers 200 with the note, or 404 when there is none
test('[AC-3][AC-10] fetch a note by id and 404 for missing id', async ({ request }) => {
  const created = await request.post('/notes', {
    data: { title: 'Fetch test', body: 'Find me' },
  });
  expect(created.status()).toBe(201);
  const createdBody = await created.json();

  const response = await request.get(`/notes/${createdBody.id}`);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.id).toBe(createdBody.id);
  expect(body.title).toBe('Fetch test');
  expect(body.body).toBe('Find me');

  // AC-10: non-existent id returns 404
  const missing = await request.get('/notes/99999');
  expect(missing.status()).toBe(404);
  const missingBody = await missing.json();
  expect(missingBody).toEqual({ error: 'Note not found' });
});

// AC-4: Update a note's title and body
// AC-11: PUT /notes/{id} with {"title": ..., "body": ...} replaces both and answers 200, or 404
test('[AC-4][AC-11] update a note via PUT /notes/{id}', async ({ request }) => {
  const created = await request.post('/notes', {
    data: { title: 'Old title', body: 'Old body' },
  });
  expect(created.status()).toBe(201);
  const createdBody = await created.json();

  const response = await request.put(`/notes/${createdBody.id}`, {
    data: { title: 'New title', body: 'New body' },
  });
  expect(response.status()).toBe(200);
  const updated = await response.json();
  expect(updated.title).toBe('New title');
  expect(updated.body).toBe('New body');

  // AC-11: PUT on non-existent id returns 404
  const missing = await request.put('/notes/99999', {
    data: { title: 'Nope', body: 'Nope' },
  });
  expect(missing.status()).toBe(404);
  expect(await missing.json()).toEqual({ error: 'Note not found' });
});

// AC-5: Delete a note
// AC-12: DELETE /notes/{id} answers 204, or 404
test('[AC-5][AC-12] delete a note via DELETE /notes/{id}', async ({ request }) => {
  const created = await request.post('/notes', {
    data: { title: 'To delete', body: 'Gone' },
  });
  expect(created.status()).toBe(201);
  const createdBody = await created.json();

  const response = await request.delete(`/notes/${createdBody.id}`);
  expect(response.status()).toBe(204);

  // Verify the note is gone by checking remaining state
  const getResponse = await request.get(`/notes/${createdBody.id}`);
  expect(getResponse.status()).toBe(404);

  // AC-12: DELETE on non-existent id returns 404
  const missing = await request.delete('/notes/99999');
  expect(missing.status()).toBe(404);
  expect(await missing.json()).toEqual({ error: 'Note not found' });
});

// AC-7: JSON over HTTP – validate response shape strictly
test('[AC-7] JSON shape of a note response', async ({ request }) => {
  const created = await request.post('/notes', {
    data: { title: 'Shape check', body: 'Fields only' },
  });
  expect(created.status()).toBe(201);
  const body = await created.json();

  // Exactly three keys: id, title, body
  expect(Object.keys(body).length).toBe(3);
  expect(Object.keys(body).sort()).toEqual(['body', 'id', 'title']);

  // id is a non-negative integer
  expect(Number.isInteger(body.id)).toBeTruthy();
  expect(body.id).toBeGreaterThanOrEqual(0);

  // title and body are strings
  expect(typeof body.title).toBe('string');
  expect(typeof body.body).toBe('string');
});

  // AC-13: A title that is missing or empty is refused with 400 or 422
  // AC-18: Invalid input is refused without storing anything
  test('[AC-13][AC-18] empty title is refused and nothing stored', async ({ request }) => {
    const before = await request.get('/notes');
    expect(before.status()).toBe(200);
    const beforeBody = await before.json();
    expect(Array.isArray(beforeBody)).toBeTruthy();
    const beforeCount = beforeBody.length;
  
    const response = await request.post('/notes', {
      data: { title: '', body: 'Body' },
    });
    expect([400, 422]).toContain(response.status());
  
    // Nothing stored
    const notes = await request.get('/notes');
    expect(notes.status()).toBe(200);
    const body = await notes.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBe(beforeCount);
  });

// AC-13: Blank (whitespace-only) title is also refused
test('[AC-13][AC-18] whitespace-only title is refused and nothing stored', async ({ request }) => {
    const before = await request.get('/notes');
    expect(before.status()).toBe(200);
    const beforeBody = await before.json();
    expect(Array.isArray(beforeBody)).toBeTruthy();
    const beforeCount = beforeBody.length;
  
    const response = await request.post('/notes', {
      data: { title: '   ', body: 'Body' },
    });
    expect([400, 422]).toContain(response.status());
  
    const notes = await request.get('/notes');
    expect(notes.status()).toBe(200);
    const body = await notes.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBe(beforeCount);
  });

// AC-13: Missing title is refused
test('[AC-13][AC-18] missing title is refused and nothing stored', async ({ request }) => {
    const before = await request.get('/notes');
    expect(before.status()).toBe(200);
    const beforeBody = await before.json();
    expect(Array.isArray(beforeBody)).toBeTruthy();
    const beforeCount = beforeBody.length;
  
    const response = await request.post('/notes', {
      data: JSON.stringify({ body: 'Body' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect([400, 422]).toContain(response.status());
  
    const notes = await request.get('/notes');
    expect(notes.status()).toBe(200);
    const body = await notes.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBe(beforeCount);
  });

// AC-13: PUT with empty title is refused and nothing stored
test('[AC-13][AC-18] PUT with empty title is refused and nothing stored', async ({ request }) => {
    // Create a note to update
    const created = await request.post('/notes', {
      data: { title: 'Before update', body: 'Original' },
    });
    expect(created.status()).toBe(201);
    const createdBody = await created.json();

    // Record the note's original state
    const getBefore = await request.get(`/notes/${createdBody.id}`);
    expect(getBefore.status()).toBe(200);
    const noteBefore = await getBefore.json();
    expect(noteBefore.title).toBe('Before update');

    // Try to PUT with empty title
    const response = await request.put(`/notes/${createdBody.id}`, {
      data: { title: '', body: 'New body' },
    });
    expect([400, 422]).toContain(response.status());

    // Verify the note is unchanged
    const getAfter = await request.get(`/notes/${createdBody.id}`);
    expect(getAfter.status()).toBe(200);
    const noteAfter = await getAfter.json();
    expect(noteAfter.title).toBe('Before update');
    expect(noteAfter.body).toBe('Original');
  });

// AC-13: PUT with blank (whitespace-only) title is refused and nothing stored
test('[AC-13][AC-18] PUT with blank title is refused and nothing stored', async ({ request }) => {
    // Create a note to update
    const created = await request.post('/notes', {
      data: { title: 'Before update', body: 'Original' },
    });
    expect(created.status()).toBe(201);
    const createdBody = await created.json();

    // Record the note's original state
    const getBefore = await request.get(`/notes/${createdBody.id}`);
    expect(getBefore.status()).toBe(200);
    const noteBefore = await getBefore.json();
    expect(noteBefore.title).toBe('Before update');

    // Try to PUT with whitespace-only title
    const response = await request.put(`/notes/${createdBody.id}`, {
      data: { title: '   ', body: 'New body' },
    });
    expect([400, 422]).toContain(response.status());

    // Verify the note is unchanged
    const getAfter = await request.get(`/notes/${createdBody.id}`);
    expect(getAfter.status()).toBe(200);
    const noteAfter = await getAfter.json();
    expect(noteAfter.title).toBe('Before update');
    expect(noteAfter.body).toBe('Original');
  });

// AC-13: PUT with missing title is refused and nothing stored
test('[AC-13][AC-18] PUT with missing title is refused and nothing stored', async ({ request }) => {
    // Create a note to update
    const created = await request.post('/notes', {
      data: { title: 'Before update', body: 'Original' },
    });
    expect(created.status()).toBe(201);
    const createdBody = await created.json();

    // Record the note's original state
    const getBefore = await request.get(`/notes/${createdBody.id}`);
    expect(getBefore.status()).toBe(200);
    const noteBefore = await getBefore.json();
    expect(noteBefore.title).toBe('Before update');

    // Try to PUT with missing title field
    const response = await request.put(`/notes/${createdBody.id}`, {
      data: JSON.stringify({ body: 'New body' }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect([400, 422]).toContain(response.status());

    // Verify the note is unchanged
    const getAfter = await request.get(`/notes/${createdBody.id}`);
    expect(getAfter.status()).toBe(200);
    const noteAfter = await getAfter.json();
    expect(noteAfter.title).toBe('Before update');
    expect(noteAfter.body).toBe('Original');
  });

// AC-16: Full CRUD lifecycle with invalid input
test('[AC-16] full CRUD lifecycle', async ({ request }) => {
    // Record what exists before we act
    const listBefore = await request.get('/notes');
    expect(listBefore.status()).toBe(200);
    const beforeNotes = await listBefore.json();
    expect(Array.isArray(beforeNotes)).toBeTruthy();
    const beforeCount = beforeNotes.length;
  
    // Create
    const create = await request.post('/notes', {
      data: { title: 'Lifecycle', body: 'Full test' },
    });
    expect(create.status()).toBe(201);
    const note = await create.json();
    expect(note.title).toBe('Lifecycle');
  
    // Read
    const get = await request.get(`/notes/${note.id}`);
    expect(get.status()).toBe(200);
    expect(await get.json()).toMatchObject({ id: note.id, title: 'Lifecycle' });
  
      // Update
      const update = await request.put(`/notes/${note.id}`, {
        data: { title: 'Updated', body: 'Changed' },
      });
      expect(update.status()).toBe(200);
      expect(await update.json()).toMatchObject({ title: 'Updated' });

      // Update with invalid title is refused
      const updateBad = await request.put(`/notes/${note.id}`, {
        data: { title: '', body: 'Nope' },
      });
      expect([400, 422]).toContain(updateBad.status());
      // Verify note is still updated (not reverted)
      const getAfterUpdate = await request.get(`/notes/${note.id}`);
      expect(getAfterUpdate.status()).toBe(200);
      expect((await getAfterUpdate.json()).title).toBe('Updated');
  
    // Delete
    const del = await request.delete(`/notes/${note.id}`);
    expect(del.status()).toBe(204);
  
    // Verify gone
    const getAfter = await request.get(`/notes/${note.id}`);
    expect(getAfter.status()).toBe(404);
    expect(getAfter.headers()['content-type']).toBe('application/json');
  
    // Invalid input does not store
    const bad = await request.post('/notes', {
      data: { title: '', body: 'Nope' },
    });
    expect([400, 422]).toContain(bad.status());
  
    // Verify no new notes were added
    const listAfter = await request.get('/notes');
    expect(listAfter.status()).toBe(200);
    const listBody = await listAfter.json();
    expect(Array.isArray(listBody)).toBeTruthy();
    expect(listBody.length).toBe(beforeCount);
  });

// AC-7: Verify Content-Type header is application/json
test('[AC-7] response Content-Type is application/json', async ({ request }) => {
  const create = await request.post('/notes', {
    data: { title: 'CT check', body: 'Header check' },
  });
  expect(create.headers()['content-type']).toContain('application/json');

  const get = await request.get('/notes');
  expect(get.headers()['content-type']).toContain('application/json');

  const getOne = await request.get(`/notes/${(await create.json()).id}`);
  expect(getOne.headers()['content-type']).toContain('application/json');
});
