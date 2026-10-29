import { test, expect } from '@playwright/test';

// AC-4: Update a note – verifies 200 response and updated data.

test('[AC-4] updates a note', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Old' } });
  const created = await create.json();
  const id = created.id;

  const updateRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Body' } });
  expect(updateRes.status()).toBe(200);
  const updated = await updateRes.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Body');

  // Non-existent id
  const notFound = await request.put('/notes/9999', { data: { title: 'X' } });
  expect(notFound.status()).toBe(404);
});
