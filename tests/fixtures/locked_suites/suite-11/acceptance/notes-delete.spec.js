import { test, expect } from '@playwright/test';

// AC-12: DELETE /notes/:id returns 204 when existing, 404 when missing
const jsonBody = (body) => ({ data: body });

test('[AC-12] DELETE /notes/:id returns 204 for existing note and 404 for non‑existent', async ({ request }) => {
  // create a note to delete
  const createRes = await request.post('/notes', jsonBody({ title: 'ToDelete', body: 'Will be removed' }));
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // delete the note – should get 204
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  // verify it is gone
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(404);

  // attempt to delete a non‑existent id – should get 404
  const delNonRes = await request.delete('/notes/999999');
  expect(delNonRes.status()).toBe(404);
});
