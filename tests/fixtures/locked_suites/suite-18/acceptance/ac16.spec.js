import { test, expect } from '@playwright/test';

// AC-16: Every operation works as the interface says – a full CRUD sequence in one test.
test('[AC-16] Full CRUD sequence', async ({ request }) => {
  // Create
  const createRes = await request.post('/notes', { data: { title: 'SeqCreate', body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;
  // List
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  expect(list.find((n) => n.id === id)).toEqual(created);
  // Get
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const got = await getRes.json();
  expect(got).toEqual(created);
  // Update
  const updRes = await request.put(`/notes/${id}`, { data: { title: 'SeqUpdated', body: 'New' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated).toEqual({ id, title: 'SeqUpdated', body: 'New' });
  // Delete
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  // Get after delete
  const getDelRes = await request.get(`/notes/${id}`);
  expect(getDelRes.status()).toBe(404);
});
