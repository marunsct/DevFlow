import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-6 and AC-17: Notes survive a restart
test('[AC-6][AC-17] Notes survive a restart', async ({ request }) => {
  const first = await startService();
  // create note via first baseURL
  const resp1 = await request.post(first.baseURL + '/notes', { data: { title: 'Persist', body: 'Data' } });
  expect(resp1.status()).toBe(201);
  const created = await resp1.json();
  await first.stop();
  const second = await startService({ dataDir: first.dataDir });
  const resp2 = await request.get(second.baseURL + '/notes');
  expect(resp2.status()).toBe(200);
  const notes = await resp2.json();
  const found = notes.find(n => n.id === created.id && n.title === 'Persist');
  expect(found).toBeDefined();
  await second.stop();
});
