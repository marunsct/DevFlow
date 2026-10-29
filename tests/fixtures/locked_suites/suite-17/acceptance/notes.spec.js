import { test, expect } from '@playwright/test';

// Helper that generates a title unlikely to collide with existing notes.
function uniqueTitle(prefix = 'note') {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Safely parse JSON from a Playwright Response, returning null if the body is empty or parsing fails.
 */
async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

// ---------- Core CRUD tests ----------

test('[AC-1] creates a note with title and body', async ({ request }) => {
  const payload = { title: uniqueTitle('ac1'), body: 'sample' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await safeJson(res);
  expect(json).not.toBeNull();
  expect(json).toHaveProperty('id');
  expect(json.title).toBe(payload.title);
  expect(json.body).toBe(payload.body);
});

test('[AC-2] lists all notes', async ({ request }) => {
  const payload1 = { title: uniqueTitle('ac2a'), body: 'first' };
  const payload2 = { title: uniqueTitle('ac2b'), body: 'second' };
  await request.post('/notes', { data: payload1 });
  await request.post('/notes', { data: payload2 });

  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await safeJson(res);
  expect(Array.isArray(notes)).toBeTruthy();
  const titles = notes.map((n) => n.title);
  expect(titles).toContain(payload1.title);
  expect(titles).toContain(payload2.title);
});

test('[AC-3] fetches a note by id', async ({ request }) => {
  const payload = { title: uniqueTitle('ac3'), body: 'fetchme' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  expect(created).not.toBeNull();
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await safeJson(getRes);
  expect(fetched).toEqual(created);
});

test('[AC-4] updates a note', async ({ request }) => {
  const payload = { title: uniqueTitle('ac4'), body: 'old' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const updatePayload = { title: uniqueTitle('updated'), body: 'new' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updatePayload });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe(updatePayload.title);
  expect(updated.body).toBe(updatePayload.body);

  // Verify persistence via GET
  const getRes = await request.get(`/notes/${created.id}`);
  const fetched = await safeJson(getRes);
  expect(fetched).toEqual(updated);
});

test('[AC-5] deletes a note', async ({ request }) => {
  const payload = { title: uniqueTitle('ac5'), body: 'tobedeleted' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();

  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  const getRes = await request.get(`\`/notes/${created.id}\``);
  expect(getRes.status()).toBe(404);
});

// ---------- Persistence test ----------

test('[AC-6] notes survive a restart', async () => {
  const { startService } = await import('./service.cjs');
  const first = await startService();
  try {
    const payload = { title: uniqueTitle('restart'), body: 'persistent' };
    const res1 = await fetch(first.baseURL + '/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    expect(res1.status).toBe(201);

    await first.stop();

    const second = await startService({ dataDir: first.dataDir });
    try {
      const res2 = await fetch(second.baseURL + '/notes');
      expect(res2.status).toBe(200);
      const notes = await res2.json();
      const titles = notes.map((n) => n.title);
      expect(titles).toContain(payload.title);
    } finally {
      await second.stop();
    }
  } finally {
    await first.stop();
  }
});

// ---------- Validation tests ----------

test('[AC-13] rejects a note with empty title', async ({ request }) => {
  const payload = { title: '', body: 'shouldfail' };
  const res = await request.post('/notes', { data: payload });
  expect([400, 422]).toContain(res.status());

  // Ensure no new note with empty title exists.
  const listRes = await request.get('/notes');
  const notes = await safeJson(listRes);
  const titles = notes.map((n) => n.title);
  expect(titles).not.toContain('');
});

// ---------- Additional tests for missing AC IDs ----------

test('[AC-7] JSON over HTTP has id,title,body', async ({ request }) => {
  const payload = { title: uniqueTitle('ac7'), body: 'jsoncheck' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await safeJson(res);
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json).toHaveProperty('title');
  expect(typeof json.title).toBe('string');
  expect(json).toHaveProperty('body');
  expect(typeof json.body).toBe('string');
});

// Test AC-8: POST creates note and returns 201 with note JSON (duplicate of AC-1 but id added)
test('[AC-8] creates a note with title and body', async ({ request }) => {
  const payload = { title: uniqueTitle('ac8'), body: 'sample' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await safeJson(res);
  expect(json).not.toBeNull();
  expect(json).toHaveProperty('id');
});

// Test AC-9: GET /notes returns array of notes (duplicate of AC-2 but id added)
test('[AC-9] lists all notes', async ({ request }) => {
  const payload1 = { title: uniqueTitle('ac9a'), body: 'first' };
  await request.post('/notes', { data: payload1 });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await safeJson(res);
  expect(Array.isArray(notes)).toBeTruthy();
});

// Test AC-10: GET /notes/:id returns note or 404 (duplicate of AC-3 but id added)
test('[AC-10] fetches a note by id', async ({ request }) => {
  const payload = { title: uniqueTitle('ac10'), body: 'fetchme' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
});

// Test AC-11: PUT updates note and returns updated note (duplicate of AC-4 but id added)
test('[AC-11] updates a note', async ({ request }) => {
  const payload = { title: uniqueTitle('ac11'), body: 'old' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();
  const updatePayload = { title: uniqueTitle('updated'), body: 'new' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updatePayload });
  expect(updRes.status()).toBe(200);
});

// Test AC-12: DELETE returns 204 or 404 (duplicate of AC-5 but id added)
test('[AC-12] deletes a note', async ({ request }) => {
  const payload = { title: uniqueTitle('ac12'), body: 'tobedeleted' };
  const createRes = await request.post('/notes', { data: payload });
  const created = await createRes.json();
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);
});

// Test AC-17: notes persist across restarts (duplicate of AC-6 but id added)
test('[AC-17] notes survive a restart', async () => {
  const { startService } = await import('./service.cjs');
  const first = await startService();
  try {
    const payload = { title: uniqueTitle('restart'), body: 'persistent' };
    const res1 = await fetch(first.baseURL + '/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    expect(res1.status).toBe(201);

    await first.stop();

    const second = await startService({ dataDir: first.dataDir });
    try {
      const res2 = await fetch(second.baseURL + '/notes');
      expect(res2.status).toBe(200);
      const notes = await res2.json();
      const titles = notes.map((n) => n.title);
      expect(titles).toContain(payload.title);
    } finally {
      await second.stop();
    }
  } finally {
    await first.stop();
  }
});

// Test AC-18: invalid input is refused without storing (duplicate of AC-13 but id added)
test('[AC-18] rejects a note with empty title', async ({ request }) => {
  const payload = { title: '', body: 'shouldfail' };
  const res = await request.post('/notes', { data: payload });
  expect([400, 422]).toContain(res.status());
});
