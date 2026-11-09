import { test, expect } from '@playwright/test';

// Helper for persistence across restart using the harness's service starter.
const { startService } = await import('./service.cjs');

/**
 * Utility to create a note and return its id.
 */
async function createNote(request, title, body) {
  const response = await request.post('/notes', { data: { title, body } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  return json.id;
}

/**
 * Test AC-1: Create a note with a title and a body.
 */
test('[AC-1][AC-8][AC-16] create a note returns 201 and the note', async ({ request }) => {
  const response = await request.post('/notes', { data: { title: 'Test', body: 'Sample' } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test');
  expect(json.body).toBe('Sample');
});

/**
 * Test AC-2: List all notes.
 */
test('[AC-2] list notes returns an array of created notes', async ({ request }) => {
  const id1 = await createNote(request, 'A', 'One');
  const id2 = await createNote(request, 'B', 'Two');
  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  const notes = await response.json();
  expect(Array.isArray(notes)).toBe(true);
  const ids = notes.map(n => n.id);
  expect(ids).toContain(id1);
  expect(ids).toContain(id2);
});

/**
 * Test AC-3: Get a single note by id.
 */
test('[AC-3] get a specific note returns the correct data', async ({ request }) => {
  const id = await createNote(request, 'Solo', 'Only one');
  const response = await request.get(`/notes/${id}`);
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json.id).toBe(id);
  expect(json.title).toBe('Solo');
});

/**
 * Test AC-3: Get non‑existent note returns 404 with error.
 */
test('[AC-10] get a missing note returns 404 and error object', async ({ request }) => {
  const response = await request.get('/notes/99999');
  expect(response.status()).toBe(404);
  const json = await response.json();
  expect(json).toEqual({ error: 'Not found' });
});

/**
 * Test AC-4: Update a note.
 */
test('[AC-4] update a note replaces title and body', async ({ request }) => {
  const id = await createNote(request, 'Old', 'Body');
  const response = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Content' } });
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json.id).toBe(id);
  expect(json.title).toBe('New');
  expect(json.body).toBe('Content');
});

/**
 * Test AC-4: Update non‑existent note returns 404.
 */
test('[AC-11] update missing note returns 404', async ({ request }) => {
  const response = await request.put('/notes/99999', { data: { title: 'X', body: 'Y' } });
  expect(response.status()).toBe(404);
});

/**
 * Test AC-5: Delete a note.
 */
test('[AC-5] delete a note returns 204 and it is gone', async ({ request }) => {
  const id = await createNote(request, 'DeleteMe', 'Gone');
  const delResp = await request.delete(`/notes/${id}`);
  expect(delResp.status()).toBe(204);
  const getResp = await request.get(`/notes/${id}`);
  expect(getResp.status()).toBe(404);
});

/**
 * Test AC-5: Delete non‑existent note returns 404.
 */
test('[AC-12] delete missing note returns 404', async ({ request }) => {
  const response = await request.delete('/notes/99999');
  expect(response.status()).toBe(404);
});

/**
 * Test AC-6 & AC-17: Notes survive a restart of the service.
 */
test('[AC-6][AC-17] notes persist after restarting the server', async () => {
  const first = await startService();
  const createResp = await fetch(`${first.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' })
  });
  expect(createResp.status).toBe(201);
  const note = await createResp.json();
  const id = note.id;
  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const getResp = await fetch(`${second.baseURL}/notes/${id}`);
  expect(getResp.status).toBe(200);
  const fetched = await getResp.json();
  expect(fetched.id).toBe(id);
  expect(fetched.title).toBe('Persist');
  await second.stop();
});

/**
 * Test AC-7: JSON structure of a note.
 */
test('[AC-7] note JSON has id, title, body', async ({ request }) => {
  const id = await createNote(request, 'Schema', 'Check');
  const response = await request.get(`/notes/${id}`);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json).toHaveProperty('title');
  expect(typeof json.title).toBe('string');
  expect(json).toHaveProperty('body');
  expect(typeof json.body).toBe('string');
});

/**
 * Test AC-9: Content-Type for GET /notes.
 */
test('[AC-9] list notes content‑type is application/json', async ({ request }) => {
  await createNote(request, 'CT', 'Check');
  const response = await request.get('/notes');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/json');
});

/**
 * Test AC-10: Health endpoint.
 */
test('[AC-14] health returns OK text', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const text = await response.text();
  expect(text).toBe('OK');
  expect(response.headers()['content-type']).toContain('text/plain');
});

/**
 * Test AC-13: Missing title returns 400.
 */
test('[AC-13][AC-18] create without title returns 400', async ({ request }) => {
  const response = await request.post('/notes', { data: { body: 'No title' } });
  expect(response.status()).toBe(400);
  const json = await response.json();
  expect(json).toEqual({ error: 'Title is required' });
});

/**
 * Test AC-13: Body too long returns 422.
 */
test('[AC-13] create with body >10000 chars returns 422', async ({ request }) => {
  const longBody = 'a'.repeat(10001);
  const response = await request.post('/notes', { data: { title: 'Long', body: longBody } });
  expect(response.status()).toBe(422);
  const json = await response.json();
  expect(json).toEqual({ error: 'Body too long' });
});

/**
 * Test AC-15: start.sh exists.
 */
test('[AC-15] start.sh is present', async () => {
  const fs = await import('node:fs');
  expect(fs.existsSync('./start.sh')).toBe(true);
});
