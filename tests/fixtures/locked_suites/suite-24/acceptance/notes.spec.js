import { test, expect } from '@playwright/test';

// Helper to start a fresh service for the restart test (AC-6).
import { startService } from './service.cjs';

/**
 * Create a note via POST /notes and return its id.
 */
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  return json.id;
}

/**
 * Delete a note by id.
 */
async function deleteNote(request, id) {
  const res = await request.delete(`/notes/${id}`);
  expect(res.status()).toBe(204);
}

// AC-14: Health endpoint.
test('[AC-14] GET /health returns status 200 and ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.ok()).toBeTruthy();
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});

// AC-1: Create a note and delete it.
test('[AC-1] POST /notes creates a note and DELETE removes it', async ({ request }) => {
  const id = await createNote(request, 'Test Note', 'Body');
  // Verify returned content shape.
  const resGet = await request.get(`/notes/${id}`);
  expect(resGet.status()).toBe(200);
  const note = await resGet.json();
  expect(note).toEqual({ id, title: 'Test Note', body: 'Body' });
  // Clean up
  await deleteNote(request, id);
});

// AC-2: List all notes.
test('[AC-2] GET /notes returns list of created notes', async ({ request }) => {
  const id1 = await createNote(request, 'First', 'A');
  const id2 = await createNote(request, 'Second', 'B');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBeTruthy();
  // Find the two notes by id
  const note1 = list.find((n) => n.id === id1);
  const note2 = list.find((n) => n.id === id2);
  expect(note1).toEqual({ id: id1, title: 'First', body: 'A' });
  expect(note2).toEqual({ id: id2, title: 'Second', body: 'B' });
  // Clean up
  await deleteNote(request, id1);
  await deleteNote(request, id2);
});

// AC-3: Fetch one note by its id.
test('[AC-3] GET /notes/:id returns the correct note', async ({ request }) => {
  const id = await createNote(request, 'Unique', 'Content');
  const res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  const note = await res.json();
  expect(note).toEqual({ id, title: 'Unique', body: 'Content' });
  await deleteNote(request, id);
});

// AC-4: Update a note.
test('[AC-4] PUT /notes/:id updates the note', async ({ request }) => {
  const id = await createNote(request, 'Old', 'OldBody');
  const resPut = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'NewBody' } });
  expect(resPut.status()).toBe(200);
  const updated = await resPut.json();
  expect(updated).toEqual({ id, title: 'New', body: 'NewBody' });
  // Verify GET reflects update
  const resGet = await request.get(`/notes/${id}`);
  const got = await resGet.json();
  expect(got).toEqual(updated);
  await deleteNote(request, id);
});

// AC-5: Delete a note.
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const id = await createNote(request, 'ToDelete', 'Bye');
  const resDel = await request.delete(`/notes/${id}`);
  expect(resDel.status()).toBe(204);
  const resGet = await request.get(`/notes/${id}`);
  expect(resGet.status()).toBe(404);
});

// AC-6: Notes survive a restart.
test('[AC-6] Notes persist after service restart', async ({}) => {
  // Start first instance
  const first = await startService();
  // Use its request via playwright's global fixture? We'll use node fetch directly
  
  // Create note using first.baseURL
  let res = await fetch(`${first.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' }),
  });
  expect(res.status).toBe(201);
  const json = await res.json();
  const id = json.id;
  // Stop first
  await first.stop();
  // Start second with same dataDir
  const second = await startService({ dataDir: first.dataDir });
  // Get note via second.baseURL
  res = await fetch(`${second.baseURL}/notes/${id}`);
  expect(res.status).toBe(200);
  const got = await res.json();
  expect(got).toEqual({ id, title: 'Persist', body: 'Data' });
  // Clean up
  await fetch(`${second.baseURL}/notes/${id}`, { method: 'DELETE' });
  await second.stop();
});

// AC-7: JSON shape for note endpoints.
test('[AC-7] Note responses match expected schema', async ({ request }) => {
  const id = await createNote(request, 'Schema', 'Check');
  const resGet = await request.get(`/notes/${id}`);
  expect(resGet.status()).toBe(200);
  const note = await resGet.json();
  expect(note).toHaveProperty('id');
  expect(typeof note.id).toBe('number');
  expect(note).toHaveProperty('title', 'Schema');
  expect(note).toHaveProperty('body', 'Check');
  await deleteNote(request, id);
});

// AC-8: Missing title error.
test('[AC-13][AC-8] POST /notes without title returns error', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toHaveProperty('error');
  // Ensure no new note created
  const listRes = await request.get('/notes');
  const list = await listRes.json();
  const titles = list.map((n) => n.title);
  expect(titles).not.toContain('NoTitle');
});

// AC-10: GET non-existent id returns 404.
test('[AC-10] GET /notes/:id for missing note returns 404', async ({ request }) => {
  const res = await request.get('/notes/99999999');
  expect(res.status()).toBe(404);
});
