import { test, expect } from '@playwright/test';

// AC-14: Health check returns status ok.

test('[AC-14] health endpoint', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
