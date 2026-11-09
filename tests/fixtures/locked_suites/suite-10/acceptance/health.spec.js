import { test, expect } from '@playwright/test';

// [AC-14] GET /health returns status 200 and JSON {status:"ok"}
test('[AC-14] health endpoint responds with ok', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toEqual({ status: 'ok' });
});
