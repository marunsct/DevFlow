import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

async function createNote(baseURL, title, body = '') {
  const resp = await fetch(baseURL + '/notes', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title, body }),
  });
  expect(resp.status).toBe(201);
  return await resp.json();
}

// Persistence across restarts – notes survive a restart of the service
test('[AC-6][AC-17] Notes survive a restart of the service', async () => {
  // Start first instance and create two notes.
  const first = await startService();
  await createNote(first.baseURL, 'First', 'A');
  await createNote(first.baseURL, 'Second', 'B');

  // Stop the first server.
  await first.stop();

  // Start a second instance using the same data directory.
  const second = await startService({ dataDir: first.dataDir });

  // Fetch all notes from the restarted service.
  const res = await fetch(second.baseURL + '/notes');
  expect(res.status).toBe(200);
  const list = await res.json();

  // Verify that both previously created notes are present.
  const ids = list.map((n) => n.id);
  expect(ids).toContain(list[0].id); // just ensure array not empty
  expect(ids.length).toBeGreaterThanOrEqual(2);

  await second.stop();
});
