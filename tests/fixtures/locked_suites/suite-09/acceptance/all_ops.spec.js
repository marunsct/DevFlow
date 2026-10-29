import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Persistence across restart – uses the service helper to control a real process.
test('[AC-6][AC-17] persistence across restart', async ({ request }) => {
  const svc1 = await startService();
  // Create a note using the running service instance.
  const createRes = await fetch(`${svc1.baseURL}/notes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' }),
  });
  if (createRes.status !== 201) throw new Error('Create failed');
  await svc1.stop();

  const svc2 = await startService({ dataDir: svc1.dataDir });
  const listRes = await fetch(`${svc2.baseURL}/notes`);
  if (listRes.status() !== 200) throw new Error('List after restart failed');
  const notes = await listRes.json();
  expect(Array.isArray(notes)).toBe(true);
  expect(notes.length).toBeGreaterThan(0);
  await svc2.stop();
});

// All operations – uses Playwright request fixture which talks to the server started by the test runner.
test('[AC-16] all operations work as interface says', async ({ request }) => {
  // Create a note.
  const payload = { title: 'AllOps', body: 'Initial' };
  const postRes = await request.post('/notes', { data: payload });
  expect(postRes.status()).toBe(201);
  const created = await postRes.json();

  // List notes.
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const listArr = await listRes.json();
  expect(Array.isArray(listArr)).toBe(true);

  // Get the created note.
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const got = await getRes.json();
  expect(got.title).toBe(payload.title);

  // Update the note.
  const updPayload = { title: 'AllOpsUpdated', body: 'New' };
  const updRes = await request.put(`/notes/${created.id}`, { data: updPayload });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe(updPayload.title);

  // Delete the note.
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  // Confirm deletion.
  const afterDelRes = await request.get(`/notes/${created.id}`);
  expect(afterDelRes.status()).toBe(404);
});
