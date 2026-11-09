import { test, expect } from '@playwright/test';

test('[AC-14][AC-16] GET /health returns 200 and ok status', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const json = await response.json();
  expect(json).toEqual({ status: 'ok' });
});
