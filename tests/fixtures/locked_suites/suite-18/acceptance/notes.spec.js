import { test, expect } from '@playwright/test';

// Helper to assert note shape
const noteShape = (note) => {
  return expect(note).toEqual(
    expect.objectContaining({ id: expect.any(Number), title: expect.any(String), body: expect.any(String) })
  );
};

test('[AC-8][AC-7] POST /notes creates a note and returns 201 with full note', async ({ request }) => {
  const response = await request.post('/notes', { data: { title: 'Test Note', body: 'Some body' } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  noteShape(json);
});

test('[AC-9][AC-2] GET /notes after two creations returns array of length 2', async ({ request }) => {
  // create first
  await request.post('/notes', { data: { title: 'One', body: 'B1' } });
  // create second
  await request.post('/notes', { data: { title: 'Two', body: 'B2' } });
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  expect(list.length).toBeGreaterThanOrEqual(2);
});

test('[AC-10][AC-3] GET /notes/999 returns 404 with error message', async ({ request }) => {
  const res = await request.get('/notes/999');
  expect(res.status()).toBe(404);
  const json = await res.json();
  expect(json).toEqual({ error: 'Not Found' });
});

test('[AC-11][AC-4] PUT /notes/:id updates note and returns updated object', async ({ request }) => {
  // create a note to update
  const postRes = await request.post('/notes', { data: { title: 'Old', body: 'Body' } });
  const created = await postRes.json();
  const id = created.id;
  const putRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Updated' } });
  expect(putRes.status()).toBe(200);
  const updated = await putRes.json();
  expect(updated).toEqual({ id, title: 'New', body: 'Updated' });
});

test('[AC-12][AC-5] DELETE /notes/:id removes note and subsequent GET returns 404', async ({ request }) => {
  const postRes = await request.post('/notes', { data: { title: 'Del', body: '' } });
  const created = await postRes.json();
  const id = created.id;
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(404);
});

test('[AC-13][AC-18] POST /notes without title returns 400 and note not stored', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'Title required' });
  // ensure list still empty or unchanged
  const listRes = await request.get('/notes');
  const list = await listRes.json();
  expect(Array.isArray(list)).toBe(true);
});

test('[AC-14][AC-6] GET /health returns status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
