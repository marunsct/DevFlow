import { test, expect } from '@playwright/test';

// AC-5: Delete a note – verifies 204 and subsequent 404.

test('[AC-5] deletes a note', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'DeleteMe' } });
  const created = await create.json();
  const id = created.id;

  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);

  const getAfter = await request.get(`/notes/${id}`);
  expect(getAfter.status()).toBe(404);

  // Delete non-existent
  const notFound = await request.delete('/notes/9999');
  expect(notFound.status()).toBe(404);
});
