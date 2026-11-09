import { test, expect } from '@playwright/test';

// AC-5: Delete a note
// Create a note, delete it, then verify 204 and subsequent GET returns 404.
test('[AC-5][AC-12] DELETE /notes/:id removes the note', async ({ request }) => {
  const createRes = await request.post('/notes', { data: { title: 'Del', body: 'To be deleted' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  // No content body
  const emptyBody = await delRes.text();
  expect(emptyBody).toBe('');
  const getAfter = await request.get(`/notes/${id}`);
  expect(getAfter.status()).toBe(404);
  const err = await getAfter.json();
  expect(err).toEqual({ error: 'Not found' });
});
