import { test, expect } from '@playwright/test';

const { startService } = await import('./service.cjs');

async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(json.title).toBe(title);
  expect(json.body).toBe(body);
  return json.id;
}

test('[AC-14][AC-16] GET /health returns ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});

test('[AC-1][AC-8] POST /notes creates a note and returns 201 with Location', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'Test Note', body: 'Body content' } });
  expect(res.status()).toBe(201);
  const location = res.headers()['location'];
  expect(location).toMatch(/^\/notes\/\d+$/);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  expect(json.title).toBe('Test Note');
  expect(json.body).toBe('Body content');
});

test('[AC-2][AC-9] GET /notes returns all created notes', async ({ request }) => {
  const id1 = await createNote(request, 'First', 'One');
  const id2 = await createNote(request, 'Second', 'Two');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBe(true);
  const found1 = list.find((n) => n.id === id1);
  const found2 = list.find((n) => n.id === id2);
  expect(found1).toEqual({ id: id1, title: 'First', body: 'One' });
  expect(found2).toEqual({ id: id2, title: 'Second', body: 'Two' });
});

test('[AC-3][AC-10] GET /notes/:id returns 200 for existing and 404 for missing', async ({ request }) => {
  const id = await createNote(request, 'Retrieve', 'Here');
  let res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  let json = await res.json();
  expect(json).toEqual({ id, title: 'Retrieve', body: 'Here' });
  res = await request.get('/notes/999999');
  expect(res.status()).toBe(404);
  json = await res.json();
  expect(json).toEqual({ error: 'Not Found' });
});

test('[AC-4][AC-7] PUT /notes/:id updates title and body', async ({ request }) => {
  const id = await createNote(request, 'Old Title', 'Old Body');
  let res = await request.put(`/notes/${id}`, { data: { title: 'New Title', body: 'New Body' } });
  expect(res.status()).toBe(200);
  let json = await res.json();
  expect(json).toEqual({ id, title: 'New Title', body: 'New Body' });
  res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  json = await res.json();
  expect(json).toEqual({ id, title: 'New Title', body: 'New Body' });
});

test('[AC-5][AC-10][AC-12] DELETE /notes/:id removes the note', async ({ request }) => {
  const id = await createNote(request, 'To Delete', 'Bye');
  let res = await request.delete(`/notes/${id}`);
  expect(res.status()).toBe(204);
  const text = await res.text();
  expect(text).toBe('');
  res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(404);
  const json = await res.json();
  expect(json).toEqual({ error: 'Not Found' });
});

test('[AC-6][AC-17] Notes survive a service restart', async ({ request }) => {
  const first = await startService();

// Helper to create a note via the started service before restart
async function createNoteViaFirst(title, body) {
  const res = await fetch(first.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, body }),
  });
  if (res.status !== 201) throw new Error('Failed to create note');
  const json = await res.json();
  return json.id;
}

  const id1 = await createNoteViaFirst('Persist One', 'Data');
  const id2 = await createNoteViaFirst('Persist Two', 'More');
  // Create an additional note via original server
  
  // Restart service with same DATA_DIR
  await new Promise((r)=>setTimeout(r,500));
    await first.stop();
    const second = await startService({ dataDir: first.dataDir });
const res = await fetch(second.baseURL + '/notes', { method: 'GET' });
    expect(res.status).toBe(200);
  const list = await res.json();
  const ids = list.map((n) => n.id);
  expect(ids).toEqual(expect.arrayContaining([id1, id2]));
  await second.stop();
});

test('[AC-13] POST /notes without title returns 400', async ({ request }) => {
  const res = await request.post('/notes', { data: { body: 'No title' } });
  expect(res.status()).toBe(400);
  const json = await res.json();
  expect(json).toEqual({ error: 'Title is required' });
});
