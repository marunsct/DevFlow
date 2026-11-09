import { test, expect } from '@playwright/test';
const { startService } = await import('./service.cjs');

// Test that notes survive a restart of the service
test('[AC-6] Notes persist after server restart', async ({ request }) => {
  // Start first instance
  const first = await startService();
  const client = request;
  // Create a note via the request fixture against baseURL
  const createResp = await client.post(`${first.baseURL}/notes`, { data: { title: 'Persist', body: 'Keep' } });
  expect(createResp.status()).toBe(201);
  const created = await createResp.json();
  // Stop first instance
  await first.stop();
  // Start second instance with same dataDir
  const second = await startService({ dataDir: first.dataDir });
  const getResp = await client.get(`${second.baseURL}/notes/${created.id}`);
  expect(getResp.status()).toBe(200);
  const got = await getResp.json();
  expect(got.title).toBe('Persist');
  expect(got.body).toBe('Keep');
  await second.stop();
});
