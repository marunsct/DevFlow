import { test, expect } from '@playwright/test';

// Test that every operation behaves as the interface contract specifies.
test('[AC-16] all CRUD operations follow the contract', async ({ request }) => {
  // Create a note.
  const createResp = await request.post('/notes', { data: { title: 'InterfaceTest', body: 'Body1' } });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();
  expect(created).toHaveProperty('id');
  const id = created.id;

  // List notes, ensure our note is present.
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const list = await listResp.json();
  expect(Array.isArray(list)).toBe(true);
  const found = list.find((n) => n.id === id);
  expect(found).toMatchObject({ title: 'InterfaceTest', body: 'Body1' });

  // Get the note.
  const getResp = await request.get(`/notes/${id}`);
  expect(getResp.status()).toBe(200);
  const fetched = await getResp.json();
  expect(fetched).toMatchObject({ title: 'InterfaceTest', body: 'Body1' });

  // Update the note.
  const updResp = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'Body2' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated).toMatchObject({ id, title: 'Updated', body: 'Body2' });

  // Delete the note.
  const delResp = await request.delete(`/notes/${id}`);
  expect(delResp.status()).toBe(204);

  // Confirm deletion.
  const getAfterDelResp = await request.get(`/notes/${id}`);
  expect(getAfterDelResp.status()).toBe(404);
  const afterDelete = await getAfterDelResp.json();
  expect(afterDelete).toHaveProperty('error');
});
