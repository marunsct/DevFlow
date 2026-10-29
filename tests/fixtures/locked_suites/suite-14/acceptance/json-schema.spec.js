import { test, expect } from '@playwright/test';

// Helper to create a note and return its id and body
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  return json;
}

// AC-7: JSON over HTTP. A note is {"id":<int>,"title":<string>,"body":<string>}
test('[AC-7] POST /notes returns a note with id, title and body as numbers/strings', async ({ request }) => {
  const note = await createNote(request, 'Schema Title', 'Schema Body');
  expect(typeof note.id).toBe('number');
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');
});

// Verify GET /notes/:id returns the same shape
test('[AC-7] GET /notes/:id returns a note with id, title and body as numbers/strings', async ({ request }) => {
  const created = await createNote(request, 'Get Title', 'Get Body');
  const res = await request.get(`/notes/${created.id}`);
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(typeof json.id).toBe('number');
  expect(typeof json.title).toBe('string');
  expect(typeof json.body).toBe('string');
});
