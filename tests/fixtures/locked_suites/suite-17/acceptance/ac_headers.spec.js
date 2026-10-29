import { test, expect } from '@playwright/test';

// Helper to create a note and return its id
async function createNote(request) {
  const payload = { title: 'header-test', body: 'test' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const json = await res.json();
  return json.id;
}

test('[AC-14] health endpoint returns application/json content type', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

test('[AC-1] POST /notes returns application/json content type', async ({ request }) => {
  const payload = { title: 'ct-test', body: 'body' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

test('[AC-2] GET /notes returns application/json content type', async ({ request }) => {
  await createNote(request); // ensure at least one note
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

test('[AC-3] GET /notes/:id returns application/json content type', async ({ request }) => {
  const id = await createNote(request);
  const res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

test('[AC-4] PUT /notes/:id returns application/json content type', async ({ request }) => {
  const id = await createNote(request);
  const payload = { title: 'updated', body: 'new' };
  const res = await request.put(`/notes/${id}`, { data: payload });
  expect(res.status()).toBe(200);
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});
