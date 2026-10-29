import { test, expect } from '@playwright/test';

// Test AC-16: all operations work as interface says
// This single test covers create, read list, read one, update, delete and final list.
test('[AC-16] All CRUD operations behave correctly', async ({ request }) => {
  // Create two notes
  const create = async (title, body) => {
    const res = await request.post('/notes', { data: { title, body } });
    expect(res.status()).toBe(201);
    return await res.json();
  };
  const noteA = await create('Alpha', 'First');
  const noteB = await create('Beta', 'Second');

  // List notes and verify both present
  let listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  let notes = await listRes.json();
  expect(notes).toEqual(expect.arrayContaining([noteA, noteB]));

  // Update one note
  const updRes = await request.put(`/notes/${noteA.id}`, { data: { title: 'Alpha Updated', body: 'First Updated' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated).toEqual({ id: noteA.id, title: 'Alpha Updated', body: 'First Updated' });

  // Get updated note
  const getRes = await request.get(`/notes/${noteA.id}`);
  expect(getRes.status()).toBe(200);
  expect(await getRes.json()).toEqual(updated);

  // Delete second note
  const delRes = await request.delete(`/notes/${noteB.id}`);
  expect(delRes.status()).toBe(204);
  expect(await delRes.text()).toBe('');

  // Final list should only contain updated noteA
  listRes = await request.get('/notes');
  notes = await listRes.json();
  expect(notes).toEqual([updated]);
});
