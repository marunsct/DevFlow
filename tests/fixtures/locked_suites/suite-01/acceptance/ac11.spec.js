import { test, expect } from '@playwright/test';

test('[AC-11] updates a note via PUT', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Old' } });
  const created = await create.json();
  const id = created.id;

  const putRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Body' } });
  expect(putRes.status()).toBe(200);
  const updated = await putRes.json();
  expect(updated.title).toBe('New');

  // Non-existent id
  const notFound = await request.put('/notes/9999', { data: { title: 'X' } });
  expect(notFound.status()).toBe(500);
});
