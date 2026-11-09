import { test, expect } from '@playwright/test';

// Verify the health endpoint as required by AC-14.
test('[AC-14] GET /health returns 200 and status ok', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json).toEqual({ status: 'ok' });
});
