import { test, expect } from '@playwright/test';

// Helper to create a note and return its id
async function createNote(request) {
  const res = await request.post('/notes', {
    data: { title: 'Original', body: 'Body' },
  });
  const json = await res.json();
  return json.id;
}

test('[AC-4][AC-13] PUT missing or empty title returns 400 and does not modify note', async ({ request }) => {
  const id = await createNote(request);
  // Empty title
  let res = await request.put(`/notes/${id}`, { data: { title: '   ', body: 'New' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title required' });
  // Ensure note unchanged
  const getRes = await request.get(`/notes/${id}`);
  const note = await getRes.json();
  expect(note.title).toBe('Original');
});

test('[AC-18] PUT non‑JSON body returns 415', async ({ request }) => {
  const id = await createNote(request);
  const res = await request.put(`/notes/${id}`, {
    data: 'plain text',
    headers: { 'Content-Type': 'text/plain' },
  });
  expect(res.status()).toBe(415);
  const err = await res.json();
  expect(err).toEqual({ error: 'Unsupported media type' });
});

test('[AC-18] PUT with too long title returns 400', async ({ request }) => {
  const id = await createNote(request);
  const longTitle = 'a'.repeat(256);
  const res = await request.put(`/notes/${id}`, { data: { title: longTitle, body: 'Body' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title too long or invalid' });
});

test('[AC-7][AC-8] POST and PUT responses include Content-Type application/json', async ({ request }) => {
  // POST
  const postRes = await request.post('/notes', { data: { title: 'C', body: 'D' } });
  expect(postRes.headers()['content-type']).toContain('application/json');
  // PUT
  const id = (await postRes.json()).id;
  const putRes = await request.put(`/notes/${id}`, { data: { title: 'E', body: 'F' } });
  expect(putRes.headers()['content-type']).toContain('application/json');
});

test('[AC-12] DELETE 204 response has no body', async ({ request }) => {
  const id = await createNote(request);
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  const text = await delRes.text();
  expect(text.trim()).toBe('');
});
