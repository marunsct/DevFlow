import { test, expect } from '@playwright/test';

// Test that all operations behave as per the interface contract.
// This covers creating, listing, fetching by id, updating, deleting and health check.

async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  return (await res.json());
}

test('[AC-16] all operations work as the interface says', async ({ request }) => {
  // Ensure starting empty by deleting any existing notes via API if possible.
  const list = await request.get('/notes');
  const ids = (await list.json()).map(n => n.id);
  for (const id of ids) {
    await request.delete(`/notes/${id}`);
  }

  // Create two notes
  const note1 = await createNote(request, 'First', 'One');
  const note2 = await createNote(request, 'Second', 'Two');

  // List all
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const notes = await listRes.json();
  expect(notes.length).toBe(2);
  const titles = notes.map(n => n.title).sort();
  expect(titles).toEqual(['First', 'Second']);

  // Get by id
  const getRes = await request.get(`/notes/${note1.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched.title).toBe('First');

  // Update
  const updRes = await request.put(`/notes/${note1.id}`, { data: { title: 'Updated', body: 'One updated' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('Updated');

  // Delete
  const delRes = await request.delete(`/notes/${note2.id}`);
  expect(delRes.status()).toBe(204);
  const afterDel = await request.get('/notes');
  const remaining = await afterDel.json();
  expect(remaining.length).toBe(1);

  // Health check
  const health = await request.get('/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });
});
