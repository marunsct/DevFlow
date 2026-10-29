import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-6 and AC-17: persistence across restart
test('[AC-6][AC-17] notes survive a service restart', async ({ request }) => {
  // start first instance
  const first = await startService();
  const base1 = first.baseURL;
  // create note via request fixture pointing to baseURL? use request fixture which uses default baseURL from config, not first.baseURL.
  // Instead use fetch directly
  const resPost = await fetch(base1 + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persist', body: 'data' })
  });
  expect(resPost.status).toBe(201);
  const created = await resPost.json();
  // stop first
  await first.stop();
  // start second with same dataDir
  const second = await startService({ dataDir: first.dataDir });
  const base2 = second.baseURL;
  const resGet = await fetch(base2 + '/notes');
  expect(resGet.status).toBe(200);
  const list = await resGet.json();
  expect(list.length).toBe(1);
  expect(list[0].id).toBe(created.id);
  expect(list[0].title).toBe('Persist');
  await second.stop();
});
