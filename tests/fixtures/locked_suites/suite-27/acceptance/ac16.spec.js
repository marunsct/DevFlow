import { test, expect } from '@playwright/test';

// Helper that creates a note and returns the parsed JSON.
async function createNote(request, title, body) {
  const resp = await request.post('/notes', { data: { title, body } });
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-16] all operations work as the interface says', async ({ request }) => {
  // Health check
  const health = await request.get('/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });

  // Create a note
  const created = await createNote(request, 'TestTitle', 'TestBody');
  expect(created).toHaveProperty('id');
  expect(typeof created.id).toBe('number');
  expect(created.title).toBe('TestTitle');
  expect(created.body).toBe('TestBody');

  // List notes includes the new one
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const list = await listResp.json();
  expect(Array.isArray(list)).toBe(true);
  const found = list.find((n) => n.id === created.id);
  expect(found).toEqual(created);

  // Get the note by id
  const getResp = await request.get(`/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  expect(await getResp.json()).toEqual(created);

  // Update the note
  const updResp = await request.put(`/notes/${created.id}`, { data: { title: 'Updated', body: 'NewBody' } });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated).toEqual({ id: created.id, title: 'Updated', body: 'NewBody' });

  // Verify update reflected on get
  const getAfterUpd = await request.get(`/notes/${created.id}`);
  expect(getAfterUpd.status()).toBe(200);
  expect(await getAfterUpd.json()).toEqual(updated);

  // Delete the note
  const delResp = await request.delete(`/notes/${created.id}`);
  expect(delResp.status()).toBe(204);

  // Confirm deletion
  const getAfterDel = await request.get(`/notes/${created.id}`);
  expect(getAfterDel.status()).toBe(404);
});
