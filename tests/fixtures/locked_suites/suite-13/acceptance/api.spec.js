import { test, expect } from '@playwright/test';

// Helper to create a note and return its id and content
async function createNote(request, title = 'Test', body = 'Body') {
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  return json;
}

test('[AC-14] GET /health returns 200 and status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.ok()).toBeTruthy();
  expect(await res.json()).toEqual({ status: 'ok' });
});

test('[AC-8] POST /notes creates a note and returns it', async ({ request }) => {
  const note = await createNote(request, 'Hello', 'World');
  expect(typeof note.id).toBe('number');
  expect(note.title).toBe('Hello');
  expect(note.body).toBe('World');
});

test('[AC-2] GET /notes lists all created notes', async ({ request }) => {
  // create two distinct notes
  const a = await createNote(request, 'A', 'a');
  const b = await createNote(request, 'B', 'b');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  // find the created notes by id
  const ids = list.map((x) => x.id);
  expect(ids).toContain(a.id);
  expect(ids).toContain(b.id);
});

test('[AC-3] GET /notes/:id returns note or 404', async ({ request }) => {
  const note = await createNote(request, 'Solo', 'Only');
  const res = await request.get(`/notes/${note.id}`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual(note);
  const missing = await request.get('/notes/9999');
  expect(missing.status()).toBe(404);
});

test('[AC-4] PUT /notes/:id updates note', async ({ request }) => {
  const note = await createNote(request, 'Old', 'Body');
  const updResp = await request.put(`/notes/${note.id}`, { data: { title: 'New', body: 'Changed' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Changed');
  const get = await request.get(`/notes/${note.id}`);
  expect((await get.json()).title).toBe('New');
});

test('[AC-5] DELETE /notes/:id removes note', async ({ request }) => {
  const note = await createNote(request, 'DeleteMe', 'Bye');
  const del = await request.delete(`/notes/${note.id}`);
  expect(del.status()).toBe(204);
  const getAfter = await request.get(`/notes/${note.id}`);
  expect(getAfter.status()).toBe(404);
});

test('[AC-9] GET /notes has Content-Type application/json', async ({ request }) => {
  const note = await createNote(request, 'HeaderTest', 'Content');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('application/json');
});

test('[AC-13] missing or empty title results in error and no persistence', async ({ request }) => {
  const miss = await request.post('/notes', { data: { body: 'No title' } });
  expect(miss.status()).toBe(400);
  const missBody = await miss.json();
  expect(missBody).toEqual({ error: 'Title required' });

  const empty = await request.post('/notes', { data: { title: '', body: 'Empty' } });
  expect(empty.status()).toBe(422);
  const emptyBody = await empty.json();
  expect(emptyBody).toEqual({ error: 'Title required' });

  // ensure no note was added
  const listResp = await request.get('/notes');
  const list = await listResp.json();
  const titles = list.map((x) => x.title);
  expect(titles).not.toContain('No title');
  expect(titles).not.toContain('Empty');
});
