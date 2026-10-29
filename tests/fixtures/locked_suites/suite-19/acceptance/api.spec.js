import { test, expect } from '@playwright/test';

// Helper to create a note via the running service and return its payload
async function createNote(request, title, body) {
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toHaveProperty('id');
  return json;
}

// AC-1: Create a note with a title and a body
test('[AC-1] create a note returns 201 with full note', async ({ request }) => {
  const title = 'AC1 Title';
  const body = 'Body content';
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toEqual({ id: expect.any(Number), title, body });
});

// AC-2: List all notes
test('[AC-2] list returns array of created notes', async ({ request }) => {
  const note1 = await createNote(request, 'list1', 'b1');
  const note2 = await createNote(request, 'list2', 'b2');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const list = await resp.json();
  expect(Array.isArray(list)).toBeTruthy();
  const ids = list.map((n) => n.id);
  expect(ids).toEqual(expect.arrayContaining([note1.id, note2.id]));
});

// AC-3: Retrieve single note by id
test('[AC-3] get a note by id', async ({ request }) => {
  const created = await createNote(request, 'getbyid', 'content');
  const resp = await request.get(`/notes/${created.id}`);
  expect(resp.status()).toBe(200);
  const json = await resp.json();
  expect(json).toEqual(created);
});

// AC-4: Update a note
test('[AC-4] update replaces title and body', async ({ request }) => {
  const created = await createNote(request, 'old', 'oldbody');
  const respUpd = await request.put(`/notes/${created.id}`, { data: { title: 'new', body: 'newbody' } });
  expect(respUpd.status()).toBe(200);
  const updated = await respUpd.json();
  expect(updated).toEqual({ id: created.id, title: 'new', body: 'newbody' });
  const respGet = await request.get(`/notes/${created.id}`);
  expect(respGet.status()).toBe(200);
  expect(await respGet.json()).toEqual(updated);
});

// AC-5: Delete a note
test('[AC-5] delete returns 204 and note no longer exists', async ({ request }) => {
  const created = await createNote(request, 'todelete', 'del');
  const respDel = await request.delete(`/notes/${created.id}`);
  expect(respDel.status()).toBe(204);
  const respGet = await request.get(`/notes/${created.id}`);
  expect(respGet.status()).toBe(404);
});

// AC-6 & AC-17: persistence across restart
import { createRequire } from 'node:module';
const requireFn = createRequire(import.meta.url);
const { startService } = requireFn('./service.cjs');
test('[AC-6][AC-17] note survives service restart', async ({ request }) => {
  const first = await startService();
  const respCreate = await request.post('/notes', { data: { title: 'persist', body: 'data' } });
  expect(respCreate.status()).toBe(201);
  const created = await respCreate.json();
  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const respList = await request.get('/notes');
  expect(respList.status()).toBe(200);
  const list = await respList.json();
  expect(list).toEqual(expect.arrayContaining([created]));
  await second.stop();
});

// AC-7: JSON structure of a note
test('[AC-7] note JSON has id, title, body', async ({ request }) => {
  const created = await createNote(request, 'jsoncheck', 'body');
  expect(created).toHaveProperty('id');
  expect(created).toHaveProperty('title', 'jsoncheck');
  expect(created).toHaveProperty('body', 'body');
});

// AC-8: POST /notes creates and returns 201 with note (same as AC-1)
test('[AC-8] post notes returns 201 with note', async ({ request }) => {
  const title = 'ac8';
  const body = 'b';
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  expect(json).toEqual({ id: expect.any(Number), title, body });
});

// AC-9: GET /notes returns array of all notes
test('[AC-9] get /notes returns all', async ({ request }) => {
  const note = await createNote(request, 'allcheck', 'b');
  const resp = await request.get('/notes');
  expect(resp.status()).toBe(200);
  const list = await resp.json();
  expect(list).toEqual(expect.arrayContaining([note]));
});

// AC-10: GET /notes/:id 404 when none
test('[AC-10] get non-existent id returns 404', async ({ request }) => {
  const resp = await request.get('/notes/999999');
  expect(resp.status()).toBe(404);
});

// AC-11: PUT /notes/:id 404 when none
test('[AC-11] put non-existent id returns 404', async ({ request }) => {
  const resp = await request.put('/notes/999999', { data: { title: 'x', body: 'y' } });
  expect(resp.status()).toBe(404);
});

// AC-12: DELETE /notes/:id 404 when none
test('[AC-12] delete non-existent id returns 404', async ({ request }) => {
  const resp = await request.delete('/notes/999999');
  expect(resp.status()).toBe(404);
});

// AC-13: missing or empty title errors
test('[AC-13] missing title gives 400 with error message', async ({ request }) => {
  const resp = await request.post('/notes', { data: { body: 'b' } });
  expect(resp.status()).toBe(400);
  const json = await resp.json();
  expect(json).toEqual({ error: 'Title is required' });
});

test('[AC-13] empty title after trim gives 422', async ({ request }) => {
  const resp = await request.post('/notes', { data: { title: '   ', body: 'b' } });
  expect(resp.status()).toBe(422);
  const json = await resp.json();
  expect(json).toEqual({ error: 'Title cannot be empty' });
});

// AC-14: health check
test('[AC-14][AC-15] health endpoint returns ok', async ({ request }) => {
  const resp = await request.get('/health');
  expect(resp.status()).toBe(200);
  expect(await resp.json()).toEqual({ status: 'ok' });
});

// AC-16: full CRUD cycle works as interface says
test('[AC-16] full CRUD cycle works', async ({ request }) => {
  const created = await createNote(request, 'cycle', 'data');
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const list = await listResp.json();
  expect(list).toEqual(expect.arrayContaining([created]));
  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  expect(await getResp.json()).toEqual(created);
  const updResp = await request.put(`/notes/${created.id}`, { data: { title: 'updated', body: 'new' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated).toEqual({ id: created.id, title: 'updated', body: 'new' });
  const delResp = await request.delete(`/notes/${created.id}`);
  expect(delResp.status()).toBe(204);
});

// AC-18: invalid input is refused without storing anything
test('[AC-18] invalid input is refused without storing', async ({ request }) => {
  const beforeResp = await request.get('/notes');
  const beforeList = await beforeResp.json();
  const beforeCount = Array.isArray(beforeList) ? beforeList.length : 0;
  const badResp = await request.post('/notes', { data: { body: 'oops' } });
  expect(badResp.status()).toBe(400);
  const afterResp = await request.get('/notes');
  const afterList = await afterResp.json();
  const afterCount = Array.isArray(afterList) ? afterList.length : 0;
  expect(afterCount).toBe(beforeCount);
});
