import { test, expect } from '@playwright/test';

// Helper to find a note in an array by title
const findByTitle = (arr, title) => arr.find(n => n.title === title);

test('[AC-14][AC-16] GET /health answers 200', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: 'ok' });
});

let createdNoteId;
const noteTitle = 'Test Note';
const noteBody = 'This is a test body.';

test('[AC-1][AC-8] POST /notes creates a note and returns 201', async ({ request }) => {
  const response = await request.post('/notes', { data: { title: noteTitle, body: noteBody } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(noteTitle);
  expect(json.body).toBe(noteBody);
  createdNoteId = json.id;
});

test('[AC-2][AC-9] GET /notes includes the created note', async ({ request }) => {
  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const notes = await response.json();
  expect(Array.isArray(notes)).toBeTruthy();
  const found = findByTitle(notes, noteTitle);
  expect(found).toBeDefined();
  expect(found.id).toBe(createdNoteId);
});

test('[AC-3][AC-10] GET /notes/:id returns the note and 404 for missing', async ({ request }) => {
  const resp = await request.get(`/notes/${createdNoteId}`);
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json.id).toBe(createdNoteId);
  expect(json.title).toBe(noteTitle);

  const missing = await request.get('/notes/9999');
  expect(missing.status()).toBe(404);
  const err = await missing.json();
  expect(err).toEqual({ error: 'Note not found' });
});

test('[AC-4][AC-11] PUT /notes/:id updates the note', async ({ request }) => {
  const newTitle = 'Updated Note';
  const newBody = 'Updated body content.';
  const resp = await request.put(`/notes/${createdNoteId}`, { data: { title: newTitle, body: newBody } });
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json.id).toBe(createdNoteId);
  expect(json.title).toBe(newTitle);
  expect(json.body).toBe(newBody);

  const getResp = await request.get(`/notes/${createdNoteId}`);
  const getJson = await getResp.json();
  expect(getJson.title).toBe(newTitle);
});

test('[AC-5][AC-12] DELETE /notes/:id removes the note', async ({ request }) => {
  const resp = await request.delete(`/notes/${createdNoteId}`);
  expect(resp.status()).toBe(204);

  const getResp = await request.get(`/notes/${createdNoteId}`);
  expect(getResp.status()).toBe(404);
});

test('[AC-13][AC-18] POST /notes with missing or empty title returns 400', async ({ request }) => {
  // Missing title
  const resp1 = await request.post('/notes', { data: { body: 'no title' } });
  expect(resp1.status()).toBe(400);
  const err1 = await resp1.json();
  expect(err1).toEqual({ error: 'Title is required' });

  // Empty title
  const resp2 = await request.post('/notes', { data: { title: '', body: 'empty title' } });
  expect(resp2.status()).toBe(400);
  const err2 = await resp2.json();
  expect(err2).toEqual({ error: 'Title is required' });
});

test('[AC-6][AC-17] Notes persist across restarts', async () => {
  const { startService } = await import('./service.cjs');
  // Start first instance and create a note
  const first = await startService();
  const title = 'Persisted Note';
  const body = 'Should survive restart';
  let resp = await fetch(`${first.baseURL}/notes`, {
      method: 'POST',
      data: { title, body }
  });
  expect(resp.status).toBe(201);
  const json = await resp.json();
  const noteId = json.id;
  await first.stop();

  // Restart service with same data dir
  const second = await startService({ dataDir: first.dataDir });
  resp = await fetch(`${second.baseURL}/notes/${noteId}`, { method: 'GET' });
  expect(resp.status).toBe(200);
  const persisted = await resp.json();
  expect(persisted.title).toBe(title);
  expect(persisted.body).toBe(body);

  await second.stop();});
