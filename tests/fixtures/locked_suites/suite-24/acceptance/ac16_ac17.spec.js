import { test, expect } from '@playwright/test';

// Test that every CRUD operation behaves as specified (AC‑16).
test('[AC-16] CRUD operations work as the interface says', async ({ request }) => {
  // Create a note.
  const resCreate = await request.post('/notes', { data: { title: 'PersistNote', body: 'Data' } });
  expect(resCreate.status()).toBe(201);
  const created = await resCreate.json();
  const id = created.id;
  expect(created).toHaveProperty('id');
  expect(created.title).toBe('PersistNote');

  // Retrieve the note.
  const resGet = await request.get(`/notes/${id}`);
  expect(resGet.status()).toBe(200);
  const fetched = await resGet.json();
  expect(fetched).toEqual(created);

  // Update the note.
  const resPut = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'More' } });
  expect(resPut.status()).toBe(200);
  const updated = await resPut.json();
  expect(updated.title).toBe('Updated');
  expect(updated.body).toBe('More');

  // Delete the note.
  const resDel = await request.delete(`/notes/${id}`);
  expect(resDel.status()).toBe(204);

  // Verify deletion.
  const resGet2 = await request.get(`/notes/${id}`);
  expect(resGet2.status()).toBe(404);
});

// Test that notes survive a restart of the service (AC‑17).
import { startService } from './service.cjs';
test('[AC-17] Notes persist after service restart', async () => {
  const first = await startService();
  // Create a note via raw fetch.
  let res = await fetch(`${first.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'Data' }),
  });
  expect(res.status).toBe(201);
  const json = await res.json();
  const id = json.id;
  await first.stop();

  // Restart with same data directory.
  const second = await startService({ dataDir: first.dataDir });
  res = await fetch(`${second.baseURL}/notes/${id}`);
  expect(res.status).toBe(200);
  const got = await res.json();
  expect(got).toEqual(json);

  // Cleanup.
  await fetch(`${second.baseURL}/notes/${id}`, { method: 'DELETE' });
  await second.stop();
});
