import { test, expect } from '@playwright/test';

const randomTitle = () => `test-${Math.random().toString(36).slice(2)}`;

// Helper to create a note via POST and return the parsed JSON
async function createNote(request, title, body) {
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  return resp.json();
}

// Health endpoint
test('[AC-14] GET /health answers 200', async ({ request }) => {
  const resp = await request.get('/health');
  expect(resp.status()).toBe(200);
  expect(await resp.json()).toEqual({ status: 'ok' });
});

// Create note and retrieve it
test('[AC-1][AC-7][AC-8] POST /notes creates a note', async ({ request }) => {
  const title = randomTitle();
  const body = 'Body';
  const created = await createNote(request, title, body);
  expect(typeof created.id).toBe('number');
  expect(created.title).toBe(title);
  expect(created.body).toBe(body);

  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  expect(await getResp.json()).toEqual(created);
});

// List notes after creating two
test('[AC-2][AC-9] GET /notes lists all notes', async ({ request }) => {
  const titles = [randomTitle(), randomTitle()];
  const ids = [];
  for (const t of titles) {
    const r = await createNote(request, t, 'Body');
    const json = await r;
    ids.push(json.id);
  }

  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const notes = await resp.json();
  const foundIds = notes.map((n) => n.id);
  for (const id of ids) {
    expect(foundIds).toContain(id);
  }
});

// Get existing and non-existent note
test('[AC-3] GET /notes/:id returns 200 or 404', async ({ request }) => {
  const title = randomTitle();
  const created = await createNote(request, title, 'Body');

  const existingResp = await request.get(`/notes/${created.id}`);
  expect(existingResp.status()).toBe(200);
  expect(await existingResp.json()).toEqual(created);

  const missingResp = await request.get('/notes/9999');
  expect(missingResp.status()).toBe(404);
  expect(await missingResp.json()).toEqual({ error: 'Not found' });
});

// Update note and check 404 for unknown id
test('[AC-4][AC-11] PUT /notes/:id updates a note', async ({ request }) => {
  const title = randomTitle();
  const created = await createNote(request, title, 'Body');

  const updatedResp = await request.put(`/notes/${created.id}`, { data: { title: 'Updated', body: 'New body' } });
  expect(updatedResp.status()).toBe(200);
  const updated = await updatedResp.json();
  expect(updated.title).toBe('Updated');
  expect(updated.body).toBe('New body');

  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  expect(await getResp.json()).toEqual(updated);

  // Unknown id
  const missingPut = await request.put('/notes/9999', { data: { title: 'X', body: 'Y' } });
  expect(missingPut.status()).toBe(404);
  expect(await missingPut.json()).toEqual({ error: 'Not found' });
});

// Delete note and check 404 for unknown id
test('[AC-5][AC-12] DELETE /notes/:id removes a note', async ({ request }) => {
  const title = randomTitle();
  const created = await createNote(request, title, 'Body');

  const delResp = await request.delete(`/notes/${created.id}`);
  expect(delResp.status()).toBe(204);

  const getAfterDel = await request.get(`/notes/${created.id}`);
  expect(getAfterDel.status()).toBe(404);
  expect(await getAfterDel.json()).toEqual({ error: 'Not found' });

  // Unknown id
  const missingDel = await request.delete('/notes/9999');
  expect(missingDel.status()).toBe(404);
  expect(await missingDel.json()).toEqual({ error: 'Not found' });
});

// Persistence across restarts (AC-6 & AC-17)
test('[AC-16][AC-6][AC-17] Notes survive a restart of the service', async ({ request }) => {
  const { startService } = await import('./service.cjs');
  const first = await startService();

  const res1 = await request.post(first.baseURL + '/notes', { data: { title: 'Persist', body: 'Data' } });
  expect(res1.status()).toBe(201);
  const note = await res1.json();

  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const res2 = await fetch(`${second.baseURL}/notes/${note.id}`);
  expect(res2.status).toBe(200);
  const fetched = await res2.json();
  expect(fetched).toEqual(note);

  await second.stop();
});

// Missing or empty title rejected (AC-13)
test('[AC-13] POST /notes with missing or empty title returns error', async ({ request }) => {
  let r = await request.post('/notes', { data: { body: 'Body' } });
  expect(r.status()).toBe(422);
  expect((await r.json()).error).toMatch(/title/i);

  r = await request.post('/notes', { data: { title: '', body: 'Body' } });
  expect(r.status()).toBe(422);
});

// Invalid input does not store a note (AC-18)
test('[AC-18] Invalid input is refused without storing anything', async ({ request }) => {
  const before = await request.get('/notes');
  const notesBefore = await before.json();
  const lenBefore = Array.isArray(notesBefore) ? notesBefore.length : 0;

  const r = await request.post('/notes', { data: { body: 'Missing title' } });
  expect(r.status()).toBe(422);

  const after = await request.get('/notes');
  const notesAfter = await after.json();
  expect(Array.isArray(notesAfter)).toBeTruthy();
  expect(notesAfter.length).toBe(lenBefore);
});
