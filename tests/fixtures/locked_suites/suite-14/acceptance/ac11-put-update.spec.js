import { test, expect } from '@playwright/test';

// Verify PUT /notes/:id updates a note or returns 404 when not found
// AC-11: PUT /notes/{id} with {"title": ..., "body": ...} replaces both and answers 200 with the note, or 404

test('[AC-11] PUT /notes/:id updates a note or 404', async ({ request }) => {
  // Create a note first
  const createRes = await request.post('/notes', { data: { title: 'Orig', body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const orig = await createRes.json();

  // Update the note
  const updRes = await request.put(`/notes/${orig.id}`, { data: { title: 'New', body: 'Updated' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Updated');

  // Fetch to confirm persistence of update
  const getRes = await request.get(`/notes/${orig.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(updated);

  // Attempt to update a non‑existent id
  const notFoundRes = await request.put('/notes/9999', { data: { title: 'X', body: 'Y' } });
  expect(notFoundRes.status()).toBe(404);
  const err = await notFoundRes.json();
  expect(err).toEqual({ error: 'not found' });
});
