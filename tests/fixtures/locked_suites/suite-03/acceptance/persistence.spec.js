import { test, expect } from '@playwright/test';

// Test that notes survive a restart of the service.
// The helper in `service.cjs` starts the product on a free port and returns an object with `baseURL` and `dataDir`.
// This test creates a note, stops the first instance, restarts it with the same data directory, and
// verifies that the note is still present.

test('[AC-6][AC-17] Notes persist across restarts', async () => {
  const { startService } = await import('./service.cjs');

  // Start first instance and create a note
  const first = await startService();
  const title = 'Persisted Note';
  const body = 'Should survive restart';
  let resp = await fetch(`${first.baseURL}/notes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title, body }),
  });
  expect(resp.status).toBe(201);
  const json1 = await resp.json();
  const noteId = json1.id;

  // Stop the first instance
  await first.stop();

  // Restart service with same data directory and verify note exists
  const second = await startService({ dataDir: first.dataDir });
  resp = await fetch(`${second.baseURL}/notes/${noteId}`, { method: 'GET' });
  expect(resp.status).toBe(200);
  const persisted = await resp.json();
  expect(persisted.title).toBe(title);
  expect(persisted.body).toBe(body);

  // Clean up
  await second.stop();
});
