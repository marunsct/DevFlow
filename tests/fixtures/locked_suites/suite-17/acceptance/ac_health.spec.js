import { test, expect } from '@playwright/test';

// AC-14: GET /health answers 200 with JSON {status:'ok'}
test('[AC-14] health endpoint returns status ok', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
