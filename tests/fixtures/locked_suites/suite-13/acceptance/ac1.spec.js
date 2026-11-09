import { test, expect } from '@playwright/test';

// Helper to create a note and return its id and content
async function createNote(request, title = 'Test', body = 'Body') {
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  const json = await resp.json();
  return json;
}

test('[AC-1] POST /notes creates a note with title and body', async ({ request }) => {
  const note = await createNote(request, 'Hello', 'World');
  expect(typeof note.id).toBe('number');
  expect(note.title).toBe('Hello');
  expect(note.body).toBe('World');
});
