import { test, expect } from '@playwright/test';

// Helper to create a note and return its id and body.
async function createNote(request, title, body) {
  const response = await request.post('/notes', { data: { title, body } });
  expect(response.status()).toBe(201);
  const json = await response.json();
  expect(json).toHaveProperty('id');
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
  return json;
}

// Test AC-1: Create a note with title and body.
test('[AC-1] create a note', async ({ request }) => {
  await createNote(request, 'Test Title', 'Test Body');
});

// Test AC-2: List all notes after creating two.
test('[AC-2] list all notes', async ({ request }) => {
  const note1 = await createNote(request, 'First', 'Body A');
  const note2 = await createNote(request, 'Second', 'Body B');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const list = await resp.json();
  expect(Array.isArray(list)).toBe(true);
  // Find our notes by id.
  const found1 = list.find((n) => n.id === note1.id);
  const found2 = list.find((n) => n.id === note2.id);
  expect(found1).toMatchObject({ title: 'First', body: 'Body A' });
  expect(found2).toMatchObject({ title: 'Second', body: 'Body B' });
});

// Test AC-3: Fetch one note by id and 404 for non-existent.
test('[AC-3] fetch a note by id and 404 on missing', async ({ request }) => {
  const created = await createNote(request, 'FetchMe', 'Body');
  const resp = await request.get(`/notes/${created.id}`);
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json).toMatchObject({ title: 'FetchMe', body: 'Body' });

  const notFoundResp = await request.get('/notes/999999');
  expect(notFoundResp.status()).toBe(404);
});

// Test AC-4: Update a note.
test('[AC-4] update a note', async ({ request }) => {
  const created = await createNote(request, 'Old', 'OldBody');
  const updResp = await request.put(`/notes/${created.id}`, { data: { title: 'New', body: 'NewBody' } });
  expect(updResp.status()).toBe(200);
  const updJson = await updResp.json();
  expect(updJson).toMatchObject({ id: created.id, title: 'New', body: 'NewBody' });

  const getResp = await request.get(`/notes/${created.id}`);
  const getJson = await getResp.json();
  expect(getJson).toMatchObject({ title: 'New', body: 'NewBody' });
});

// Test AC-5: Delete a note.
test('[AC-5] delete a note', async ({ request }) => {
  const created = await createNote(request, 'ToDelete', 'Del');
  const delResp = await request.delete(`/notes/${created.id}`);
  expect(delResp.status()).toBe(204);

  const getAfter = await request.get(`/notes/${created.id}`);
  expect(getAfter.status()).toBe(404);

  const listResp = await request.get('/notes');
  const list = await listResp.json();
  const exists = list.some((n) => n.id === created.id);
  expect(exists).toBe(false);
});

// Test AC-7: JSON structure validation.
test('[AC-7] note JSON has id, title, body', async ({ request }) => {
  const created = await createNote(request, 'JSONTest', 'Body');
  expect(typeof created.id).toBe('number');
  expect(typeof created.title).toBe('string');
  expect(typeof created.body).toBe('string');
});

// Test AC-8: POST returns 201 with note.
test('[AC-8] post creates note and returns it', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: 'PostTest', body: 'Body' } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toHaveProperty('id');
});

// Test AC-9: GET /notes returns array.
test('[AC-9] get all notes', async ({ request }) => {
  const created = await createNote(request, 'ArrayTest', 'Body');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const list = await resp.json();
  expect(Array.isArray(list)).toBe(true);
  const found = list.find((n) => n.id === created.id);
  expect(found).toBeDefined();
});

// Test AC-10: GET /notes/:id 404 when missing.
test('[AC-10] get non-existent note returns 404', async ({ request }) => {
  const resp = await request.get('/notes/123456789');
  expect(resp.status()).toBe(404);
});

// Test AC-11: PUT /notes/:id updates and 404 if missing.
test('[AC-11] put non-existent note returns 404', async ({ request }) => {
  const resp = await request.put('/notes/987654321', { data: { title: 'X', body: 'Y' } });
  expect(resp.status()).toBe(404);
});

// Test AC-12: DELETE non-existent returns 404.
test('[AC-12] delete non-existent note returns 404', async ({ request }) => {
  const resp = await request.delete('/notes/5555555');
  expect(resp.status()).toBe(404);
});

// Test AC-13: Invalid title handling.
test('[AC-13] missing or empty title is rejected', async ({ request }) => {
  // Missing title
  const missResp = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(missResp.status()).toBe(400);
  const missJson = await missResp.json();
  expect(missJson).toHaveProperty('error');

  // Empty title
  const emptyResp = await request.post('/notes', { data: { title: '   ', body: 'Empty' } });
  expect(emptyResp.status()).toBe(400);
  const emptyJson = await emptyResp.json();
  expect(emptyJson).toHaveProperty('error');
});

// Test AC-14: Health check.
test('[AC-14] health endpoint', async ({ request }) => {
  const resp = await request.get('/health');
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json).toHaveProperty('status', 'ok');
});

// Test AC-18: No persistence on invalid input.
test('[AC-18] invalid post does not change count', async ({ request }) => {
  // Count before
  const listBefore = await (await request.get('/notes')).json();
  const countBefore = listBefore.length;

  const badResp = await request.post('/notes', { data: { title: '', body: 'Bad' } });
  expect(badResp.status()).toBe(400);

  const listAfter = await (await request.get('/notes')).json();
  expect(listAfter.length).toBe(countBefore);
});
