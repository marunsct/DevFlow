import { test, expect } from '@playwright/test';

// AC-14: GET /health returns 200 with status ok

test('[AC-14] GET /health returns status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toEqual({ status: 'ok' });
});
