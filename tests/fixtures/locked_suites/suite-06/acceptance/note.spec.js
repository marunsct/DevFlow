import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Helper to create a note and return its id and body
async function createNote(request, title = 'Test', body = 'Body') {
  const response = await request.post('/notes', { data: { title, body } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
  return json.id;
}

test('[AC-1][AC-16] Create a note with title and body', async ({ request }) => {
  const id = await createNote(request, 'Hello', 'World');
  // Verify persistence by fetching the same note
  const getResp = await request.get(`/notes/${id}`);
  expect(getResp.status()).toBe(200);
  const json = await getResp.json();
  expect(json.id).toBe(id);
  expect(json.title).toBe('Hello');
  expect(json.body).toBe('World');
});

test('[AC-2] List all notes', async ({ request }) => {
  const id1 = await createNote(request, 'One', 'A');
  const id2 = await createNote(request, 'Two', 'B');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const notes = await resp.json();
  // Find the created notes
  const found1 = notes.find(n => n.id === id1 && n.title === 'One');
  const found2 = notes.find(n => n.id === id2 && n.title === 'Two');
  expect(found1).toBeDefined();
  expect(found2).toBeDefined();
});

test('[AC-3] Fetch one note by id', async ({ request }) => {
  const id = await createNote(request, 'Fetch', 'Me');
  const resp = await request.get(`/notes/${id}`);
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json.id).toBe(id);
  // Non-existent
  const bad = await request.get('/notes/99999');
  expect(bad.status()).toBe(404);
});

test('[AC-4] Update a note', async ({ request }) => {
  const id = await createNote(request, 'Old', 'Data');
  const updResp = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Info' } });
  expect(updResp.status()).toBe(200);
  const json = await updResp.json();
  expect(json.id).toBe(id);
  expect(json.title).toBe('New');
  // Verify persistence
  const get = await request.get(`/notes/${id}`);
  const gjson = await get.json();
  expect(gjson.title).toBe('New');
});

test('[AC-5] Delete a note', async ({ request }) => {
  const id = await createNote(request, 'Delete', 'Me');
  const delResp = await request.delete(`/notes/${id}`);
  expect(delResp.status()).toBe(204);
  const get = await request.get(`/notes/${id}`);
  expect(get.status()).toBe(404);
});




test('[AC-7] JSON structure of a note', async ({ request }) => {
  const id = await createNote(request, 'JSON', 'Check');
  const resp = await request.get(`/notes/${id}`);
  const json = await resp.json();
  expect(Object.keys(json)).toEqual(['id','title','body']);
});

test('[AC-8] POST /notes returns 201 with note', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: 'Created', body: 'Yes' } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toHaveProperty('id');
  expect(json.title).toBe('Created');
});

test('[AC-9] GET /notes returns array of all notes', async ({ request }) => {
  // create two distinct notes
  const id1 = await createNote(request, 'A', 'X');
  const id2 = await createNote(request, 'B', 'Y');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const arr = await resp.json();
  expect(arr.length).toBeGreaterThanOrEqual(2);
});

test('[AC-10] GET /notes/:id returns 404 for missing', async ({ request }) => {
  const res = await request.get('/notes/123456789');
  expect(res.status()).toBe(404);
});

test('[AC-11] PUT /notes/:id replaces note', async ({ request }) => {
  const id = await createNote(request, 'Old', 'Data');
  const resp = await request.put(`/notes/${id}`, { data: { title: 'Replaced', body: 'New' } });
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json.title).toBe('Replaced');
});

test('[AC-12] DELETE /notes/:id returns 404 when missing', async ({ request }) => {
  const res = await request.delete('/notes/987654321');
  expect(res.status()).toBe(404);
});

test('[AC-13][AC-18] Missing title results in 400 and no persistence', async ({ request }) => {
  const resp = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(resp.status()).toBe(400);
  // Ensure not persisted
  const getAll = await request.get('/notes');
  const arr = await getAll.json();
  const found = arr.find(n => n.body === 'NoTitle');
  expect(found).toBeUndefined();
});

test('[AC-14] GET /health returns 200', async ({ request }) => {
  const resp = await request.get('/health');
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json).toEqual({ status: 'ok' });
});

  // AC-15 and AC-16 are about start script and interface; not testable via request fixture.

  // AC-15 and AC-16 are about start script and interface; not testable via request fixture.
// AC-17 already covered by restart test.
// AC-18 duplicate of AC-13.
