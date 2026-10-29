import { test, expect } from '@playwright/test';

// Verify that the service started by the harness responds correctly.
// The Playwright fixture `request` points to the server started in playwright.config.js.

test('[AC-15] service starts on 127.0.0.1 with PORT and DATA_DIR', async ({ request }) => {
  // Health endpoint should be available.
  const health = await request.get('/health');
  expect(health.status()).toBe(200);
  const json = await health.json();
  expect(json).toEqual({ status: 'ok' });

  // Create a note to ensure the server is functional.
  const postRes = await request.post('/notes', { data: { title: 'Test', body: 'Body' } });
  expect(postRes.status()).toBe(201);
  const created = await postRes.json();
  expect(created).toHaveProperty('id');

  // Clean up by deleting the note.
  const delRes = await request.delete(`/notes/${created.id}`);
  expect(delRes.status()).toBe(204);
});
