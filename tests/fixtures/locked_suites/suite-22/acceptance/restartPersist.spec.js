import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Test AC-17: notes persist across restarts.
test('[AC-17] persists a note after service restart', async ({ request }) => {
  // Start first instance
  const first = await startService();
  // Create a note via the request fixture
  const res1 = await fetch(first.baseURL + '/notes', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: 'Persisted', body: 'Data remains' }),
});
  expect(res1.status).toBe(201);
  const id = (await res1.json()).id;

  // Stop first instance.
  await first.stop();

  // Restart with same data directory.
  const second = await startService({ dataDir: first.dataDir });
  const res2 = await fetch(second.baseURL + '/notes', { method: 'GET' });
  expect(res2.status).toBe(200);
  const notes = await res2.json();
  const found = notes.find((n) => n.id === id);
  expect(found).not.toBeUndefined();

  await second.stop();
});
