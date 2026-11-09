import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Test AC-1: create a note with title and body
test('[AC-8][AC-1] creates a note', async ({ request }) => {
  const res = await request.post('/notes', {
    data: { title: 'Test Note', body: 'Body text' },
  });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test Note');
  expect(json.body).toBe('Body text');
});

// Test AC-2: list all notes (after creating two)
test('[AC-9][AC-2] lists all notes', async ({ request }) => {
  const r1 = await request.post('/notes', { data: { title: 'A', body: 'B' } });
  const json1 = await r1.json(); expect(r1.status()).toBe(201); const id1 = json1.id;
  const r2 = await request.post('/notes', { data: { title: 'C', body: 'D' } });
  const id2 = (await r2.json()).id;

  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const arr = await res.json();
  expect(Array.isArray(arr)).toBe(true);
  const ids = arr.map((n) => n.id);
  expect(ids).toEqual(expect.arrayContaining([id1, id2]));
});

// Test AC-3: fetch a note by id and non‑existent id
test('[AC-10][AC-3] fetches a note or returns 404', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'X', body: 'Y' } });
  const id = (await create.json()).id;
  const res1 = await request.get(`/notes/${id}`);
  expect(res1.status()).toBe(200);
  const json1 = await res1.json();
  expect(json1.id).toBe(id);

  const res2 = await request.get('/notes/999999');
  expect(res2.status()).toBe(404);
  const err = await res2.json();
  expect(err.error).toBe('Not found');
});

// Test AC-4: update a note
test('[AC-11][AC-4] updates a note', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Old', body: 'Body' } });
  const id = (await create.json()).id;
  const updRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Updated' } });
  expect(updRes.status()).toBe(200);
  const updJson = await updRes.json();
  expect(updJson.title).toBe('New');

  const getRes = await request.get(`/notes/${id}`);
  const getJson = await getRes.json();
  expect(getJson.body).toBe('Updated');
});

// Test AC-5: delete a note
test('[AC-5] deletes a note', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Del', body: 'To be deleted' } });
  const id = (await create.json()).id;
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(404);
});

// Test AC-6: notes survive a restart
test('[AC-6] persists across restarts', async () => {
  const first = await startService();
  // create note using fetch (global fetch available in Node 18+)
  const res1 = await fetch(first.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' }),
  });
  expect(res1.status).toBe(201);
  const id = (await res1.json()).id;

  await first.stop();
  const second = await startService({ dataDir: first.dataDir });
  const res2 = await fetch(second.baseURL + '/notes');
  expect(res2.status).toBe(200);
  const arr = await res2.json();
  const found = arr.find((n) => n.id === id);
  expect(found).not.toBeUndefined();
  await second.stop();
});

// Test AC-7: note JSON structure
test('[AC-7] returns correct JSON schema', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Schema', body: 'Check' } });
  const json = await create.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json).toHaveProperty('title', 'Schema');
  expect(json).toHaveProperty('body', 'Check');
});

// Test AC-13: missing or empty title is rejected
test('[AC-13][AC-18] rejects missing title', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err.error).toBe('Title required');
});

test('[AC-13] rejects empty title', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: '   ', body: 'Empty' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err.error).toBe('Title required');
});

// Test AC-14: health check
test('[AC-14] health endpoint', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
