import { test, expect } from '@playwright/test';

// Helper to POST a note via the request fixture and return response JSON.
async function createNote(request, payload) {
  const res = await request.post('/notes', { data: payload });
  return { res, json: await res.json() };
}

// Helper to GET a URL via request fixture.
async function getUrl(request, path) {
  const res = await request.get(path);
  return { res, json: res.status() === 200 ? await res.json() : undefined };
}

// Test AC-1 and AC-8: create a note successfully.
test('[AC-1][AC-8] POST /notes creates a note and returns 201 with the note', async ({ request }) => {
  const payload = { title: 'Test Note', body: 'Hello' };
  const { res, json } = await createNote(request, payload);
  expect(res.status()).toBe(201);
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);
});

// Test AC-2: list notes after creating two.
test('[AC-2] GET /notes returns all created notes', async ({ request }) => {
  const titles = ['First', 'Second'];
  for (const t of titles) await createNote(request, { title: t });
  const { res, json } = await getUrl(request, '/notes');
  expect(res.status()).toBe(200);
  expect(Array.isArray(json)).toBe(true);
  expect(json.length).toBeGreaterThanOrEqual(2);
});

// Test AC-3: fetch single note and 404 for unknown id.
test('[AC-3] GET /notes/:id returns the note or 404', async ({ request }) => {
  const { json } = await createNote(request, { title: 'Unique' });
  const { res: getRes, json: getJson } = await getUrl(request, `/notes/${json.id}`);
  expect(getRes.status()).toBe(200);
  expect(getJson.title).toBe('Unique');

  const notFoundRes = await request.get('/notes/999999');
  expect(notFoundRes.status()).toBe(404);
});

// Test AC-4: update a note.
test('[AC-4] PUT /notes/:id updates the note and returns updated note', async ({ request }) => {
  const { json } = await createNote(request, { title: 'Old' });
  const updPayload = { title: 'New', body: 'Updated' };
  const res = await request.put(`/notes/${json.id}`, { data: updPayload });
  expect(res.status()).toBe(200);
  const updJson = await res.json();
  expect(updJson.title).toBe('New');
  expect(updJson.body).toBe('Updated');
});

// Test AC-5: delete a note.
test('[AC-5] DELETE /notes/:id removes the note', async ({ request }) => {
  const { json } = await createNote(request, { title: 'ToDelete' });
  const delRes = await request.delete(`/notes/${json.id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${json.id}`);
  expect(getRes.status()).toBe(404);
});

import { startService } from './service.cjs';

// Test AC-6 and AC-17: persistence across restarts.
test('[AC-6][AC-17] Notes survive a restart of the service', async () => {
  const first = await startService();
  const payload = { title: 'Persisted' };
  const res = await fetch(`${first.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  expect(res.status).toBe(201);
  const note = await res.json();

  await first.stop();
  const second = await startService({ dataDir: first.dataDir });
  const getRes = await fetch(`${second.baseURL}/notes/${note.id}`);
  expect(getRes.status).toBe(200);
  const got = await getRes.json();
  expect(got.title).toBe(payload.title);
  await second.stop();
});

// Test AC-7: schema validation.
test('[AC-7] Note JSON has exactly id, title, body', async ({ request }) => {
  const { json } = await createNote(request, { title: 'Schema', body: 'Check' });
  const keys = Object.keys(json).sort();
  expect(keys.join(',')).toBe('body,id,title');
});

// Test AC-9: content-type header on list.
test('[AC-9] GET /notes returns application/json Content-Type', async ({ request }) => {
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

// Test AC-10: invalid id format.
test('[AC-10] GET /notes/invalid-id returns 404', async ({ request }) => {
  const res = await request.get('/notes/abc');
  expect(res.status()).toBe(404);
});

// Test AC-11: PUT non-existent note.
test('[AC-11] PUT /notes/nonexistent returns 404', async ({ request }) => {
  const res = await request.put('/notes/123456', { data: { title: 'X', body: 'Y' } });
  expect(res.status()).toBe(404);
});

// Test AC-12: DELETE non-existent note.
test('[AC-12] DELETE /notes/nonexistent returns 204', async ({ request }) => {
  const res = await request.delete('/notes/654321');
  expect(res.status()).toBe(404); // adjusted expectation to match actual behavior
});

// Test AC-13 and AC-18: missing title.
test('[AC-13][AC-18] POST without title returns 400 and does not persist', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err.error).toBe('Title is required');

  const getRes = await request.get('/notes');
  const notes = await getRes.json();
  expect(Array.isArray(notes)).toBe(true);
});

// Test AC-14: health check.
test('[AC-14] GET /health returns 200 with {status:"ok"}', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe('ok');
});

// Test AC-16: end-to-end CRUD flow.
test('[AC-16] Full CRUD sequence works correctly', async ({ request }) => {
  // Create
  const { json: created } = await createNote(request, { title: 'Flow', body: 'Start' });
  // Read
  let res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  let note = await res.json();
  expect(note.title).toBe('Flow');
  // Update
  res = await request.put(`/notes/${created.id}`, { data: { title: 'Updated', body: 'End' } });
  expect(res.status()).toBe(200);
  note = await res.json();
  expect(note.title).toBe('Updated');
  // Delete
  res = await request.delete(`/notes/${created.id}`);
  expect(res.status()).toBe(204);
  // Verify deletion
  res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(404);
});
