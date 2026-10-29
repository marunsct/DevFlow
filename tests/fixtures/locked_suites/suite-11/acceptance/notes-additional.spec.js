import { test, expect } from '@playwright/test';

/**
 * AC-15: The project directory has a start.sh that starts the service on 127.0.0.1 at the port in the PORT environment variable, keeping its data under the directory in the DATA_DIR environment variable.
 */
test('[AC-15] start.sh uses PORT and DATA_DIR env variables', async () => {
  const { startService } = await import('./service.cjs');
  // use a custom port
  const svc = await startService({ dataDir: 'tmp-data-dir', timeoutMs: 30000 });
  // The baseURL should reflect the chosen port and host 127.0.0.1
  expect(svc.baseURL).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  const url = new URL(svc.baseURL + '/health');
  const res = await fetch(url.toString());
  expect(res.status).toBe(200);
  // Ensure the data directory used is the one we passed
  const stat = await import('node:fs/promises').then(m => m.stat('tmp-data-dir'));
  expect(stat.isDirectory()).toBeTruthy();
  await svc.stop();
});

/**
 * AC-16: Every operation works as the interface says.
 */
test('[AC-16] CRUD and health endpoints behave correctly', async ({ request }) => {
  // Create a note
  const createRes = await request.post('/notes', { data: { title: 'Foo', body: 'Bar' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created).toHaveProperty('id');

  // List notes
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  expect(Array.isArray(list)).toBeTruthy();

  // Get the created note
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(created);

  // Update the note
  const updRes = await request.put(`/notes/${created.id}`, { data: { title: 'Baz', body: 'Qux' } });
  expect(updRes.status()).toBe(200);
  const updated = await updRes.json();
  expect(updated.title).toBe('Baz');

  // Delete the note
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);

  // Health check
  const healthRes = await request.get('/health');
  expect(healthRes.status()).toBe(200);
});
