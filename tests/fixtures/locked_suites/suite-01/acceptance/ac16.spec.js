import { test, expect } from '@playwright/test';

// AC-16: Interface compliance – all endpoints behave as specified.

test('[AC-16] full interface compliance', async ({ request }) => {
  // Create a note
  const create = await request.post('/notes', { data: { title: 'Comply' } });
  expect(create.status()).toBe(201);
  const created = await create.json();
  const id = created.id;

  // Get list
  const list = await request.get('/notes');
  expect(list.status()).toBe(200);
  const notes = await list.json();
  expect(notes.some((n) => n.id === id)).toBe(true);

  // Get single
  const get = await request.get(`/notes/${id}`);
  expect(get.status()).toBe(200);

  // Update
  const upd = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'Body' } });
  expect(upd.status()).toBe(200);

  // Delete
  const del = await request.delete(`/notes/${id}`);
  expect(del.status()).toBe(204);

  // Confirm deleted
  const afterDel = await request.get(`/notes/${id}`);
  expect(afterDel.status()).toBe(404);
});
