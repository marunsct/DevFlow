import { test, expect } from '@playwright/test';

// AC-12: DELETE /notes/{id} answers 204 or 404.
test('[AC-12] delete a note returns 204 and not-found returns 404', async ({ request }) => {
  // Create a note first
  const createRes = await request.post('/notes', { data: { title: 'DeleteMe' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // Delete the existing note
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  expect(await delRes.text()).toBe('');

  // Verify it is gone
  const getAfterDel = await request.get(`/notes/${id}`);
  expect(getAfterDel.status()).toBe(404);
});
