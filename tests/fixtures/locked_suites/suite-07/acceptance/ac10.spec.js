import { test, expect } from '@playwright/test';

// Test for AC-10: GET /notes/{id} answers 200 with the note, or 404 when there is none

test('[AC-10] Get existing and non‑existent note', async ({ request }) => {
  // Create a note first
  const title = 'Existing Note';
  const createRes = await request.post('/notes', { data: { title, body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // Existing note should return 200 and the same data
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  expect(await getRes.json()).toEqual(created);

  // Non‑existent id returns 404 with error message
  const missingRes = await request.get('/notes/9999');
  expect(missingRes.status()).toBe(404);
  expect(await missingRes.json()).toEqual({ error: 'Not found' });
});
