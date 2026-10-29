import { test, expect } from '@playwright/test';

// Test health endpoint returns 200 OK

test('[AC-14] health endpoint returns 200', async ({ request }) => {
  const resp = await request.get('/health');
  expect(resp.status()).toBe(200);
});
