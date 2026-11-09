import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-6 & AC-17: Notes survive a restart of the service
// Create a note, stop service, restart with same data dir, ensure note is present.
test('[AC-6][AC-17] notes persist across restarts', async ({ request }) => {
  // The harness starts the service for all tests. We use its helper to start a second instance on the same data dir.
  const first = await startService();
  // Create note via existing request fixture against first service
  const createRes = await fetch(first.baseURL + '/notes', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:'Persist',body:'Data'}) });
  expect(createRes.status).toBe(201);
  const created = await createRes.json();
  // Stop the first instance
  await first.stop();
  // Start new service on same data dir
  const second = await startService({ dataDir: first.dataDir });
  // Use request fixture (still pointing to original baseURL) – we need a new one for second.
  // Instead, use fetch via the second.baseURL directly.
  const getRes = await fetch(second.baseURL + '/notes/' + created.id);
  expect(getRes.status).toBe(200);
  const json = await getRes.json();
  expect(json).toEqual(created);
  await second.stop();
});
