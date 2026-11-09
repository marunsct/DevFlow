import { test, expect } from '@playwright/test';

// Verify DELETE /notes/:id removes a note or returns 404 when not found
// AC-12: DELETE /notes/{id} answers 204, or 404

test('[AC-12] DELETE /notes/:id removes a note or 404', async ({ request }) => {
  // Create a note first
  const createRes = await request.post('/notes', { data: { title: 'ToDelete', body: 'Bye' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();

  // Delete the note
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  // Verify it is gone
  const getAfter = await request.get(`/notes/${created.id}`);
  expect(getAfter.status()).toBe(404);
  const err = await getAfter.json();
  expect(err).toEqual({ error: 'not found' });

  // Attempt to delete a non‑existent id
  const notFoundRes = await request.delete('/notes/9999');
  expect(notFoundRes.status()).toBe(404);
  const err2 = await notFoundRes.json();
  expect(err2).toEqual({ error: 'not found' });
});
