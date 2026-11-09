import { test, expect } from '@playwright/test';

// Helper to clear all notes before a test runs.
async function clearAll(request) {
  const res = await request.get('/notes');
  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// Test AC-1: Create a note with title and body.
test('[AC-1][AC-2] POST /notes creates a note', async ({ request }) => {
  await clearAll(request);
  const body = { title: 'Test Note', body: 'Sample' };
  const res = await request.post('/notes', { data: body });
  expect(res.status()).toBe(201);
  const note = await res.json();
  expect(note).toHaveProperty('id');
  expect(note.title).toBe(body.title);
  expect(note.body).toBe(body.body);
  // Location header
  const location = res.headers()['location'];
  expect(location).toBe(`/notes/${note.id}`);
});

// Test AC-2: List all notes.
test('[AC-2] GET /notes returns all notes', async ({ request }) => {
  await clearAll(request);
  const notesToCreate = [
    { title: 'One', body: 'A' },
    { title: 'Two', body: 'B' }
  ];
  for (const n of notesToCreate) {
    await request.post('/notes', { data: n });
  }
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await res.json();
  expect(notes).toHaveLength(2);
  // Order by creation
  expect(notes[0].title).toBe('One');
  expect(notes[1].title).toBe('Two');
});

// Test AC-3: Get a single note and 404 after deletion.
test('[AC-3] GET /notes/:id returns note or 404', async ({ request }) => {
  await clearAll(request);
  const createRes = await request.post('/notes', { data: { title: 'Solo', body: 'Only' } });
  const created = await createRes.json();
  const resGet = await request.get(`/notes/${created.id}`);
  expect(resGet.status()).toBe(200);
  const fetched = await resGet.json();
  expect(fetched).toEqual(created);

  // Delete and check 404
  await request.delete(`/notes/${created.id}`);
  const resNotFound = await request.get(`/notes/${created.id}`);
  expect(resNotFound.status()).toBe(404);
  const err = await resNotFound.json();
  expect(err).toEqual({ error: 'Not found' });
});

// Test AC-4: Update a note.
test('[AC-4] PUT /notes/:id updates title and body', async ({ request }) => {
  await clearAll(request);
  const createRes = await request.post('/notes', { data: { title: 'Old', body: 'Data' } });
  const created = await createRes.json();
  const updateBody = { title: 'New', body: 'Info' };
  const resUpdate = await request.put(`/notes/${created.id}`, { data: updateBody });
  expect(resUpdate.status()).toBe(200);
  const updated = await resUpdate.json();
  expect(updated.title).toBe(updateBody.title);
  expect(updated.body).toBe(updateBody.body);

  // Verify persistence via GET
  const resGet = await request.get(`/notes/${created.id}`);
  const fetched = await resGet.json();
  expect(fetched).toEqual(updated);
});

// Test AC-5: Delete a note.
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  await clearAll(request);
  const createRes = await request.post('/notes', { data: { title: 'Del', body: 'Bye' } });
  const created = await createRes.json();
  const resDelete = await request.delete(`/notes/${created.id}`);
  expect(resDelete.status()).toBe(204);

  // Subsequent GET should be 404
  const resGet = await request.get(`/notes/${created.id}`);
  expect(resGet.status()).toBe(404);
  const err = await resGet.json();
  expect(err).toEqual({ error: 'Not found' });

  // List should be empty
  const resList = await request.get('/notes');
  const list = await resList.json();
  expect(list).toHaveLength(0);
});

// Test AC-6 & AC-17: Persistence across restarts.
test('[AC-6][AC-17] Notes survive a restart of the service', async ({ request }) => {
  // Use helper to start and stop service with same dataDir
  const { startService } = await import('./service.cjs');
  const first = await startService();
  try {
    // Create note using raw fetch against first.baseURL
    const createRes = await fetch(first.baseURL + '/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Persist', body: 'Data' })
    });
    expect(createRes.status).toBe(201);
    const created = await createRes.json();

    // Stop service
    await first.stop();

    // Restart with same dataDir
    const second = await startService({ dataDir: first.dataDir });
    try {
      const listRes = await fetch(second.baseURL + '/notes');
      expect(listRes.status).toBe(200);
      const notes = await listRes.json();
      expect(notes).toHaveLength(1);
      expect(notes[0]).toEqual(created);
    } finally {
      await second.stop();
    }
  } catch (e) {
    // ensure stop in case of error
    await first.stop();
    throw e;
  }
});

// Test AC-7: JSON schema for note.
test('[AC-7] Note has id, title, body fields', async ({ request }) => {
  await clearAll(request);
  const res = await request.post('/notes', { data: { title: 'Schema', body: 'Check' } });
  const note = await res.json();
  expect(note).toHaveProperty('id');
  expect(typeof note.id).toBe('number');
  expect(note).toHaveProperty('title', 'Schema');
  expect(note).toHaveProperty('body', 'Check');
});

// Test AC-8: POST returns 201 and Location header.
test('[AC-8] POST /notes includes Location header', async ({ request }) => {
  await clearAll(request);
  const res = await request.post('/notes', { data: { title: 'Loc', body: 'Here' } });
  expect(res.status()).toBe(201);
  const location = res.headers()['location'];
  const note = await res.json();
  expect(location).toBe(`/notes/${note.id}`);
});

// Test AC-9: Notes returned in insertion order.
test('[AC-9] GET /notes returns notes in creation order', async ({ request }) => {
  await clearAll(request);
  const titles = ['First', 'Second', 'Third'];
  for (const t of titles) {
    await request.post('/notes', { data: { title: t, body: 'B' } });
  }
  const res = await request.get('/notes');
  const notes = await res.json();
  expect(notes.map(n => n.title)).toEqual(titles);
});

// Test AC-10: GET non-existent id returns 404.
test('[AC-10] GET /notes/:id with unknown id returns 404', async ({ request }) => {
  await clearAll(request);
  const res = await request.get('/notes/9999');
  expect(res.status()).toBe(404);
  const err = await res.json();
  expect(err).toEqual({ error: 'Not found' });
});

// Test AC-13 & AC-18: Invalid input rejected.
test('[AC-13][AC-18] POST /notes without title returns 400', async ({ request }) => {
  await clearAll(request);
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title required' });
  // Ensure no note added
  const listRes = await request.get('/notes');
  const notes = await listRes.json();
  expect(notes).toHaveLength(0);
});

// Test AC-14: Health endpoint.
test('[AC-14] GET /health returns status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toEqual({ status: 'ok' });
});
