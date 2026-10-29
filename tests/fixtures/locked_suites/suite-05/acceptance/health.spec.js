import { test, expect } from '@playwright/test';

test('[AC-14] GET /health returns status ok', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json).toEqual({ status: 'ok' });
});
