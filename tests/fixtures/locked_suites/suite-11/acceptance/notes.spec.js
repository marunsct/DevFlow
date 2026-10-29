import { test, expect } from '@playwright/test';

const jsonBody = (body) => ({ data: body });

/**
 * AC-1: Create a note with a title and a body.
 */
test('[AC-1] POST /notes creates a note', async ({ request }) => {
  const res = await request.post('/notes', jsonBody({ title: 'Test', body: 'Body' }));
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test');
  expect(json.body).toBe('Body');
});

/**
 * AC-2: List all notes.
 */
test('[AC-2] GET /notes lists created notes', async ({ request }) => {
  await request.post('/notes', jsonBody({ title: 'One', body: '' }));
  await request.post('/notes', jsonBody({ title: 'Two', body: 'Second' }));
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBeTruthy();
  expect(list.length).toBeGreaterThanOrEqual(2);
  const titles = list.map((n) => n.title);
  expect(titles).toContain('One');
  expect(titles).toContain('Two');
});

/**
 * AC-3: Fetch one note by its id.
 */
test('[AC-3] GET /notes/:id returns the created note', async ({ request }) => {
  const createRes = await request.post('/notes', jsonBody({ title: 'Single', body: 'Only' }));
  const created = await createRes.json();
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const fetched = await res.json();
  expect(fetched).toEqual(created);
});

/**
 * AC-4: Update a note's title and body.
 */
test('[AC-4][AC-11] PUT /notes/:id updates the note', async ({ request }) => {
  const createRes = await request.post('/notes', jsonBody({ title: 'Old', body: 'Old body' }));
  const created = await createRes.json();
  const updateRes = await request.put(`/notes/${created.id}`, jsonBody({ title: 'New', body: 'New body' }));
  expect(updateRes.status()).toBe(200);
  const updated = await updateRes.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('New body');

  // Verify persistence
  const getRes = await request.get(`/notes/${created.id}`);
  const got = await getRes.json();
  expect(got).toEqual(updated);
});

/**
 * AC-5: Delete a note.
 */
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const createRes = await request.post('/notes', jsonBody({ title: 'ToDelete', body: '' }));
  const created = await createRes.json();
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(404);
});

/**
 * AC-6: Notes survive a restart of the service.
 */
test('[AC-6][AC-17] notes persist after restarting the service', async ({ request }) => {
  const { startService } = await import('./service.cjs');
  // Start first instance, create note
  const svc1 = await startService();
  const res1 = await request.post('/notes', jsonBody({ title: 'Persist', body: 'Data' }));
  expect(res1.status()).toBe(201);
  const note = await res1.json();
  await svc1.stop();

  // Restart with same data dir
  const svc2 = await startService({ dataDir: svc1.dataDir });
  const res2 = await request.get(`/notes/${note.id}`);
  expect(res2.status()).toBe(200);
  const persisted = await res2.json();
  expect(persisted).toEqual(note);
  await svc2.stop();
});

/**
 * AC-7: JSON over HTTP – note object structure.
 */
test('[AC-7] GET /notes returns notes with id, title, body', async ({ request }) => {
  const createRes = await request.post('/notes', jsonBody({ title: 'Schema', body: 'Check' }));
  const created = await createRes.json();
  const res = await request.get(`/notes/${created.id}`);
  const note = await res.json();
  expect(note).toHaveProperty('id');
  expect(typeof note.id).toBe('number');
  expect(note).toHaveProperty('title', 'Schema');
  expect(note).toHaveProperty('body', 'Check');
});

/**
 * AC-8: POST /notes with missing title returns 400.
 */
test('[AC-8] POST /notes without title fails', async ({ request }) => {
  const res = await request.post('/notes', jsonBody({ body: 'No title' }));
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toHaveProperty('message', 'Title is required');
});

/**
 * AC-9: GET /health returns status ok.
 */
test('[AC-9] GET /health returns 200 with status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});

/**
 * AC-10: DELETE non-existent id returns 404.
 */
test('[AC-10] DELETE /notes/:id for missing note returns 404', async ({ request }) => {
  const res = await request.delete('/notes/999999');
  expect(res.status()).toBe(404);
  const err = await res.json();
  expect(err).toHaveProperty('message', 'Note not found');
});
