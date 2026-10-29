import { test, expect } from '@playwright/test';

// Verify GET /notes/:id returns the note or 404 when not found
// AC-10: GET /notes/{id} answers 200 with the note, or 404 when there is none

test('[AC-10] GET /notes/:id returns a note or 404', async ({ request }) => {
  // Create a note first
  const createRes = await request.post('/notes', { data: { title: 'Temp', body: 'Data' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();

  // Fetch the created note by id
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(created);

  // Attempt to fetch a non‑existent id
  const notFoundRes = await request.get('/notes/9999');
  expect(notFoundRes.status()).toBe(404);
  const err = await notFoundRes.json();
  expect(err).toEqual({ error: 'not found' });
});
